# 学伴 StudyMate 运行说明（run.md）

## 1. 运行环境

| 项 | 要求 | 说明 |
| --- | --- | --- |
| 操作系统 | Windows 10/11、Linux、macOS | 已在 Windows 11 实测 |
| Python | 3.11 ~ 3.13 | 3.13 实测通过 |
| 网络 | 首次运行需联网 | 仅用于下载中文嵌入模型（约 90MB，之后完全离线） |
| 依赖 | 见 `requirements.txt` | `pip install -r requirements.txt` |

## 2. 依赖安装

```bash
# Windows（PowerShell）
python -m pip install -r requirements.txt

# Linux / macOS
python3 -m pip install -r requirements.txt
```

依赖说明：

| 包 | 作用 |
| --- | --- |
| `fastapi` / `uvicorn` | Web 服务 |
| `pylibseekdb` | **seekdb** 嵌入式原生绑定（本地数据库引擎） |
| `pymysql` | 通过 MySQL 协议连接 seekdb 并执行 SQL（向量/全文/标量混合检索） |
| `pyseekdb` | **seekdb** 官方高层客户端（本项目使用其 ONNX 中文嵌入能力） |
| `python-multipart` | FastAPI 表单支持 |

## 3. 启动

### 3.1 一键启动（推荐）

```powershell
# Windows
.\start.ps1
# Linux/macOS
./start.sh
```

脚本会自动：创建虚拟环境 → 安装依赖 → 启动 PowerContext（兼容实现，端口 8010）→ 启动主应用（端口 8080）。

打开浏览器访问 **http://127.0.0.1:8080**，首次访问自动导入 18 条示例学习数据。

### 3.2 分步启动（手动控制）

```bash
# 终端 1：PowerContext 记忆服务（兼容实现，端口 8010）
python pc_server/server.py

# 终端 2：主应用（端口 8080）
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

### 3.3 使用官方 PowerContext Server（可选，效果相同）

本应用只依赖 PowerContext 的公开 HTTP 契约（`/v1/scopes`、`/v1/memory/remember`、
`/v1/memory/search`、`/v1/atomic-memory/list`、`/v1/context/prepare`），可直接对接官方服务：

```bash
# 安装官方 PowerContext Server（需要 uv）
uv tool install --force "powercontext[cli,server] @ git+https://github.com/oceanbase/powercontext.git@master"

# 启动（端口 8000）
powercontext server run --host 127.0.0.1 --port 8000

# 另开终端启动应用，指定 PowerContext 地址
set POWERCONTEXT_URL=http://127.0.0.1:8000   # Windows PowerShell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

> 两种 PowerContext 部署方式对应用完全透明（`POWERCONTEXT_URL` 切换即可），
> 本项目已分别用两种方式跑通 17/17 验证（见 `samples/verify-output-*.txt`）。

## 4. 配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `POWERCONTEXT_URL` | `http://127.0.0.1:8010` | PowerContext 服务地址（官方或兼容实现） |
| `STUDYMATE_SEEKDB` | `data/seekdb` | seekdb 数据库文件路径 |
| `STUDYMATE_PORT` | `8080` | 主应用端口 |
| `STUDYMATE_SCOPE` | `studymate-user-001` | PowerContext Scope 名称（每人一个） |

## 5. 数据位置

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| seekdb 知识库 | `data/seekdb` | 笔记、向量、全文索引 |
| PowerContext 记忆 | `data/powercontext.db`（兼容实现）或官方 Server 数据目录 | 薄弱点/进度/偏好 |
| Scope ID | `data/powercontext_scope_id.txt` | 记住当前用户属于哪个 Scope |

## 6. 重置（评审重复验证用）

调用接口即可清空知识库并创建全新 Scope：

```bash
curl -X POST http://127.0.0.1:8080/api/reset
# 或运行验证脚本时加 --reset：python samples/verify.py --reset
```

## 7. 常见问题

- **首次访问较慢/卡在"正在下载模型"**：首次需下载 bge-small-zh-v1.5 ONNX 模型（~90MB），
  若下载慢可设置环境变量 `HF_ENDPOINT=https://hf-mirror.com` 后重启应用。
- **PowerContext 显示未连接**：确认 `pc_server` 已启动，或 `POWERCONTEXT_URL` 指向了正确的服务。
- **端口被占用**：修改 `start.ps1`/环境变量中的端口。
