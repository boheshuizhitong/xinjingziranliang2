#!/usr/bin/env python3
"""One-click startup: install deps + launch PowerContext server."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    os.chdir(HERE)
    print("=" * 50)
    print("  PowerContext Memory Server · 启动中")
    print("=" * 50)

    # 1. 安装依赖（如果 fastapi 没装）
    try:
        import fastapi  # noqa
        print("[✓] fastapi 已安装")
    except ImportError:
        print("[…] 正在安装依赖 fastapi / uvicorn ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "fastapi", "uvicorn", "pydantic"]
        )
        print("[✓] 依赖安装完成")

    # 2. 启动 server（监听 0.0.0.0:8000）
    print(f"\n🚀 启动 PowerContext Server on http://0.0.0.0:8000")
    print("   Ctrl+C 停止\n")
    os.execv(sys.executable, [sys.executable, "server.py"])


if __name__ == "__main__":
    main()
