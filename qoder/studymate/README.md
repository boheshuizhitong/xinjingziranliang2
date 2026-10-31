# 学伴 StudyMate · 越用越懂你的学习记忆助手

> Qoder × OceanBase 赛道参赛作品。用 Qoder 开发，实际结合 **seekdb** 与 **PowerContext**
> 双技术：seekdb 管知识（混合检索），PowerContext 管记忆（跨会话复用）。
> 项目网站经 Qoder Sites 发布（可见范围：任何人都可访问）。

## 一、解决什么问题

学习中最耗时的三件事：**复习时找不到笔记**（几十篇 PDF 里翻）、**不知道自己哪些知识点薄弱**
（考完才知道）、**上次复习到哪了要重新想**（进度全靠脑子记）。学伴把这三件事收进一个页面：

1. **知识库混合检索** —— 把课程笔记/文献/英语语料导入 seekdb，按语义+关键词+学科一条入口检索，
   命中即给出处；
2. **记忆教练问答** —— 提问时自动召回 PowerContext 里存过的薄弱点与复习进度，回答带"我记得你…"；
3. **今日复习计划** —— 由记忆里的薄弱知识点调度，自动到知识库匹配复习资料，按间隔重复排期。

## 二、技术分工（评审核对用）

| 组件 | 在项目中做什么 | 关键技术 |
| --- | --- | --- |
| **seekdb**（必选其一） | 知识库：18 条示例笔记的存储与混合检索 | 嵌入式 pylibseekdb；`VECTOR` 向量列 + `FULLTEXT`(ik 中文分词) + 学科标量过滤，双路召回 + RRF 融合，命中信号 semantic/keyword/both 可展示 |
| **PowerContext**（必选其一） | 记忆：薄弱知识点 / 复习进度 / 学习偏好的保存与复用 | Scope 化记忆，官方 HTTP 契约（`/v1/memory/remember`、`/v1/atomic-memory/list`、`/v1/context/prepare` 等），跨会话召回 |
| 主应用 | FastAPI 单进程 Web（问答/检索/计划/记忆四页） | Python 3.13，全离线可复现，不依赖外部大模型 API |

> 双实现可切换：应用层只依赖 PowerContext 公开 HTTP 契约。设 `POWERCONTEXT_URL` 指向
> 官方 Server（8000）或仓库自带离线兼容实现（8010，`pc_server/server.py`，SQLite 存储），
> 行为一致。评审在无网络环境也能跑通。

## 三、快速开始

```powershell
# 1) 一键启动（自动建 venv、装依赖、起兼容 PowerContext 8010、起主应用 8080）
.\start.ps1

# 2) 打开浏览器
#    http://127.0.0.1:8080   （首次访问自动导入 18 条示例数据）
```

分步启动、官方 PowerContext 接入、配置变量与常见问题，见 **[run.md](run.md)**。

## 四、验证样例（评审复现）

```powershell
python samples\verify.py --reset    # 17 项断言：健康/初始化/混合检索/记忆写入/跨会话召回/复习计划
```

实测输出（两份，均已入库可直接查看）：
- 官方 PowerContext：[samples/verify-output-official-powercontext.txt](samples/verify-output-official-powercontext.txt)（17/17）
- 离线兼容实现：[samples/verify-output-compatible-powercontext.txt](samples/verify-output-compatible-powercontext.txt)（17/17）

样例说明见 **[samples/verify.md](samples/verify.md)**。运行演示截图见 `docs/screenshots/`。

## 五、项目结构

```
qoder/studymate/
├─ README.md              # 本文件：评审入口
├─ run.md                 # 运行说明（环境/依赖/启动/配置/排障）
├─ requirements.txt       # fastapi/uvicorn/pylibseekdb/pymysql/pyseekdb/python-multipart
├─ start.ps1 / start.sh   # 一键启动脚本
├─ app/                   # FastAPI 主应用
│  ├─ main.py             #   接口入口 + 静态页挂载
│  ├─ config.py           #   配置（POWERCONTEXT_URL / STUDYMATE_* 环境变量）
│  ├─ embedding.py        #   bge-small-zh-v1.5 ONNX 中文嵌入（本地 CPU）
│  ├─ seekdb_store.py     #   知识库：建表/导入/双路召回+RRF 混合检索
│  ├─ memory_client.py    #   PowerContext HTTP 客户端（记忆读写/上下文准备）
│  ├─ coach.py            #   复习教练：问答组装/记忆写入/复习计划调度
│  ├─ seed.py             #   18 条示例数据（物理5/高数3/电路3/英语5/文献2）
│  └─ static/             #   前端页面（问答/知识库/复习计划/记忆）
├─ pc_server/server.py    # PowerContext 离线兼容实现（契约一致，SQLite）
├─ samples/               # 验证样例（verify.py / verify.md / 实测输出×2）
└─ docs/                  # qoder-dev-log.md（Qoder 开发记录）/ qoder-sites.md（发布指南）/ screenshots/
```

## 六、Qoder 赛题提交索引

| 提交材料 | 位置 / 说明 |
| --- | --- |
| 项目网站网址 | Qoder Sites 公开站点（见 [docs/qoder-sites.md](docs/qoder-sites.md)） |
| 代码仓库 | 本仓库分支 `2026-competition-ecosystem` 下 `qoder/studymate/` |
| 运行说明 | [run.md](run.md) |
| 验证样例 | [samples/verify.md](samples/verify.md) + `verify.py` + 实测输出×2 |
| Qoder 开发记录 | [docs/qoder-dev-log.md](docs/qoder-dev-log.md)（含 Qoder 账号 UID 与截图位） |
| 使用效果（鼓励） | 站点访问统计、用户反馈（可在站点后台查看后补充） |

## 七、复现环境（已实测）

- Windows 11 + PowerShell，Python 3.13
- seekdb 嵌入式（pylibseekdb + pymysql），模型 `Xenova/bge-small-zh-v1.5`（ONNX，首次联网下载后离线）
- PowerContext：官方 Server v1.4.2.dev85（`uv tool install --force "powercontext[cli,server] @ git+https://github.com/oceanbase/powercontext.git@master"`）
