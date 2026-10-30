# 验证脚本 · 记忆大考验

> **评审操作指南**：从 PowerContext Server 启动 → Dify DSL 导入 → 5 步完整体验游戏玩法
> 每一步都有截图位置标注（`📷 截图`），操作完成后保存到对应文件

---

## 🔍 前置条件检查（开始前确认）

| # | 检查项 | 验证命令 | 期望结果 |
|---|---|---|---|
| 1 | PowerContext Server 运行中 | `curl http://localhost:8000/health` | `{"status": "ok"}` |
| 2 | Dify 控制台可访问 | 浏览器打开 Dify 地址 | 能登录并进入工作室 |
| 3 | LLM Provider 已配置 | Dify 设置 → 模型供应商 | OpenAI / DeepSeek 等启用，有 API Key |
| 4 | HTTP Request 插件 | Dify 设置 → 插件 | 已安装 `HTTP Request` |

✅ **全部打勾后，开始验证**

---

## 🧪 Step 1：导入 Chatflow DSL

**操作：**
1. Dify 控制台 → 工作室 → 创建应用 → 导入 DSL
2. 选择 `dify/AI记忆梗王/memory-joker-chatflow.yml`
3. 应用名称自动填入「AI 记忆梗王 · 记忆大考验」
4. 进入编辑器 → 检查 **梗王核心** LLM 节点的模型是否可用（必要时切换）
5. 检查两个 HTTP Request 节点的 URL 是否为 `http://localhost:8000`（PowerContext 跑在其他地址时改这里）
6. **点「发布」** → 保存版本

**📷 截图：** Dify 应用编辑器发布页（含 6 节点连线图） → 保存为 `01-dify-published.png`

---

## 🧪 Step 2：闲聊模式 + PowerContext 写入

**目标：** 验证「闲聊 → 存记忆」路径

**Dify 调试面板输入：**
```
我超爱吃麻辣火锅，尤其是海底捞的番茄锅，今天加班到9点好累啊
```

**Dify 侧预期输出（AI 回复）：**
- ✅ 语气活泼带梗（不是冷冰冰的）
- ✅ 提到"火锅"、"番茄锅"或"加班"（引用了用户输入）
- ✅ 没有报错

**📷 截图：** Dify 对话框回复 → 保存为 `02-chat-reply.png`

**PowerContext 侧验证（在终端执行）：**
```bash
curl "http://localhost:8000/api/v1/memories/search?query=火锅&scope=user-{USER_ID}"
```
> `{USER_ID}` 替换成 Dify 调试面板显示的 user_id（通常在右下角或运行日志里）

**PowerContext 预期输出：**
- ✅ 返回的 JSON 里包含刚才用户说的"火锅"、"加班"等内容
- ✅ 每条记忆带 scope / metadata

**📷 截图：** PowerContext API 返回 JSON → 保存为 `02-powercontext-json.png`

---

## 🧪 Step 3：挑战模式 · AI 出题

**目标：** 验证「挑战请求 → 从 PowerContext 召回记忆 → 出 3 道填空题」

**Dify 调试面板输入（同一对话，不要开新会话）：**
```
考我
```

**Dify 侧预期输出（AI 回复）：**
- ✅ 开头有「🎯 记忆大考验」或类似标题
- ✅ 列出 **3 道带横线填空**的题目
- ✅ 题目内容基于你刚才 Step 2 说过的火锅/加班等
- ✅ 没有说"你还没告诉我太多事"（因为 Step 2 已经存了）

**📷 截图：** AI 出的 3 道题 → 保存为 `03-challenge-questions.png`

**PowerContext 侧验证：**
```bash
curl "http://localhost:8000/api/v1/memories/search?query=麻辣火锅%20加班&scope=user-{USER_ID}&limit=5"
```
**预期：** 返回至少 2-3 条相关记忆

---

## 🧪 Step 4：答题判分 · 完整游戏回路

**目标：** 验证「答题 → 对比记忆 → 逐题判分 → 总分」

**Dify 调试面板输入（同一对话，回答刚才的 3 道题）：**
```
海底捞番茄锅
8点（我记得是8点？）
```
> （故意答错第 2 题，看 AI 会不会吐槽）

**Dify 侧预期输出（AI 判题回复）：**
- ✅ 逐题显示 ✅ 或 ❌
- ✅ 第 1 题（火锅）→ ✅
- ✅ 第 2 题（加班时间）→ ❌ + 爆梗吐槽（比如"你说的是9点好吗——果然加班使人失忆"）
- ✅ 末尾有 **本轮得分：X / 3** + **累计总分**
- ✅ 有梗王评语（比如"记忆还行但别高兴太早"）

**📷 截图：** AI 判分结果（含 ✅❌ + 得分）→ 保存为 `04-judging-score.png`

**运行日志验证（可选）：**
在 Dify 应用编辑器左上角点「运行日志」→ 找到这条记录 → 查看：
- ✅ HTTP Request「召回用户记忆」节点：有实际返回内容（非空）
- ✅ HTTP Request「保存记忆」节点：200 OK
- ✅ Code「解析得分」节点：output 有 `new_score` 字段

**📷 截图：** Dify 运行日志（显示 6 节点执行顺序）→ 保存为 `04-run-logs.png`

---

## 🧪 Step 5：跨会话记忆 · 终极验证

**目标：** 验证 PowerContext 的核心价值——**换会话 AI 还能记得你**

**操作：**
1. 在 Dify 调试面板点 **"新对话"** 按钮（或开一个新的浏览器 tab 访问应用）
2. Dify 会生成全新的 `conversation_id`

**新会话输入：**
```
考我
```

**关键预期：**
- ✅ AI **仍然能出基于你之前闲聊内容的题**（火锅、加班等）
- ✅ 这是因为 PowerContext 按 `scope=user-{user_id}` 持久化存储，跟 `conversation_id` 无关
- ✅ 如果 Dify 侧没配置 PowerContext，这里会说"你还没告诉我太多事"

**📷 截图：** 新会话的挑战题目 → 保存为 `05-cross-session.png`

---

## 📋 验收 Checklist

评审逐项打勾，全部通过即基础验收合格：

### 可运行性
- [ ] DSL 成功导入 Dify，6 节点连线完整
- [ ] PowerContext Server 启动，health endpoint 返回 ok
- [ ] 两个 HTTP Request 节点能正常调用（Dify 运行日志里无 connect error）

### 功能完整性（游戏回路）
- [ ] **Step 2** 闲聊模式：AI 正常回复 + PowerContext 有数据写入
- [ ] **Step 3** 挑战模式：AI 成功从 PowerContext 召回记忆并出 3 道题
- [ ] **Step 4** 答题判分：AI 逐题对比 + ✅❌标记 + 本轮/累计得分
- [ ] **Step 5** 跨会话记忆：新会话 AI 还能出题（PowerContext 持久化生效）

### 技术结合有效性
- [ ] **Dify** 承担完整流程编排（6 节点：Start → HTTP → LLM → Answer → Code → HTTP）
- [ ] **PowerContext 写入**：`/api/v1/memories/remember` 被实际调用（Step 2 后 curl 能查到）
- [ ] **PowerContext 召回**：`/api/v1/memories/search` 返回的记忆被 LLM 实际使用（Step 3 出题内容来自之前闲聊）
- [ ] **判题回路**：LLM 对比「用户回答」vs「PowerContext 原始记忆」并打分，Code 节点正则提取得分后存入 conversation_variables 并回写 PowerContext metadata

### 运行证据
- [ ] 5 张截图全部获取（见上方 📷 标记）
- [ ] PowerContext API curl 返回 JSON 可验证（不是空数组）
- [ ] Dify 运行日志里可见 HTTP 节点的请求/响应体

---

## 🛠 故障排查

| 现象 | 可能原因 | 排查 |
|---|---|---|
| HTTP Request 节点超时/连接失败 | PowerContext 没启动或 URL 错 | `curl http://localhost:8000/health`；检查 Dify 里两个 HTTP 节点 URL |
| 挑战模式说"还没告诉我太多事" | PowerContext 里没数据写入 | 先做 Step 2，或用 §7 的 curl 手动写一条记忆 |
| 答题全判错 | PowerContext 召回内容为空 | 检查 `scope` 参数是否匹配（Dify 传的是 `user-{sys.user_id}`） |
| LLM 直接输出 JSON 格式给用户 | model 不遵循 prompt | 换用 GPT-4o-mini 或同级别模型 |
| `conversation_variables` 不更新 | Dify 版本过低 | 检查 Dify 是否支持 conversation_variables（0.6+） |
