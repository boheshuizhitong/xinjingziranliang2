"""业务工程 HTTP 接口（FastAPI）

对外提供商品查询接口 /api/products，封装 catalog.search_products。
展示"调整接口行为"：v2 支持 min_price/max_price 查询参数，非法输入返回 400。
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from business_app.catalog import Product, search_products

app = FastAPI(title="商品目录查询服务", version="2.0.0")

# 内置样例数据（与 tests 中的 _sample 一致）
SAMPLE_PRODUCTS = [
    Product(1, "机械键盘", "外设", 299.0, True, 5),
    Product(2, "无线鼠标", "外设", 129.0, True, 0),
    Product(3, "USB-C 数据线", "外设", 39.0, True, 20),
    Product(4, "4K 显示器", "显示", 1999.0, False, 3),
    Product(5, "27寸显示器", "显示", 1299.0, True, 8),
    Product(6, "旋转支架", "显示", 99.0, True, 12),
]


@app.get("/api/products")
def list_products(
    category: Optional[str] = None,
    in_stock_only: bool = False,
    min_price: Optional[float] = Query(default=None, ge=0),
    max_price: Optional[float] = Query(default=None, ge=0),
) -> dict:
    try:
        items = search_products(
            SAMPLE_PRODUCTS,
            category=category,
            in_stock_only=in_stock_only,
            min_price=min_price,
            max_price=max_price,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "count": len(items),
        "items": [p.__dict__ for p in items],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "business_app"}
