"""中文文本嵌入（基于 seekdb 官方 pyseekdb 的 ONNX 运行时，本地 CPU）

向量化是可选的增强能力：若模型不可用（离线/下载失败），返回 None，
上层自动回退到纯全文/关键词检索，保证评审在无网络环境下仍可复现。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from . import config as cfg

_cached_ef: Any = None
_available: Optional[bool] = None


def embedding_available() -> bool:
    """探测嵌入是否可用（首次调用会触发模型加载）。"""
    global _available
    if _available is None:
        try:
            _ensure_ef()
            _available = True
        except Exception:  # noqa: BLE001
            _available = False
    return _available


def _ensure_ef() -> Any:
    global _cached_ef
    if _cached_ef is None:
        from pyseekdb.utils.embedding_functions.onnx_embedding_function import (
            OnnxEmbeddingFunction,
        )
        _cached_ef = OnnxEmbeddingFunction(
            model_name=cfg.EMBED_MODEL_NAME,
            hf_model_id=cfg.EMBED_HF_ID,
            dimension=cfg.EMBED_DIM,
        )
    return _cached_ef


def embed_text(text: str) -> Optional[list[float]]:
    """返回向量列表；模型不可用时返回 None。"""
    if not embedding_available():
        return None
    try:
        return _ensure_ef()([text])[0]
    except Exception:  # noqa: BLE001
        _available = False
        return None


def embed_query(question: str) -> Optional[list[float]]:
    if embed_text is None:
        return None
    q = cfg.QUERY_INSTRUCTION + question
    return embed_text(q)


def to_vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
