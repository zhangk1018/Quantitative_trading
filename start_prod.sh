#!/bin/bash
# ============================================
# start_prod.sh - 量化交易系统生产部署脚本
# ============================================
# 用法:
#   ./start_prod.sh build    # 构建镜像
#   ./start_prod.sh start    # 启动所有服务
#   ./start_prod.sh stop     # 停止所有服务
#   ./start_prod.sh restart  # 重启所有服务
#   ./start_prod.sh status   # 查看服务状态
#   ./start_prod.sh health   # 健康检查
#   ./start_prod.sh logs     # 查看日志（全部）
#   ./start_prod.sh logs <svc> # 查看指定服务日志
#   ./start_prod.sh psql     # 进入数据库
#   ./start_prod.sh shell <svc> # 进入容器 shell
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose.yml"
FRONTEND_COMPOSE="docker-compose.frontend.yml"
ENV_FILE=".env.production"

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ---- 前置检查 ----
check_env() {
    if [ ! -f "$ENV_FILE" ]; then
        log_warn ".env.production 不存在，从模板创建..."
        if [ -f ".env.production.example" ]; then
            cp .env.production.example "$ENV_FILE"
            log_info "已创建 $ENV_FILE，请编辑并填入密码"
        else
            log_error ".env.production.example 也不存在"
            exit 1
        fi
    fi
    if grep -q "CHANGE_ME" "$ENV_FILE" 2>/dev/null; then
        log_warn "$ENV_FILE 中仍有 CHANGE_ME 占位符，请先编辑"
    fi
}

# ---- 命令：构建镜像 ----
cmd_build() {
    log_info "构建后端镜像..."
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build backend

    log_info "构建前端镜像..."
    docker compose --env-file "$ENV_FILE" -f "$FRONTEND_COMPOSE" build frontend

    log_info "镜像构建完成"
}

# ---- 命令：启动 ----
cmd_start() {
    check_env
    log_info "启动所有服务（后台模式）..."
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d
    docker compose --env-file "$ENV_FILE" -f "$FRONTEND_COMPOSE" up -d
    log_info "服务已启动（5-10s 后健康）"
    cmd_status
}

# ---- 命令：停止 ----
cmd_stop() {
    log_info "停止所有服务..."
    docker compose --env-file "$ENV_FILE" -f "$FRONTEND_COMPOSE" down 2>/dev/null || true
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down 2>/dev/null || true
    log_info "服务已停止"
}

# ---- 命令：重启 ----
cmd_restart() {
    cmd_stop
    sleep 2
    cmd_start
}

# ---- 命令：状态 ----
cmd_status() {
    echo ""
    echo "SERVICE          STATE    PORTS"
    echo "----------------------------------------"
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.State}}\t{{.Ports}}" 2>/dev/null || echo "(后端服务未运行)"
    docker compose --env-file "$ENV_FILE" -f "$FRONTEND_COMPOSE" ps --format "table {{.Name}}\t{{.State}}\t{{.Ports}}" 2>/dev/null || echo "(前端服务未运行)"
    echo ""
}

# ---- 命令：健康检查 ----
cmd_health() {
    echo ""
    echo "=== 容器状态 ==="
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps 2>/dev/null

    echo ""
    echo "=== API 健康检查 ==="

    # Nginx
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/nginx-health 2>/dev/null || echo "000")
    [ "$HTTP_CODE" = "200" ] && echo "✅ Nginx: $HTTP_CODE" || echo "❌ Nginx: $HTTP_CODE"

    # Backend health
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health 2>/dev/null || echo "000")
    [ "$HTTP_CODE" = "200" ] && echo "✅ Backend /health: $HTTP_CODE" || echo "❌ Backend /health: $HTTP_CODE"

    # API meta
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/meta/ 2>/dev/null || echo "000")
    [ "$HTTP_CODE" = "200" ] && echo "✅ API /api/meta/: $HTTP_CODE" || echo "❌ API /api/meta/: $HTTP_CODE"

    # API stocks
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/stocks/ 2>/dev/null || echo "000")
    [ "$HTTP_CODE" = "200" ] && echo "✅ API /api/stocks/: $HTTP_CODE" || echo "❌ API /api/stocks/: $HTTP_CODE"

    echo ""
    echo "=== 资源使用 ==="
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
        $(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps -q 2>/dev/null) 2>/dev/null || true
    echo ""
}

# ---- 命令：日志 ----
cmd_logs() {
    SERVICE="$2"
    if [ -n "$SERVICE" ]; then
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs -f --tail=100 "$SERVICE"
    else
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs -f --tail=50
    fi
}

# ---- 命令：数据库 ----
cmd_psql() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec postgres \
        psql -U "${PG_USER:-quant_user}" -d "${PG_DATABASE:-quant_trading}"
}

# ---- 命令：Shell ----
cmd_shell() {
    SERVICE="${2:-backend}"
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec "$SERVICE" /bin/bash
}

# ---- 主入口 ----
ACTION="${1:-}"
case "$ACTION" in
    build)   cmd_build ;;
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    health)  cmd_health ;;
    logs)    cmd_logs "$@" ;;
    psql)    cmd_psql ;;
    shell)   cmd_shell "$@" ;;
    *)
        echo "用法: $0 {build|start|stop|restart|status|health|logs [service]|psql|shell [service]}"
        echo ""
        echo "  build   — 构建镜像（首次部署或代码变更后）"
        echo "  start   — 启动所有服务"
        echo "  stop    — 停止所有服务"
        echo "  restart — 重启所有服务"
        echo "  status  — 查看服务状态"
        echo "  health  — 健康检查（含 API 探测）"
        echo "  logs     — 查看日志（可选：logs [service]）"
        echo "  psql    — 进入 PostgreSQL"
        echo "  shell   — 进入容器 shell（默认 backend）"
        exit 1
        ;;
esac
