#!/bin/bash
# ============================================
# verify_prod.sh - Phase 5 上线验收脚本
# 用法: ./verify_prod.sh
# ============================================
# 验收项目：
#   1. 容器健康状态
#   2. API 端点响应
#   3. 数据库连通性
#   4. 容器资源使用
#   5. 近期日志错误扫描
# ============================================

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE=".env.production"
COMPOSE_FILE="docker-compose.yml"

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

log_pass()  { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS++)); }
log_fail()  { echo -e "${RED}[FAIL]${NC} $1"; ((FAIL++)); }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; ((WARN++)); }
log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
section()   { echo ""; echo "══════════════════════════════"; echo " $1"; echo "══════════════════════════════"; }

# ============================================================
# 1. 容器健康状态
# ============================================================
section "1. 容器健康状态"

# 检查容器是否在运行
for svc in postgres backend; do
    state=$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps -q "$svc" 2>/dev/null)
    if [ -n "$state" ]; then
        status=$(docker inspect --format='{{.State.Status}}' "$state" 2>/dev/null)
        health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$state" 2>/dev/null)
        if [ "$status" = "running" ]; then
            if [ "$health" = "healthy" ] || [ "$health" = "no-healthcheck" ]; then
                log_pass "容器 $svc: running, health=$health"
            else
                log_warn "容器 $svc: running, health=$health（等待健康中...）"
            fi
        else
            log_fail "容器 $svc: $status"
        fi
    else
        log_fail "容器 $svc: 不存在（未启动？）"
    fi
done

# ============================================================
# 2. API 端点响应
# ============================================================
section "2. API 端点响应"

BASE_URL="${API_BASE_URL:-http://localhost:8000}"

check_api() {
    local path="$1"
    local name="$2"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$BASE_URL$path" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        log_pass "$name ($path) → HTTP $code"
    elif [ "$code" = "401" ] || [ "$code" = "403" ]; then
        log_warn "$name ($path) → HTTP $code（需认证，预期）"
    else
        log_fail "$name ($path) → HTTP $code"
    fi
}

check_api "/health" "健康检查"
check_api "/api/meta/" "元数据 API"
check_api "/api/stocks/" "股票列表 API"
check_api "/api/kline/000001.SZ" "K线数据 API"

# ============================================================
# 3. 数据库连通性
# ============================================================
section "3. 数据库连通性"

# 通过 docker exec 连接 postgres
pg_result=$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "${PG_USER:-quant_user}" -d "${PG_DATABASE:-quant_trading}" -t -c \
    "SELECT COUNT(*) FROM stock_quotes LIMIT 1;" 2>/dev/null | tr -d '[:space:]')

if [ -n "$pg_result" ] && [ "$pg_result" -gt 0 ] 2>/dev/null; then
    log_pass "PostgreSQL 连通性: stock_quotes 表有数据（$pg_result 条）"
else
    log_fail "PostgreSQL 连通性: 查询失败或无数据"
fi

# 检查 stock_indicators 表
ind_result=$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "${PG_USER:-quant_user}" -d "${PG_DATABASE:-quant_trading}" -t -c \
    "SELECT COUNT(*) FROM stock_indicators LIMIT 1;" 2>/dev/null | tr -d '[:space:]')

if [ -n "$ind_result" ] && [ "$ind_result" -gt 0 ] 2>/dev/null; then
    log_pass "stock_indicators 表: $ind_result 条记录"
else
    log_warn "stock_indicators 表: $ind_result 条记录（可能为空，需确认指标是否已跑）"
fi

# ============================================================
# 4. 容器资源使用
# ============================================================
section "4. 容器资源使用"

docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
    $(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps -q 2>/dev/null) 2>/dev/null || \
    log_warn "无法获取资源统计（需 Docker 权限）"

# ============================================================
# 5. 近期日志错误扫描
# ============================================================
section "5. 近期日志错误扫描（最后 200 行）"

# 扫描 backend 日志中的 ERROR
backend_errors=$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
    logs --tail=200 backend 2>/dev/null | grep -ci "error" || true)
if [ "$backend_errors" -gt 0 ]; then
    log_warn "Backend 日志中发现 $backend_errors 处 ERROR 关键字"
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
        logs --tail=200 backend 2>/dev/null | grep -i "error" | tail -5 | \
        sed 's/^/       /'
else
    log_pass "Backend 日志无 ERROR（最近 200 行）"
fi

# ============================================================
# 总结
# ============================================================
section "验收总结"
echo ""
echo -e "  ${GREEN}PASS${NC}: $PASS   ${RED}FAIL${NC}: $FAIL   ${YELLOW}WARN${NC}: $WARN"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}✅ 验收通过，可以上线！${NC}"
    exit 0
elif [ "$FAIL" -le 2 ]; then
    echo -e "${YELLOW}⚠️  验收有 $FAIL 项失败，请检查后再上线${NC}"
    exit 1
else
    echo -e "${RED}❌ 验收有 $FAIL 项失败，请修复后再上线${NC}"
    exit 1
fi
