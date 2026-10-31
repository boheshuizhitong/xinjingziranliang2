"""复习教练：把 seekdb 知识检索与 PowerContext 记忆组合成学习建议

设计原则：不依赖外部大模型 API —— 全部逻辑由"记忆召回 + 知识库混合检索 +
间隔重复调度"的确定性规则构成，评审可离线完整复现。
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime
from typing import Any

import memory_client
import seekdb_store

# 间隔重复档位（天）：距离上次复习越久，优先级越高
INTERVAL_BUCKETS = [(1, 0.0), (3, 0.4), (7, 0.6), (14, 0.8), (30, 0.95), (9999, 1.0)]


def _due_weight(days: int) -> float:
    for threshold, w in INTERVAL_BUCKETS:
        if days <= threshold:
            return w
    return 1.0


def _parse_meta_dt(text: str) -> date | None:
    m = re.search(r"last_review=(\d{4}-\d{2}-\d{2})", text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


class StudyCoach:
    def __init__(self, kb: seekdb_store.KnowledgeBase, mem: memory_client.PowerContextClient):
        self.kb = kb
        self.mem = mem

    # ------------------------------------------------------------------
    # 1. 生成今日复习计划（记忆 + 知识库联动）
    # ------------------------------------------------------------------
    def review_plan(self) -> dict[str, Any]:
        today = date.today()
        memory_error = ""
        try:
            weak = self.mem.list_by_kind("weak_point", limit=30)
            progress = self.mem.list_by_kind("progress", limit=30)
        except Exception as e:  # noqa: BLE001
            weak, progress = [], []
            memory_error = f"PowerContext 未连接：{e}"

        # 合并同一知识点的进度与薄弱记录
        topics: dict[str, dict[str, Any]] = {}
        for m in weak:
            text = memory_client.strip_meta(m["text"]).replace("薄弱知识点：", "").strip()
            meta = memory_client.parse_meta(m["text"])
            topics.setdefault(
                text,
                {"topic": text, "course": meta.get("course", "未分类"),
                 "weak": True, "note": meta.get("note", ""),
                 "last_review": None, "progress_note": ""},
            )
        for m in progress:
            text = memory_client.strip_meta(m["text"]).replace("复习进度：", "").strip()
            meta = memory_client.parse_meta(m["text"])
            entry = topics.get(text) or {
                "topic": text, "course": meta.get("course", "未分类"),
                "weak": False, "note": "", "last_review": None, "progress_note": ""}
            entry["last_review"] = _parse_meta_dt(m["text"])
            entry["progress_note"] = meta.get("note", "")
            topics[text] = entry

        items = []
        for t in topics.values():
            days = (today - t["last_review"]).days if t["last_review"] else 99
            due = (days >= 3) or t["weak"] and t["last_review"] is None
            # 为每个知识点在知识库中检索可复习资料（seekdb 混合检索）
            kb_hit = self.kb.hybrid_search(t["topic"], course=t["course"] or "", top_k=2)
            items.append(
                {
                    "topic": t["topic"],
                    "course": t["course"],
                    "is_weak": t["weak"],
                    "last_review": t["last_review"].isoformat() if t["last_review"] else None,
                    "days_since": days,
                    "due": due,
                    "priority": round(_due_weight(days) + (0.5 if t["weak"] else 0.0), 3),
                    "progress_note": t["progress_note"],
                    "materials": kb_hit["results"],
                    "search_engine": "seekdb",
                }
            )

        items.sort(key=lambda x: x["priority"], reverse=True)
        due_items = [i for i in items if i["due"]]
        review_items = [i for i in items if not i["due"]]
        return {
            "generated_at": today.isoformat(),
            "memory_server": self.mem.health().get("url"),
            "memory_error": memory_error,
            "summary": {
                "tracked_topics": len(items),
                "due_today": len(due_items),
                "consolidating": len(review_items),
            },
            "due_today": due_items,
            "consolidating": review_items,
        }

    # ------------------------------------------------------------------
    # 2. 问答：记忆上下文 + 知识库证据
    # ------------------------------------------------------------------
    def answer(self, question: str, course: str = "") -> dict[str, Any]:
        # ① PowerContext 召回与问题相关的历史记忆（准备有界上下文；异常时降级不影响检索）
        ctx: dict[str, Any] = {}
        mem_hits: list[dict] = []
        try:
            ctx = self.mem.prepare(question, max_bytes=4000)
            mem_hits = self.mem.search(question, limit=5)
        except Exception as e:  # noqa: BLE001
            ctx = {"status": "degraded", "error": str(e)}
            mem_hits = []

        # ② seekdb 混合检索知识库证据
        kb = self.kb.hybrid_search(question, course=course, top_k=4)

        # ③ 组装回答
        lines = ["根据你的学习记录和知识库，找到以下相关内容：\n"]
        if kb["results"]:
            for i, r in enumerate(kb["results"], 1):
                lines.append(
                    f"{i}. 【{r['course']}】{r['title']}"
                    + (f"（出处：{r['source']}）" if r["source"] else "")
                )
                lines.append(f"   {r['content']}")
                lines.append(f"   ——命中方式：{r['signal']}")
        else:
            lines.append("知识库中暂未找到直接相关的内容，建议补充笔记后再试。")

        # 记忆线索（体现 PowerContext 跨会话记忆）
        memory_notes = []
        for h in mem_hits:
            if h.get("kind") in ("weak_point", "progress", "preference"):
                memory_notes.append(
                    f"{h['kind']}：{memory_client.strip_meta(h['text'])}"
                )
        if memory_notes:
            lines.append("\n📌 我记着关于你的这些信息（来自 PowerContext 记忆）：")
            for n in memory_notes[:3]:
                lines.append(f"  · {n}")

        return {
            "question": question,
            "answer": "\n".join(lines),
            "knowledge": kb,
            "memory_context": {
                "status": ctx.get("status"),
                "content": ctx.get("content"),
                "hits": mem_hits,
            },
            "server": {"seekdb": "embedded", "powercontext": self.mem.health().get("url")},
        }

    # ------------------------------------------------------------------
    # 3. 记忆写入操作
    # ------------------------------------------------------------------
    def record_weak_point(self, topic: str, course: str, detail: str = "") -> dict[str, Any]:
        return self.mem.remember_weak_point(topic, course, detail)

    def mark_reviewed(self, topic: str, course: str, note: str = "") -> dict[str, Any]:
        return self.mem.remember_review(topic, course, note)

    def set_preference(self, text: str) -> dict[str, Any]:
        return self.mem.remember_preference(text)

    def memory_overview(self) -> dict[str, Any]:
        return {
            "weak_points": self.mem.list_by_kind("weak_point", 20),
            "progress": self.mem.list_by_kind("progress", 20),
            "preferences": self.mem.list_by_kind("preference", 10),
        }
