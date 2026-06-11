#!/usr/bin/env bash
# ============================================
# start_prod.sh - 量化交易系统生产环境管理脚本
# ============================================
# 用法:
#   ./start_prod.sh build      # 构建镜像
#   ./start_prod.sh start      # 启动所有服务
#   ./start_prod.sh stop       # 停止所有服务
#   ./start_prod.sh restart    # 重启
#   ./start_prod.sh status     # 查看状态
#   ./start_prod.sh logs [svc] # 查看日志（可选服务名：backend/frontend/postgres/redis）
#   ./start_prod.sh psql       # 进入 PostgreSQL CLI
#   ./start_prod.sh shell [svc]# 进入容器 shell
#   ./start_prod.sh health     # 健康检查
#   ./start_prod.sh clean      # 清理（停服务+删容器，不删数据卷）
#   ./start_prod.sh nuke       # 彻底清理（含数据卷，慎用）
# ============================================

set -e

# ---- 颜色输出 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ---- 路径定位 ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---- 配置 ----
COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env.production"
PROJECT_NAME="quant-trading"

# ---- 辅助函数 ----
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err()  { echo -e "${RED}[ERR]${NC} $1"; }

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_err "Docker 未安装，请先安装 Docker Desktop/Docker Engine"
        exit 1
    fi
    if ! docker info &> /dev/null; then
        log_err "Docker daemon 未运行，请启动 Docker"
        exit 1
    fi
}

check_env() {
    if [ ! -f "$ENV_FILE" ]; then
        log_warn "未找到 $ENV_FILE，正在从模板创建"
        if [ ! -f ".env.production.example" ]; then
            log_err ".env.production.example 模板不存在"
            exit 1
        fi
        cp .env.production.example .env.production
        log_warn "已生成 .env.production，请编辑密码后重新运行"
        log_warn "  vim .env.production  # 修改 PG_PASSWORD / PGADMIN_PASSWORD"
        exit 0
    fi
}

# ---- 命令实现 ----
cmd_build() {
    check_docker
    check_env
    log_info "构建 Docker 镜像..."
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" build --no-cache
    log_ok "镜像构建完成"
}

cmd_start() {
    check_docker
    check_env
    log_info "启动服务..."
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" up -d
    log_ok "服务已启动"
    sleep 3
    cmd_status
    log_info "等待后端就绪..."
    for i in 1 2 3 4 5 6 7 8 9 10; do
        if curl -fsS http://localhost/health > /dev/null 2>&1; then
            log_ok "后端就绪（http://localhost/health）"
            break
        fi
        sleep 3
    done
    log_info "访问地址: http://localhost/"
    log_info "管理后台: http://localhost/admin"
}

cmd_stop() {
    check_docker
    log_info "停止服务..."
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" stop
    log_ok "服务已停止"
}

cmd_down() {
    check_docker
    log_info "停止并移除容器（保留数据卷）..."
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" down
    log_ok "容器已移除，数据卷保留"
}

cmd_restart() {
    check_docker
    log_info "重启服务..."
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" restart
    log_ok "服务已重启"
}

cmd_status() {
    check_docker
    echo
    log_info "服务状态:"
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" ps
    echo
    log_info "健康检查:"
    printf "  Nginx:    "
    if curl -fsS http://localhost/nginx-health > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi
    printf "  后端API:  "
    if curl -fsS http://localhost/health > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi
    printf "  前端:     "
    if curl -fsS http://localhost/ > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi
}

cmd_logs() {
    check_docker
    local svc="${1:-}"
    if [ -n "$svc" ]; then
        docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" logs -f --tail=100 "$svc"
    else
        docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" logs -f --tail=100
    fi
}

cmd_psql() {
    check_docker
    log_info "进入 PostgreSQL CLI（输入 \\q 退出）"
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" exec postgres \
        psql -U "${PG_USER:-quant_user}" -d "${PG_DATABASE:-quant_trading}"
}

cmd_shell() {
    check_docker
    local svc="${1:-backend}"
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" exec "$svc" /bin/bash
}

cmd_health() {
    check_docker
    log_info "详细健康检查:"
    echo

    # 1. 容器状态
    echo -e "${BLUE}=== 容器状态 ===${NC}"
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" ps --format "table {{.Name}}\t{{.State}}\t{{.Status}}"
    echo

    # 2. API 健康
    echo -e "${BLUE}=== API 健康 ===${NC}"
    for endpoint in /nginx-health /health /api/meta/ /api/stocks/; do
        printf "  %-25s " "$endpoint"
        local code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost$endpoint" 2>/dev/null || echo "000")
        if [[ "$code" =~ ^2 ]]; then
            echo -e "${GREEN}OK ($code)${NC}"
        else
            echo -e "${RED}FAIL ($code)${NC}"
        fi
    done
    echo

    # 3. 数据库连接
    echo -e "${BLUE}=== 数据库连接 ===${NC}"
    if docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" exec -T postgres \
        pg_isready -U "${PG_USER:-quant_user}" -d "${PG_DATABASE:-quant_trading}" > /dev/null 2>&1; then
        echo -e "  PostgreSQL:   ${GREEN}OK${NC}"
    else
        echo -e "  PostgreSQL:   ${RED}FAIL${NC}"
    fi
    echo

    # 4. 资源使用
    echo -e "${BLUE}=== 资源使用 ===${NC}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" \
        $(docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" ps -q 2>/dev/null) 2>/dev/null || true
}

cmd_clean() {
    check_docker
    log_warn "清理（停服务+删容器，数据卷保留）"
    read -p "确认? [y/N] " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" down
        docker image prune -f
        log_ok "清理完成"
    else
        log_info "已取消"
    fi
}

cmd_nuke() {
    check_docker
    log_err "彻底清理（含数据卷，会删除所有数据）"
    read -p "确认? [y/N] " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" down -v
        docker image prune -af
        log_ok "彻底清理完成"
    else
        log_info "已取消"
    fi
}

cmd_help() {
    cat <<'EOF'
量化交易系统生产环境管理

用法:
  ./start_prod.sh <command> [args...]

命令:
  build       构建 Docker 镜像
  start       启动所有服务（构建+up -d）
  stop        停止服务（保留容器）
  down        停止并移除容器（保留数据卷）
  restart     重启所有服务
  status      查看服务状态
  health      详细健康检查（容器+API+DB+资源）
  logs [svc]  查看日志（可选服务名：backend/frontend/postgres/redis）
  psql        进入 PostgreSQL CLI
  shell [svc] 进入容器 shell（默认 backend）
  clean       清理：停服务+删容器+清理镜像（保留数据卷）
  nuke        彻底清理：含数据卷（慎用）
  help        显示帮助

示例:
  # 首次部署
  cp .env.production.example .env.production
  vim .env.production                          # 修改密码
  ./start_prod.sh build                        # 构建镜像
  ./start_prod.sh start                        # 启动服务

  # 日常运维
  ./start_prod.sh status                       # 查看状态
  ./start_prod.sh logs backend                 # 查看后端日志
  ./start_prod.sh restart                      # 重启

  # 调试
  ./start_prod.sh psql                         # 进入数据库
  ./start_prod.sh shell backend                # 进入后端容器
  ./start_prod.sh health                       # 详细健康检查

  # 维护
  ./start_prod.sh clean                        # 清理（保留数据）
  ./start_prod.sh nuke                         # 彻底清理
EOF
}

# ---- 主入口 ----
case "${1:-help}" in
    build)   cmd_build ;;
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    down)    cmd_down ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    health)  cmd_health ;;
    logs)    shift; cmd_logs "$@" ;;
    psql)    cmd_psql ;;
    shell)   shift; cmd_shell "$@" ;;
    clean)   cmd_clean ;;
    nuke)    cmd_nuke ;;
    help|--help|-h|*) cmd_help ;;
esac
