#!/bin/bash
# ============================================
# pre_commit_check.sh - Git commit 前置检查钩子
# ============================================
# 用法:
#   bash scripts/pre_commit_check.sh
#   # 或在 .git/hooks/pre-commit 软链到本脚本
#
# 检查项:
#   1. 暂存区敏感文件检测（.env / .pem / .key / .pfx / .rsa / id_rsa）
#   2. 暂存区真实 CHANGE_ME 占位符扫描（精确匹配 "=CHANGE_ME"）
#   3. .env.production 文件存在性 + 占位符扫描
#   4. 暂存区包含脚本是否可执行（fix-exec 可选）
# ============================================
# 退出码:
#   0 - 全部通过
#   1 - 检查失败阻断 commit
#   2 - 警告不阻断
# ============================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

FAIL=0
WARN=0

log_pass()  { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail()  { echo -e "${RED}[FAIL]${NC} $1"; ((FAIL++)); }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; ((WARN++)); }
log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
section()   { echo ""; echo "══════════════════════════════════════"; echo " $1"; echo "══════════════════════════════════════"; }

# ============================================================
# 1. 暂存区敏感文件检测
# ============================================================
section "1. 暂存区敏感文件检测"

# macOS BSD find 不支持 -printf，用兼容写法
SENSITIVE_FILES=$(git diff --cached --name-only --diff-filter=ACMRT 2>/dev/null | \
    grep -E "(^|/)(\.env(\.production)?|\.env\.[a-z]+|\.pem|\.key|\.pfx|\.rsa|id_rsa|id_ed25519)(\.[a-z0-9]+)?$" || true)

if [ -n "$SENSITIVE_FILES" ]; then
    log_fail "暂存区包含敏感文件（请勿提交）："
    echo "$SENSITIVE_FILES" | sed 's/^/       /'
else
    log_pass "暂存区无敏感文件"
fi

# ============================================================
# 2. 暂存区真实 CHANGE_ME 占位符扫描
# ============================================================
section "2. 暂存区真实 CHANGE_ME 占位符扫描"

STAGED_TEXT=$(git diff --cached --diff-filter=ACMRT 2>/dev/null | \
    grep -E "^\+[^+].*CHANGE_ME" | \
    grep -vE "^\+.*#.*CHANGE_ME" || true)

if [ -n "$STAGED_TEXT" ]; then
    log_fail "暂存区包含真实 CHANGE_ME 占位符（应使用 openssl rand -base64 32 替换）："
    echo "$STAGED_TEXT" | head -10 | sed 's/^/       /'
    if [ "$(echo "$STAGED_TEXT" | wc -l)" -gt 10 ]; then
        echo "       ...（共 $(echo "$STAGED_TEXT" | wc -l | tr -d ' ') 处，仅显示前 10 处）"
    fi
else
    log_pass "暂存区无真实 CHANGE_ME 占位符（仅注释中说明性文字不视为占位符）"
fi

# ============================================================
# 3. .env.production 文件存在性 + 占位符扫描
# ============================================================
section "3. .env.production 文件检查（即使未暂存也要确保本地有正确配置）"

if [ ! -f ".env.production" ]; then
    log_warn ".env.production 不存在（首次部署请 cp .env.production.example .env.production）"
else
    # 精确匹配 =CHANGE_ME 形式（排除注释行）
    REAL_PLACEHOLDERS=$(grep -E "^\s*[A-Z_][A-Z0-9_]*=.*CHANGE_ME" .env.production 2>/dev/null || true)
    if [ -n "$REAL_PLACEHOLDERS" ]; then
        log_fail ".env.production 含真实 CHANGE_ME 占位符："
        echo "$REAL_PLACEHOLDERS" | sed 's/^/       /'
    else
        log_pass ".env.production 无真实 CHANGE_ME 占位符"
    fi
fi

# ============================================================
# 4. 暂存区可执行脚本检查
# ============================================================
section "4. 暂存区 shell 脚本可执行位检查"

# 找到暂存区中所有 .sh 文件
STAGED_SH=$(git diff --cached --name-only --diff-filter=ACMRT 2>/dev/null | grep -E "\.sh$" || true)

if [ -n "$STAGED_SH" ]; then
    NOT_EXEC=$(echo "$STAGED_SH" | while IFS= read -r f; do
        if [ -n "$f" ] && [ -f "$f" ] && [ ! -x "$f" ]; then
            echo "$f"
        fi
    done)
    if [ -n "$NOT_EXEC" ]; then
        log_warn "以下 shell 脚本未设可执行位（chmod +x <file>）："
        echo "$NOT_EXEC" | sed 's/^/       /'
    else
        log_pass "所有暂存 .sh 脚本均已设可执行位"
    fi
else
    log_info "暂存区无 .sh 文件，跳过检查"
fi

# ============================================================
# 总结
# ============================================================
section "检查总结"
echo ""
echo -e "  ${RED}FAIL${NC}: $FAIL   ${YELLOW}WARN${NC}: $WARN"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}❌ pre_commit_check 未通过，commit 已被阻断${NC}"
    echo ""
    echo "请修复以上 FAIL 项后重新执行 git commit。"
    echo "如确认是误报，可使用 git commit --no-verify 跳过此检查（不推荐）。"
    exit 1
elif [ "$WARN" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  pre_commit_check 有 $WARN 项警告，建议修复后提交${NC}"
    exit 0
else
    echo -e "${GREEN}✅ pre_commit_check 全部通过，可以提交${NC}"
    exit 0
fi
