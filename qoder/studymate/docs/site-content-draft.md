# Qoder Sites 站点内容草稿（docs/site-content-draft.md）

> 直接把本节内容粘贴进 Qoder Sites 页面编辑器，替换 ★ 占位后发布。
> 发布后需再次点击「发布」才更新线上版本；可见范围务必设为「任何人都可访问」。

---

## 📚 学伴 StudyMate · 越用越懂你的学习记忆助手

> 复习时找不到笔记？不知道自己哪些知识点薄弱？上次复习到哪全凭记忆？
> 学伴用 seekdb 建个人知识库、用 PowerContext 记住你的薄弱点与进度，
> 让每次复习都有据可查、越用越懂你。

### 解决什么问题
学习/科研中最耗时的三件小事：几十篇笔记里翻答案、考完才知道哪里没掌握、复习进度全靠脑子记。
学伴把它们收进一个页面：**搜得准**（混合检索）、**记得住**（跨会话记忆）、**排得清**（今日复习计划）。

### 核心功能
| 功能 | 说明 | 技术 |
| --- | --- | --- |
| 知识库混合检索 | 笔记/文献/英语语料按语义+关键词+学科检索，命中标注 semantic/keyword/both 并给出处 | seekdb（向量 + ik 中文全文 + 标量过滤，双路召回 RRF 融合） |
| 记忆教练问答 | 提问自动召回历史薄弱点/进度，回答带"我记得你…" | PowerContext Scope 记忆 |
| 今日复习计划 | 薄弱知识点进计划，自动匹配知识库复习资料，间隔重复排期 | PowerContext 记忆调度 + seekdb 检索联动 |

### 演示
![检索演示](docs/screenshots/01-search-demo.png)
![跨会话记忆召回](docs/screenshots/02-memory-recall-demo.png)
![今日复习计划](docs/screenshots/03-review-plan-demo.png)
![PowerContext 记忆](docs/screenshots/04-memory-demo.png)
![知识库](docs/screenshots/05-knowledge-base-demo.png)

### 验证结果
- 端到端验证 **17/17 通过**（官方 PowerContext 与离线兼容实现双跑）
- 覆盖：18 条示例导入、5 组中文混合检索首位命中、学科过滤、3 类记忆写入、跨会话记忆召回、复习计划调度

### 代码仓库
- gitee：`https://gitee.com/boheshuizhitong/power-context-competition`（分支 `2026-competition-ecosystem`，目录 `qoder/studymate/`）

### 体验入口
- 本地运行：`.\start.ps1` 后访问 http://127.0.0.1:8080（运行说明见仓库 run.md）
- ★ 在线体验地址：`____`（如有）

### Qoder 开发记录
项目由 Qoder 完成需求拆解、编码、调试与验证（详见仓库 docs/qoder-dev-log.md，含账号 UID 与截图）。
