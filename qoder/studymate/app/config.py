"""学伴 StudyMate 全局配置"""
from __future__ import annotations

import os
from pathlib import Path

# 项目根目录（app/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Web 应用
# ---------------------------------------------------------------------------
APP_HOST = os.environ.get("STUDYMATE_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("STUDYMATE_PORT", "8080"))

# ---------------------------------------------------------------------------
# seekdb（嵌入式知识库）
# ---------------------------------------------------------------------------
SEEKDB_PATH = os.environ.get("STUDYMATE_SEEKDB", str(DATA_DIR / "seekdb"))
# 中文嵌入模型（首次使用会从 HuggingFace 镜像下载，之后本地缓存）
EMBED_MODEL_NAME = os.environ.get("STUDYMATE_EMBED_MODEL", "bge-small-zh-v1.5")
EMBED_HF_ID = "Xenova/bge-small-zh-v1.5"
EMBED_DIM = 512
# bge 中文模型检索指令（提升查询向量质量）
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

# ---------------------------------------------------------------------------
# PowerContext（记忆服务）
# ---------------------------------------------------------------------------
# 默认连接本仓库自带的兼容实现（pc_server/server.py，端口 8010）。
# 若已部署官方 PowerContext Server，设置环境变量 POWERCONTEXT_URL 指向它即可无缝切换。
PC_BASE_URL = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8010")
PC_TOKEN = os.environ.get("POWERCONTEXT_TOKEN", "")
# 每个用户一个 Scope；demo 默认用户标识
PC_SCOPE_TITLE = os.environ.get("STUDYMATE_SCOPE", "studymate-user-001")
PC_SCOPE_ID_FILE = DATA_DIR / "powercontext_scope_id.txt"
PC_TIMEOUT = 5

# 记忆条目类型
KIND_WEAK_POINT = "weak_point"      # 薄弱知识点
KIND_PROGRESS = "progress"          # 复习进度
KIND_PREFERENCE = "preference"      # 学习偏好
KIND_FACT = "fact"                  # 用户事实
