"""seekdb 知识库层：嵌入式存储 + 向量/全文/标量混合检索

技术说明（seekdb 官方能力落地方式）：
- 存储：pylibseekdb 嵌入式启动本地 seekdb，pymysql 走 MySQL 协议执行 SQL。
- 全文：content/title 建 ik 中文分词全文索引，MATCH ... AGAINST 检索。
- 向量：bge-small-zh-v1.5 本地 ONNX 嵌入，VECTOR(512) 列 + l2_distance 检索。
- 混合：全文 TopK 与向量 TopK 双路召回，Reciprocal Rank Fusion 融合，
  并可叠加 course 学科标量过滤 —— 一条查询内完成向量+全文+结构化检索。
"""
from __future__ import annotations

import re
import threading
import time
from contextlib import closing
from typing import Any

import pymysql

import config
import embedding

DB_NAME = "test"


def _split_query(q: str) -> list[str]:
    """把用户问题切成全文检索关键词（ik 分词前先粗切：中文连续串 + 英文单词）。"""
    tokens = re.findall(r"[\u4e00-\u9fff]+|[A-Za-z][A-Za-z0-9_\-]*", q)
    # 中文连续串再按 2 字滑窗拆分（ik 对短串分词不稳，用词元兜底）
    out: list[str] = []
    for t in tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]+", t) and len(t) > 4:
            step = 2
            for i in range(0, len(t) - 1, step):
                out.append(t[i : i + step])
        else:
            out.append(t)
    return out


class KnowledgeBase:
    """嵌入式 seekdb 知识库封装（进程内单例）。"""

    def __init__(self, path: str = config.SEEKDB_PATH):
        self.path = path
        self._db = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    def _ensure_db(self):
        if self._db is None:
            import pylibseekdb

            self._db = pylibseekdb.open(self.path)
        return self._db

    def _connect(self):
        db = self._ensure_db()
        options = db.connection_options()
        conn = pymysql.connect(
            database=DB_NAME,
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
            **options,
        )
        return conn

    def close(self):
        if self._db is not None:
            try:
                self._db.close()
            finally:
                self._db = None

    # ------------------------------------------------------------------
    # 建表
    # ------------------------------------------------------------------
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS notes (
      id         INT PRIMARY KEY AUTO_INCREMENT,
      title      TEXT NOT NULL,
      content    TEXT NOT NULL,
      course     VARCHAR(32)  NOT NULL,
      source     VARCHAR(128) NOT NULL DEFAULT '',
      tags       VARCHAR(256) NOT NULL DEFAULT '',
      embedding  VECTOR(512),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FULLTEXT INDEX idx_fts_content (content) WITH PARSER ik,
      FULLTEXT INDEX idx_fts_title (title) WITH PARSER ik
    ) ORGANIZATION = HEAP
    """

    def init(self):
        with self._lock:
            with closing(self._connect()) as conn:
                with conn.cursor() as cur:
                    cur.execute(self.SCHEMA)
                    cur.execute("SHOW TABLES")
                    tables = [list(r.values())[0] for r in cur.fetchall()]
                    return {"status": "ok", "tables": tables, "path": self.path}

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def add_note(self, title: str, content: str, course: str,
                 source: str = "", tags: str = "") -> dict[str, Any]:
        with self._lock:
            vec = embedding.embed_text(f"{title}。{content}")
            vlit = embedding.to_vector_literal(vec)
            with closing(self._connect()) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO notes (title, content, course, source, tags, embedding) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (title, content, course, source, tags, vlit),
                    )
                    new_id = cur.lastrowid
                    return {"id": new_id, "title": title, "course": course}

    def add_notes_bulk(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for it in items:
            results.append(self.add_note(**it))
        return results

    def delete_note(self, note_id: int) -> bool:
        with self._lock:
            with closing(self._connect()) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM notes WHERE id = %s", (note_id,))
                    return cur.rowcount > 0

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def list_notes(self, course: str = "") -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            with conn.cursor() as cur:
                if course:
                    cur.execute(
                        "SELECT id, title, course, source, tags, content, created_at "
                        "FROM notes WHERE course = %s ORDER BY id DESC",
                        (course,),
                    )
                else:
                    cur.execute(
                        "SELECT id, title, course, source, tags, content, created_at "
                        "FROM notes ORDER BY id DESC"
                    )
                rows = cur.fetchall()
                for r in rows:
                    if isinstance(r.get("created_at"), str):
                        r["created_at"] = r["created_at"]
                return rows

    def stats(self) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM notes")
                total = cur.fetchone()["c"]
                cur.execute("SELECT course, COUNT(*) AS c FROM notes GROUP BY course")
                by_course = {r["course"]: r["c"] for r in cur.fetchall()}
                return {"total": total, "by_course": by_course}

    # ------------------------------------------------------------------
    # 混合检索：向量 + 全文 + 标量过滤
    # ------------------------------------------------------------------
    def hybrid_search(self, query: str, course: str = "",
                      top_k: int = 5) -> dict[str, Any]:
        """双路召回 + RRF 融合。

        返回结构包含每条的命中信号（semantic/fulltext/both），供前端与验证样例展示
        seekdb 的向量+全文混合检索实际作用。
        """
        q_tokens = _split_query(query)
        fulltext_expr = " ".join(q_tokens[:8]) if q_tokens else query

        # ---- 1) 向量召回（语义）----
        qvec = embedding.embed_query(query)
        vlit = embedding.to_vector_literal(qvec)
        vec_rows: list[dict] = []
        with closing(self._connect()) as conn:
            with conn.cursor() as cur:
                sql = (
                    "SELECT id, title, content, course, source, "
                    "l2_distance(embedding, %s) AS dist "
                    "FROM notes ORDER BY dist APPROXIMATE LIMIT %s"
                )
                params: list = [vlit, top_k * 4]
                if course:
                    sql = (
                        "SELECT id, title, content, course, source, "
                        "l2_distance(embedding, %s) AS dist "
                        "FROM notes WHERE course = %s "
                        "ORDER BY dist APPROXIMATE LIMIT %s"
                    )
                    params = [vlit, course, top_k * 4]
                cur.execute(sql, params)
                for r in cur.fetchall():
                    r["vec_rank"] = None
                    vec_rows.append(r)

        # ---- 2) 全文召回（关键词，ik 分词）----
        fts_rows: list[dict] = []
        with closing(self._connect()) as conn:
            with conn.cursor() as cur:
                sql = (
                    "SELECT id, title, content, course, source, "
                    "MATCH(content) AGAINST(%s) + MATCH(title) AGAINST(%s) AS fts_score "
                    "FROM notes WHERE MATCH(content) AGAINST(%s IN BOOLEAN MODE) "
                    "OR MATCH(title) AGAINST(%s IN BOOLEAN MODE) "
                    "ORDER BY fts_score DESC LIMIT %s"
                )
                params: list = [fulltext_expr, fulltext_expr, fulltext_expr, fulltext_expr, top_k * 4]
                if course:
                    sql = (
                        "SELECT id, title, content, course, source, "
                        "MATCH(content) AGAINST(%s) + MATCH(title) AGAINST(%s) AS fts_score "
                        "FROM notes WHERE (MATCH(content) AGAINST(%s IN BOOLEAN MODE) "
                        "OR MATCH(title) AGAINST(%s IN BOOLEAN MODE)) AND course = %s "
                        "ORDER BY fts_score DESC LIMIT %s"
                    )
                    params = [fulltext_expr, fulltext_expr, fulltext_expr, fulltext_expr, course, top_k * 4]
                cur.execute(sql, params)
                for r in cur.fetchall():
                    r["fts_rank"] = None
                    fts_rows.append(r)

        # ---- 3) RRF 融合 ----
        def rrf(rows: list[dict], key: str, k: int = 60) -> None:
            for i, r in enumerate(rows):
                r[key] = 1.0 / (k + i + 1)

        rrf(vec_rows, "vec_rank")
        rrf(fts_rows, "fts_rank")

        merged: dict[int, dict] = {}
        for r in vec_rows:
            r["signal"] = "semantic"
            merged[r["id"]] = r
        for r in fts_rows:
            if r["id"] in merged:
                merged[r["id"]]["fts_rank"] = r["fts_rank"]
                merged[r["id"]]["signal"] = "both"
                merged[r["id"]]["fts_score"] = r.get("fts_score", 0)
            else:
                r["signal"] = "keyword"
                merged[r["id"]] = r

        results = []
        for r in merged.values():
            score = (r.get("vec_rank") or 0) + (r.get("fts_rank") or 0)
            results.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "content": r["content"],
                    "course": r["course"],
                    "source": r["source"],
                    "signal": r["signal"],
                    "score": round(score, 4),
                    "vec_dist": round(r.get("dist", 0) or 0, 4),
                    "fts_score": round(r.get("fts_score", 0) or 0, 4),
                }
            )
        results.sort(key=lambda x: x["score"], reverse=True)

        return {
            "query": query,
            "course": course,
            "top_k": top_k,
            "fulltext_expr": fulltext_expr,
            "results": results[:top_k],
            "raw": {"vector_hits": len(vec_rows), "fulltext_hits": len(fts_rows)},
            "engine": "seekdb-embedded",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
