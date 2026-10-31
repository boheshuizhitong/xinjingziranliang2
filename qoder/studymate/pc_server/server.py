"""PowerContext 兼容实现（离线评审兜底）

实现与官方 PowerContext Server 相同的 HTTP 契约，供本作品在无网络/不装官方
Server 的环境下完成评审验证：

  GET  /health/live、/health/ready
  POST /v1/scopes            创建 Scope
  POST /v1/sources/content   记录证据 Source
  POST /v1/memory/remember   写入记忆
  POST /v1/memory/search     召回记忆
  POST /v1/context/prepare   准备有界上下文
  GET  /v1/memories/all      调试

存储：SQLite；召回：关键词匹配打分（多词命中加分）。请求/响应字段与官方
契约一致（见 openapi/powercontext.yaml），应用层无需任何改动即可切换。

说明：正式使用时可将 POWERCONTEXT_URL 指向官方 PowerContext Server
（uv tool install powercontext[cli,server] 后启动），本文件仅作离线备用。
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field
import uvicorn

# 数据库默认放在项目 data/ 目录（与主应用数据同目录，便于统一清理与备份）
_DEFAULT_DB = str(Path(__file__).resolve().parent.parent / "data" / "powercontext.db")
DB_PATH = os.environ.get("POWERCONTEXT_DB", _DEFAULT_DB)
HOST = os.environ.get("POWERCONTEXT_HOST", "127.0.0.1")
PORT = int(os.environ.get("POWERCONTEXT_PORT", "8010"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS scopes (
  scope_id    TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  summary     TEXT DEFAULT '',
  created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  scope_id    TEXT NOT NULL,
  artifact    TEXT NOT NULL,
  kind        TEXT NOT NULL,
  text        TEXT NOT NULL,
  reason      TEXT DEFAULT '',
  state       TEXT DEFAULT 'active',
  state_version INTEGER DEFAULT 1,
  created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(scope_id);
CREATE TABLE IF NOT EXISTS sources (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  scope_id    TEXT NOT NULL,
  source_id   TEXT NOT NULL,
  content     TEXT NOT NULL,
  metadata    TEXT DEFAULT '{}',
  created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_src_scope ON sources(scope_id);
"""


def _init_db():
    with sqlite3_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def sqlite3_conn():
    import sqlite3

    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# 请求模型（与官方契约一致）
# ---------------------------------------------------------------------------
class CreateScopeRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    summary: str = Field(..., min_length=1, max_length=2000)
    idempotency_key: str = Field(..., min_length=1, max_length=256)


class RememberRequest(BaseModel):
    scope_id: str
    kind: str
    text: str
    reason: str | None = None
    expected_revision: int | None = None
    description: str | None = None


class SearchRequest(BaseModel):
    scope_id: str
    query: str
    limit: int = 10
    mode: str = "auto"


class ListMemoryRequest(BaseModel):
    scope_id: str
    kind: str | None = None
    states: list[str] | None = None
    limit: int = 50


class PrepareRequest(BaseModel):
    scope_id: str
    query: str
    max_bytes: int = 8000


class SourceRequest(BaseModel):
    scope_id: str
    source_id: str
    content: str
    metadata: dict | None = None


app = FastAPI(title="PowerContext Compatible Server", version="1.0.0")


@app.on_event("startup")
def _startup():
    _init_db()
    print(f"[PowerContext] DB: {os.path.abspath(DB_PATH)}")
    print(f"[PowerContext] Listening on http://{HOST}:{PORT} (compatible contract)")


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    return {"status": "ready", "db": DB_PATH}


@app.post("/v1/scopes")
def create_scope(req: CreateScopeRequest):
    scope_id = req.idempotency_key if req.idempotency_key else f"scope-{uuid.uuid4().hex[:12]}"
    with sqlite3_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO scopes(scope_id, title, summary, created_at) VALUES (?,?,?,?)",
            (scope_id, req.title, req.summary, _now()),
        )
    return {"scope_id": scope_id, "title": req.title, "created": True}


@app.post("/v1/sources/content")
def capture_source(req: SourceRequest):
    with sqlite3_conn() as conn:
        conn.execute(
            "INSERT INTO sources(scope_id, source_id, content, metadata, created_at) VALUES (?,?,?,?,?)",
            (req.scope_id, req.source_id, req.content,
             json.dumps(req.metadata or {}, ensure_ascii=False), _now()),
        )
    return {
        "source": {
            "type": "content",
            "scope_id": req.scope_id,
            "source_id": req.source_id,
            "status": "active",
        }
    }


@app.post("/v1/memory/remember")
def remember(req: RememberRequest):
    artifact = f"atomic-memory/{uuid.uuid4().hex[:10]}@1"
    ts = _now()
    with sqlite3_conn() as conn:
        conn.execute(
            "INSERT INTO memories(scope_id, artifact, kind, text, reason, state, state_version, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (req.scope_id, artifact, req.kind, req.text, req.reason or "",
             "active", 1, ts),
        )
    return {
        "changed": True,
        "records": [
            {
                "artifact": artifact,
                "kind": req.kind,
                "text": req.text,
                "state": "active",
                "state_version": 1,
                "merged_into_id": None,
                "description": (req.text[:120] + "…") if len(req.text) > 120 else req.text,
            }
        ],
    }


def _split_terms(query: str) -> list[str]:
    """查询切词：英文单词按空格，中文连续串做 2 字滑窗（兼容无空格提问）。"""
    import re as _re

    tokens = _re.findall(r"[\u4e00-\u9fff]+|[A-Za-z][A-Za-z0-9_\-]*", query)
    out: list[str] = []
    for t in tokens:
        if _re.fullmatch(r"[\u4e00-\u9fff]+", t):
            if len(t) <= 2:
                out.append(t)
            else:
                out.extend(t[i : i + 2] for i in range(len(t) - 1))
        else:
            out.append(t)
    return [t for t in out if t][:12]


def _term_score(text: str, terms: list[str]) -> float:
    """关键词命中打分：每个词命中得 1 分。"""
    score = 0.0
    low = text.lower()
    for t in terms:
        if t and t.lower() in low:
            score += 1.0
    return score


@app.post("/v1/atomic-memory/list")
def list_memories(req: ListMemoryRequest):
    """官方契约：按 kind/state 精确列出记忆。"""
    with sqlite3_conn() as conn:
        sql = "SELECT artifact, kind, text, reason, state, state_version, created_at FROM memories WHERE scope_id = ?"
        params: list = [req.scope_id]
        if req.kind:
            sql += " AND kind = ?"
            params.append(req.kind)
        if req.states:
            sql += " AND state IN (%s)" % ",".join("?" * len(req.states))
            params.extend(req.states)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(req.limit)
        rows = conn.execute(sql, params).fetchall()
    return {
        "items": [
            {
                "artifact": r["artifact"],
                "kind": r["kind"],
                "text": r["text"],
                "state": r["state"],
                "state_version": r["state_version"],
                "merged_into_id": None,
            }
            for r in rows
        ],
        "next_cursor": None,
    }


@app.post("/v1/memory/search")
def search(req: SearchRequest):
    terms = _split_terms(req.query)
    with sqlite3_conn() as conn:
        rows = conn.execute(
            "SELECT artifact, kind, text, reason, state, state_version, created_at "
            "FROM memories WHERE scope_id = ? AND state = 'active' ORDER BY created_at DESC",
            (req.scope_id,),
        ).fetchall()

    hits = []
    for r in rows:
        score = _term_score(r["text"], terms) if terms else 0.5
        if score <= 0:
            continue
        hits.append(
            {
                "memory": {
                    "artifact": r["artifact"],
                    "kind": r["kind"],
                    "text": r["text"],
                    "state": r["state"],
                    "state_version": r["state_version"],
                    "merged_into_id": None,
                },
                "score": round(score, 4),
                "matched_by": ["text"],
            }
        )
    hits.sort(key=lambda h: h["score"], reverse=True)
    return {"mode": "text", "hits": hits[: req.limit]}


@app.post("/v1/context/prepare")
def prepare(req: PrepareRequest):
    terms = _split_terms(req.query)
    with sqlite3_conn() as conn:
        rows = conn.execute(
            "SELECT artifact, kind, text, reason FROM memories "
            "WHERE scope_id = ? AND state = 'active' ORDER BY created_at DESC",
            (req.scope_id,),
        ).fetchall()

    scored = [(r, _term_score(r["text"], terms)) for r in rows]
    scored = [(r, s) for r, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)

    parts: list[str] = []
    used = 0
    for r, _s in scored:
        piece = f"[{r['kind']}] {r['text']}"
        piece_b = len(piece.encode("utf-8"))
        if used + piece_b > req.max_bytes:
            break
        parts.append(piece)
        used += piece_b

    if not parts:
        return {"schema": "context.prepared.v1", "status": "empty",
                "content": None, "content_bytes": 0, "reason": None}
    return {
        "schema": "context.prepared.v1",
        "status": "ready",
        "content": "\n".join(parts),
        "content_bytes": used,
        "reason": None,
    }


@app.get("/v1/memories/all")
def all_memories(scope_id: str = Query("")):
    with sqlite3_conn() as conn:
        if scope_id:
            rows = conn.execute(
                "SELECT artifact, kind, text, state, created_at FROM memories "
                "WHERE scope_id = ? ORDER BY created_at", (scope_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT scope_id, artifact, kind, text, state, created_at FROM memories "
                "ORDER BY created_at"
            ).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    uvicorn.run("server:app", host=HOST, port=PORT, reload=False)
