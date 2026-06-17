#!/bin/bash
set -eo pipefail
# ============================================
# git_push.sh - 一键提交到 GitHub（SSH 协议）
# ============================================
# 用法:
#   bash scripts/git_push.sh                                    # 交互式选 commit 类型
#   bash scripts/git_push.sh "feat: xxx"                        # 直接用命令行 commit message
#   echo "y" | bash scripts/git_push.sh "feat: xxx"             # 非交互模式（CI/CD 用）
#
# 自动处理:
#   - 忽略目录: temp/ logs/ data/cache/（在 IGNORE_DIRS 数组）
#   - 备份后缀: .bak .backup .old .tmp .swp ~（在 IGNORE_FILE_SUFFIXES 数组）
#   - 敏感文件: .env* .pem .key .pfx .rsa id_rsa credentials.json secrets.json
#   - 分支白名单: main/master 之外需二次确认（在 ALLOW_PUSH_BRANCH 数组）
#
# 提交者: -c 临时指定 K 的 user.name/email，不修改本机全局 Git 配置
# 协议: SSH（需 K 提前撤销暴露的 PAT + 切换 git remote 为 git@github.com:...）
#
# 变更历史:
#   V1.1.4 fix(git): 修复中文文件名八进制转义（printf '%b' 解码）
#   V1.1.3 chore(git): 敏感文件名 word boundary + 备份后缀过滤 + read 输入加固
#   V1.1.2 fix(git): macOS BSD xargs 不支持 -d，改用 while read（POSIX 兼容）
#   V1.1.1 chore(git): PAT 脱敏 + HTTPS 告警 + 空字符串判断 + 固定字符串匹配
# ============================================

# ===================== 可配置项 =====================
# 需自动排除的目录，后续可直接在此数组扩展
IGNORE_DIRS=("temp/" "logs/" "data/cache/")
# 允许直接推送的主分支，其他分支需二次确认
ALLOW_PUSH_BRANCH=("main" "master")
# 敏感文件名完整匹配（word boundary 正则，精确匹配敏感文件而非子串）
# .env.*: 拦截所有 .env 变体（含 .env.production、.env.local，不含 .bak/.old/.tmp/.swp 等备份后缀）
# 扩展名：使用负向后顾 (?<!\.) 确保匹配的是文件扩展名而非子串
SENSITIVE_PATTERNS_REGEX='(^|/)((\.env)(\.[a-z0-9_-]+)*|\.pem|\.key|\.pfx|\.rsa|id_rsa|credentials\.json|secrets\.json)$'
# 备份/临时文件后缀，命中则跳过不提交
IGNORE_FILE_SUFFIXES=(".bak" ".backup" ".old" ".tmp" ".swp" "~")
# ====================================================

# 切换到项目根目录
cd "$(dirname "$0")/.." || exit 1

# 1. HTTPS+PAT 安全风险告警（保留原有逻辑，待切换SSH后自动消失）
# 微调3: REMOTE_URL 读出后立即脱敏，仅展示协议+用户名+仓库路径
REMOTE_URL_RAW=$(git config --get remote.origin.url 2>/dev/null || echo "")
# 将 user:token@ 部分替换为 ***@，避免 PAT 在脚本后续执行中意外暴露
REMOTE_URL=$(echo "$REMOTE_URL_RAW" | sed -E 's#://[^/@]+@#://***@#')
if echo "$REMOTE_URL_RAW" | grep -qE "https://.*@github.com"; then
    echo "⚠️  警告：当前 remote 使用 HTTPS + Personal Access Token"
    echo "   风险：任何 'git remote -v' / 'git config --get remote.origin.url' 命令都会暴露 PAT"
    echo "   建议：K 处理完安全风险后，使用 SSH 协议："
    echo "     git remote set-url origin git@github.com:zhangk1018/Quantitative_trading.git"
    echo ""
fi

echo "=========================================="
echo "  提交到 GitHub"
echo "=========================================="
echo ""

# 2. 检查工作区是否存在变更
CHANGED=$(git status --porcelain)
if [ -z "$CHANGED" ]; then
    echo "✅ 工作区干净，没有待提交的更改"
    exit 0
fi

# 3. 拆分：已跟踪变更、未跟踪文件
TRACKED_CHANGED=$(git status --porcelain | grep -v "^??" || true)
ALL_UNTRACKED=$(git status --porcelain | grep "^??" || true)

# 过滤：忽略目录下的文件 + 备份/临时后缀文件
IGNORED_UNTRACKED=""
NON_IGNORED_UNTRACKED="$ALL_UNTRACKED"
for dir in "${IGNORE_DIRS[@]}"; do
    TMP_IGNORE=$(echo "$NON_IGNORED_UNTRACKED" | grep "$dir" || true)
    IGNORED_UNTRACKED+="$TMP_IGNORE"$'\n'
    NON_IGNORED_UNTRACKED=$(echo "$NON_IGNORED_UNTRACKED" | grep -v "$dir" || true)
done

# 过滤备份/临时后缀文件（问题2修复）
for suffix in "${IGNORE_FILE_SUFFIXES[@]}"; do
    TMP_SUFFIX=$(echo "$NON_IGNORED_UNTRACKED" | grep "$suffix" || true)
    IGNORED_UNTRACKED+="$TMP_SUFFIX"$'\n'
    NON_IGNORED_UNTRACKED=$(echo "$NON_IGNORED_UNTRACKED" | grep -v "$suffix" || true)
done

# 4. 前置安全检测：敏感密钥文件名拦截（word boundary 完整匹配）
check_sensitive_file() {
    local file_list="$1"
    local matched
    matched=$(echo "$file_list" | grep -iE "$SENSITIVE_PATTERNS_REGEX" || true)
    if [ -n "$matched" ]; then
        echo "❌ 高危拦截：检测到敏感密钥类文件，禁止提交！"
        echo "$matched" | sed 's/^/   /'
        echo ""
        echo "请确认该文件已正确加入 .gitignore，或手动删除后再执行提交"
        exit 1
    fi
}
check_sensitive_file "$TRACKED_CHANGED"
check_sensitive_file "$NON_IGNORED_UNTRACKED"

# 5. 分类打印变更文件
echo "📝 待提交的变更文件:"
if [ -n "$TRACKED_CHANGED" ]; then
    echo "$TRACKED_CHANGED" | nl
fi
if [ -n "$NON_IGNORED_UNTRACKED" ]; then
    echo ""
    echo "📄 新增文件（非临时/忽略目录）:"
    echo "$NON_IGNORED_UNTRACKED" | nl
fi
if [ -n "$(echo "$IGNORED_UNTRACKED" | tr -d '[:space:]')" ]; then
    echo ""
    echo "🗑️  忽略目录文件（自动排除，统一规则集中清理）:"
    echo "$IGNORED_UNTRACKED" | nl
fi
echo ""

# 6. 用户提交确认
read -p "确认提交以上变更吗？(y/N) " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "❌ 已取消本次提交"
    exit 0
fi

# 7. 分支白名单校验，非主分支需二次确认
CURR_BRANCH=$(git rev-parse --abbrev-ref HEAD)
BRANCH_ALLOWED=false
for b in "${ALLOW_PUSH_BRANCH[@]}"; do
    if [[ "$CURR_BRANCH" == "$b" ]]; then
        BRANCH_ALLOWED=true
        break
    fi
done

if [ "$BRANCH_ALLOWED" = false ]; then
    read -p "⚠️ 当前分支【$CURR_BRANCH】不在允许直接推送的主分支列表内，确定继续推送？(y/N) " BR_CONFIRM
    if [[ "$BR_CONFIRM" != "y" && "$BR_CONFIRM" != "Y" ]]; then
        echo "❌ 分支推送已取消"
        exit 0
    fi
fi

# 8. 获取 Commit 提交信息（支持 Conventional Commit + Scope）
if [ -n "$1" ]; then
    COMMIT_MSG="$1"
else
    echo ""
    echo "📋 Conventional Commit 快捷选项:"
    echo "  1) feat:     新功能"
    echo "  2) fix:      缺陷修复"
    echo "  3) docs:     文档更新"
    echo "  4) refactor: 代码重构"
    echo "  5) chore:    工程杂项/配置调整"
    echo "  6) custom:   自定义完整提交信息"
    read -p "请选择类型(1-6)或直接输入完整提交文案: " CHOICE

    case $CHOICE in
        1) PREFIX="feat";;
        2) PREFIX="fix";;
        3) PREFIX="docs";;
        4) PREFIX="refactor";;
        5) PREFIX="chore";;
        6) PREFIX="";;
        *) PREFIX=""
           COMMIT_MSG="$CHOICE";;
    esac

    # 标准类型，支持 scope + 描述
    if [[ "$CHOICE" =~ ^[1-5]$ ]]; then
        read -t 30 -n 50 -p "请输入模块Scope(如backtest/indicator，留空跳过): " SCOPE
        echo ""
        if [ -n "$SCOPE" ]; then
            PREFIX="${PREFIX}(${SCOPE}): "
        else
            PREFIX="${PREFIX}: "
        fi
        read -t 30 -n 200 -p "提交详细描述: " SUFFIX
        echo ""
        COMMIT_MSG="${PREFIX}${SUFFIX}"
    elif [ "$CHOICE" = "6" ]; then
        read -t 60 -n 300 -p "请输入完整commit提交信息: " COMMIT_MSG
        echo ""
    fi

    if [ -z "$COMMIT_MSG" ]; then
        echo "❌ 错误：提交信息不能为空"
        exit 1
    fi
fi

# 9. 安全暂存文件：使用 while read 逐行处理（POSIX 兼容，支持中文/空格/特殊字符）
# 微调1: 替代原 xargs -I {} / xargs -d '\n'（macOS BSD xargs 不支持 -d，且 -0 需 null 分隔输入）
# V1.1.4 修复: L189 增加 printf '%b' 解码 git status --porcelain 中文文件名八进制转义
add_files_from_list() {
    local file_list="$1"
    [ -z "$file_list" ] && return 0
    echo "$file_list" | awk '{print substr($0,4)}' | while IFS= read -r line; do
        [ -n "$line" ] && file=$(printf '%b' "$line") && git add "$file"
    done
}
add_files_from_list "$TRACKED_CHANGED"
add_files_from_list "$NON_IGNORED_UNTRACKED"

# 10. 执行提交，捕获异常退出
echo ""
echo "📤 正在提交代码..."
git -c user.name="K" -c user.email="k@quantitative-trading.local" commit -m "$COMMIT_MSG" || {
    echo "❌ git commit 执行失败，请检查代码冲突、文件锁定等问题"
    exit 1
}

# 11. 执行推送，捕获异常退出
echo "🚀 正在推送到远程 origin/$CURR_BRANCH ..."
git push origin "$CURR_BRANCH" || {
    echo "❌ git push 推送失败，请检查网络、仓库权限或远端代码冲突"
    exit 1
}

echo ""
echo "✅ 代码提交并推送远程完成！"
echo "=========================================="
