#!/bin/bash
# ============================================
# 量化交易系统 - 定时任务安装脚本
# ============================================
# 用法：./install_cron.sh
# 安装源：./quant_crontab.active
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRONTAB_FILE="$SCRIPT_DIR/quant_crontab.active"

if [ ! -f "$CRONTAB_FILE" ]; then
    echo "❌ 错误: 找不到 $CRONTAB_FILE"
    exit 1
fi

echo "=========================================="
echo "📋 准备安装定时任务"
echo "=========================================="
echo "源文件: $CRONTAB_FILE"
echo ""
echo "预览内容:"
echo "----------------------------------------"
cat "$CRONTAB_FILE"
echo "----------------------------------------"
echo ""

# 备份当前 crontab
BACKUP_FILE="/tmp/crontab.bak.$(date +%Y%m%d_%H%M%S)"
crontab -l > "$BACKUP_FILE" 2>/dev/null || echo "# (无现有 crontab)" > "$BACKUP_FILE"
echo "📦 已备份当前 crontab 到: $BACKUP_FILE"
echo ""

# 安装新 crontab
crontab "$CRONTAB_FILE"
echo "✅ 定时任务安装完成"
echo ""
echo "=========================================="
echo "📅 当前 crontab 内容:"
echo "=========================================="
crontab -l
echo ""
echo "=========================================="
echo "⏰ 任务清单:"
echo "=========================================="
echo "  - 16:05 (1-5)  数据下载"
echo "  - 16:30 (1-5)  宽表同步（使用 sync_quotes_to_snapshot.py）"
echo "  - 16:35 (1-5)  日频基本面"
echo "  - 17:30 (1-5)  复权因子（间隔 4200 秒避开 Tushare 限频）"
echo "  - 18:00 (1-5)  技术指标（全市场）"
echo "  - 18:30 (1-5)  信号预计算"
echo "  - 22:00        完整性检查"
echo "  - 23:30        cron 时间漂移检测"
echo "  - 周日 02:00   股票基础信息更新"
echo ""
echo "⚠️  若要卸载: crontab -r"
echo "📜 若要回滚:  crontab $BACKUP_FILE"
