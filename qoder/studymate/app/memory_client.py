"""PowerContext 记忆客户端（HTTP API）

对接官方 PowerContext Server 的公开契约：
  POST /v1/scopes               创建 Scope（每个用户一个）
  POST /v1/sources/content      记录证据（Source journal）
  POST /v1/memory/remember      写入记忆（kind/text/reason）
  POST /v1/memory/search        召回记忆（query/limit）
  POST /v1/context/prepare      为一次交互准备有界上下文

本客户端只发送契约允许的字段，可同时兼容：
  1) 官方 PowerContext Server（uv 部署，Windows/Linux/macOS）
  2) 本仓库自带兼容实现 pc_server/server.py（离线评审兜底，契约一致）
通过环境变量 POWERCONTEXT_URL 切换，无需改代码。
"""
from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import config

# 记忆条目文本前缀（用作可检索的"伪标签"，兼容官方契约无 metadata 字段的限制）
PREFIX = {
    config.KIND_WEAK_POINT: "薄弱知识点",
    config.KIND_PROGRESS: "复习进度",
    config.KIND_PREFERENCE: "学习偏好",
    config.KIND_FACT: "用户事实",
}


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if config.PC_TOKEN:
        headers["Authorization"] = f"Bearer {config.PC_TOKEN}"
    req = Request(
        f"{config.PC_BASE_URL}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(req, timeout=config.PC_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {}
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"PowerContext {path} -> HTTP {e.code}: {detail[:400]}") from e


class PowerContextClient:
    def __init__(self):
        self.scope_id: str | None = None

    # ------------------------------------------------------------------
    # Scope 管理
    # ------------------------------------------------------------------
    def ensure_scope(self) -> str:
        if self.scope_id:
            return self.scope_id
        if config.PC_SCOPE_ID_FILE.exists():
            self.scope_id = config.PC_SCOPE_ID_FILE.read_text(encoding="utf-8").strip()
            if self.scope_id:
                return self.scope_id
        resp = _post(
            "/v1/scopes",
            {
                "title": config.PC_SCOPE_TITLE,
                "summary": "学伴 StudyMate 的个人学习记忆（薄弱知识点/复习进度/偏好）",
                "idempotency_key": f"studymate-{int(time.time())}",
            },
        )
        scope_id = resp.get("scope_id") or resp.get("id")
        if not scope_id:
            raise RuntimeError(f"创建 PowerContext Scope 失败: {resp}")
        self.scope_id = scope_id
        config.PC_SCOPE_ID_FILE.write_text(scope_id, encoding="utf-8")
        return scope_id

    # ------------------------------------------------------------------
    # 写入记忆
    # ------------------------------------------------------------------
    def remember(self, kind: str, text: str,
                 reason: str = "", meta: dict[str, Any] | None = None) -> dict[str, Any]:
        """写入一条记忆。kind 映射到文本前缀，meta 以 `| key=value` 形式结构化编码进文本。"""
        scope = self.ensure_scope()
        prefix = PREFIX.get(kind, kind)
        suffix = ""
        if meta:
            suffix = " | " + " | ".join(f"{k}={v}" for k, v in meta.items())
        full_text = f"{prefix}：{text}{suffix}"
        payload: dict[str, Any] = {
            "scope_id": scope,
            "kind": kind,
            "text": full_text,
            "reason": reason or f"学伴 StudyMate 记录 {prefix}",
        }
        resp = _post("/v1/memory/remember", payload)
        return {
            "scope_id": scope,
            "text": full_text,
            "kind": kind,
            "response": resp,
            "server": config.PC_BASE_URL,
        }

    def remember_weak_point(self, topic: str, course: str, detail: str = "") -> dict[str, Any]:
        text = topic if not detail else f"{topic}（{detail}）"
        return self.remember(config.KIND_WEAK_POINT, text, meta={"course": course})

    def remember_review(self, topic: str, course: str, note: str = "") -> dict[str, Any]:
        return self.remember(
            config.KIND_PROGRESS,
            topic,
            reason="完成一次复习，记录进度",
            meta={"course": course, "last_review": time.strftime("%Y-%m-%d"), "note": note},
        )

    def remember_preference(self, text: str) -> dict[str, Any]:
        return self.remember(config.KIND_PREFERENCE, text)

    # ------------------------------------------------------------------
    # 召回记忆
    # ------------------------------------------------------------------
    @staticmethod
    def _record(mem: dict[str, Any]) -> dict[str, Any]:
        return {
            "text": mem.get("text", ""),
            "kind": mem.get("kind", ""),
            "score": 1.0,
            "matched_by": ["listed"],
            "state": mem.get("state", ""),
            "artifact": mem.get("artifact", ""),
        }

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """召回记忆，返回 [{text, kind, score, state, artifact}]。"""
        scope = self.ensure_scope()
        resp = _post(
            "/v1/memory/search",
            {"scope_id": scope, "query": query, "limit": limit},
        )
        out = []
        for hit in resp.get("hits", []):
            mem = hit.get("memory") or {}
            rec = self._record(mem)
            rec["score"] = round(float(hit.get("score", 0)), 4)
            rec["matched_by"] = hit.get("matched_by", [])
            out.append(rec)
        return out

    def list_by_kind(self, kind: str, limit: int = 50) -> list[dict[str, Any]]:
        """按类型精确列出记忆（官方 /v1/atomic-memory/list）。

        若服务不支持该端点（如旧版本/兼容实现），回退为文本前缀检索。
        """
        scope = self.ensure_scope()
        try:
            resp = _post(
                "/v1/atomic-memory/list",
                {"scope_id": scope, "kind": kind,
                 "states": ["active"], "limit": limit},
            )
            return [self._record(m) for m in resp.get("items", [])]
        except RuntimeError:
            return self.search(PREFIX.get(kind, kind), limit=limit)

    def prepare(self, query: str, max_bytes: int = 4000) -> dict[str, Any]:
        """为一次交互准备有界上下文（官方 PreparedContext）。"""
        scope = self.ensure_scope()
        resp = _post(
            "/v1/context/prepare",
            {"scope_id": scope, "query": query, "max_bytes": max_bytes},
        )
        return {
            "status": resp.get("status"),
            "content": resp.get("content"),
            "content_bytes": resp.get("content_bytes", 0),
            "server": config.PC_BASE_URL,
        }

    # ------------------------------------------------------------------
    # 证据（Source journal）
    # ------------------------------------------------------------------
    def record_source(self, source_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        scope = self.ensure_scope()
        payload: dict[str, Any] = {
            "scope_id": scope,
            "source_id": source_id,
            "content": content,
        }
        if metadata is not None:
            payload["metadata"] = metadata
        resp = _post("/v1/sources/content", payload)
        return {"scope_id": scope, "source_id": source_id, "response": resp}

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        try:
            with urlopen(f"{config.PC_BASE_URL}/health/live", timeout=2) as resp:
                return {"ok": resp.status == 200, "url": config.PC_BASE_URL}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "url": config.PC_BASE_URL, "error": str(e)}


def parse_meta(text: str) -> dict[str, str]:
    """从记忆文本中解析 `key=value` 结构化后缀。"""
    meta: dict[str, str] = {}
    if " | " in text:
        head, _, tail = text.partition(" | ")
        for part in tail.split(" | "):
            if "=" in part:
                k, _, v = part.partition("=")
                meta[k.strip()] = v.strip()
        return meta
    return {}


def strip_meta(text: str) -> str:
    """去掉结构化后缀，还原可读正文。"""
    if " | " in text:
        return text.split(" | ", 1)[0]
    return text
