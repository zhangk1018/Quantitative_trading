#!/bin/bash
# ============================================
# Cron 定时任务配置脚本
# 用于在 launchd 不可用时替代调度任务
# ============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs/cron"

mkdir -p "$LOG_DIR"

# Cron 任务配置 - 简洁安全版本
# 依赖：项目使用 python-dotenv，Python 脚本会自动读取 .env 文件
CRON_TASKS="# ============================================
# 量化交易定时任务 - Cron 版本
# 安装时间: $(date '+%Y-%m-%d %H:%M:%S')
# ============================================

# 每日 16:05 - 增量导入行情数据（周一至周五）
5 16 * * 2,3,4,5,6 cd /Users/zhangk/workspace/Quantitative_trading && ./venv/bin/python ./backend/collector/etl/import_daily_data.py >> ./logs/cron/daily_import.log 2>&1

# 每日 16:30 - 宽表同步（周一至周五）
30 16 * * 2,3,4,5,6 cd /Users/zhangk/workspace/Quantitative_trading && ./venv/bin/python ./backend/collector/etl/daily_snapshot_sync.py --latest >> ./logs/cron/daily_sync.log 2>&1

# 每日 16:35 - 日频基本面同步（周一至周五）
35 16 * * 2,3,4,5,6 cd /Users/zhangk/workspace/Quantitative_trading && ./venv/bin/python ./backend/collector/etl/sync_daily_basic.py --latest >> ./logs/cron/daily_basic_sync.log 2>&1

# 每日 17:00 - 复权因子同步（周一至周五）
0 17 * * 2,3,4,5,6 cd /Users/zhangk/workspace/Quantitative_trading && ./venv/bin/python ./backend/collector/etl/sync_adj_factor.py --latest >> ./logs/cron/adj_factor_sync.log 2>&1

# 每周日 02:00 - 更新股票基础信息
0 2 * * 0 cd /Users/zhangk/workspace/Quantitative_trading && ./venv/bin/python ./backend/collector/etl/init_data.py >> ./logs/cron/stock_basic_update.log 2>&1

# 每日 22:00 - 完整性检查
0 22 * * * cd /Users/zhangk/workspace/Quantitative_trading && ./venv/bin/python ./backend/clean/quality/check_data_quality.py >> ./logs/cron/integrity_check.log 2>&1

# 每日 18:00 - 技术指标计算
0 18 * * 2,3,4,5,6 cd /Users/zhangk/workspace/Quantitative_trading && ./venv/bin/python ./backend/clean/etl/compute_indicators_daily.py >> ./logs/cron/indicators_compute.log 2>&1

# 每日 18:30 - 信号预计算（基于技术指标计算买卖信号）
30 18 * * 2,3,4,5,6 cd /Users/zhangk/workspace/Quantitative_trading && ./venv/bin/python ./backend/clean/etl/signal_precompute.py >> ./logs/cron/signal_precompute.log 2>&1
"

echo ""
echo "=========================================="
echo "  Cron 定时任务配置脚本"
echo "=========================================="
echo ""

# 安装 Cron 任务
echo "📦 正在安装 Cron 任务..."
echo "$CRON_TASKS" | crontab -
echo "✅ Cron 任务安装成功"
echo ""

# 显示已安装的任务
echo "📋 已安装的定时任务："
echo ""
crontab -l | grep -v "^#" | grep -v "^$" | nl
echo ""

# 显示任务说明
echo "💡 定时任务说明："
echo "  • 每日 16:05 - 增量导入行情数据"
echo "  • 每日 16:30 - 宽表同步"
echo "  • 每日 16:35 - 日频基本面同步"
echo "  • 每日 17:00 - 复权因子同步"
echo "  • 每周日 02:00 - 更新股票基础信息"
echo "  • 每日 22:00 - 完整性检查"
echo "  • 每日 18:00 - 技术指标计算"
echo "  • 每日 18:30 - 信号预计算（MACD/RSI/BOLL 买卖点）"
echo ""

# 显示日志位置
echo "📁 日志目录："
echo "  $LOG_DIR"
echo ""

# 显示常用命令
echo "💡 常用命令："
echo "  查看当前 Cron 任务:   crontab -l"
echo "  编辑 Cron 任务:       crontab -e"
echo "  删除所有 Cron 任务:   crontab -r"
echo "  查看 Cron 日志:       cat $LOG_DIR/*.log"
echo ""

echo "=========================================="