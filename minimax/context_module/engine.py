"""SDD 上下文组装引擎

输入：开发任务描述（query）+ 可选 task_id。
过程：
  1) 在 seekdb 工程资料库中做混合检索，召回与任务相关的规格/代码/测试；
  2) 从 PowerContext 读取该任务的历史状态（已完成/待办/验证结果）。
输出（结构化 JSON，供 MiniMax 开发助手 / 评审核对）：
  - materials.specs   适用的规格条目（含来源 source，真实存在）
  - materials.code    需要修改的代码文件/符号（含来源）
  - materials.tests   用于验证功能与兼容性的测试（含来源）
  - state.done / todo / verification  已完成事项、待办事项、已有验证结果
"""
from __future__ import annotations

from typing import Any, Optional

from . import config as cfg
from .powercontext_client import PowerContextClient
from .seekdb_store import MaterialStore, M_SPEC, M_CODE, M_TEST


class ContextEngine:
    def __init__(self, store: MaterialStore | None = None,
                 pc: PowerContextClient | None = None):
        self.store = store or MaterialStore()
        self.store.init()
        self.pc = pc or PowerContextClient()

    def build_context(self, task_query: str, task_id: str = "",
                      top_k: int = 0) -> dict[str, Any]:
        top_k = top_k or cfg.CONTEXT_OUTPUT_TOP_K
        search = self.store.hybrid_search(task_query, top_k=top_k)

        grouped: dict[str, list] = {M_SPEC: [], M_CODE: [], M_TEST: []}
        for r in search["results"]:
            grouped.setdefault(r["mtype"], []).append(r)

        state = self._load_state()

        return {
            "task": {"id": task_id or "task-001", "query": task_query},
            "materials": {
                "specs": grouped[M_SPEC],
                "code": grouped[M_CODE],
                "tests": grouped[M_TEST],
            },
            "state": state,
            "database": {
                "engine": search["engine"],
                "vector_enabled": search["raw"]["vector_enabled"],
                "signal": search["raw"],
            },
            "generated_at": search["generated_at"],
        }

    def _load_state(self) -> dict[str, list[dict]]:
        return {
            "done": self.pc.list_by_kind(cfg.KIND_DONE),
            "todo": self.pc.list_by_kind(cfg.KIND_TODO),
            "verification": self.pc.list_by_kind(cfg.KIND_VERIFICATION),
        }

    def save_state(self, done: list[str], todo: list[str],
                   verification: list[str]) -> dict[str, Any]:
        """把任务进展写入 PowerContext（供后续运行读取复用）。"""
        return self.pc.save_task_state(done, todo, verification)


def format_context(context: dict[str, Any]) -> str:
    """把引擎输出渲染成给 MiniMax 助手的纯文本上下文。"""
    lines: list[str] = []
    t = context["task"]
    lines.append(f"# 开发任务：{t['query']}（id={t['id']}）")

    for key, label in (("specs", "适用规格"), ("code", "需修改代码"), ("tests", "验证测试")):
        items = context["materials"].get(key, [])
        lines.append(f"\n## {label}（{len(items)} 条）")
        for it in items:
            lines.append(f"- [{it.get('signal')}] {it['title']}  source={it['source']}")
            lines.append(f"  score={it.get('score')}  {it['content'][:600]}")

    st = context["state"]
    lines.append("\n## 任务状态（PowerContext）")
    lines.append(f"- 已完成：{len(st['done'])} 条")
    for d in st["done"]:
        lines.append(f"  · {d['text']}")
    lines.append(f"- 待办：{len(st['todo'])} 条")
    for d in st["todo"]:
        lines.append(f"  · {d['text']}")
    lines.append(f"- 验证结果：{len(st['verification'])} 条")
    for d in st["verification"]:
        lines.append(f"  · {d['text']}")

    db = context["database"]
    lines.append(f"\n## 资料库：{db['engine']} vector_enabled={db['vector_enabled']}")
    return "\n".join(lines)
