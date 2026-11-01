"""业务工程：商品目录查询服务（v1，修改前基线）

当前只支持按 `category` 与 `in_stock_only` 两个条件过滤商品。

本次开发任务（参见 specs/product_spec_v2.md）将新增：
  - min_price / max_price 价格区间筛选；
  - 边界输入校验（负数、min>max 抛 ValueError）。
该修改由 MiniMax 基于上下文模块提供的开发上下文完成。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class Product:
    """商品。price/stock 均为非负（规格不变式）。"""
    id: int
    name: str
    category: str
    price: float
    in_stock: bool
    stock: int


def search_products(
    products: Iterable[Product],
    category: Optional[str] = None,
    in_stock_only: bool = False,
) -> list[Product]:
    """按条件筛选商品。

    过滤语义（规格 v1，见 specs/product_spec_v1.md）：
      - category 指定时，仅保留该分类商品；
      - in_stock_only=True 时，仅保留 in_stock 为真且 stock>0 的商品；
      - 未指定条件时返回全部商品；
      - 结果保持输入顺序，不修改输入。
    """
    result: list[Product] = []
    for p in products:
        if category is not None and p.category != category:
            continue
        if in_stock_only and not (p.in_stock and p.stock > 0):
            continue
        result.append(p)
    return result
