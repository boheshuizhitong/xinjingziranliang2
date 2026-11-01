# 一页技术说明（docs/one-page-tech-note.md）

## 1. 模块结构

```
业务工程(business_app)         上下文模块(context_module)        开发助手(minimax_agent)
┌───────────────┐   导入    ┌──────────────────────────┐  上下文  ┌────────────────┐
│ catalog.py    │ ────────► │ seekdb_store(资料库/检索)  │ ───────► │ agent.py       │
│ server.py     │           │ engine(上下文组装)         │          │ (MiniMax 生成) │
│ specs/*.md    │           │ powercontext_client(状态)  │ ◄─────── │ 修改后的代码    │
│ tests/*.py    │           └──────────────────────────┘  状态复用  └────────────────┘
└───────────────┘                   │
                              seekdb(存储) + PowerContext(记忆)
```

## 2. 上下文选择方式

给定任务描述，上下文模块在 **seekdb** 中做**向量 + 全文混合检索**（RRF 融合），
召回并分组输出三部分：**适用规格**（spec）、**需修改代码**（code）、**验证测试**（test）；
再从 **PowerContext** 读取任务状态（done/todo/verification）。输出以来源字段保证真实可查。

## 3. 各项技术的分工

| 技术 | 分工 | 证据位置 |
| --- | --- | --- |
| **MiniMax** | 依据上下文生成并应用代码修改（catalog.py v1→v2），生成差异 | `docs/minimax-dev-log.jsonl`、`samples/test_logs/minimax_modification.diff` |
| **seekdb** | 存储规格/代码/测试及向量/全文索引，检索结果构造上下文 | `context_module/seekdb_store.py`、检索日志 `samples/test_logs/` |
| **PowerContext** | 保存任务进展与验证结果，重启后读取复用 | `context_module/powercontext_client.py`、状态日志 |

## 4. 一次 SDD 闭环

规格导入 seekdb → 按任务检索出上下文 → 交给 MiniMax 改代码 →
目标/回归测试验证（改前失败、改后通过）→ 结果写入 PowerContext → 重启复用。
