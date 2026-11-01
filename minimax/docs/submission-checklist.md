# 提测材料清单（docs/submission-checklist.md）

> 对照赛题《规有所依——面向软件持续演进的 SDD 上下文管理系统》验收标准逐项核对。
> 提交前打开本文件逐项确认。

## 1. 代码仓库

- 仓库：`https://github.com/boheshuizhitong/xinjingziranliang2`
- 分支：`2026-competition-ecosystem`（赛事要求基于该分支/commit 开发）
- 项目目录：`minimax/`

## 2. 完整源码（context_module 必做项：能够运行）

- [x] 上下文模块：`context_module/`（CLI 入口 `python -m context_module`）
- [x] Agent 接入：`minimax_agent/agent.py`
- [x] 业务工程：`business_app/`（可运行、带 pytest）
- [x] PowerContext 兼容服务：`pc_server/server.py`
- [x] 配套程序：`start.ps1`、`requirements.txt`

## 3. 运行说明（run.md）

- [x] 依赖版本、配置步骤（.env）、数据初始化（--import --clear）
- [x] 调用入口（CLI 输入/输出）、测试命令、已知限制

## 4. 验证样例（samples/）

- [x] `samples/verify.md`：任务描述、有效规格、初始数据、操作步骤、预期结果、重置方法
- [x] `samples/verify.py`：可执行、`--reset` 保证可复现
- [x] `samples/test_logs/`：修改前/后 pytest 日志、MiniMax 差异

## 5. 代码与测试

- [x] 修改前后代码快照：`business_app/snapshots/catalog_v1_before.py`、`catalog_v2_after.py`
- [x] 代码差异：`samples/test_logs/minimax_modification.diff`
- [x] 新增功能测试 + 回归测试：`business_app/tests/test_catalog.py`
- [x] 测试日志（含命令、退出码、代码版本）：`samples/test_logs/`

## 6. 技术使用记录

- [x] MiniMax 开发记录：`docs/minimax-dev-log.jsonl`（上下文/提示/回复/差异/用量）+ `docs/minimax-dev-log.md`
- [x] 数据库查询记录：`samples/test_logs/`（seekdb stats、检索信号）
- [x] PowerContext 状态写入与复用记录：`docs/` + verify 输出
- [x] 一页技术说明：`docs/one-page-tech-note.md`

## 7. 必做验收项自检

| 验收项 | 自检 |
| --- | --- |
| 能够运行 | 按 run.md 从零初始化、启动、执行样例 |
| MiniMax 实际参与 | dev-log 包含本次任务、上下文、修改过程，与差异对应 |
| 上下文正确 | 输出含规格/代码/测试来源；规格更新重导后用新内容 |
| 数据库实际参与 | seekdb 保存资料/索引，查询结果用于上下文 |
| 状态能够复用 | 空状态保存 → 重启读取并用于后续 |
| 代码修改有效 | 目标测试改前失败、改后通过；回归通过 |

## 8. 提交前自检

- [ ] `.env` 不提交（已 gitignore），配置为占位值
- [ ] 无真实凭据
- [ ] `python samples\verify.py --reset` 全绿（配置 MINIMAX_API_KEY 后）
- [ ] 已推送最新提交
