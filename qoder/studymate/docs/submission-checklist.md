# 提测材料清单（docs/submission-checklist.md）

> 对照赛题《Build with Qoder——用 Qoder 做一个让学习、科研和工作更高效的项目》验收标准逐项核对。
> 提交前打开本文件，把 ★ 项替换成你的实际值，其余已就绪。

## 1. 项目网站网址（Qoder Sites 发布，任何人都可访问）

- ★ 站点网址：`https://____.qodersites.cn/____`（发布后在 Qoder Sites 后台复制完整网址）
- 发布步骤见 `docs/qoder-sites.md`；提交前用浏览器无痕窗口打开确认可访问。

## 2. 代码仓库

- 仓库：`https://gitee.com/boheshuizhitong/power-context-competition`
- 分支：`2026-competition-ecosystem`（赛事要求基于该分支/commit 开发）
- 项目目录：`qoder/studymate/`，远端最新提交 `1be7141`（含 README、双场景 17/17 证据、演示截图）

## 3. 运行说明

- 文件：`qoder/studymate/run.md`
- 覆盖：运行环境、依赖版本、seekdb 嵌入式接入、PowerContext（官方 Server + 离线兼容实现）部署与切换、从安装到启动完整步骤、配置变量、重置与排障。

## 4. 验证样例（至少一组可执行步骤 + 初始数据 + 输入 + 操作 + 预期 + 技术作用记录）

- 文件：`qoder/studymate/samples/verify.md` + `samples/verify.py`（17 项断言，`--reset` 保证任意状态可复现）
- 实测证据：`samples/verify-output-official-powercontext.txt`（官方 Server 17/17）、`samples/verify-output-compatible-powercontext.txt`（离线兼容 17/17）
- 初始数据：`app/seed.py` 内置 18 条示例（物理5/高数3/电路3/英语5/文献2）
- seekdb 作用证据：检索结果命中方式字段（semantic/keyword/both）、`/api/search` 双路召回+RRF
- PowerContext 作用证据：记忆写入 `changed:true`、跨会话召回"我记着：复习进度…"、复习计划由记忆调度

## 5. Qoder 开发记录

- 文件：`docs/qoder-dev-log.md`
- ★ Qoder 账号 UID：`[在此填写]`（进入 Qoder 个人中心查看）
- ★ 6 处截图位：在 Qoder 中打开本项目做真实操作（如让 Qoder 新增功能/修 bug/补测试）后截图填入对应行；
  运行演示截图已就绪：`docs/screenshots/01~05`（检索/记忆召回/复习计划/记忆/知识库）
- 开发环境栏写明 Qoder 桌面端/IDE 名称与版本。

## 6. 使用效果（鼓励项，可选）

- 建议：站点发布后把 Qoder Sites「访问统计」截图、真实用户（同学/室友）试用反馈截图补进 `docs/usage.md` 并加入站点。

## 7. 提交前自检清单

- [ ] 无痕窗口打开站点 URL，未登录可访问
- [ ] 按 run.md 从零启动，`python samples\verify.py --reset` 通过 17/17
- [ ] dev-log 已填 UID 与截图，与站点内容一致
- [ ] 仓库已推送最新提交，评审账号可访问
- [ ] 配置文件中无真实凭据（均为占位/环境变量）
- [ ] 测试平台表单：站点网址、仓库地址、Qoder UID 三项均已填写
- [ ] 其余材料（运行说明/验证样例/开发记录/使用效果）已上传
