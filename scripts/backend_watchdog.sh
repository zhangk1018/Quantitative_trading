#!/bin/bash
# backend_watchdog.sh - 后端进程监控 + 自动重启
# 用法：
#   bash scripts/backend_watchdog.sh stop          # 停止后端
#   bash scripts/backend_watchdog.sh start         # 启动后端并监控
#   bash scripts/backend_watchdog.sh check         # 检查一次，不在运行则重启

# 不使用 set -e，用显式错误处理替代

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="/tmp/quant_backend.pid"
WATCHDOG_PID_FILE="/tmp/quant_backend_watchdog.pid"
WATCHDOG_LOG="$SCRIPT_DIR/logs/watchdog.log"
BACKEND_LOG="$SCRIPT_DIR/logs/quant_backend.log"
BACKEND_PORT=8000
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
BACKEND_ENTRY="$SCRIPT_DIR/backend/core/api/main.py"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$WATCHDOG_LOG"; }
log_info() { log "INFO - $*"; }
log_warn() { log "WARN - $*"; }
log_err() { log "ERR  - $*"; }

# 检查后端是否在运行
is_backend_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    # 检查端口
    if lsof -i :"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null | grep -q .; then
        local pid
        pid=$(lsof -t -i :"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null | head -1)
        echo "$pid" > "$PID_FILE"
        return 0
    fi
    return 1
}

# 启动后端
start_backend() {
    if [ ! -f "$VENV_PYTHON" ]; then
        log_err "虚拟环境 Python 不存在: $VENV_PYTHON"
        return 1
    fi
    if [ ! -f "$BACKEND_ENTRY" ]; then
        log_err "后端入口文件不存在: $BACKEND_ENTRY"
        return 1
    fi

    log_info "启动后端..."
    cd "$SCRIPT_DIR/backend"
    PYTHONPATH="$SCRIPT_DIR" nohup "$VENV_PYTHON" -m uvicorn core.api.main:app \
        --host 0.0.0.0 --port "$BACKEND_PORT" \
        < /dev/null >> "$BACKEND_LOG" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    cd "$SCRIPT_DIR"

    # 等待就绪
    local waited=0
    while [ $waited -lt 30 ]; do
        sleep 1
        waited=$((waited + 1))
        if lsof -i :"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null | grep -q .; then
            log_info "后端启动成功 (PID: $pid, 耗时 ${waited}s)"
            return 0
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            log_err "后端进程已退出，启动失败"
            return 1
        fi
    done
    log_err "后端启动超时"
    return 1
}

# 停止后端
stop_backend() {
    log_info "停止后端..."

    # 先通过 PID 文件停止
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 2
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$PID_FILE"
    fi

    # 清理端口占用
    local lport_pid
    lport_pid=$(lsof -t -i :"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$lport_pid" ]; then
        kill "$lport_pid" 2>/dev/null || true
        sleep 1
        kill -9 "$lport_pid" 2>/dev/null || true
    fi
    log_info "后端已停止"
}

# 监控模式：循环检查
watchdog_loop() {
    # 写入看门狗 PID
    echo "$$" > "$WATCHDOG_PID_FILE"

    log_info "================================"
    log_info "看门狗启动 (PID: $$)"
    log_info "项目目录: $SCRIPT_DIR"
    log_info "================================"

    # 首次启动
    if ! is_backend_running; then
        start_backend || true
    fi

    # 循环检查（每 15 秒一次）
    while true; do
        if ! is_backend_running; then
            log_warn "后端进程已停止，正在重启..."
            start_backend || log_err "重启失败"
        fi
        sleep 15
    done
}

# 检查一次
check_once() {
    if is_backend_running; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null || echo "unknown")
        echo "后端运行中 (PID: $pid)"
        return 0
    fi
    echo "后端未运行，正在启动..."
    start_backend
}

# 主入口
case "${1:-check}" in
    start)
        # 后台运行
        nohup bash "$0" watchdog_loop < /dev/null >> "$WATCHDOG_LOG" 2>&1 &
        echo "看门狗已启动 (PID: $!)"
        ;;
    stop)
        if [ -f "$WATCHDOG_PID_FILE" ]; then
            local wpid
            wpid=$(cat "$WATCHDOG_PID_FILE")
            kill "$wpid" 2>/dev/null || true
            rm -f "$WATCHDOG_PID_FILE"
        fi
        stop_backend
        echo "看门狗已停止"
        ;;
    watchdog_loop)
        watchdog_loop
        ;;
    check)
        check_once
        ;;
    *)
        echo "用法: $0 {start|stop|check}"
        exit 1
        ;;
esac