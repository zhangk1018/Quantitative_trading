#!/usr/bin/env bash
# ============================================
# start.sh - 量化交易系统统一启停脚本（最终优化版）
# ============================================
set -eo pipefail

# ---- 颜色输出 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err()  { echo -e "${RED}[ERR]${NC} $1"; }

# ---- 配置参数 ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/quant-trading-frontend"
VENV_DIR="$SCRIPT_DIR/venv"
BACKEND_PID_FILE="/tmp/quant_backend.pid"
FRONTEND_PID_FILE="/tmp/quant_frontend.pid"
BACKEND_PORT=8000
FRONTEND_PORT=5173
BACKEND_START_TIMEOUT=30
BACKEND_HEALTH_TIMEOUT=60
FRONTEND_START_TIMEOUT=8
BACKEND_LOG="$SCRIPT_DIR/logs/quant_backend.log"
FRONTEND_LOG="$SCRIPT_DIR/logs/quant_frontend.log"
mkdir -p "$SCRIPT_DIR/logs"

COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env.production"
PROJECT_NAME="quant-trading"

# ---- 通用进程管理 ----
find_pid_by_port() {
    lsof -t -i :"$1" -sTCP:LISTEN 2>/dev/null | head -1
}

is_port_in_use() {
    lsof -i :"$1" -sTCP:LISTEN >/dev/null 2>&1
}

check_pid() {
    local pid_file=$1 port=${2:-}
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"; return 0
        fi
        rm -f "$pid_file"
    fi
    if [ -n "$port" ]; then
        local pid=$(find_pid_by_port "$port")
        if [ -n "$pid" ]; then
            echo "$pid"; return 0
        fi
    fi
    return 1
}

# 简化归属判断（兼容 macOS）
is_our_process() {
    local pid=$1
    local comm=$(ps -p "$pid" -o comm= 2>/dev/null || true)
    [[ -z "$comm" ]] && return 1
    # 允许的进程名
    [[ ! "$comm" =~ ^(python|uvicorn|node|npm) ]] && return 1
    local args=$(ps -p "$pid" -o args= 2>/dev/null || true)
    # 检查是否包含项目路径或关键词
    [[ "$args" != *"$BACKEND_DIR"* && "$args" != *"$FRONTEND_DIR"* && "$args" != *"quant"* ]] && return 1
    return 0
}

# 安全终止：若提供 pid_file 且 PID 匹配则直接终止，否则做归属校验
kill_safely() {
    local pid=$1
    local pid_file=${2:-}
    # 如果提供了 pid_file，并且文件中的 PID 与当前一致，则直接信任
    if [ -n "$pid_file" ] && [ -f "$pid_file" ]; then
        local file_pid=$(cat "$pid_file")
        if [ "$file_pid" -eq "$pid" ] 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 2
            kill -9 "$pid" 2>/dev/null || true
            return 0
        fi
    fi
    # 否则走归属校验
    if ! is_our_process "$pid"; then
        log_warn "进程 $pid 不属于本项目，跳过终止"
        return 1
    fi
    kill "$pid" 2>/dev/null || true
    sleep 2
    kill -9 "$pid" 2>/dev/null || true
    return 0
}

# 清理端口：支持传入 pid_file 优先信任
clean_port() {
    local port=$1
    local pid_file=${2:-}
    if is_port_in_use "$port"; then
        local pid=$(find_pid_by_port "$port")
        if [ -n "$pid" ]; then
            log_warn "端口 $port 被占用 (PID: $pid)，尝试安全终止..."
            # 如果提供了 pid_file 且匹配，直接终止
            if [ -n "$pid_file" ] && [ -f "$pid_file" ]; then
                local file_pid=$(cat "$pid_file")
                if [ "$file_pid" -eq "$pid" ] 2>/dev/null; then
                    kill "$pid" 2>/dev/null || true
                    sleep 2
                    kill -9 "$pid" 2>/dev/null || true
                    log_info "已终止占用进程 $pid"
                    return 0
                fi
            fi
            # 否则调用 kill_safely（内部会做归属校验）
            if kill_safely "$pid"; then
                log_info "已终止占用进程 $pid"
            else
                log_err "无法终止进程 $pid，请手动处理"
                return 1
            fi
        fi
    fi
    return 0
}

# ---- 等待端口与健康检查 ----
wait_for_port() {
    local port=$1 timeout=$2 name=$3
    local waited=0
    while [ $waited -lt $timeout ]; do
        sleep 1; waited=$((waited + 1))
        if nc -z localhost "$port" 2>/dev/null; then
            log_ok "$name 端口 $port 监听成功 (耗时 ${waited}s)"
            return 0
        fi
    done
    log_warn "$name 端口 $port 在 ${timeout}s 内未监听"
    return 1
}

wait_for_health() {
    local url=$1 timeout=$2 name=$3
    local waited=0
    while [ $waited -lt $timeout ]; do
        sleep 1; waited=$((waited + 1))
        if curl -fsS "$url" > /dev/null 2>&1; then
            log_ok "$name 健康检查通过 (耗时 ${waited}s)"
            return 0
        fi
    done
    log_warn "$name 健康检查在 ${timeout}s 内未通过"
    return 1
}

# ---- 安全加载环境变量 ----
load_env() {
    local env_file="${1:-.env}"
    if [ -f "$env_file" ]; then
        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            if [[ "$line" =~ ^[[:space:]]*(QUANT_|PG_|BACKEND_|FRONTEND_)[[:alnum:]_]+= ]]; then
                export "$line"
            fi
        done < "$env_file"
        chmod 600 "$env_file" 2>/dev/null || log_warn "无法设置 $env_file 权限"
        log_info "已加载项目环境变量"
    else
        log_warn "未找到 $env_file"
    fi
}

# ---- 后端启动 ----
dev_start_backend() {
    log_info "启动后端服务..."
    if check_pid "$BACKEND_PID_FILE" "$BACKEND_PORT" >/dev/null; then
        log_ok "后端服务已在运行 (端口: $BACKEND_PORT)"
        return 0
    fi
    clean_port "$BACKEND_PORT" "$BACKEND_PID_FILE" || return 1
    rm -f "$BACKEND_PID_FILE"

    if [ ! -d "$VENV_DIR" ]; then
        log_err "虚拟环境不存在，请先执行 ./start.sh install"; return 1
    fi
    if [ ! -f "$BACKEND_DIR/core/api/main.py" ]; then
        log_err "后端入口文件不存在"; return 1
    fi

    cd "$BACKEND_DIR"
    export PYTHONPATH="$SCRIPT_DIR"
    load_env "$SCRIPT_DIR/.env"

    nohup "$VENV_DIR/bin/python" -m uvicorn core.api.main:app \
        --host 0.0.0.0 --port "$BACKEND_PORT" > "$BACKEND_LOG" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$BACKEND_PID_FILE"

    if ! wait_for_port "$BACKEND_PORT" "$BACKEND_START_TIMEOUT" "后端"; then
        if ps -p "$new_pid" >/dev/null 2>&1; then
            log_info "后端进程仍在运行，可能数据加载较慢"
        else
            log_err "后端进程已退出，查看日志"; tail -n 20 "$BACKEND_LOG"; rm -f "$BACKEND_PID_FILE"; return 1
        fi
    fi

    if wait_for_health "http://localhost:$BACKEND_PORT/health" "$BACKEND_HEALTH_TIMEOUT" "后端"; then
        log_ok "后端服务完全就绪"
    else
        log_warn "健康检查未通过，但进程仍在运行，请手动检查"
    fi
    return 0
}

dev_stop_backend() {
    log_info "停止后端服务..."
    local stopped=0
    if [ -f "$BACKEND_PID_FILE" ]; then
        local pid=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            if kill_safely "$pid" "$BACKEND_PID_FILE"; then
                stopped=1
            fi
        fi
        rm -f "$BACKEND_PID_FILE"
    fi
    if is_port_in_use "$BACKEND_PORT"; then
        clean_port "$BACKEND_PORT" "$BACKEND_PID_FILE" && stopped=1
    fi
    [ $stopped -eq 1 ] && log_ok "后端服务已停止" || log_warn "后端服务未运行"
}

# ---- 前端启动 ----
dev_start_frontend() {
    log_info "启动前端服务..."
    if check_pid "$FRONTEND_PID_FILE" "$FRONTEND_PORT" >/dev/null; then
        log_ok "前端服务已在运行 (端口: $FRONTEND_PORT)"
        return 0
    fi
    clean_port "$FRONTEND_PORT" "$FRONTEND_PID_FILE" || return 1
    rm -f "$FRONTEND_PID_FILE"

    if ! command -v npm &>/dev/null; then log_err "npm 未安装"; return 1; fi
    if [ ! -d "$FRONTEND_DIR" ]; then log_err "前端目录不存在"; return 1; fi
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        log_info "安装前端依赖..."
        cd "$FRONTEND_DIR" && npm install -q || { log_err "依赖安装失败"; return 1; }
    fi

    cd "$FRONTEND_DIR"
    nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" > "$FRONTEND_LOG" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$FRONTEND_PID_FILE"

    if wait_for_port "$FRONTEND_PORT" "$FRONTEND_START_TIMEOUT" "前端"; then
        log_ok "前端服务启动成功"
        return 0
    else
        log_err "前端启动失败"; tail -n 20 "$FRONTEND_LOG"; rm -f "$FRONTEND_PID_FILE"; return 1
    fi
}

dev_stop_frontend() {
    log_info "停止前端服务..."
    local stopped=0
    if [ -f "$FRONTEND_PID_FILE" ]; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            if kill_safely "$pid" "$FRONTEND_PID_FILE"; then
                stopped=1
            fi
        fi
        rm -f "$FRONTEND_PID_FILE"
    fi
    if is_port_in_use "$FRONTEND_PORT"; then
        clean_port "$FRONTEND_PORT" "$FRONTEND_PID_FILE" && stopped=1
    fi
    [ $stopped -eq 1 ] && log_ok "前端服务已停止" || log_warn "前端服务未运行"
}

# ---- 状态与组合命令 ----
dev_status() {
    echo -e "${YELLOW}============================================${NC}"
    echo -e "${YELLOW}  服务状态（开发模式）${NC}"
    echo -e "${YELLOW}============================================${NC}"
    local bp=$(check_pid "$BACKEND_PID_FILE" "$BACKEND_PORT")
    echo -n "后端服务: "
    if [ -n "$bp" ]; then
        echo -e "${GREEN}✅ 运行中 (PID: $bp, 端口: $BACKEND_PORT)${NC}"
    else
        echo -e "${RED}❌ 未运行${NC}"
    fi
    local fp=$(check_pid "$FRONTEND_PID_FILE" "$FRONTEND_PORT")
    echo -n "前端服务: "
    if [ -n "$fp" ]; then
        echo -e "${GREEN}✅ 运行中 (PID: $fp, 端口: $FRONTEND_PORT)${NC}"
    else
        echo -e "${RED}❌ 未运行${NC}"
    fi
    echo -e "\n访问地址:\n  前端页面: http://localhost:$FRONTEND_PORT\n  后端API:  http://localhost:$BACKEND_PORT/api\n  API文档:  http://localhost:$BACKEND_PORT/docs\n  系统看板: http://localhost:$BACKEND_PORT/admin"
    echo "============================================"
}

dev_start() { dev_start_backend && dev_start_frontend; echo ""; dev_status; }
dev_stop() { dev_stop_backend; dev_stop_frontend; }
dev_restart() { dev_stop; sleep 1; dev_start; }

# ---- 前台启动（调试用） ----
dev_start_backend_fg() {
    log_info "前台启动后端服务（调试模式）..."
    if is_port_in_use "$BACKEND_PORT"; then
        clean_port "$BACKEND_PORT" "$BACKEND_PID_FILE" || return 1
    fi
    rm -f "$BACKEND_PID_FILE"

    if [ ! -d "$VENV_DIR" ]; then
        log_err "虚拟环境不存在，请先执行 ./start.sh install"; return 1
    fi
    if [ ! -f "$BACKEND_DIR/core/api/main.py" ]; then
        log_err "后端入口文件不存在"; return 1
    fi

    cd "$BACKEND_DIR"
    export PYTHONPATH="$SCRIPT_DIR"
    load_env "$SCRIPT_DIR/.env"

    log_info "执行: uvicorn core.api.main:app --host 0.0.0.0 --port $BACKEND_PORT"
    echo -e "${YELLOW}按 Ctrl+C 停止${NC}"
    exec "$VENV_DIR/bin/python" -m uvicorn core.api.main:app \
        --host 0.0.0.0 --port "$BACKEND_PORT"
}

dev_start_frontend_fg() {
    log_info "前台启动前端服务（调试模式）..."
    if is_port_in_use "$FRONTEND_PORT"; then
        clean_port "$FRONTEND_PORT" "$FRONTEND_PID_FILE" || return 1
    fi
    rm -f "$FRONTEND_PID_FILE"

    if ! command -v npm &>/dev/null; then log_err "npm 未安装"; return 1; fi
    if [ ! -d "$FRONTEND_DIR" ]; then log_err "前端目录不存在"; return 1; fi
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        log_info "安装前端依赖..."
        cd "$FRONTEND_DIR" && npm install -q || { log_err "依赖安装失败"; return 1; }
    fi

    cd "$FRONTEND_DIR"
    log_info "执行: npm run dev -- --host 0.0.0.0 --port $FRONTEND_PORT"
    echo -e "${YELLOW}按 Ctrl+C 停止${NC}"
    exec npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
}

# ---- 生产模式（保持原有） ----
check_docker() {
    if ! command -v docker &> /dev/null; then log_err "Docker 未安装"; exit 1; fi
    if ! docker info &> /dev/null; then log_err "Docker daemon 未运行"; exit 1; fi
}
check_env_file() {
    if [ ! -f "$ENV_FILE" ]; then
        log_warn "未找到 $ENV_FILE，从模板创建"
        cp .env.production.example "$ENV_FILE" 2>/dev/null || { log_err "模板不存在"; exit 1; }
        chmod 600 "$ENV_FILE"
        log_warn "请编辑 $ENV_FILE 后重新运行"; exit 0
    fi
}
prod_build() { check_docker; check_env_file; log_info "构建镜像..."; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" build --no-cache; log_ok "完成"; }
prod_start() { check_docker; check_env_file; log_info "启动服务..."; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" up -d; log_ok "已启动"; }
prod_stop() { check_docker; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" stop; log_ok "已停止"; }
prod_down() { check_docker; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" down; log_ok "已移除容器"; }
prod_restart() { check_docker; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" restart; log_ok "已重启"; }
prod_status() { check_docker; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" ps; }
prod_health() { check_docker; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" exec -T backend curl -fsS http://localhost/health || log_err "后端不健康"; }
prod_logs() { check_docker; local svc="${1:-}"; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" logs -f --tail=100 "$svc"; }
prod_psql() { check_docker; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" exec postgres psql -U "${PG_USER:-quant_user}" -d "${PG_DATABASE:-quant_trading}"; }
prod_shell() { check_docker; local svc="${1:-backend}"; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" exec "$svc" /bin/bash; }
prod_clean() { check_docker; log_warn "清理容器（保留数据卷）"; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" down; }
prod_nuke() { check_docker; log_err "彻底清理（删除数据卷）"; docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" down -v; docker image prune -af; }

# ---- 通用命令 ----
cmd_install() {
    echo -e "${YELLOW}安装依赖...${NC}"
    [ -d "$VENV_DIR" ] || python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install -r "$BACKEND_DIR/requirements.txt" -q || { log_err "后端安装失败"; return 1; }
    cd "$FRONTEND_DIR" && npm install -q || { log_err "前端安装失败"; return 1; }
    log_ok "全部依赖安装完成"
}
cmd_check() {
    echo -e "${YELLOW}环境检查${NC}"
    command -v python3 && echo -e "${GREEN}✅ Python3: $(python3 --version)${NC}" || echo -e "${RED}❌ Python3${NC}"
    command -v node && echo -e "${GREEN}✅ Node.js: $(node --version)${NC}" || echo -e "${RED}❌ Node.js${NC}"
    [ -d "$VENV_DIR" ] && echo -e "${GREEN}✅ venv${NC}" || echo -e "${YELLOW}⚠️ venv 未创建${NC}"
    is_port_in_use "$BACKEND_PORT" && echo -e "${RED}❌ 端口 $BACKEND_PORT 被占用${NC}" || echo -e "${GREEN}✅ 端口 $BACKEND_PORT 可用${NC}"
    is_port_in_use "$FRONTEND_PORT" && echo -e "${RED}❌ 端口 $FRONTEND_PORT 被占用${NC}" || echo -e "${GREEN}✅ 端口 $FRONTEND_PORT 可用${NC}"
}
cmd_logs() {
    local svc="${1:-}"
    case "$svc" in
        backend)  tail -f "$BACKEND_LOG" ;;
        frontend) tail -f "$FRONTEND_LOG" ;;
        *)        log_err "请指定 backend 或 frontend" ;;
    esac
}
cmd_help() {
    cat <<'EOF'
用法:
  ./start.sh <mode> <command> [args]
  dev start|stop|restart|status                           # 前后台全部启停
  dev backend [bg|fg]                                     # 后端单独（默认后台）
  dev frontend [bg|fg]                                    # 前端单独（默认后台）
  prod build|start|stop|down|restart|status|health|logs|psql|shell|clean|nuke
  install|check|logs <svc>|help
EOF
}

# ---- 主入口 ----
case "${1:-help}" in
    dev)
        case "${2:-start}" in
            start)          dev_start ;;
            stop)           dev_stop ;;
            restart)        dev_restart ;;
            status)         dev_status ;;
            backend)         # 默认后台启动
                case "${3:-bg}" in
                    fg|foreground) dev_start_backend_fg ;;
                    bg|background|*) dev_start_backend ;;
                esac ;;
            frontend)
                case "${3:-bg}" in
                    fg|foreground) dev_start_frontend_fg ;;
                    bg|background|*) dev_start_frontend ;;
                esac ;;
            *)              log_err "未知 dev 命令"; cmd_help ;;
        esac
        ;;
    prod)
        case "${2:-start}" in
            build)   prod_build ;;
            start)   prod_start ;;
            stop)    prod_stop ;;
            down)    prod_down ;;
            restart) prod_restart ;;
            status)  prod_status ;;
            health)  prod_health ;;
            logs)    shift 2; prod_logs "$@" ;;
            psql)    prod_psql ;;
            shell)   shift 2; prod_shell "$@" ;;
            clean)   prod_clean ;;
            nuke)    prod_nuke ;;
            *)       log_err "未知 prod 命令"; cmd_help ;;
        esac
        ;;
    install) cmd_install ;;
    check)   cmd_check ;;
    logs)    shift; cmd_logs "$@" ;;
    help|*)  cmd_help ;;
esac