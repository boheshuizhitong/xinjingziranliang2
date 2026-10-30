"""
PowerContext-Compatible Memory Server
=====================================
A lightweight FastAPI server providing the two endpoints that our
Dify Chatflow (AI 记忆梗王) needs:

  GET  /api/v1/memories/search?query=xxx&scope=user-yyy&limit=10
  POST /api/v1/memories/remember

Plus:
  GET  /health
  GET  /api/v1/memories/all?scope=user-yyy   (debug)

Storage: SQLite + LIKE matching. Same request/response shapes
as the real PowerContext server — drop-in compatible.

Run:
  pip install -r requirements.txt
  python server.py          # default http://localhost:8000
"""

import json
import os
import sqlite3
import time
from contextlib import contextmanager

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field
import uvicorn

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get("POWERCONTEXT_DB", "powercontext.db")
HOST = os.environ.get("POWERCONTEXT_HOST", "0.0.0.0")
PORT = int(os.environ.get("POWERCONTEXT_PORT", "8000"))

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scope       TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    TEXT DEFAULT '{}',
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scope ON memories(scope);
"""


def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------
class RememberMessage(BaseModel):
    role: str
    content: str


class RememberRequest(BaseModel):
    scope: str
    messages: list[RememberMessage]
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PowerContext Memory Server",
    version="0.1.0",
    description="Lightweight memory store for Dify Chatflow",
)


@app.on_event("startup")
def _on_start():
    _init_db()
    print(f"[PowerContext] DB at {os.path.abspath(DB_PATH)}")
    print(f"[PowerContext] Listening on http://{HOST}:{PORT}")


@app.get("/health")
def health():
    return {"status": "ok", "db": DB_PATH}


# ---------------------------------------------------------------------------
# GET /api/v1/memories/search
# ---------------------------------------------------------------------------
@app.get("/api/v1/memories/search")
def search_memories(
    query: str = Query(""),
    scope: str = Query(""),
    limit: int = Query(10),
):
    """
    Search memories by scope + query substring match.

    Response: [{"content": "...", "metadata": {...}, "score": 0.95}, ...]
    """
    results = []
    with _conn() as conn:
        if query.strip():
            rows = conn.execute(
                """
                SELECT content, metadata, created_at
                FROM memories
                WHERE scope = ? AND content LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (scope, f"%{query}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT content, metadata, created_at
                FROM memories
                WHERE scope = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (scope, limit),
            ).fetchall()

        for r in rows:
            try:
                meta = json.loads(r["metadata"])
            except Exception:
                meta = {}
            results.append(
                {
                    "content": r["content"],
                    "metadata": meta,
                    "score": 0.95,
                }
            )

    return results


# ---------------------------------------------------------------------------
# POST /api/v1/memories/remember
# ---------------------------------------------------------------------------
@app.post("/api/v1/memories/remember")
def remember(req: RememberRequest):
    """
    Store a conversation (user + assistant messages) under a scope.
    """
    stored = []
    ts = time.time()
    with _conn() as conn:
        for msg in req.messages:
            conn.execute(
                "INSERT INTO memories(scope, content, metadata, created_at) "
                "VALUES (?, ?, ?, ?)",
                (req.scope, msg.content, json.dumps(req.metadata, ensure_ascii=False), ts),
            )
            stored.append(msg.content[:80])

    print(f"[remember] scope={req.scope} msgs={len(req.messages)} meta={req.metadata}")
    return {"ok": True, "stored": len(req.messages), "snippet": stored}


# ---------------------------------------------------------------------------
# GET /api/v1/memories/all (debug)
# ---------------------------------------------------------------------------
@app.get("/api/v1/memories/all")
def all_memories(scope: str = Query("")):
    with _conn() as conn:
        if scope:
            rows = conn.execute(
                "SELECT content, metadata, created_at FROM memories WHERE scope=? ORDER BY created_at",
                (scope,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT content, metadata, created_at FROM memories ORDER BY created_at"
            ).fetchall()
        return [
            {
                "content": r["content"],
                "metadata": json.loads(r["metadata"] or "{}"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("server:app", host=HOST, port=PORT, reload=False)
