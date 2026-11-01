# MiniMax 开发记录（docs/minimax-dev-log.md）

> 本文档汇总 **MiniMax 实际参与代码修改** 的证据（验收项「MiniMax 实际参与」）。
> 逐条原始记录（任务上下文、提示词、模型回复、差异、用量）见 `docs/minimax-dev-log.jsonl`。

## 1. 本次任务

为商品目录查询服务的 `search_products` 增加**价格区间筛选**（`min_price`/`max_price`）
并校验**边界输入**（负数、`min>max` 抛 `ValueError`），对应规格 `product_spec_v2.md`。

## 2. 提供给 MiniMax 的上下文

由上下文模块 `ContextEngine.build_context` 组装，包含：
- 适用规格：`business_app/specs/product_spec_v2.md`（价格区间筛选 + 校验要求）
- 需修改代码：`business_app/catalog.py`（v1 源码）
- 验证测试：`business_app/tests/test_catalog.py`（目标 8 项 + 回归 5 项）
- 任务状态：PowerContext 中已完成/待办/验证结果

## 3. 修改过程

1. `minimax_agent/agent.py` 把「任务 + 上下文 + 当前 catalog.py」组装成提示词；
2. 调用 MiniMax（OpenAI 兼容端点，模型见 dev-log.jsonl）生成修改后的 catalog.py；
3. 语法校验 → 写回 `business_app/catalog.py`；
4. `difflib` 生成修改前后差异（见 `samples/test_logs/minimax_modification.diff`）。

## 4. 调用记录（来自 docs/minimax-dev-log.jsonl）

| 时间 | 模型 | 任务 | 用量 total_tokens | 生成 diff | 应用 | 测试 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-01 11:06:36 | MiniMax-Text-01 | 为商品查询增加价格区间筛选，并校验边界输入 | 2455 | 64 行 | ✅ | 修改后 13 passed |
| 2026-11-01 11:56:09 | MiniMax-Text-01 | 为商品查询增加价格区间筛选，并校验边界输入（验证复现） | 2423 | 59 行 | ✅ | 修改后 13 passed |

> 两条记录分别来自 `samples\verify.py --reset` 的两次完整复现；其中第一条为项目构建时的首次真实修改，
> 第二条为最终交付验证（`samples/test_logs/verify_output.txt`）所用。两条的 `diff` 均写入
> `docs/minimax-dev-log.jsonl`，并与 `business_app/snapshots/catalog_v2_after.py` 一致。

## 5. 与代码差异的对应

`docs/minimax-dev-log.jsonl` 中每条记录的 `diff` 字段与
`samples/test_logs/minimax_modification.diff`、`business_app/snapshots/catalog_v2_after.py`
一致；应用该 diff 后，目标功能测试由失败转为全部通过。

> 生成方式：`python -c "import sys;sys.path.insert(0,'.');from minimax_agent import agent; from context_module.engine import ContextEngine,format_context; c=ContextEngine().build_context('为商品查询增加价格区间筛选，并校验边界输入'); agent.run_modification('为商品查询增加价格区间筛选，并校验边界输入', format_context(c))"`
