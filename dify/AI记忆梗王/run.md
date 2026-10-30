# AI 记忆梗王 · 记忆大考验

> Dify Chatflow + PowerContext Server 打造的跨会话记忆挑战游戏

---

## 一、作品简介

### 玩法

🎯 **AI 记忆梗王** 是一个有**胜负判定**的对话记忆游戏。核心玩法：

1. **闲聊存梗**（输入："我超爱吃麻辣火锅"）
   → AI 正常回复 + 把对话存入 PowerContext
2. **发起挑战**（输入："考我" / "开始挑战"）
   → AI 从 PowerContext 召回你的历史记忆，出 3 道填空题
3. **答题判分**（输入：逐题作答）
   → AI 对比你的回答 vs PowerContext 原始记忆，**逐题打分** + 爆梗吐槽
4. **跨会话验证**（新开对话 → 输入："考我"）
   → PowerContext 不丢记忆，AI 还能出题考你上次说过什么

### 技术分工

| 组件 | 角色 | 具体能力 |
|---|---|---|
| **Dify Chatflow** | 核心流程编排 | 意图判断（闲聊/挑战/答题）、LLM 出题判题、HTTP 节点调用外部服务、conversation_variables 追踪得分 |
| **PowerContext Server** | 跨会话记忆存储 | `/api/v1/memories/remember` 写入、`/api/v1/memories/search` 召回；`scope=user-{user_id}` 隔离不同用户记忆 |

### 为什么需要 PowerContext？

Dify 自带的 `conversation_variables` 和会话记忆**只在当前会话有效**——开新对话就全没了。PowerContext 作为独立记忆服务，可以让 AI 跨会话"记住你"，这正是挑战模式最有趣的地方：**你换个新对话，AI 还能翻你黑历史**。

---

## 二、文件清单

```
dify/AI记忆梗王/
├── memory-joker-chatflow.yml   ← Dify Chatflow DSL（导入即用）
├── run.md                       ← 本文件（部署指南）
└── samples/
    └── verify.md                ← 完整验证脚本 + 运行证据位置
```

---

## 三、环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | 3.10+ | PowerContext Server 运行环境 |
| Node.js | 18+ | Dify 部署（可选，详见 Dify 文档） |
| Dify | 0.6.1 兼容 | DSL version: 0.6.1；导入前需绑定 LLM Provider |
| LLM | GPT-4o-mini 或同级别 | 需要支持中文、函数调用可选 |
| PowerContext | 仓库 HEAD | 本团队仓库 `powercontext/` 目录下的 Python 服务 |

### LLM Provider 配置

DSL 中默认使用 `langgenius/openai/openai` → `gpt-4o-mini`。导入 Dify 后：

1. 进入 **设置 → 模型供应商**
2. 启用 OpenAI（或兼容 API 的供应商如 DeepSeek / 火山方舟 / MiniMax）
3. 填入 API Key 和 Base URL
4. 如果用的不是 GPT-4o-mini，在 Chatflow 编辑器里点开「梗王核心」LLM 节点，切换模型

---

## 四、启动 PowerContext Server

### 4.1 从团队仓库

```bash
cd powercontext/
pip install -r requirements.txt
python -m powercontext.server
```

默认监听 `http://localhost:8000`，提供两个关键端点：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/memories/search?query=xxx&scope=user-yyy&limit=10` | 按 scope 召回记忆 |
| POST | `/api/v1/memories/remember` | 写入对话记忆 |

### 4.2 健康检查

启动后在终端验证：

```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

### 4.3 写入测试（可选）

```bash
curl -X POST http://localhost:8000/api/v1/memories/remember \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "user-test",
    "messages": [
      {"role": "user", "content": "我最爱吃海底捞番茄锅"},
      {"role": "assistant", "content": "好嘞，记住了！"}
    ]
  }'

curl "http://localhost:8000/api/v1/memories/search?query=火锅&scope=user-test"
# → 返回刚才写入的记忆
```

---

## 五、导入 Dify Chatflow

### 5.1 前置

- Dify 已部署（Docker Compose 或本地开发都行）
- 已配置 LLM Provider（见 §3）
- HTTP Request 插件已安装（Dify 内置，通常无需额外安装）

### 5.2 导入步骤

1. 打开 Dify 控制台 → **工作室**
2. 点 **创建应用** → **导入 DSL**
3. 选择本项目下的 `memory-joker-chatflow.yml`
4. 导入后进入应用编辑器
5. **检查 HTTP 节点的 URL**：默认 `http://localhost:8000`，如果 PowerContext 跑在其他地址/端口，改两个 HTTP Request 节点的 URL
6. **发布**：右上角点 **发布** → 确认版本号

### 5.3 快速测试

编辑器左上角点 **调试预览**，在对话框输入：

```
我超爱吃麻辣火锅，尤其是海底捞的番茄锅，今天加班好累啊
```

预期回复里应该：
- ✅ 语气活泼带梗
- ✅ 提到火锅和加班（引用了你的输入）
- ✅ 没有报错

---

## 六、Chatflow 节点一览

```
┌─────────────────────────────────────────────────────────────────────┐
│                     AI 记忆梗王 · Chatflow                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Start (query)                                                      │
│      │                                                              │
│      ▼                                                              │
│  HTTP Request: recall (GET PowerContext /memories/search)          │
│      │                                                              │
│      ▼                                                              │
│  LLM Core: 梗王核心                                                 │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 意图分类 → 三种模式：                                         │   │
│  │  A) 闲聊 → 梗式回复                                          │   │
│  │  B) 挑战 → 从记忆出 3 道填空题                                │   │
│  │  C) 答题 → 对比用户回答 vs 记忆原始内容 → 逐题判分 + 总分    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│      │                                                              │
│      ├──▶ Answer (输出给用户)                                       │
│      │                                                              │
│      ▼                                                              │
│  Code: 解析得分 + 组装 PowerContext payload                        │
│      │                                                              │
│      ▼                                                              │
│  HTTP Request: save (POST PowerContext /memories/remember)          │
│                                                                     │
│  Conversation Variables:                                            │
│  • score: number (累计得分)                                         │
│  • round: number (当前回合)                                         │
│  • challenge_mode: string (idle/questioning/answered)               │
│  • pending_questions: string (JSON 待答题目)                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 节点详解

| # | 节点 | 类型 | 关键配置 |
|---|---|---|---|
| 1 | 开始 | start | 用户输入 → `query` (max 2000) |
| 2 | 召回用户记忆 | http-request | GET `http://localhost:8000/api/v1/memories/search`，params: `query`, `scope=user-{user_id}`, `limit=10` |
| 3 | 梗王核心 | llm | system prompt 内含三种模式规则；引用 HTTP 召回 + conversation_variables |
| 4 | 回复用户 | answer | 输出 LLM text |
| 5 | 解析得分 + 准备记忆 | code (python3) | 正则匹配"本轮得分：X"，组装 PowerContext payload JSON |
| 6 | 保存记忆 | http-request | POST `http://localhost:8000/api/v1/memories/remember`，body 来自 Code 节点 |

---

## 七、PowerContext 接口适配说明

本项目**不修改 PowerContext 源码**，直接 HTTP 调用。依赖 PowerContext Server 实现以下两个端点：

### GET `/api/v1/memories/search`

```
Query params:
  query: string (用于语义搜索)
  scope: string (推荐 "user-{user_id}")
  limit: int (默认 10)

Response (示例):
[
  {"content": "用户说爱吃麻辣火锅", "metadata": {...}, "score": 0.95},
  {"content": "用户吐槽加班到9点", "metadata": {...}, "score": 0.87}
]
```

### POST `/api/v1/memories/remember`

```json
{
  "scope": "user-{user_id}",
  "messages": [
    {"role": "user", "content": "我爱吃火锅"},
    {"role": "assistant", "content": "好嘞记住了"}
  ],
  "metadata": {
    "conversation_id": "xxx",
    "score": 0,
    "round": 1,
    "challenge_mode": "idle"
  }
}
```

---

## 八、外部依赖与限制

| 项目 | 说明 |
|---|---|
| HTTP Request 插件 | Dify 内置，DSL 依赖 `http-request` extension_id，导入后自动绑定 |
| Dify 版本 | DSL v0.6.1，兼容 Dify 0.6.x 和 0.7.x 控制台；不保证 0.5.x 向下兼容 |
| 网络条件 | PowerContext Server 需对 Dify 容器/进程可达（默认 localhost:8000） |
| Embedding / Rerank | 未使用；语义搜索依赖 PowerContext 内部实现 |
| 错误处理 | HTTP 节点 `error_handle_mode: continue_on_error`，PowerContext 不可用时 Chatflow 仍能跑（只是没有记忆召回） |
| 硬限制 | DSL 中 URL 为 localhost；多机部署需在导入后手动修改两个 HTTP 节点的 URL |

---

## 九、已知功能限制

- **判题精度**：LLM 判题基于语义相似度，非严格字符串匹配；语义正确即可得分，不要求逐字一致
- **并发**：conversation_variables 是单会话状态，多用户并发时各自独立（scope=user-{user_id} 隔离）
- **题目数量**：每轮 3 题，由 LLM 从召回的记忆中自由组织；如果记忆 < 3 条会提示用户先闲聊
- **跨会话**：PowerContext 持久化，换 Dify 会话/换用户浏览器 tab 都不丢记忆
