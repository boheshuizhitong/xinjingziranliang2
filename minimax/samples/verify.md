# 验证样例说明（samples/verify.md）

> 复现入口：在 `minimax/` 目录执行 `.\.venv\Scripts\python samples\verify.py --reset`

## 一、任务描述

业务工程「商品目录查询服务」的**本次开发任务**：

> 为 `search_products` 增加**价格区间筛选**（`min_price` / `max_price`），
> 并对**边界输入**做校验（负数、`min>max` 抛 `ValueError`）。

- **要改什么**：`business_app/catalog.py` 的 `search_products` 函数（由 MiniMax 修改）。
- **必须保持**：`category`、`in_stock_only` 过滤语义、结果顺序、不修改输入。

## 二、上下文中必须包含的来源（评审核对用）

| 类别 | 来源（真实文件） |
| --- | --- |
| 规格 | `business_app/specs/product_spec_v1.md`（基线）、`business_app/specs/product_spec_v2.md`（本次要求，含价格区间/校验） |
| 代码 | `business_app/catalog.py`、`business_app/server.py` |
| 测试 | `business_app/tests/test_catalog.py`（目标 8 项 + 回归 5 项） |

上下文模块输出中这些来源逐条给出（`materials.specs/code/tests` 的 `source` 字段）。

## 三、初始数据与操作步骤

| 步骤 | 操作 | 预期 |
| --- | --- | --- |
| 0 | `--reset` | 恢复到 v1 代码 + 空资料库 + 空 Scope（可复现） |
| 1 | 只导入 v1 规格 → 查询任务 | 上下文含 v1、不含"价格区间"要求（P1a） |
| 2 | 加入并重新导入 v2 规格 → 查询任务 | 上下文改用 v2（含 `min_price`/价格区间筛选）（P1b） |
| 3 | 查询 seekdb 资料库 | 已存 spec/code/test，命中信号真实（P2） |
| 4 | 运行 pytest（v1 代码） | 目标 8 项失败（行为未实现）、回归 5 项通过（P3） |
| 5 | MiniMax 依据上下文修改 catalog.py | 生成差异并应用，`min_price` 出现在代码中（P4） |
| 6 | 运行 pytest（修改后） | 13 项全部通过（P5） |
| 7 | 保存任务状态 → 新进程读取 | 空状态写入后能重启读取复用（P6） |

## 四、实测结果（本仓库已生成）

- 验证汇总：`samples/test_logs/verify_output.txt`（P1~P6 逐项 PASS/FAIL）
- 修改前测试：`samples/test_logs/pytest_BEFORE_modification.txt`（8 failed, 5 passed）
- 修改后测试：`samples/test_logs/pytest_AFTER_modification.txt`（13 passed）
- MiniMax 差异：`samples/test_logs/minimax_modification.diff`
- MiniMax 开发记录：`docs/minimax-dev-log.jsonl`（上下文/提示/回复/差异/用量）
- 修改前后代码快照：`business_app/snapshots/catalog_v1_before.py`、`business_app/snapshots/catalog_v2_after.py`

## 五、seekdb 作用证据

- 检索结果命中方式字段 `signal`（`semantic`/`keyword`/`both`）；
- `engine=seekdb-embedded`、`vector_enabled=true`（或回退 false）；
- 资料库统计 `stats`（spec/code/test 条数）。

## 六、PowerContext 作用证据

- 写入：`/v1/memory/remember` 返回 `changed:true`；
- 读取：`/v1/atomic-memory/list` 按 kind 列出 done/todo/verification；
- 复用：删除 scope 文件后（模拟重启/新环境）从空状态写入 → 新进程能读回。

## 七、重置方法

```bash
python samples/verify.py --reset
# 1) 恢复 catalog.py 为 v1（snapshots/catalog_v1_before.py）
# 2) 清空 seekdb materials
# 3) 删除 scope 文件，下次创建全新空 Scope
```

> 说明：运行中的 PowerContext 进程持有 SQLite 连接，重置不删除其数据库文件，
> 而是通过新建空 Scope 实现"从空状态开始"，避免破坏服务。
