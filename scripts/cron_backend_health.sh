#!/bin/bash
# cron_backend_health.sh - 每分钟检测后端健康状态，异常时自动重启
# 由 crontab 调用，使用 cron 守护进程（系统进程，不会被 jetsam 杀死）
# 用法：bash scripts/cron_backend_health.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PID_FILE="/tmp/quant_backend.pid"
BACKEND_PORT=8000
HEALTH_LOG="$SCRIPT_DIR/logs/cron_health.log"
BACKEND_LOG="$SCRIPT_DIR/logs/quant_backend.log"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
BACKEND_ENTRY="$SCRIPT_DIR/backend/core/api/main.py"

# 日志函数（带日期）
log() {
    local level="$1"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*" >> "$HEALTH_LOG"
}

# 检查后端是否在运行
is_backend_running() {
    # 先检查 PID 文件
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            # 再确认端口
            if lsof -i :"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null | grep -q .; then
                return 0
            fi
            # PID 文件有效但端口不在监听，进程可能挂了
            log "WARN" "PID $pid 存在但端口 $BACKEND_PORT 未监听，清理 PID 文件"
            rm -f "$PID_FILE"
            return 1
        fi
        # PID 无效，清理
        rm -f "$PID_FILE"
    fi
    # 备用：直接检查端口
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
        log "ERR" "虚拟环境 Python 不存在: $VENV_PYTHON"
        return 1
    fi

    cd "$SCRIPT_DIR/backend"
    PYTHONPATH="$SCRIPT_DIR" nohup "$VENV_PYTHON" -m uvicorn core.api.main:app \
        --host 0.0.0.0 --port "$BACKEND_PORT" \
        < /dev/null >> "$BACKEND_LOG" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    cd "$SCRIPT_DIR"

    # 等待就绪（最多 30 秒）
    local waited=0
    while [ $waited -lt 30 ]; do
        sleep 1
        waited=$((waited + 1))
        if lsof -i :"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null | grep -q .; then
            log "OK" "后端启动成功 (PID: $pid, 耗时 ${waited}s)"
            return 0
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            log "ERR" "后端进程已退出，启动失败"
            return 1
        fi
    done
    log "ERR" "后端启动超时 (${waited}s)"
    return 1
}

# ========== 主逻辑 ==========
if is_backend_running; then
    exit 0
fi

# 后端未运行，尝试重启
log "WARN" "后端未运行（端口 $BACKEND_PORT 无监听），正在重启..."

# 清理可能残留的端口占用
lport_pid=$(lsof -t -i :"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$lport_pid" ]; then
    kill "$lport_pid" 2>/dev/null || true
    sleep 1
    kill -9 "$lport_pid" 2>/dev/null || true
fi

start_backend || log "ERR" "后端重启失败"