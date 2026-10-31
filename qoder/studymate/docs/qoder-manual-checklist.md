# Qoder 客户端手动操作清单（docs/qoder-manual-checklist.md）

> 站点发布与开发记录截图必须在 Qoder CN 桌面客户端完成（无网页版）。
> 打开 Qoder CN 客户端，登录你下载时的账号，按下面三步操作即可，约 10 分钟。

## 第 1 步：在 Qoder 里做一段真实开发（产出开发记录截图）

1. 打开 Qoder CN 客户端 → 打开文件夹：`C:\Users\Lenovo\source\powercontext-gitee\qoder\studymate`
2. 在对话输入框粘贴下面这段话，发送：

```
这是我的参赛项目"学伴 StudyMate"（FastAPI + seekdb + PowerContext）。
请帮我做一件小事：在 app/static/index.html 页面底部加一个页脚，
文字写"学伴 StudyMate · seekdb 知识库混合检索 × PowerContext 跨会话记忆 · Qoder × OceanBase 参赛作品"，
样式与现有浅色卡片风格一致。改完后告诉我改了哪个文件。
```

3. 等它改完（约 1-2 分钟），**对这个对话截图**（这就是"Qoder 开发记录"里的关键证据）。
4. 如果它改好了，用 git 提交一下（或让它提交）：
   ```
   git add qoder/studymate
   git commit -m "feat(qoder): add footer to index.html"
   git push origin 2026-competition-ecosystem
   ```

## 第 2 步：发布 Qoder Sites 站点

1. Qoder 客户端左侧栏点 **「站点」** → **添加站点**
2. 用一句话创建（或选模板后粘贴内容），把 `docs/site-content-draft.md` 的全部内容贴进去作为站点文案
3. 预览确认排版 OK → 点右上角 **「发布」**
4. 发布后点 **分享 → 更改访问范围 → 选「任何人都可访问」**（会弹"允许公开访问"确认，点允许）
5. 复制站点完整网址

## 第 3 步：查 Qoder UID

1. Qoder 客户端左下角头像 / 设置 → **个人资料 → 编辑**
2. 页面里显示的 **UID**（一串字符）复制下来

## 把这两样发我

- 站点网址
- Qoder UID

我会：①填进 `docs/qoder-dev-log.md` 并提交；②对照 `docs/submission-checklist.md` 逐项核对；③告诉你平台提测表单怎么填。
