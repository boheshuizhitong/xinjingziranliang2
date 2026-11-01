# SDD 上下文管理系统 —— 运行说明（run.md）

## 1. 运行环境

| 项 | 要求 | 说明 |
| --- | --- | --- |
| 操作系统 | Windows 10/11、Linux、macOS | 已在 Windows 11 实测 |
| Python | 3.11 ~ 3.13 | 3.13 实测通过 |
| 网络 | 首次运行需联网 | 仅用于：下载中文嵌入模型（约 90MB，之后离线）、调用 MiniMax |
| 依赖 | 见 `requirements.txt` | `pip install -r requirements.txt` |
| MiniMax 密钥 | 必需 | 用于「MiniMax 实际参与」验收；写入本地 `.env`，不提交仓库 |

## 2. 依赖安装

```bash
# Windows（PowerShell）
python -m pip install -r requirements.txt

# Linux / macOS
python3 -m pip install -r requirements.txt
```

依赖说明：

| 包 | 作用 |
| --- | --- |
| `fastapi` / `uvicorn` | Web 服务（PowerContext 兼容服务器） |
| `pylibseekdb` | **seekdb** 嵌入式原生绑定（本地数据库引擎） |
| `pymysql` | 通过 MySQL 协议连接 seekdb 并执行 SQL（向量/全文/标量） |
| `pyseekdb` | **seekdb** 高层客户端（本项目使用其 ONNX 中文嵌入能力） |
| `pytest` | 业务工程测试 |
| `requests` | MiniMax API 调用 |

## 3. 配置 MiniMax 密钥

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入：
#   MINIMAX_API_KEY=<你的密钥>          # platform.minimaxi.com -> API管理 -> API Key -> 创建密钥
#   MINIMAX_BASE_URL=https://api.minimax.cn/v1
#   MINIMAX_MODEL=<可用模型>            # 如 MiniMax-Text-01 / MiniMax-M1 / abab6.5s-chat
```

`.env` 已被 `.gitignore` 忽略，绝不提交仓库。

## 4. 启动与验证

### 4.1 一键启动（推荐）

```powershell
.\start.ps1
```

脚本自动：建虚拟环境 → 装依赖 → 启动 PowerContext（兼容实现，端口 8010）→
导入工程资料到 seekdb → 运行验收验证样例（`samples/verify.py --reset`）。

### 4.2 分步启动（手动控制）

```bash
# 终端 1：PowerContext 记忆服务（兼容实现，端口 8010）
python pc_server/server.py

# 终端 2：导入工程资料到 seekdb + 运行完整验证
python -m context_module --import --clear
python samples/verify.py --reset
```

### 4.3 使用官方 PowerContext Server（可选，效果相同）

上下文模块只依赖 PowerContext 公开 HTTP 契约，可直接对接官方服务：

```bash
uv tool install --force "powercontext[cli,server] @ git+https://github.com/oceanbase/powercontext.git@master"
powercontext server run --host 127.0.0.1 --port 8000
# 另开终端，指定地址
set POWERCONTEXT_URL=http://127.0.0.1:8000   # Windows PowerShell
python samples/verify.py --reset
```

## 5. 上下文模块调用入口（输入/输出）

```bash
# 输入：任务描述；输出：适用规格、需修改代码、验证测试、任务状态（文本）
python -m context_module "为商品查询增加价格区间筛选，并校验边界输入" --task-id task-001

# 结构化 JSON 输出
python -m context_module "为商品查询增加价格区间筛选" --json

# 仅导入工程资料
python -m context_module --import
python -m context_module --import --clear   # 清空后重新导入

# 把本次任务状态写入 PowerContext
python -m context_module "任务描述" --save
```

输出结构（JSON）字段：

| 字段 | 含义 |
| --- | --- |
| `materials.specs` | 适用的规格条目（含 `source` 真实来源、`content`） |
| `materials.code` | 需修改的代码文件（含 `source`） |
| `materials.tests` | 用于验证功能与兼容性的测试（含 `source`） |
| `state.done / todo / verification` | 已完成事项、待办事项、已有验证结果（来自 PowerContext） |
| `database` | seekdb 检索引擎、向量是否启用、命中信号 |

## 6. MiniMax 参与方式与版本

- **方式**：OpenAI 兼容 HTTP API（`POST {MINIMAX_BASE_URL}/chat/completions`），
  由 `minimax_agent/agent.py` 驱动。
- **流程**：上下文模块组装任务上下文（规格+代码+测试+状态）→ 作为提示词交给 MiniMax →
  MiniMax 输出修改后的 `catalog.py` → 语法校验 → 写回 → 生成差异。
- **版本**：模型名由 `.env` 的 `MINIMAX_MODEL` 指定；每次调用的模型与用量记录在
  `docs/minimax-dev-log.jsonl`。
- **记录**：每次修改的上下文、提示词、模型回复、差异、应用结果逐条入库。

## 7. seekdb 参与方式与版本

- **方式**：嵌入式 `pylibseekdb` 本地启动 + `pymysql` 走 MySQL 协议执行 SQL。
- **存储**：`data/seekdb` 中 `materials` 表（mtype=spec/code/test，含 `VECTOR(512)` 向量列
  与 `FULLTEXT`(ik) 全文索引）。
- **检索**：向量 + 全文双路召回 + RRF 融合；向量模型不可用时自动回退全文检索。
- **版本**：`pylibseekdb` 1.4.0.post2、`pyseekdb` 1.4.0.post1、`pymysql` 1.2.3。

## 8. 数据位置

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| seekdb 工程资料库 | `data/seekdb` | 规格/代码/测试 + 向量 + 全文索引 |
| PowerContext 记忆 | `data/powercontext.db` | 已完成/待办/验证结果（兼容实现） |
| Scope ID | `data/powercontext_scope_id.txt` | 记住当前任务状态域 |
| MiniMax 开发记录 | `docs/minimax-dev-log.jsonl` | 每次修改的上下文/提示/回复/差异 |

## 9. 重置（评审重复验证用）

```bash
python samples/verify.py --reset
# 恢复：v1 代码（snapshots/catalog_v1_before.py）+ 清空 seekdb + 新建空 Scope
```

## 10. 已知限制

- 嵌入模型首次需联网下载（约 90MB），下载慢可设 `HF_ENDPOINT=https://hf-mirror.com`；
  模型不可用时上下文模块自动退化为全文检索，验收不受影响。
- MiniMax 实际修改依赖 `MINIMAX_API_KEY`；未配置时 `verify.py --skip-minimax`
  只验证基础设施（P1/P2/P3/P6）。
- 上下文模块输出中的来源均为真实文件路径，可复核；不返回固定答案，规格更新后
  重新导入即使用新内容。
