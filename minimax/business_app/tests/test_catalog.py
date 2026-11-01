"""业务工程测试套件：目标功能测试 + 回归测试。

设计说明：
- 目标功能测试（test_price_*）针对本次开发任务（规格 v2）新增的行为。
  在修改前（v1，catalog.py 不含 min_price/max_price 参数）它们会因
  TypeError（参数不存在）而失败——即"目标行为未实现而失败"；
  修改后（v2）全部通过。
- 回归测试（test_category_* 等）覆盖 v1 已有行为，修改后必须继续通过。

命令：在 minimax/ 根目录执行 `python -m pytest business_app/tests -v`
"""
from __future__ import annotations

import pytest

from business_app.catalog import Product, search_products


def _sample() -> list[Product]:
    """样例数据（6 件商品，覆盖各分类/库存/价格情形）。"""
    return [
        Product(1, "机械键盘", "外设", 299.0, True, 5),
        Product(2, "无线鼠标", "外设", 129.0, True, 0),      # in_stock=True 但库存 0
        Product(3, "USB-C 数据线", "外设", 39.0, True, 20),
        Product(4, "4K 显示器", "显示", 1999.0, False, 3),   # 未在售
        Product(5, "27寸显示器", "显示", 1299.0, True, 8),
        Product(6, "旋转支架", "显示", 99.0, True, 12),
    ]


# ---------------------------------------------------------------------------
# 目标功能测试（规格 v2：价格区间筛选 + 边界校验）——修改前应失败
# ---------------------------------------------------------------------------
def test_price_range_filter():
    """min_price/max_price 都指定时按区间过滤（39、1999、99 被排除）。"""
    out = search_products(_sample(), min_price=100.0, max_price=1500.0)
    assert [p.name for p in out] == ["机械键盘", "无线鼠标", "27寸显示器"]


def test_min_equals_max_boundary():
    """min_price == max_price 时返回价格恰好等于该值的商品（闭区间边界）。"""
    out = search_products(_sample(), min_price=129.0, max_price=129.0)
    assert [p.name for p in out] == ["无线鼠标"]


def test_only_min_price():
    """只给 min_price 时，上限不限制。"""
    out = search_products(_sample(), min_price=1300.0)
    assert [p.name for p in out] == ["4K 显示器"]


def test_only_max_price():
    """只给 max_price 时，下限不限制。"""
    out = search_products(_sample(), max_price=40.0)
    assert [p.name for p in out] == ["USB-C 数据线"]


def test_price_filter_combined_with_category():
    """价格筛选与既有 category 过滤叠加。"""
    out = search_products(_sample(), category="显示", min_price=100.0, max_price=1500.0)
    assert [p.name for p in out] == ["27寸显示器"]


def test_negative_min_price_rejected():
    """min_price < 0 必须抛 ValueError。"""
    with pytest.raises(ValueError):
        search_products(_sample(), min_price=-1.0)


def test_negative_max_price_rejected():
    """max_price < 0 必须抛 ValueError。"""
    with pytest.raises(ValueError):
        search_products(_sample(), max_price=-0.5)


def test_min_gt_max_rejected():
    """min_price > max_price 必须抛 ValueError。"""
    with pytest.raises(ValueError):
        search_products(_sample(), min_price=500.0, max_price=100.0)


# ---------------------------------------------------------------------------
# 回归测试（v1 已有行为，修改后必须继续通过）
# ---------------------------------------------------------------------------
def test_category_filter():
    out = search_products(_sample(), category="外设")
    assert [p.name for p in out] == ["机械键盘", "无线鼠标", "USB-C 数据线"]


def test_in_stock_filter():
    out = search_products(_sample(), in_stock_only=True)
    names = [p.name for p in out]
    assert "无线鼠标" not in names   # 库存为 0
    assert "4K 显示器" not in names  # 未在售
    assert len(out) == 4


def test_no_filter_returns_all():
    assert len(search_products(_sample())) == 6


def test_empty_result():
    assert search_products(_sample(), category="不存在") == []


def test_order_preserved():
    """结果保持输入顺序，且 id 唯一。"""
    out = search_products(_sample(), in_stock_only=True)
    ids = [p.id for p in out]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
