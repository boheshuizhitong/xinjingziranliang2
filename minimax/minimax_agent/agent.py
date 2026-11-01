"""MiniMax 集成代理：基于 SDD 上下文完成业务工程代码修改

流程：
  1) 读取上下文模块组装的任务上下文（context_module.engine）；
  2) 把上下文 + 当前 catalog.py 源码交给 MiniMax（OpenAI 兼容端点）；
  3) MiniMax 返回修改后的完整 catalog.py（v2）；
  4) 代理校验语法、写回文件，并用 difflib 生成修改前后差异；
  5) 把「任务上下文 + 提示词 + 模型回复 + 差异 + 测试结果」写入 docs/minimax-dev-log.jsonl，
     作为 MiniMax 实际参与的开发记录。
"""
from __future__ import annotations

import difflib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = BASE_DIR / "business_app" / "catalog.py"
DEV_LOG_PATH = BASE_DIR / "docs" / "minimax-dev-log.jsonl"
ENV_PATH = BASE_DIR / ".env"


def load_env() -> dict[str, str]:
    """读取 minimax/.env（不提交仓库），键：MINIMAX_API_KEY、MINIMAX_BASE_URL、MINIMAX_MODEL。"""
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def minimax_chat(messages: list[dict[str, str]], temperature: float = 0.3,
                 max_tokens: int = 4000) -> dict[str, Any]:
    """调用 MiniMax 文本模型（OpenAI 兼容）。"""
    env = load_env()
    api_key = os.environ.get("MINIMAX_API_KEY") or env.get("MINIMAX_API_KEY")
    base_url = os.environ.get("MINIMAX_BASE_URL") or env.get("MINIMAX_BASE_URL") or "https://api.minimax.cn/v1"
    model = os.environ.get("MINIMAX_MODEL") or env.get("MINIMAX_MODEL") or "MiniMax-Text-01"
    if not api_key:
        raise RuntimeError("未配置 MINIMAX_API_KEY（请写入 minimax/.env）")
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"MiniMax API {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    return {"model": model, "text": data["choices"][0]["message"]["content"],
            "usage": data.get("usage"), "raw": data}


def build_prompt(task: str, context_text: str, current_code: str) -> list[dict[str, str]]:
    system = (
        "你是资深软件工程师，正在按规格驱动开发（SDD）完成一次代码修改。"
        "下面给出了开发任务、适用的规格、需修改的代码与验证测试。"
        "请只修改必要的代码以实现任务目标，严格保持规格中'保持不变'的既有行为。"
        "直接输出修改后的完整 catalog.py 文件内容（Python 代码，不要解释，不要用代码围栏）。"
    )
    user = (
        f"## 开发任务\n{task}\n\n"
        f"## 开发上下文\n{context_text}\n\n"
        f"## 当前 catalog.py\n```python\n{current_code}\n```\n\n"
        "请输出修改后的完整 catalog.py。"
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def _extract_code(reply: str) -> str:
    """从模型回复中提取 Python 代码（去掉可能出现的 ```python 围栏）。"""
    s = reply.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
    if "```" in s:
        s = s.split("```")[0]
    return s.strip("\n") + "\n"


def make_diff(before: str, after: str, path: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}"))


def run_modification(task: str, context_text: str, apply: bool = True,
                     save_log: bool = True) -> dict[str, Any]:
    """用 MiniMax 完成一次代码修改。返回上下文、提示词、回复、差异与测试信息。"""
    current = CATALOG_PATH.read_text(encoding="utf-8")
    messages = build_prompt(task, context_text, current)
    result = minimax_chat(messages)
    new_code = _extract_code(result["text"])
    diff = make_diff(current, new_code, "business_app/catalog.py")

    # 语法校验
    compile(new_code, str(CATALOG_PATH), "exec")

    record: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task": task,
        "context": context_text,
        "prompt": messages,
        "model": result["model"],
        "usage": result.get("usage"),
        "reply": result["text"],
        "diff": diff,
        "applied": False,
    }
    if apply:
        CATALOG_PATH.write_text(new_code, encoding="utf-8")
        record["applied"] = True

    if save_log:
        DEV_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEV_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    record["new_code"] = new_code
    return record
