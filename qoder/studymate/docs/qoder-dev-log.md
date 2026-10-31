# Qoder 开发记录（docs/qoder-dev-log.md）

> 本赛道要求：项目主要开发工作必须在 Qoder 中完成，并保留关键环节的对话截图/录屏，
> 附 **Qoder 账号 UID** 以核对站点归属与使用记录。
> 以下表格记录各开发环节；截图位请在对应表格行插入 Qoder 对话截图。

## Qoder 账号

| 项 | 内容 |
| --- | --- |
| Qoder 账号 UID | **[在此填写你的 Qoder 账号 UID]** |
| 开发环境 | Qoder 桌面端 / IDE |
| 站点发布 | Qoder Sites（见 `docs/qoder-sites.md`） |

## 开发环节与 Qoder 参与

| # | 环节 | Qoder 承担的工作 | 产出 | 截图/录屏位 |
| --- | --- | --- | --- | --- |
| 1 | 需求拆解 | 把"复习找不到笔记/不知道薄弱点/进度要重讲"的痛点拆成：知识库检索、记忆教练、复习计划三个模块，确定 seekdb 管知识、PowerContext 管记忆的分工 | 方案文档（README 第一节） | 📷 截图1：需求拆解对话 |
| 2 | 技术选型与可行性验证 | 分析 seekdb 嵌入式（pylibseekdb+pymysql）与 pyseekdb ONNX 中文嵌入在 Windows 的可行性，选定 ik 中文全文 + bge-small-zh-v1.5 向量方案；确认 PowerContext HTTP 契约 | `requirements.txt`、`app/embedding.py` | 📷 截图2：选型论证 |
| 3 | 核心编码 | ① seekdb 知识库层：建表（VECTOR+FULLTEXT ik）、向量化、双路召回+RRF 融合检索；② PowerContext 客户端：Scope 管理、记忆读写、上下文准备；③ 复习教练：间隔重复调度+检索联动；④ FastAPI 接口与前端页面 | `app/seekdb_store.py`、`app/memory_client.py`、`app/coach.py`、`app/main.py`、`app/static/` | 📷 截图3：核心模块编码 |
| 4 | 调试与修复 | ① 修复 pyseekdb 默认嵌入模型中文语义弱的问题（换 bge-small-zh-v1.5 + 查询指令前缀）；② 修复 ik 全文索引与向量索引共存时的检索返回为空（改用 APPROXIMATE 全扫描）；③ 修复无空格中文查询在记忆召回中分词失败（2 字滑窗）；④ 修复静态资源 404（挂载 StaticFiles）；⑤ 兼容官方 `/v1/atomic-memory/list` 精确拉取记忆 | 见 git 提交历史 | 📷 截图4：调试过程 |
| 5 | 端到端验证 | 编写 `samples/verify.py`（17 项断言），分别对官方 PowerContext 与离线兼容实现跑通 | `samples/verify-output-official-powercontext.txt`、`samples/verify-output-compatible-powercontext.txt` | 📷 截图5：验证通过 |
| 6 | 文档与发布 | 编写 README/run.md/verify.md；Qoder Sites 发布网站并设置公开访问 | 本站点 | 📷 截图6：Sites 发布 |

## 关键决策记录

| 决策 | 理由 |
| --- | --- |
| seekdb 管知识、PowerContext 管记忆 | 各自官方定位：seekdb 是检索数据库，PowerContext 是 Agent 记忆/上下文服务；分工明确便于评审核对 |
| 双路召回 + RRF 融合做混合检索 | seekdb 官方卖点即"向量+全文+标量一条 SQL"；双路召回对小数据集更稳，且命中信号（semantic/keyword/both）可展示 |
| 嵌入模型选 bge-small-zh-v1.5（ONNX） | 纯本地 CPU 推理、离线可用；pyseekdb 默认模型中文语义弱（实测前 3 名检索全错，替换后全对） |
| 应用层只依赖 PowerContext 公开 HTTP 契约 | 官方 Server（uv 部署）与离线兼容实现（pc_server/）可无缝切换，评审在无网络环境也能复现 |
| 不接外部大模型 API | 问答/复习计划全部由记忆召回+混合检索+规则调度构成，离线可完整复现，避免评审环境无 API Key 的依赖 |

## 复现步骤（评审核对 Qoder 开发过程）

1. 打开本仓库 `qoder/studymate/`，对照 git 提交历史（`git log --oneline`）查看各环节产出；
2. 按 `run.md` 启动应用，运行 `python samples/verify.py --reset`，比对 `samples/verify-output-*.txt`；
3. 打开 Qoder Sites 站点，核对"Qoder 开发记录"章节与站点内容一致性。
