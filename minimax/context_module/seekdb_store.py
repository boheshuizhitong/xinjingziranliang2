"""seekdb 工程资料库层：存储规格/代码/测试，支持向量+全文混合检索

技术说明（seekdb 官方能力落地方式，与业务工程共享同一嵌入式实例）：
- 存储：pylibseekdb 嵌入式启动本地 seekdb，pymysql 走 MySQL 协议执行 SQL。
- 全文：content/title 建 ik 中文分词全文索引，MATCH ... AGAINST 检索。
- 向量：bge-small-zh-v1.5 本地 ONNX 嵌入（可选，模型不可用时自动回退全文）。
- 混合：全文 TopK 与向量 TopK 双路召回 + Reciprocal Rank Fusion（RRF）融合。
- 更新：以 (mtype, source) 为主键 upsert，重新导入规格时覆盖旧内容。
"""
from __future__ import annotations

import re
import threading
import time
from contextlib import closing
from typing import Any, Optional

import pymysql

from . import config as cfg
from . import embedding

DB_NAME = "test"

M_SPEC = "spec"
M_CODE = "code"
M_TEST = "test"
MTYPES = (M_SPEC, M_CODE, M_TEST)


def _split_query(q: str) -> list[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]+|[A-Za-z][A-Za-z0-9_\-]*", q)
    out: list[str] = []
    for t in tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]+", t) and len(t) > 4:
            step = 2
            for i in range(0, len(t) - 1, step):
                out.append(t[i: i + step])
        else:
            out.append(t)
    return out


class MaterialStore:
    """seekdb 工程资料库封装（进程内单例）。"""

    def __init__(self, path: str = str(cfg.SEEKDB_PATH)):
        self.path = path
        self._db = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ 连接
    def _ensure_db(self):
        if self._db is None:
            import pylibseekdb
            from pathlib import Path
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self._db = pylibseekdb.open(self.path)
        return self._db

    def _connect(self):
        db = self._ensure_db()
        options = db.connection_options()
        return pymysql.connect(database=DB_NAME, autocommit=True,
                               cursorclass=pymysql.cursors.DictCursor, **options)

    def close(self):
        if self._db is not None:
            try:
                self._db.close()
            finally:
                self._db = None

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS materials (
      id         INT PRIMARY KEY AUTO_INCREMENT,
      mtype      VARCHAR(16)  NOT NULL,
      title      TEXT NOT NULL,
      content    TEXT NOT NULL,
      source     VARCHAR(256) NOT NULL,
      tags       VARCHAR(256) NOT NULL DEFAULT '',
      version    VARCHAR(32)  NOT NULL DEFAULT '',
      embedding  VECTOR(512),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FULLTEXT INDEX idx_m_content (content) WITH PARSER ik,
      FULLTEXT INDEX idx_m_title (title) WITH PARSER ik
    ) ORGANIZATION = HEAP
    """

    def init(self) -> dict[str, Any]:
        with self._lock:
            with closing(self._connect()) as conn, conn.cursor() as cur:
                cur.execute(self.SCHEMA)
                cur.execute("SHOW TABLES")
                tables = [list(r.values())[0] for r in cur.fetchall()]
                return {"status": "ok", "tables": tables, "path": self.path}

    # ------------------------------------------------------------------ 写入
    def upsert_material(self, mtype: str, title: str, content: str,
                        source: str, tags: str = "", version: str = "") -> dict[str, Any]:
        """以 (mtype, source) 为准插入或覆盖（重新导入时更新旧内容）。"""
        if mtype not in MTYPES:
            raise ValueError(f"unknown mtype: {mtype}")
        with self._lock:
            vec = embedding.embed_text(f"{title}。{content}")
            vlit = embedding.to_vector_literal(vec) if vec else None
            with closing(self._connect()) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM materials WHERE mtype=%s AND source=%s",
                            (mtype, source))
                if vlit:
                    cur.execute(
                        "INSERT INTO materials (mtype,title,content,source,tags,version,embedding) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (mtype, title, content, source, tags, version, vlit),
                    )
                else:
                    cur.execute(
                        "INSERT INTO materials (mtype,title,content,source,tags,version) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (mtype, title, content, source, tags, version),
                    )
                return {"id": cur.lastrowid, "mtype": mtype, "source": source}

    def clear_all(self) -> int:
        with self._lock:
            with closing(self._connect()) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM materials")
                return cur.rowcount

    def stats(self) -> dict[str, Any]:
        with closing(self._connect()) as conn, conn.cursor() as cur:
            cur.execute("SELECT mtype, COUNT(*) AS c FROM materials GROUP BY mtype")
            by_type = {r["mtype"]: r["c"] for r in cur.fetchall()}
            cur.execute("SELECT COUNT(*) AS c FROM materials")
            return {"total": cur.fetchone()["c"], "by_type": by_type, "vector_enabled": embedding.embedding_available()}

    # ------------------------------------------------------------------ 检索
    def hybrid_search(self, query: str, mtypes: Optional[list[str]] = None,
                      top_k: int = 6) -> dict[str, Any]:
        """双路召回 + RRF 融合，返回扁平结果（engine 层再按 mtype 分组）。

        mtypes 为 None 表示不限类型。向量不可用时自动退化为全文检索。
        """
        q_tokens = _split_query(query)
        fulltext_expr = " ".join(q_tokens[:8]) if q_tokens else query
        # 类型过滤子句：mtypes 为空时为空串，非空时拼出 ` AND mtype IN (%s,...)`
        type_clause = ""
        tparams: list = []
        if mtypes:
            type_clause = " AND mtype IN (" + ",".join(["%s"] * len(mtypes)) + ")"
            tparams = list(mtypes)

        vec_rows: list[dict] = []
        qvec = embedding.embed_query(query)
        if qvec:
            vlit = embedding.to_vector_literal(qvec)
            with closing(self._connect()) as conn, conn.cursor() as cur:
                sql = ("SELECT id,mtype,title,content,source,tags,version,"
                       "l2_distance(embedding,%s) AS dist FROM materials WHERE 1=1"
                       f"{type_clause} ORDER BY dist APPROXIMATE LIMIT %s")
                params: list = [vlit] + tparams + [top_k * 4]
                cur.execute(sql, params)
                for r in cur.fetchall():
                    r["vec_rank"] = None
                    vec_rows.append(r)

        fts_rows: list[dict] = []
        with closing(self._connect()) as conn, conn.cursor() as cur:
            sql = ("SELECT id,mtype,title,content,source,tags,version,"
                   "MATCH(content) AGAINST(%s)+MATCH(title) AGAINST(%s) AS fts_score "
                   "FROM materials WHERE (MATCH(content) AGAINST(%s IN BOOLEAN MODE) "
                   "OR MATCH(title) AGAINST(%s IN BOOLEAN MODE))"
                   f"{type_clause} ORDER BY fts_score DESC LIMIT %s")
            params = [fulltext_expr, fulltext_expr, fulltext_expr, fulltext_expr]
            params += tparams
            params += [top_k * 4]
            cur.execute(sql, params)
            for r in cur.fetchall():
                r["fts_rank"] = None
                fts_rows.append(r)

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
            results.append({
                "id": r["id"], "mtype": r["mtype"], "title": r["title"],
                "content": r["content"], "source": r["source"],
                "tags": r["tags"], "version": r["version"],
                "signal": r["signal"], "score": round(score, 4),
                "vec_dist": round(r.get("dist", 0) or 0, 4),
                "fts_score": round(r.get("fts_score", 0) or 0, 4),
            })
        results.sort(key=lambda x: x["score"], reverse=True)

        return {
            "query": query,
            "top_k": top_k,
            "fulltext_expr": fulltext_expr,
            "results": results[:top_k],
            "raw": {"vector_hits": len(vec_rows), "fulltext_hits": len(fts_rows),
                    "vector_enabled": qvec is not None},
            "engine": "seekdb-embedded",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
