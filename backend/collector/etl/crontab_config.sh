#!/bin/bash
# ============================================
# ETL 定时任务配置脚本
# 生成 crontab 配置并提示安装
# ============================================

PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
VENV_DIR="$PROJECT_DIR/venv"
PIPELINE_SCRIPT="$PROJECT_DIR/backend/scheduler/run_daily_pipeline.sh"
HEARTBEAT_SCRIPT="$PROJECT_DIR/backend/collector/etl/health_monitor.py"
PARTITION_SCHEDULER="$PROJECT_DIR/backend/collector/etl/partition_scheduler.py"
STOCK_LIST_INIT="$PROJECT_DIR/backend/collector/etl/sync_stock_list_baostock.py"
LOG_DIR="$PROJECT_DIR/logs/etl"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 生成 crontab 配置
cat > /tmp/quant_crontab << 'CRONTAB_EOF'
# ============================================
# 量化系统 ETL 定时任务
# ============================================
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

# 【P0】日线数据全流程管道（16:30 执行，A股收盘后）
# 顺序：前置检查 → 基本面同步 → K线导入 → 技术指标 → 复权因子 → 信号 → 缺失值填充
CRONTAB_EOF

cat >> /tmp/quant_crontab << EOF
30 16 * * 1-5 $PROJECT_DIR/backend/scheduler/run_daily_pipeline.sh

# 【P1】每周一 09:00 更新股票基础信息（含退市/新上市，行业分类更新）
0 9 * * 1 cd $PROJECT_DIR && $VENV_DIR/bin/python $STOCK_LIST_INIT --force > $LOG_DIR/stock_basic_update.log 2>&1

# 【P1】每月 1 日 01:00 创建下月/下年的数据库分区
0 1 1 * * cd $PROJECT_DIR && $VENV_DIR/bin/python $PARTITION_SCHEDULER --mode auto > $LOG_DIR/partition_scheduler.log 2>&1

# 【P2】每周日 03:00 检查并补全缺失的数据库分区（兜底）
0 3 * * 0 cd $PROJECT_DIR && $VENV_DIR/bin/python $PARTITION_SCHEDULER --mode check > $LOG_DIR/partition_check.log 2>&1

# 心跳监控守护进程（@reboot 自动启动）
@reboot cd $PROJECT_DIR && export PG_PASSWORD=\$(awk -F= '/PG_PASSWORD/ {print \$2}' $PROJECT_DIR/.env) && $VENV_DIR/bin/python $HEARTBEAT_SCRIPT --daemon >> $LOG_DIR/heartbeat.log 2>&1

# 心跳监控守护进程（每5分钟检查一次是否还在运行）
*/5 * * * * cd $PROJECT_DIR && pgrep -f "health_monitor.py --daemon" > /dev/null || (export PG_PASSWORD=\$(awk -F= '/PG_PASSWORD/ {print \$2}' $PROJECT_DIR/.env) && nohup $VENV_DIR/bin/python $HEARTBEAT_SCRIPT --daemon >> $LOG_DIR/heartbeat.log 2>&1 &)

# 每日凌晨清理5天前的日志文件
0 1 * * * find $LOG_DIR -type f -mtime +5 -delete
EOF

echo "========================================"
echo "📋 已生成定时任务配置: /tmp/quant_crontab"
echo ""
echo "📝 如需启用，请执行:"
echo "  crontab /tmp/quant_crontab"
echo ""
echo "📋 如需查看当前 crontab:"
echo "  crontab -l"
echo ""
echo "⏰ 任务说明:"
echo "  每日 16:30（周一至周五）: 日线数据全流程管道"
echo "    Step 0: 前置条件检查（pipeline_health_check）"
echo "    Step 1: 基本面同步（sync_daily_basic）"
echo "    Step 2: K线数据导入（import_daily_data --incremental）"
echo "    Step 3: 技术指标计算（compute_indicators_daily）"
echo "    Step 4: 复权因子同步（sync_adj_factor）"
echo "    Step 5: 信号预计算（signal_precompute）"
echo "    Step 6: 缺失值处理（missing_value_fix）"
echo "  每日 22:00: 数据完整性检查（已移除，改用 monitor API）"
echo "  每月 1 日 01:00: 创建数据库分区"
echo "  每周日 02:00: 更新股票基础信息"
echo "  每周日 03:00: 补全缺失分区"
echo "  每日 01:00: 清理5天前的日志"
echo "========================================"