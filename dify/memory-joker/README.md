# AI 记忆梗王 · 记忆大考验（AI Memory Joker）

> **Dify Chatflow + PowerContext · 跨会话记忆挑战游戏**
> 
> 评审入口：先读本文件 → 按 `run.md` 启动服务 → 按 `samples/verify.md` 体验

---

## 🎯 作品简介

一个有胜负判定的**跨会话记忆挑战游戏**：

1. **闲聊存梗**：随便聊点什么（喜好、吐槽、冷笑话）→ PowerContext 记住
2. **发起挑战**：输入「考我」→ AI 从记忆里出 3 道填空题
3. **答题判分**：AI 逐题对比你的回答 vs 记忆原始内容 → ✅❌ + 得分 + 爆梗吐槽
4. **跨会话验证**：开新对话 → AI 还能出题考你（PowerContext 不丢记忆）

## 🏗 技术架构

```
┌─────────────────────────────────────────────────┐
│                   Dify Chatflow                  │
│                                                  │
│  Start → HTTP召回 → LLM核心 → Answer (给用户)    │
│              ↑                    │              │
│              │                    ▼              │
│              └── HTTP回写 ← Code解析得分         │
└─────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────────────┐
│          PowerContext Server (本项目自带)         │
│                                                  │
│  GET  /api/v1/memories/search  ← 召回记忆        │
│  POST /api/v1/memories/remember ← 写入记忆       │
│  SQLite + LIKE 匹配，scope=user-{user_id} 隔离   │
└─────────────────────────────────────────────────┘
```

## 📁 文件结构

```
dify/memory-joker/
├── README.md                     ← 本文件（评审入口）
├── run.md                        ← 完整部署指南
├── start.sh / start.ps1           ← 一键启动 PowerContext
├── memory-joker-chatflow.yml     ← Dify Chatflow DSL（导入即用）
├── powercontext/
│   ├── server.py                 ← 轻量 PowerContext 兼容服务
│   ├── requirements.txt           ← Python 依赖
│   └── start.py                  ← Python 一键启动
└── samples/
    └── verify.md                 ← 5 步验证脚本（含截图位置）
```

## 🚀 3 步启动

### Step 1 — 启动 PowerContext Server

```bash
# Linux / macOS
cd dify/memory-joker && bash start.sh

# Windows PowerShell
cd dify/memory-joker && powershell -ExecutionPolicy Bypass -File start.ps1
```

看到 `[PowerContext] Listening on http://0.0.0.0:8000` 即为成功。

### Step 2 — 导入 Dify DSL

1. Dify 控制台 → 工作室 → 创建应用 → 导入 DSL
2. 选择 `dify/memory-joker/memory-joker-chatflow.yml`
3. 检查 HTTP 节点 URL → 默认 `http://localhost:8000`（正确无需改）
4. **发布**

### Step 3 — 按 `samples/verify.md` 体验

5 步完整验证脚本，每步带 PowerContext API curl 验证 + 截图位置。

## 🔑 技术要求对应

| 要求 | 本项目实现 |
|---|---|
| ✅ Dify（必选） | Chatflow 6 节点：Start → HTTP → LLM → Answer → Code → HTTP |
| ✅ PowerContext（至少一种） | 对话记忆持久化 + 跨会话召回（scope=user-{user_id}） |
| ✅ 游戏性（评审关注） | 闲聊/挑战/答题判分 三种模式 + 逐题 ✅❌ + 累计得分 + 爆梗吐槽 |
| ✅ 跨会话记忆验证 | 换 Dify 新对话仍能召回（verify.md Step 5） |

## 📊 判题回路（游戏核心）

```
用户发起挑战 "考我"
        ↓
PowerContext.search(query=闲聊关键词, scope=user-{id})
        ↓
LLM 从召回的记忆中抽 3 条事实 → 出填空题
        ↓
用户作答
        ↓
LLM 逐题对比 "用户回答" vs "PowerContext 原始记忆内容"
        ↓
✅ 语义正确 → +1 分
❌ 错误 → 爆梗吐槽
        ↓
Code 节点正则提取 "本轮得分：X / 3" → conversation_variables → PowerContext.metadata
```

## ⚠️ 前置条件

- Python 3.10+（PowerContext Server）
- Dify 0.6.1+（Chatflow 支持 conversation_variables）
- LLM Provider 已配置（GPT-4o-mini 或同级别，需支持中文）
- **HTTP Request 插件**（Dify 内置，DSL 已声明依赖）

## 🛠 故障排查

| 现象 | 解决 |
|---|---|
| HTTP 节点连接失败 | 检查 PowerContext 是否启动在 8000 端口 |
| 挑战模式说"还没告诉我太多事" | 先做 Step 2 闲聊，再挑战；或用 curl 手动写一条记忆 |
| 判题全判错 | 检查 scope 是否匹配（Dify 传 `user-{sys.user_id}`） |
| `conversation_variables` 不更新 | Dify 版本过低 → 0.6+ 才支持 |

---

**详细说明见 `run.md`，验证脚本见 `samples/verify.md`**
