#!/bin/bash
# ============================================================
# AI Memory Joker · One-click startup (Linux / macOS)
# ============================================================
# 1. Installs Python deps for PowerContext
# 2. Launches PowerContext memory server on http://localhost:8000
#    (runs in background; use Ctrl+C to stop)
# ============================================================

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/powercontext"

echo "============================================================"
echo "  AI Memory Joker · PowerContext Server"
echo "============================================================"

# Check python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[ERROR] Python 3 not found. Please install Python 3.10+"
    exit 1
fi

PY=$(command -v python3 || command -v python)

# Install deps
echo "[…] Installing dependencies ..."
$PY -m pip install -q fastapi uvicorn pydantic 2>&1 | tail -3

if [ $? -ne 0 ]; then
    echo "[…] Retrying with --user flag ..."
    $PY -m pip install -q --user fastapi uvicorn pydantic 2>&1 | tail -3
fi

# Kill any existing server on port 8000
if command -v lsof &>/dev/null; then
    OLD_PID=$(lsof -ti:8000 2>/dev/null)
    if [ -n "$OLD_PID" ]; then
        echo "[!] Port 8000 occupied, killing PID $OLD_PID"
        kill $OLD_PID 2>/dev/null
        sleep 1
    fi
fi

# Start server
echo ""
echo "🚀 Starting PowerContext on http://0.0.0.0:8000"
echo "   Press Ctrl+C to stop"
echo ""

$PY server.py
