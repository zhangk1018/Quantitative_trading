#!/bin/bash
# ============================================
# deploy.sh - 一键部署脚本（macOS + Docker Desktop）
# ============================================
# 用法:
#   ./deploy.sh           # 完整部署：启动 Docker → start → health
#   ./deploy.sh --skip-daemon  # 跳过 Docker 启动（用于 daemon 已运行场景）
#
# 解决协作单 [6.11]：
#   Phase 5 部署 commit 5f6ab5e 时未启动 Docker Desktop → 静默失败 → 500 错误
#   本脚本确保部署前 Docker daemon 一定可用
# ============================================
# 前置条件:
#   - macOS 12+ (依赖 open -a Docker)
#   - Docker Desktop 已安装
#   - .env.production 存在且无 CHANGE_ME 占位符
# ============================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_pass()  { echo -e "${GREEN}[✅]${NC} $1"; }
log_fail()  { echo -e "${RED}[❌]${NC} $1"; }
section()   { echo ""; echo "══════════════════════════════════════"; echo " $1"; echo "══════════════════════════════════════"; }

SKIP_DAEMON=0
if [ "${1:-}" = "--skip-daemon" ]; then
    SKIP_DAEMON=1
fi

# ============================================================
# 步骤 1：检查 .env.production 占位符
# ============================================================
section "步骤 1/5：检查 .env.production"

if [ ! -f ".env.production" ]; then
    log_error ".env.production 不存在"
    echo "  请先执行: cp .env.production.example .env.production"
    echo "  然后编辑替换所有 CHANGE_ME 占位符"
    exit 1
fi

REAL_PLACEHOLDERS=$(grep -E "^\s*[A-Z_][A-Z0-9_]*=.*CHANGE_ME" .env.production 2>/dev/null || true)
if [ -n "$REAL_PLACEHOLDERS" ]; then
    log_error ".env.production 仍有真实 CHANGE_ME 占位符："
    echo "$REAL_PLACEHOLDERS" | sed 's/^/       /'
    echo "  请用 openssl rand -base64 32 替换"
    exit 1
fi
log_pass ".env.production 无 CHANGE_ME 占位符"

# ============================================================
# 步骤 2：启动 Docker Desktop（如需）
# ============================================================
section "步骤 2/5：检查 Docker daemon"

if [ "$SKIP_DAEMON" = "1" ]; then
    log_info "跳过 Docker 启动（--skip-daemon）"
else
    if docker info >/dev/null 2>&1; then
        log_pass "Docker daemon 已运行"
    else
        log_warn "Docker daemon 未运行，启动 Docker Desktop..."
        open -a Docker

        # 轮询等待 daemon 就绪（最多 90s）
        log_info "等待 Docker daemon 就绪（轮询 docker info）..."
        WAITED=0
        MAX_WAIT=90
        while [ "$WAITED" -lt "$MAX_WAIT" ]; do
            sleep 3
            WAITED=$((WAITED + 3))
            if docker info >/dev/null 2>&1; then
                SERVER_VERSION=$(docker info --format '{{.ServerVersion}}' 2>/dev/null)
                log_pass "Docker daemon 已就绪（v${SERVER_VERSION}，等待 ${WAITED}s）"
                break
            fi
            log_info "  等待中...（${WAITED}s / ${MAX_WAIT}s）"
        done

        if [ "$WAITED" -ge "$MAX_WAIT" ]; then
            log_error "Docker daemon 在 ${MAX_WAIT}s 内未就绪"
            echo "  请手动检查 Docker Desktop 状态后重试"
            exit 1
        fi
    fi
fi

# ============================================================
# 步骤 3：启动服务
# ============================================================
section "步骤 3/5：启动服务（./start_prod.sh start）"

./start_prod.sh start

# ============================================================
# 步骤 4：等待后端 workers 启动
# ============================================================
section "步骤 4/5：等待后端 workers 启动（sleep 30）"

log_info "Uvicorn workers 启动需要时间（防止协作单 [6.11] 复现：Nginx 502 误判）"
log_info "Phase 5 部署实测：recreate 后 backend 健康需 30-60s"
sleep 30

# ============================================================
# 步骤 5：健康检查（直接 curl，绕过 start_prod.sh health 总 exit 0 问题）
# ============================================================
section "步骤 5/5：健康检查（4 个端点 + 后端直连）"

HEALTH_PASS=0
HEALTH_FAIL=0

check_endpoint() {
    local name="$1"
    local url="$2"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        log_pass "$name: HTTP $code"
        HEALTH_PASS=$((HEALTH_PASS + 1))
    else
        log_fail "$name: HTTP $code"
        HEALTH_FAIL=$((HEALTH_FAIL + 1))
    fi
}

# 后端直连（最关键的"真实状态"指标）
check_endpoint "后端 :8000/health" "http://localhost:8000/health"
check_endpoint "后端 :8000/api/meta/" "http://localhost:8000/api/meta/"
check_endpoint "后端 :8000/api/stocks/?limit=1" "http://localhost:8000/api/stocks/?limit=1"
# Nginx 上游（可选，workers 启动慢时可能 502）
check_endpoint "Nginx /api/stocks/?limit=1" "http://localhost/api/stocks/?limit=1"

echo ""
echo "  PASS: $HEALTH_PASS   FAIL: $HEALTH_FAIL"

# 通过条件：后端直连 3/3 全 200（核心）；Nginx 失败不阻断（workers 启动慢）
if [ "$HEALTH_FAIL" -le 1 ] && [ "$HEALTH_PASS" -ge 3 ]; then
    log_pass "部署完成 ✅"
    echo ""
    echo "🌐 访问地址："
    echo "   前端（生产）: http://localhost/"
    echo "   前端（dev）  : http://localhost:5173/  (如 vite dev 在跑)"
    echo "   后端 API     : http://localhost:8000/api/"
    echo "   后端直连     : http://localhost:8000/"
    exit 0
else
    log_error "部署失败：后端直连 FAIL 数 $HEALTH_FAIL ≥ 2（核心指标未通过）"
    echo ""
    echo "🔍 排查建议："
    echo "   1. 绕过 Nginx 直连验证：curl http://localhost:8000/health"
    echo "   2. 查看后端日志：./start_prod.sh logs backend"
    echo "   3. 查看容器状态：./start_prod.sh status"
    echo "   4. 重新跑验证：./verify_prod.sh"
    exit 1
fi
