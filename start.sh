#!/usr/bin/env bash
# AI 学习助手 - 一键启动（Linux / macOS）
# Windows 用户请双击 start.bat
#
# 首次运行会自动建虚拟环境、装依赖，之后再运行就直接启动。
#
# 用法:
#   ./start.sh                 启动（默认 8000 端口，自动打开浏览器）
#   ./start.sh 8001            指定端口（兼容旧写法）
#   ./start.sh setup           只做环境准备（装依赖，网络慢可加 --mirror）
#   ./start.sh stop            停止服务
#   ./start.sh status          查看运行状态
#   ./start.sh doctor          环境诊断
#   ./start.sh --no-browser    其余参数原样透传给 launcher.py
#
# 真正的逻辑在 scripts/launcher.py（Windows 与 Linux 共用同一份实现）

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$DIR/scripts/launcher.py"

if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[FAIL] 未找到 Python。请先安装 Python 3.9+：https://www.python.org/downloads/"
    exit 1
fi

FIRST="${1:-}"
SECOND="${2:-}"

case "$FIRST" in
    "")
        exec "$PY" "$LAUNCHER" start
        ;;
    setup)
        # setup 不接受端口
        exec "$PY" "$LAUNCHER" setup "${@:2}"
        ;;
    stop|status|doctor)
        # 兼容旧写法 ./start.sh stop 8001：把纯数字的第二参数转成 --port
        if [[ "$SECOND" =~ ^[0-9]+$ ]]; then
            shift 2
            exec "$PY" "$LAUNCHER" "$FIRST" --port "$SECOND" "$@"
        fi
        exec "$PY" "$LAUNCHER" "$FIRST" "${@:2}"
        ;;
    [0-9]*)
        # 兼容旧写法：./start.sh 8001
        exec "$PY" "$LAUNCHER" start --port "$FIRST" "${@:2}"
        ;;
    *)
        exec "$PY" "$LAUNCHER" start "$@"
        ;;
esac
