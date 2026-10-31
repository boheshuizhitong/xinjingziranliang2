"""中文文本嵌入（基于 seekdb 官方 pyseekdb 的 ONNX 运行时，本地离线推理）"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import config

_cached_ef: Any = None


def get_embedding_function():
    """懒加载 ONNX 中文嵌入函数（bge-small-zh-v1.5，512 维，本地 CPU 推理）。

    首次使用会从 HuggingFace（默认 hf-mirror.com 镜像）下载约 90MB 模型，
    之后全部离线运行。模型缓存于 ~/.cache/pyseekdb/onnx_models/。
    """
    global _cached_ef
    if _cached_ef is None:
        from pyseekdb.utils.embedding_functions.onnx_embedding_function import (
            OnnxEmbeddingFunction,
        )

        _cached_ef = OnnxEmbeddingFunction(
            model_name=config.EMBED_MODEL_NAME,
            hf_model_id=config.EMBED_HF_ID,
            dimension=config.EMBED_DIM,
        )
    return _cached_ef


@lru_cache(maxsize=256)
def embed_text(text: str) -> list[float]:
    return get_embedding_function()([text])[0]


def embed_query(question: str) -> list[float]:
    """查询向量：加上 bge 中文检索指令前缀以获得更好的检索效果。"""
    return embed_text(config.QUERY_INSTRUCTION + question)


def to_vector_literal(vec: list[float]) -> str:
    """把向量列表转成 seekdb SQL 字面量：'[0.1,0.2,...]'"""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
