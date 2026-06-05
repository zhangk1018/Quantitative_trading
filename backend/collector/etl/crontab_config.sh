#!/bin/bash
# ============================================
# ETL 定时任务配置脚本
# ============================================

PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
VENV_DIR="$PROJECT_DIR/venv"
SYNC_SCRIPT="$PROJECT_DIR/backend/collector/etl/daily_snapshot_sync.py"
INTEGRITY_SCRIPT="$PROJECT_DIR/backend/clean/quality/check_data_quality.py"
HEARTBEAT_SCRIPT="$PROJECT_DIR/backend/collector/etl/health_monitor.py"
LOG_DIR="$PROJECT_DIR/logs/etl"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 生成 crontab 配置
cat > /tmp/quant_crontab << EOF
# ============================================
# 量化系统 ETL 定时任务
# ============================================

# 每日盘后同步（16:00 执行，确保数据已更新）
0 16 * * 1-5 cd $PROJECT_DIR && source $VENV_DIR/bin/activate && python $SYNC_SCRIPT --latest > $LOG_DIR/daily_sync.log 2>&1

# 心跳监控守护进程（@reboot 自动启动，每分钟检查一次）
@reboot cd $PROJECT_DIR && export PG_PASSWORD=\$(awk -F= '/PG_PASSWORD/ {print \$2}' $PROJECT_DIR/.env) && $VENV_DIR/bin/python $HEARTBEAT_SCRIPT --daemon >> $LOG_DIR/heartbeat.log 2>&1

# 心跳监控守护进程（系统启动后立即启动+每5分钟检查一次是否还在运行）
*/5 * * * * cd $PROJECT_DIR && pgrep -f "health_monitor.py --daemon" > /dev/null || (export PG_PASSWORD=\$(awk -F= '/PG_PASSWORD/ {print \$2}' $PROJECT_DIR/.env) && nohup $VENV_DIR/bin/python $HEARTBEAT_SCRIPT --daemon >> $LOG_DIR/heartbeat.log 2>&1 &)

# 每周日凌晨执行全量同步（可选，用于数据校验）
0 2 * * 0 cd $PROJECT_DIR && source $VENV_DIR/bin/activate && python $SYNC_SCRIPT --start-date \$(date -v -7d '+%Y-%m-%d') --end-date \$(date '+%Y-%m-%d') > $LOG_DIR/weekly_sync.log 2>&1

# 每日数据完整性检查（22:00 执行）
0 22 * * * cd $PROJECT_DIR && source $VENV_DIR/bin/activate && python $INTEGRITY_SCRIPT > $LOG_DIR/integrity_check.log 2>&1

# 每日凌晨清理5天前的日志文件
0 1 * * * find $LOG_DIR -type f -mtime +5 -delete

# ============================================
EOF

echo "📋 已生成定时任务配置"
echo "路径: /tmp/quant_crontab"
echo ""
echo "📝 如需启用，请执行:"
echo "  crontab /tmp/quant_crontab"
echo ""
echo "📋 如需查看当前 crontab:"
echo "  crontab -l"
echo ""
echo "⏰ 任务说明:"
echo "  - @reboot: 启动心跳监控守护进程"
echo "  - 每5分: 检查心跳守护进程是否存活，死掉自动拉起"
echo "  - 每日 16:00（周一至周五）: 同步当日快照数据"
echo "  - 每日 22:00: 数据完整性检查"
echo "  - 每周日 02:00: 同步过去7天数据（数据校验）"
echo "  - 每日 01:00: 清理5天前的日志"
