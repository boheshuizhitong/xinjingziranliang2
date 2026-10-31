#!/usr/bin/env bash
# 学伴 StudyMate 一键启动（Linux / macOS）
set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
$PY --version

if [ ! -d .venv ]; then
  echo "[2/4] 创建虚拟环境并安装依赖…"
  $PY -m venv .venv
  ./.venv/bin/python -m pip install -r requirements.txt -q
fi
VPY=.venv/bin/python

if [ -z "$POWERCONTEXT_URL" ]; then
  echo "[3/4] 启动 PowerContext 兼容服务 (8010)…"
  POWERCONTEXT_PORT=8010 $VPY pc_server/server.py > data/pc_server.log 2>&1 &
  sleep 3
fi

echo "[4/4] 启动主应用 http://127.0.0.1:8080"
$VPY -m uvicorn app.main:app --host 127.0.0.1 --port 8080
