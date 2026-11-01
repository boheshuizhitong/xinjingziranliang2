# 规有所依 —— 面向软件持续演进的 SDD 上下文管理系统

> **MiniMax × OceanBase** 赛道参赛作品。
> 用 **MiniMax** 参与实际代码修改，结合 **seekdb**（工程资料检索）与
> **PowerContext**（任务状态复用），实现一个规格驱动开发（SDD）的上下文模块。

## 一、解决什么问题

AI 开发助手修改代码时，需要知道：**当前该遵守哪些要求**（规格）、**该改哪些代码**、
**如何验证结果**（测试），以及**任务进行到哪了**（状态）。资料分散、规格变化或任务中断，
都容易导致遗漏约束、使用过时信息或重复工作。

本作品围绕一次真实开发任务，把这些收进一个可复现的上下文模块：

1. **导入**任务涉及的规格 / 代码 / 测试资料到 seekdb（混合检索）；
2. **选择**与任务相关的资料，形成开发上下文（定位到具体规格条目、代码文件、测试）；
3. **交给**使用 MiniMax 的开发助手，完成一次实际代码修改；
4. **运行**功能与回归测试验证修改结果；
5. **保存**任务状态到 PowerContext，重启上下文模块后能读取并复用。

## 二、本次开发任务（验证样例的核心）

业务工程为「商品目录查询服务」（`business_app/catalog.py`，自带 pytest 测试）。
本次局部修改（规格 v2）：为 `search_products` **新增价格区间筛选**（min_price / max_price）
并**校验边界输入**（负数、min>max 抛 `ValueError`）。

- **要改什么**：`search_products` 增加价格区间过滤逻辑与输入校验（由 MiniMax 完成）。
- **哪些原有行为必须保持**：`category`、`in_stock_only` 过滤、返回顺序、不修改输入。

同一组目标功能测试：修改前因该行为未实现而失败（8 个目标测试失败），修改后全部通过；
5 个回归测试全程保持通过。

## 三、技术分工（评审核对用）

| 组件 | 在作品中做什么 | 关键技术 |
| --- | --- | --- |
| **MiniMax**（必选） | 参与本次代码生成/修改：根据上下文把 catalog.py 从 v1 改到 v2，生成差异并应用 | OpenAI 兼容端点 `https://api.minimax.cn/v1`，开发记录见 `docs/minimax-dev-log.jsonl` |
| **seekdb**（必选其一） | 存储并检索工程资料（规格/代码/测试），检索结果用于构造任务上下文 | 嵌入式 `pylibseekdb`；`VECTOR(512)` + `FULLTEXT`(ik 中文分词)，双路召回 + RRF 融合 |
| **PowerContext**（必选其一） | 保存任务进展（已完成/待办/验证结果），重启后读取并复用 | 官方 HTTP 契约（`/v1/scopes`、`/v1/memory/remember`、`/v1/atomic-memory/list`、`/v1/context/prepare`） |
| 上下文模块 | 给定任务输出适用规格、需修改代码、验证测试、任务状态 | CLI（`python -m context_module`）+ 结构化 JSON |

> PowerContext 使用官方 Server（`POWERCONTEXT_URL` 指向 8000）或本仓库自带兼容实现
> （`pc_server/server.py`，SQLite，端口 8010），行为一致，评审可离线复现。

## 四、快速开始

```powershell
# 1) 配置 MiniMax 密钥（不提交仓库）
Copy-Item .env.example .env   # 然后编辑 .env 填入 MINIMAX_API_KEY

# 2) 一键启动 + 完整验证（建 venv、装依赖、起 PowerContext、导入资料、跑样例）
.\start.ps1

# 或分步：
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python pc_server\server.py &      # 终端1：PowerContext 8010
.\.venv\Scripts\python samples\verify.py --reset   # 终端2：完整验收验证
```

分步说明、配置项、数据位置与重置见 **[run.md](run.md)**。

## 五、验证样例（评审复现）

```powershell
.\.venv\Scripts\python samples\verify.py --reset
```

覆盖 6 项必做验收：

| 验证点 | 通过条件 |
| --- | --- |
| P1 | 规格更新（v1→v2）并重新导入后，上下文模块使用更新后的内容 |
| P2 | seekdb 实际存储/检索规格、代码、测试，查询结果含真实来源与命中信号 |
| P3 | 修改前目标功能测试因行为未实现而失败、回归测试通过 |
| P4 | MiniMax 实际参与代码修改（生成差异并应用，见 dev-log） |
| P5 | 修改后目标功能测试 + 回归测试全部通过 |
| P6 | 从空状态保存任务记录，重启模块后能读取并复用 |

样例说明见 **[samples/verify.md](samples/verify.md)**；实测日志见 `samples/test_logs/`。

## 六、项目结构

```
minimax/
├─ README.md                 # 本文件：评审入口
├─ run.md                    # 运行说明
├─ requirements.txt          # 依赖
├─ start.ps1                 # 一键启动
├─ .env.example              # MiniMax 密钥配置模板（.env 被 gitignore）
├─ business_app/             # 业务工程：商品目录查询服务（可运行、带 pytest）
│  ├─ catalog.py             #   核心逻辑（v1 -> v2，由 MiniMax 修改）
│  ├─ server.py              #   FastAPI 接口
│  ├─ specs/                 #   规格 v1 / v2（SDD 的"规"）
│  ├─ snapshots/             #   v1_before / v2_after 快照（代码差异来源）
│  └─ tests/test_catalog.py  #   目标功能测试 + 回归测试
├─ context_module/           # SDD 上下文模块（CLI）
│  ├─ __main__.py            #   调用入口
│  ├─ engine.py              #   上下文组装（规格/代码/测试 + 状态）
│  ├─ seekdb_store.py        #   seekdb 工程资料库（存储+混合检索）
│  ├─ powercontext_client.py #   PowerContext 记忆读写
│  ├─ import_materials.py    #   规格/代码/测试导入
│  ├─ embedding.py           #   本地 ONNX 中文嵌入（可选，失败自动回退）
│  └─ config.py
├─ minimax_agent/agent.py    # MiniMax 集成：基于上下文生成并应用代码修改
├─ pc_server/server.py       # PowerContext 兼容实现（离线兜底，契约一致）
├─ samples/                  # 验证样例（verify.py / verify.md / 实测日志）
└─ docs/                     # minimax-dev-log（MiniMax 开发记录）/ 提交清单
```

## 七、提交材料索引

| 材料 | 位置 |
| --- | --- |
| 完整源码 | `minimax/` 下全部代码（上下文模块、Agent、业务工程、配套程序） |
| 运行说明 | [run.md](run.md) |
| 验证样例 | [samples/verify.md](samples/verify.md) + `samples/verify.py` + `samples/test_logs/` |
| 代码与测试 | `business_app/snapshots/`（修改前后快照）、`samples/test_logs/minimax_modification.diff`、pytest 前后日志 |
| 技术使用记录 | [docs/minimax-dev-log.md](docs/minimax-dev-log.md) + `docs/minimax-dev-log.jsonl`（MiniMax）、seekdb 检索记录、PowerContext 状态记录 |
| 一页技术说明 | [docs/one-page-tech-note.md](docs/one-page-tech-note.md) |

## 八、复现环境（已实测）

- Windows 11 + PowerShell，Python 3.13
- seekdb 嵌入式（`pylibseekdb` 1.4.0 + `pyseekdb` 1.4.0 + `pymysql`）
- 嵌入模型 `Xenova/bge-small-zh-v1.5`（ONNX，首次联网下载后离线，不可用时自动回退全文检索）
- PowerContext：仓库自带兼容实现（离线）或官方 Server
- MiniMax：OpenAI 兼容端点
