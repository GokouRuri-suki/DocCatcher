#!/usr/bin/env bash
# AI 学习助手 - 启动脚本
# 用法:
#   ./start.sh          启动服务 (默认 8000 端口)
#   ./start.sh 8001     指定端口
#   ./start.sh stop     停止服务

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
VENV_PY="$BACKEND/venv/bin/python"
PORT="${1:-8000}"
PID_FILE="$ROOT/.uvicorn.pid"
LOG_FILE="$ROOT/backend/uvicorn.log"

# 停止服务
if [[ "$PORT" == "stop" ]]; then
    STOP_PORT="${2:-8000}"
    STOPPED=0

    # 1) 按 PID 文件停止
    if [[ -f "$PID_FILE" ]]; then
        PID="$(cat "$PID_FILE")"
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID" 2>/dev/null && echo "已结束进程 PID $PID"
            STOPPED=1
        fi
        rm -f "$PID_FILE"
    fi

    # 2) 兜底：按端口清理（PID 文件过期/缺失时仍然有效）
    if fuser -k "${STOP_PORT}/tcp" 2>/dev/null; then
        echo "已释放端口 ${STOP_PORT}"
        STOPPED=1
    fi

    # 3) 兜底：清理残留 uvicorn
    if pkill -f "uvicorn app.main:app" 2>/dev/null; then
        echo "已清理残留 uvicorn 进程"
        STOPPED=1
    fi

    sleep 1
    if ss -tln 2>/dev/null | grep -q ":${STOP_PORT} "; then
        echo "警告: 端口 ${STOP_PORT} 仍被占用" >&2
        ss -tlnp 2>/dev/null | grep ":${STOP_PORT} " >&2 || true
        exit 1
    fi

    if [[ "$STOPPED" == "1" ]]; then echo "服务已停止"; else echo "没有正在运行的服务"; fi
    exit 0
fi

# 前置检查
if [[ ! -x "$VENV_PY" ]]; then
    echo "错误: 未找到虚拟环境 $VENV_PY" >&2
    echo "请先运行: cd backend && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

# 端口占用检查
if ss -tln 2>/dev/null | grep -q ":${PORT} "; then
    echo "错误: 端口 ${PORT} 已被占用" >&2
    ss -tlnp 2>/dev/null | grep ":${PORT} " || true
    echo "可换端口: ./start.sh 8001   或停止: ./start.sh stop ${PORT}" >&2
    exit 1
fi

cd "$BACKEND"

# 启动
nohup "$VENV_PY" -m uvicorn app.main:app \
    --host 0.0.0.0 --port "$PORT" \
    > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

# 等待就绪
for i in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
        echo "✅ 服务已启动"
        echo "   访问地址: http://localhost:${PORT}"
        echo "   API 文档: http://localhost:${PORT}/docs"
        echo "   日志文件: $LOG_FILE"
        echo "   进程 PID: $(cat "$PID_FILE")"
        echo ""
        curl -fsS "http://127.0.0.1:${PORT}/health"
        echo ""
        exit 0
    fi
    sleep 0.5
done

echo "❌ 启动失败，日志尾部:" >&2
tail -30 "$LOG_FILE" >&2
rm -f "$PID_FILE"
exit 1
