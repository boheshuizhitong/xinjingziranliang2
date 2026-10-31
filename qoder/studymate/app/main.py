"""学伴 StudyMate —— FastAPI 应用入口

启动：python -m app.main （或 uvicorn app.main:app）
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# 保证 app 包内模块可用（兼容 `python app/main.py` 与 `uvicorn app.main:app`）
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from coach import StudyCoach  # noqa: E402
from memory_client import PowerContextClient  # noqa: E402
from seed import seed  # noqa: E402
from seekdb_store import KnowledgeBase  # noqa: E402

kb = KnowledgeBase()
mem = PowerContextClient()
coach = StudyCoach(kb, mem)

app = FastAPI(title="学伴 StudyMate", version="1.0.0")

STATIC_DIR = Path(__file__).resolve().parent / "static"


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    course: str = ""


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    course: str = ""


class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=8000)
    course: str = Field(..., min_length=1, max_length=32)
    source: str = ""
    tags: str = ""


class WeakRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    course: str = ""
    detail: str = ""


class ReviewedRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    course: str = ""
    note: str = ""


class PreferenceRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# 页面（挂载静态目录：/ 与 /app.js、/style.css 等）
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    kb_ok = True
    try:
        kb.init()
    except Exception as e:  # noqa: BLE001
        kb_ok = str(e)
    pc = mem.health()
    return {
        "app": "studymate",
        "seekdb": {"ok": kb_ok is True, "detail": kb_ok, "mode": "embedded"},
        "powercontext": pc,
        "powercontext_scope": config.PC_SCOPE_TITLE,
    }


# ---------------------------------------------------------------------------
# 知识库
# ---------------------------------------------------------------------------
@app.post("/api/init")
def api_init():
    """初始化知识库（建表）并写入示例数据（幂等：已有数据则跳过）。"""
    kb.init()
    result = seed(kb)
    return {"kb": kb.stats(), "seed": result, "powercontext_scope": mem.ensure_scope()}


@app.get("/api/notes")
def api_list_notes(course: str = ""):
    return {"notes": kb.list_notes(course), "stats": kb.stats()}


@app.post("/api/notes")
def api_add_note(body: NoteCreate):
    row = kb.add_note(body.title, body.content, body.course, body.source, body.tags)
    return {"status": "ok", "note": row}


@app.delete("/api/notes/{note_id}")
def api_delete_note(note_id: int):
    ok = kb.delete_note(note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return {"status": "ok", "deleted": note_id}


@app.post("/api/search")
def api_search(body: SearchRequest):
    """seekdb 混合检索：向量 + ik 全文 + 学科过滤。"""
    try:
        return kb.hybrid_search(body.query, course=body.course, top_k=5)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"检索失败：{e}") from e


# ---------------------------------------------------------------------------
# 记忆与复习教练
# ---------------------------------------------------------------------------
@app.post("/api/ask")
def api_ask(body: AskRequest):
    """问答：PowerContext 记忆上下文 + seekdb 知识库证据。"""
    try:
        return coach.answer(body.question, course=body.course)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"问答失败：{e}") from e


@app.get("/api/plan")
def api_plan():
    """今日复习计划（记忆调度 + 知识库资料匹配）。"""
    try:
        return coach.review_plan()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"生成复习计划失败：{e}") from e


@app.post("/api/weak")
def api_add_weak(body: WeakRequest):
    """记录薄弱知识点（PowerContext 记忆写入）。"""
    try:
        return coach.record_weak_point(body.topic, body.course, body.detail)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"记录薄弱点失败：{e}") from e


@app.post("/api/reviewed")
def api_mark_reviewed(body: ReviewedRequest):
    """标记完成一次复习（PowerContext 进度写入）。"""
    try:
        return coach.mark_reviewed(body.topic, body.course, body.note)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"记录复习进度失败：{e}") from e


@app.post("/api/preference")
def api_set_preference(body: PreferenceRequest):
    try:
        return coach.set_preference(body.text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"记录偏好失败：{e}") from e


@app.get("/api/memories")
def api_memories():
    try:
        return coach.memory_overview()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"读取记忆失败：{e}") from e


@app.get("/api/stats")
def api_stats():
    return {"seekdb": kb.stats(), "memory": coach.memory_overview()}


@app.post("/api/reset")
def api_reset():
    """重置知识库（删空 notes 表）并清除 Scope 缓存，便于评审重复验证。"""
    with kb._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notes")
    if config.PC_SCOPE_ID_FILE.exists():
        config.PC_SCOPE_ID_FILE.unlink()
    mem.scope_id = None  # 下次 ensure_scope 会创建全新 Scope
    return {"status": "ok", "kb": kb.stats()}


# 静态资源（在 API 路由之后挂载，保证 API 优先）
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    kb.init()
    uvicorn.run(app, host=config.APP_HOST, port=config.APP_PORT)
