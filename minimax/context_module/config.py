"""SDD 上下文管理系统 —— 配置"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # minimax/
DATA_DIR = BASE_DIR / "data"
SEEKDB_PATH = DATA_DIR / "seekdb"                         # seekdb 工程资料库文件

# ---- 业务工程路径（导入规格/代码/测试的扫描根）----
BUSINESS_APP_DIR = BASE_DIR / "business_app"
SPEC_DIR = BASE_DIR / "business_app" / "specs"

# ---- PowerContext 记忆服务 ----
PC_BASE_URL = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8010")
PC_TOKEN = os.environ.get("POWERCONTEXT_TOKEN", "")
PC_TIMEOUT = float(os.environ.get("POWERCONTEXT_TIMEOUT", "8"))
PC_SCOPE_ID_FILE = DATA_DIR / "powercontext_scope_id.txt"
PC_SCOPE_TITLE = "SDD 上下文管理系统 · 任务状态"

# ---- 记忆类型 ----
KIND_TASK_STATE = "task_state"        # 任务整体状态（完成度）
KIND_TODO = "todo"                    # 待办事项
KIND_DONE = "done"                    # 已完成事项
KIND_VERIFICATION = "verification"    # 验证结果

# ---- 嵌入模型（seekdb 官方 pyseekdb ONNX，本地 CPU）----
EMBED_MODEL_NAME = "bge-small-zh-v1.5"
EMBED_HF_ID = "Xenova/bge-small-zh-v1.5"
EMBED_DIM = 512
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

# ---- 上下文模块 ----
CONTEXT_OUTPUT_TOP_K = 6     # 每种类型（spec/code/test）默认返回条数
