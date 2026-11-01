# 商品目录查询服务 —— 规格 v2（本次开发目标）

> 本版本在 **v1**（`product_spec_v1.md`）基础上，为查询新增「价格区间筛选」与
> 「边界输入校验」两项能力。这是本次开发任务要实现的规格更新。
> 上下文模块在导入 v2 后，构造的任务上下文必须使用本文件（而非 v1）中的要求。

## 新增查询规则 search_products(..., min_price=None, max_price=None)

在 v1 的 `category`、`in_stock_only` 参数之后，新增两个可选参数：

1. `min_price` 指定时，仅返回 `price >= min_price` 的商品。
2. `max_price` 指定时，仅返回 `price <= max_price` 的商品。
3. 同时指定时取两者交集。
4. `min_price == max_price` 时，返回价格恰好等于该值的商品（闭区间边界）。
5. 仅指定其一（如只给 `min_price`）时，另一侧不做限制。
6. `min_price`/`max_price` 接受 `int`/`float`，比较前统一转为 `float`。

## 新增校验（边界输入）

- `min_price < 0` 或 `max_price < 0`：抛出 `ValueError`，错误信息应包含是哪个参数非法。
- `min_price > max_price`：抛出 `ValueError`，提示区间下限不能大于上限。
- 非法输入必须在任何过滤之前立即抛出，不允许静默忽略。

## 保持不变（回归约束，v1 全部规则继续成立）

- `category` 过滤、`in_stock_only` 过滤语义不变。
- 未指定条件时返回全部商品，顺序保持不变。
- 不修改输入数据。
