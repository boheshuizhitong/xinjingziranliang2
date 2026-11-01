"""PowerContext 记忆客户端（HTTP API）

对接 PowerContext 的公开契约，用于保存与复用任务状态：
  POST /v1/scopes              创建/获取 Scope（一个任务状态域）
  POST /v1/memory/remember     写入记忆（kind/text/reason）
  POST /v1/memory/search       召回记忆（query/limit）
  POST /v1/atomic-memory/list  按 kind 精确列出记忆
  POST /v1/context/prepare     为一次交互准备有界上下文

可同时兼容：
  1) 官方 PowerContext Server（uv 部署）
  2) 本仓库自带兼容实现 pc_server/server.py（离线评审兜底，契约一致）
通过环境变量 POWERCONTEXT_URL 切换，无需改代码。
"""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import config as cfg

PREFIX = {
    cfg.KIND_TASK_STATE: "任务状态",
    cfg.KIND_TODO: "待办事项",
    cfg.KIND_DONE: "已完成事项",
    cfg.KIND_VERIFICATION: "验证结果",
}


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if cfg.PC_TOKEN:
        headers["Authorization"] = f"Bearer {cfg.PC_TOKEN}"
    req = Request(
        f"{cfg.PC_BASE_URL}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(req, timeout=cfg.PC_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {}
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"PowerContext {path} -> HTTP {e.code}: {detail[:400]}") from e


class PowerContextClient:
    def __init__(self, scope_suffix: str = ""):
        self.scope_id: str | None = None
        self._scope_suffix = scope_suffix

    # ------------------------------------------------------------------ Scope
    def ensure_scope(self) -> str:
        if self.scope_id:
            return self.scope_id
        if cfg.PC_SCOPE_ID_FILE.exists():
            self.scope_id = cfg.PC_SCOPE_ID_FILE.read_text(encoding="utf-8").strip()
            if self.scope_id:
                return self.scope_id
        key = f"pctx-sdd-{self._scope_suffix or int(time.time())}"
        resp = _post("/v1/scopes", {
            "title": cfg.PC_SCOPE_TITLE,
            "summary": "SDD 上下文管理系统：保存任务进展与验证结果",
            "idempotency_key": key,
        })
        scope_id = resp.get("scope_id") or resp.get("id")
        if not scope_id:
            raise RuntimeError(f"创建 PowerContext Scope 失败: {resp}")
        self.scope_id = scope_id
        cfg.PC_SCOPE_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        cfg.PC_SCOPE_ID_FILE.write_text(scope_id, encoding="utf-8")
        return scope_id

    # ------------------------------------------------------------------ 写入
    def remember(self, kind: str, text: str, reason: str = "",
                 meta: dict[str, Any] | None = None) -> dict[str, Any]:
        scope = self.ensure_scope()
        prefix = PREFIX.get(kind, kind)
        suffix = ""
        if meta:
            suffix = " | " + " | ".join(f"{k}={v}" for k, v in meta.items())
        full_text = f"{prefix}：{text}{suffix}"
        resp = _post("/v1/memory/remember", {
            "scope_id": scope, "kind": kind, "text": full_text,
            "reason": reason or f"SDD 上下文模块记录 {prefix}",
        })
        return {"scope_id": scope, "kind": kind, "text": full_text, "response": resp}

    def save_task_state(self, done: list[str], todo: list[str],
                        verification: list[str], meta: dict[str, Any] | None = None) -> dict[str, Any]:
        """一次写入任务的三类状态：已完成 / 待办 / 验证结果。"""
        scope = self.ensure_scope()
        out = {"scope_id": scope, "writes": []}
        for kind, items in ((cfg.KIND_DONE, done), (cfg.KIND_TODO, todo),
                            (cfg.KIND_VERIFICATION, verification)):
            for item in items:
                out["writes"].append(self.remember(kind, item, meta=meta))
        return out

    # ------------------------------------------------------------------ 读取
    @staticmethod
    def _record(mem: dict[str, Any]) -> dict[str, Any]:
        return {"text": mem.get("text", ""), "kind": mem.get("kind", ""),
                "state": mem.get("state", ""), "artifact": mem.get("artifact", "")}

    def list_by_kind(self, kind: str, limit: int = 100) -> list[dict[str, Any]]:
        """按 kind 精确列出记忆（官方 /v1/atomic-memory/list）。"""
        scope = self.ensure_scope()
        try:
            resp = _post("/v1/atomic-memory/list",
                         {"scope_id": scope, "kind": kind, "states": ["active"], "limit": limit})
            return [self._record(m) for m in resp.get("items", [])]
        except RuntimeError:
            return self.search(PREFIX.get(kind, kind), limit=limit)

    def search(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        scope = self.ensure_scope()
        resp = _post("/v1/memory/search", {"scope_id": scope, "query": query, "limit": limit})
        out = []
        for hit in resp.get("hits", []):
            mem = hit.get("memory") or {}
            rec = self._record(mem)
            rec["score"] = round(float(hit.get("score", 0)), 4)
            out.append(rec)
        return out

    def prepare(self, query: str, max_bytes: int = 4000) -> dict[str, Any]:
        scope = self.ensure_scope()
        resp = _post("/v1/context/prepare", {"scope_id": scope, "query": query, "max_bytes": max_bytes})
        return {"status": resp.get("status"), "content": resp.get("content"),
                "content_bytes": resp.get("content_bytes", 0)}

    # ------------------------------------------------------------------ 健康
    def health(self) -> dict[str, Any]:
        try:
            with urlopen(f"{cfg.PC_BASE_URL}/health/live", timeout=2) as resp:
                return {"ok": resp.status == 200, "url": cfg.PC_BASE_URL}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "url": cfg.PC_BASE_URL, "error": str(e)}
