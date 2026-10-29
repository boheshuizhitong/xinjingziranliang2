# 🤡 AI 记忆梗王 — 运行说明

> **作品名**：AI 记忆梗王
> **赛题**：2026 OceanBase × Dify 大赛 — Just for Fun
> **技术栈**：Dify Chatflow + PowerContext Server

---

## 一、作品介绍

### 创意

你有没有想过，如果 AI 能**永远记住你说过的每一句话**，会是什么体验？

「AI 记忆梗王」就是这样一个应用：它是一个**越聊越熟**的聊天伙伴。你第一次和它说"我爱吃火锅"，它记住；你第二次开**新对话**说"好冷"，它会接"上次你说爱吃火锅——这种天气不吃可惜了！"。

**PowerContext 负责跨会话记忆，Dify 负责编排对话流程和生成梗式回复。**

### 技术架构

```
┌─────────────────────────────────────────────────┐
│                   Dify Chatflow                │
│                                                 │
│  Start → HTTP Request(召回) → LLM → Answer    │
│                        ↓                        │
│                  HTTP Request(保存)            │
└────────────────────────────────┬────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────┐
│           PowerContext Server (8000)            │
│                                                 │
│  • 跨会话记忆存储与检索                          │
│  • 按 sys.user_id 隔离不同用户                  │
│  • 默认 SQLite，可替换 OceanBase/seekdb         │
└─────────────────────────────────────────────────┘
```

---

## 二、运行环境

| 项目 | 要求 |
|---|---|
| OS | Windows / macOS / Linux |
| Python | ≥ 3.11 |
| uv | 最新（`pip install uv`） |
| Dify | ≥ 0.8.0（Docker Compose 或 Dify Cloud） |
| Docker（本地部署 Dify 时） | ≥ 24 |
| 内存 | ≥ 4GB |
| 磁盘 | ≥ 5GB |

---

## 三、部署步骤

### Step 1: 安装 PowerContext Server

```bash
# 从大赛专用分支安装
uv tool install "powercontext[cli,server] @ git+https://github.com/oceanbase/powercontext.git@2026-competition-ecosystem"
```

### Step 2: 启动 PowerContext Server

```bash
powercontext server run
```

Server 监听 `http://127.0.0.1:8000`，默认 SQLite。

验证：
```bash
curl http://localhost:8000/api/v1/memories/search?query=test&scope=verify
# 或
powercontext ready
```

### Step 3: 部署 Dify

**方式 A — Docker Compose（本地）：**
```bash
git clone https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
docker compose up -d
```
访问 `http://localhost` 进入控制台。

**方式 B — Dify Cloud：** 访问 https://cloud.dify.ai

### Step 4: 配置 Dify 模型提供者

Dify Studio → **Settings → Model Provider** → 安装至少一个 → 配置 API Key → 设为默认。

### Step 5: 导入 Chatflow DSL

1. Dify Studio → **Create from Blank → Chatflow**
2. 画布右上角 **··· → Import DSL**
3. 选择本目录下的 `memory-joker-chatflow.yml`
4. 导入后检查 HTTP Request URL（默认 `http://localhost:8000`）

### Step 6: 发布并体验

点击画布顶部 **Publish** → 预览测试 → 分享给评审。

---

## 四、容错与降级

DSL 中两个 HTTP Request 节点均配置 `continue_on_error`：
- PowerContext 不可用时，主流程不被阻断
- LLM 正常回复（只是没有历史记忆加持）
- 保存失败不影响用户体验

评审即使没有启动 PowerContext Server，DSL 也能导入并运行。
完整体验（跨会话记忆）需要 Server 正常运行。

---

## 五、OceanBase/seekdb 进阶

默认 SQLite。如需 OceanBase/seekdb：

```bash
export POWERCONTEXT_DATABASE_URL="mysql://user:pass@host:2881/powercontext"
powercontext server run
```

这样本作品同时满足 **Dify + PowerContext + seekdb/OceanBase** 完整技术栈。

---

## 六、依赖声明

| 依赖 | 说明 |
|---|---|
| PowerContext Server | `2026-competition-ecosystem` 分支 |
| Dify HTTP Request 扩展 | Dify 内置，无需额外安装 |
| LLM | 任意兼容 OpenAI API 的模型 |

---

## 七、已知限制

1. API 路径兼容性：不同 PowerContext 版本的 HTTP API 路径可能略有差异，导入后对照实际版本调整
2. 记忆提取粒度：保存完整对话，未做精细信息抽取
3. 无记忆删除 UI：记忆管理通过 API 直接操作
