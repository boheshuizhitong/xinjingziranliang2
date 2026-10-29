#!/usr/bin/env bash
# Linux / macOS 一键启动 seekdb (embedded 或 Docker) + 后端 + 前端
# 用法: ./start-all.sh

set -e
cd "$(dirname "$0")"

echo "=== [1/3] 启动 seekdb ==="
if [[ "$(uname)" == "Darwin" || "$(uname -s)" == "Linux" ]]; then
    # macOS / Linux 优先用 embedded 模式 (无需 Docker)
    export SEEKDB_MODE=${SEEKDB_MODE:-embedded}
    export SEEKDB_PATH=${SEEKDB_PATH:-$(pwd)/backend/seekdb.db}
    echo "  mode=$SEEKDB_MODE  path=$SEEKDB_PATH"
    if [ "$SEEKDB_MODE" = "embedded" ]; then
        echo "  embedded 模式: 无需额外服务, Node 端自启动"
    else
        docker run -d --name seekdb -p 2881:2881 oceanbase/seekdb 2>/dev/null || \
          docker start seekdb 2>/dev/null || true
    fi
else
    docker run -d --name seekdb -p 2881:2881 oceanbase/seekdb 2>/dev/null || \
      docker start seekdb 2>/dev/null || true
    echo "  server 模式 (Docker): 127.0.0.1:2881"
fi

echo "=== [2/3] 启动后端 ==="
cd backend
if [ ! -d node_modules ]; then npm install; fi
PORT=5174 node server.js &
BACKEND_PID=$!
cd ..
sleep 3

echo "=== [3/3] 启动前端 ==="
cd frontend
if [ ! -d node_modules ]; then npm install; fi
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "======================================"
echo " 前端: http://localhost:5173"
echo " 后端: http://localhost:5174/api/health"
echo "======================================"
echo "按 Ctrl+C 停止所有服务"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '已停止'" EXIT
wait
