#!/bin/bash
# ============================================
# 一键提交到 GitHub
# 用法: ./scripts/git_push.sh [commit message]
# ============================================

cd "$(dirname "$0")/.." || exit 1

echo "=========================================="
echo "  提交到 GitHub"
echo "=========================================="
echo ""

# 检查是否有更改
CHANGED=$(git status --porcelain)
if [ -z "$CHANGED" ]; then
    echo "✅ 工作区干净，没有待提交的更改"
    exit 0
fi

# 显示变更文件
echo "📝 变更文件:"
echo "$CHANGED" | nl
echo ""

# 获取提交信息
if [ -n "$1" ]; then
    COMMIT_MSG="$1"
else
    read -p "请输入提交信息: " COMMIT_MSG
    if [ -z "$COMMIT_MSG" ]; then
        echo "❌ 提交信息不能为空"
        exit 1
    fi
fi

# 添加所有更改
git add -A

# 提交
git commit -m "$COMMIT_MSG"

# 推送到远程
git push

echo ""
echo "✅ 提交完成"
echo "=========================================="
