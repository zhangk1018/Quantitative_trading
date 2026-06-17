#!/usr/bin/env bash
# ============================================
# start.sh - 量化交易系统统一启停脚本
# ============================================
# 用法:
#   ./start.sh dev start|stop|restart|status    # 原生开发模式
#   ./start.sh prod build|start|stop|restart    # Docker 生产模式
#   ./start.sh install                          # 安装依赖
#   ./start.sh check                            # 检查环境
#   ./start.sh logs [svc]                       # 查看日志
#   ./start.sh health                           # 健康检查
#   ./start.sh psql                             # 进入数据库
#   ./start.sh clean|nuke                       # 清理
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

# ---- 路径配置 ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/quant-trading-frontend"
VENV_DIR="$SCRIPT_DIR/venv"

# PID 文件
BACKEND_PID_FILE="/tmp/quant_backend.pid"
FRONTEND_PID_FILE="/tmp/quant_frontend.pid"

# 端口
BACKEND_PORT=8000
FRONTEND_PORT=5173

# 日志
BACKEND_LOG="$SCRIPT_DIR/logs/quant_backend.log"
FRONTEND_LOG="$SCRIPT_DIR/logs/quant_frontend.log"
mkdir -p "$SCRIPT_DIR/logs"

# Docker 配置
COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env.production"
PROJECT_NAME="quant-trading"

# ============================================
# 辅助函数
# ============================================

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
        if [ -n "$pid" ]; then echo "$pid"; return 0; fi
    fi
    return 1
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_err "Docker 未安装"; exit 1
    fi
    if ! docker info &> /dev/null; then
        log_err "Docker daemon 未运行"; exit 1
    fi
}

check_env_file() {
    if [ ! -f "$ENV_FILE" ]; then
        log_warn "未找到 $ENV_FILE，正在从模板创建"
        if [ ! -f ".env.production.example" ]; then
            log_err ".env.production.example 模板不存在"; exit 1
        fi
        cp .env.production.example .env.production
        log_warn "已生成 .env.production，请编辑密码后重新运行"
        exit 0
    fi
}

# ============================================
# 安装 & 检查
# ============================================

cmd_install() {
    echo -e "${YELLOW}============================================${NC}"
    echo -e "${YELLOW}  安装系统依赖${NC}"
    echo -e "${YELLOW}============================================${NC}"

    # 后端
    if [ -d "$VENV_DIR" ]; then
        log_warn "虚拟环境已存在，跳过创建"
    else
        log_info "创建虚拟环境..."
        python3 -m venv "$VENV_DIR" || { log_err "创建虚拟环境失败"; return 1; }
    fi

    source "$VENV_DIR/bin/activate"
    if [ ! -f "$BACKEND_DIR/requirements.txt" ]; then
        log_err "未找到 requirements.txt"; return 1
    fi
    log_info "安装 Python 依赖..."
    pip install -r "$BACKEND_DIR/requirements.txt" -q || { log_err "依赖安装失败"; return 1; }
    log_ok "后端依赖安装成功"

    # 前端
    if ! command -v npm &> /dev/null; then
        log_err "npm 未安装，请先安装 Node.js"; return 1
    fi
    if [ ! -d "$FRONTEND_DIR" ]; then
        log_err "前端目录不存在: $FRONTEND_DIR"; return 1
    fi
    if [ -d "$FRONTEND_DIR/node_modules" ]; then
        log_warn "前端依赖已安装，跳过"
    else
        log_info "安装 npm 依赖..."
        cd "$FRONTEND_DIR" && npm install -q || { log_err "前端依赖安装失败"; return 1; }
        log_ok "前端依赖安装成功"
    fi
}

cmd_check() {
    echo -e "${YELLOW}============================================${NC}"
    echo -e "${YELLOW}  检查运行环境${NC}"
    echo -e "${YELLOW}============================================${NC}"

    command -v python3 &> /dev/null && echo -e "${GREEN}✅ Python3: $(python3 --version | cut -d' ' -f2)${NC}" || echo -e "${RED}❌ Python3 未安装${NC}"
    command -v node &> /dev/null && echo -e "${GREEN}✅ Node.js: $(node --version)${NC}" || echo -e "${RED}❌ Node.js 未安装${NC}"
    [ -d "$VENV_DIR" ] && echo -e "${GREEN}✅ 虚拟环境: 已创建${NC}" || echo -e "${YELLOW}⚠️ 虚拟环境: 未创建${NC}"
    [ -d "$BACKEND_DIR" ] && echo -e "${GREEN}✅ 后端目录: 存在${NC}" || echo -e "${RED}❌ 后端目录: 不存在${NC}"
    [ -d "$FRONTEND_DIR" ] && echo -e "${GREEN}✅ 前端目录: 存在${NC}" || echo -e "${RED}❌ 前端目录: 不存在${NC}"
    [ -f "$BACKEND_DIR/core/api/main.py" ] && echo -e "${GREEN}✅ 后端入口: core/api/main.py${NC}" || echo -e "${RED}❌ 后端入口: 不存在${NC}"

    echo ""
    echo -e "${YELLOW}📡 端口检查:${NC}"
    is_port_in_use "$BACKEND_PORT" && echo -e "${RED}❌ 端口 $BACKEND_PORT 已被占用${NC}" || echo -e "${GREEN}✅ 端口 $BACKEND_PORT: 可用${NC}"
    is_port_in_use "$FRONTEND_PORT" && echo -e "${RED}❌ 端口 $FRONTEND_PORT 已被占用${NC}" || echo -e "${GREEN}✅ 端口 $FRONTEND_PORT: 可用${NC}"
}

# ============================================
# 原生开发模式 (dev)
# ============================================

dev_start_backend() {
    log_info "启动后端服务..."
    if check_pid "$BACKEND_PID_FILE" "$BACKEND_PORT"; then
        log_ok "后端服务已在运行 (端口: $BACKEND_PORT)"; return 0
    fi
    if is_port_in_use "$BACKEND_PORT"; then
        local old_pid=$(find_pid_by_port "$BACKEND_PORT")
        log_warn "端口 $BACKEND_PORT 被占用 (PID: ${old_pid:-unknown})，正在清理..."
        [ -n "$old_pid" ] && { kill "$old_pid" 2>/dev/null; sleep 2; kill -9 "$old_pid" 2>/dev/null; }
        rm -f "$BACKEND_PID_FILE"
    fi
    if [ ! -d "$VENV_DIR" ]; then
        log_err "虚拟环境不存在，请先执行: ./start.sh install"; return 1
    fi
    if [ ! -f "$BACKEND_DIR/core/api/main.py" ]; then
        log_err "后端入口文件不存在: core/api/main.py"; return 1
    fi

    cd "$BACKEND_DIR"
    export PYTHONPATH="$SCRIPT_DIR"
    nohup "$VENV_DIR/bin/python" -m uvicorn core.api.main:app --host 0.0.0.0 --port "$BACKEND_PORT" > "$BACKEND_LOG" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$BACKEND_PID_FILE"

    for i in $(seq 1 10); do
        sleep 1
        if is_port_in_use "$BACKEND_PORT"; then
            log_ok "后端服务启动成功 (PID: $new_pid, 端口: $BACKEND_PORT)"; return 0
        fi
    done
    log_err "后端服务启动失败（10秒超时），查看日志: $BACKEND_LOG"
    rm -f "$BACKEND_PID_FILE"; return 1
}

dev_stop_backend() {
    log_info "停止后端服务..."
    local stopped=0
    if [ -f "$BACKEND_PID_FILE" ]; then
        local pid=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true; sleep 2; kill -9 "$pid" 2>/dev/null || true; stopped=1
        fi
        rm -f "$BACKEND_PID_FILE"
    fi
    if is_port_in_use "$BACKEND_PORT"; then
        local port_pid=$(find_pid_by_port "$BACKEND_PORT")
        if [ -n "$port_pid" ]; then
            log_warn "发现端口 $BACKEND_PORT 残留进程 (PID: $port_pid)，正在终止..."
            kill "$port_pid" 2>/dev/null || true; sleep 2; kill -9 "$port_pid" 2>/dev/null || true; stopped=1
        fi
    fi
    [ $stopped -eq 1 ] && log_ok "后端服务已停止" || log_warn "后端服务未运行"
}

dev_start_frontend() {
    log_info "启动前端服务..."
    if check_pid "$FRONTEND_PID_FILE" "$FRONTEND_PORT"; then
        log_ok "前端服务已在运行 (端口: $FRONTEND_PORT)"; return 0
    fi
    if is_port_in_use "$FRONTEND_PORT"; then
        local old_pid=$(find_pid_by_port "$FRONTEND_PORT")
        log_warn "端口 $FRONTEND_PORT 被占用 (PID: ${old_pid:-unknown})，正在清理..."
        [ -n "$old_pid" ] && { kill "$old_pid" 2>/dev/null; sleep 2; kill -9 "$old_pid" 2>/dev/null; }
        rm -f "$FRONTEND_PID_FILE"
    fi
    if ! command -v npm &> /dev/null; then
        log_err "npm 未安装"; return 1
    fi
    if [ ! -d "$FRONTEND_DIR" ]; then
        log_err "前端目录不存在: $FRONTEND_DIR"; return 1
    fi
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        log_info "安装前端依赖..."
        cd "$FRONTEND_DIR" && npm install -q || { log_err "前端依赖安装失败"; return 1; }
    fi

    cd "$FRONTEND_DIR"
    nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" > "$FRONTEND_LOG" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$FRONTEND_PID_FILE"

    for i in $(seq 1 8); do
        sleep 1
        if is_port_in_use "$FRONTEND_PORT"; then
            log_ok "前端服务启动成功 (PID: $new_pid, 端口: $FRONTEND_PORT)"; return 0
        fi
    done
    log_err "前端服务启动失败（8秒超时），查看日志: $FRONTEND_LOG"
    rm -f "$FRONTEND_PID_FILE"; return 1
}

dev_stop_frontend() {
    log_info "停止前端服务..."
    local stopped=0
    if [ -f "$FRONTEND_PID_FILE" ]; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true; sleep 2; kill -9 "$pid" 2>/dev/null || true; stopped=1
        fi
        rm -f "$FRONTEND_PID_FILE"
    fi
    if is_port_in_use "$FRONTEND_PORT"; then
        local port_pid=$(find_pid_by_port "$FRONTEND_PORT")
        if [ -n "$port_pid" ]; then
            log_warn "发现端口 $FRONTEND_PORT 残留进程 (PID: $port_pid)，正在终止..."
            kill "$port_pid" 2>/dev/null || true; sleep 2; kill -9 "$port_pid" 2>/dev/null || true; stopped=1
        fi
    fi
    [ $stopped -eq 1 ] && log_ok "前端服务已停止" || log_warn "前端服务未运行"
}

dev_status() {
    echo -e "${YELLOW}============================================${NC}"
    echo -e "${YELLOW}  服务状态（开发模式）${NC}"
    echo -e "${YELLOW}============================================${NC}"

    echo -n "后端服务: "
    if check_pid "$BACKEND_PID_FILE" "$BACKEND_PORT"; then
        echo -e "${GREEN}✅ 运行中 (PID: $(check_pid "$BACKEND_PID_FILE" "$BACKEND_PORT"), 端口: $BACKEND_PORT)${NC}"
    else echo -e "${RED}❌ 未运行${NC}"; fi

    echo -n "前端服务: "
    if check_pid "$FRONTEND_PID_FILE" "$FRONTEND_PORT"; then
        echo -e "${GREEN}✅ 运行中 (PID: $(check_pid "$FRONTEND_PID_FILE" "$FRONTEND_PORT"), 端口: $FRONTEND_PORT)${NC}"
    else echo -e "${RED}❌ 未运行${NC}"; fi

    echo ""
    echo "访问地址:"
    echo "  前端页面: http://localhost:$FRONTEND_PORT"
    echo "  后端API:  http://localhost:$BACKEND_PORT/api"
    echo "  API文档:  http://localhost:$BACKEND_PORT/docs"
    echo "  系统看板: http://localhost:$BACKEND_PORT/admin"
    echo "============================================"
}

dev_start() {
    dev_start_backend && dev_start_frontend
    echo ""; dev_status
}

dev_stop() {
    dev_stop_backend; dev_stop_frontend
}

dev_restart() {
    dev_stop; sleep 1; dev_start
}

# ============================================
# Docker 生产模式 (prod)
# ============================================

prod_build() {
    check_docker; check_env_file
    log_info "构建 Docker 镜像..."
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" build --no-cache
    log_ok "镜像构建完成"
}

prod_start() {
    check_docker; check_env_file
    log_info "启动服务..."
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" up -d
    log_ok "服务已启动"
    sleep 3
    log_info "等待后端就绪..."
    for i in $(seq 1 10); do
        if curl -fsS http://localhost/health > /dev/null 2>&1; then
            log_ok "后端就绪"; break
        fi
        sleep 3
    done
    log_info "访问: http://localhost/  管理: http://localhost/admin"
}

prod_stop() {
    check_docker
    log_info "停止服务..."
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" stop
    log_ok "服务已停止"
}

prod_down() {
    check_docker
    log_info "停止并移除容器（保留数据卷）..."
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" down
    log_ok "容器已移除，数据卷保留"
}

prod_restart() {
    check_docker
    log_info "重启服务..."
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" restart
    log_ok "服务已重启"
}

prod_status() {
    check_docker
    echo; log_info "服务状态:"
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" ps
    echo; log_info "健康检查:"
    printf "  Nginx:    "
    curl -fsS http://localhost/nginx-health > /dev/null 2>&1 && echo -e "${GREEN}OK${NC}" || echo -e "${RED}FAIL${NC}"
    printf "  后端API:  "
    curl -fsS http://localhost/health > /dev/null 2>&1 && echo -e "${GREEN}OK${NC}" || echo -e "${RED}FAIL${NC}"
    printf "  前端:     "
    curl -fsS http://localhost/ > /dev/null 2>&1 && echo -e "${GREEN}OK${NC}" || echo -e "${RED}FAIL${NC}"
}

prod_health() {
    check_docker
    log_info "详细健康检查:"; echo

    echo -e "${BLUE}=== 容器状态 ===${NC}"
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" ps --format "table {{.Name}}\t{{.State}}\t{{.Status}}"
    echo

    echo -e "${BLUE}=== API 健康 ===${NC}"
    for endpoint in /nginx-health /health /api/meta/ /api/stocks/; do
        printf "  %-25s " "$endpoint"
        local code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost$endpoint" 2>/dev/null || echo "000")
        [[ "$code" =~ ^2 ]] && echo -e "${GREEN}OK ($code)${NC}" || echo -e "${RED}FAIL ($code)${NC}"
    done
    echo

    echo -e "${BLUE}=== 数据库连接 ===${NC}"
    if docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" exec -T postgres \
        pg_isready -U "${PG_USER:-quant_user}" -d "${PG_DATABASE:-quant_trading}" > /dev/null 2>&1; then
        echo -e "  PostgreSQL:   ${GREEN}OK${NC}"
    else echo -e "  PostgreSQL:   ${RED}FAIL${NC}"; fi
    echo

    echo -e "${BLUE}=== 资源使用 ===${NC}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" \
        $(docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" ps -q 2>/dev/null) 2>/dev/null || true
}

prod_logs() {
    check_docker
    local svc="${1:-}"
    if [ -n "$svc" ]; then
        docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" logs -f --tail=100 "$svc"
    else
        docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" logs -f --tail=100
    fi
}

prod_psql() {
    check_docker
    log_info "进入 PostgreSQL CLI（输入 \\q 退出）"
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" exec postgres \
        psql -U "${PG_USER:-quant_user}" -d "${PG_DATABASE:-quant_trading}"
}

prod_shell() {
    check_docker
    local svc="${1:-backend}"
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" exec "$svc" /bin/bash
}

prod_clean() {
    check_docker
    log_warn "清理（停服务+删容器，数据卷保留）"
    local confirm
    read -n 200 -t 30 -p "确认? [y/N] " confirm
    echo
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" down
        docker image prune -f
        log_ok "清理完成"
    else log_info "已取消"; fi
}

prod_nuke() {
    check_docker
    log_err "彻底清理（含数据卷，会删除所有数据）"
    local confirm
    read -n 200 -t 30 -p "确认? [y/N] " confirm
    echo
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" down -v
        docker image prune -af
        log_ok "彻底清理完成"
    else log_info "已取消"; fi
}

# ============================================
# 通用命令
# ============================================

cmd_logs() {
    local svc="${1:-}"
    if [ -n "$svc" ]; then
        case "$svc" in
            backend)  tail -f "$BACKEND_LOG" ;;
            frontend) tail -f "$FRONTEND_LOG" ;;
            *)        prod_logs "$svc" ;;
        esac
    else
        log_err "请指定服务名: backend|frontend 或使用 prod logs"
    fi
}

# ============================================
# 主入口
# ============================================

cmd_help() {
    cat <<'EOF'
量化交易系统统一启停脚本

用法:
  ./start.sh <mode> <command> [args...]

模式:
  dev             原生开发模式（后端 + 前端）
  prod            Docker 生产模式
  (无模式)        通用命令

开发模式命令 (dev):
  start           启动后端和前端服务
  stop            停止所有服务
  restart         重启所有服务
  status          查看服务状态

生产模式命令 (prod):
  build           构建 Docker 镜像
  start           启动所有服务
  stop            停止服务
  down            停止并移除容器（保留数据卷）
  restart         重启服务
  status          查看服务状态
  health          详细健康检查
  logs [svc]      查看日志
  psql            进入数据库
  shell [svc]     进入容器 shell
  clean           清理（保留数据卷）
  nuke            彻底清理（含数据卷）

通用命令:
  install         安装后端和前端依赖
  check           检查运行环境
  logs <svc>      查看开发模式日志 (backend|frontend|monitor)
  help            显示帮助

示例:
  ./start.sh install                    # 首次安装依赖
  ./start.sh check                      # 检查环境
  ./start.sh dev start                  # 启动开发环境
  ./start.sh dev status                 # 查看状态
  ./start.sh dev stop                   # 停止开发环境
  ./start.sh prod build                 # 构建生产镜像
  ./start.sh prod start                 # 启动生产环境
  ./start.sh prod health                # 健康检查
  ./start.sh logs backend               # 查看后端日志
EOF
}

case "${1:-help}" in
    dev)
        case "${2:-start}" in
            start)       dev_start ;;
            stop)        dev_stop ;;
            restart)     dev_restart ;;
            status)      dev_status ;;
            *)           log_err "未知命令: dev $2"; cmd_help ;;
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
            *)       log_err "未知命令: prod $2"; cmd_help ;;
        esac
        ;;
    install)   cmd_install ;;
    check)     cmd_check ;;
    logs)      shift; cmd_logs "$@" ;;
    help|--help|-h|*) cmd_help ;;
esac
