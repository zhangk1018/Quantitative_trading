#!/bin/bash
# 加载 daily_job_runner 的 3 个阶段 plist 到 launchd
# 使用方式：bash scripts/load_launchd_plists.sh

set -e

PLIST_DIR="/Users/zhangk/workspace/Quantitative_trading/scripts/launchctl"

echo "=== 卸载旧任务（如有）==="
for f in "$PLIST_DIR"/com.quant.daily_job_runner.stage*.plist; do
    launchctl unload "$f" 2>/dev/null || true
done
# 清理旧版遗留条目
for label in com.quant.daily_job.stage1 com.quant.daily_job.stage2; do
    launchctl remove "$label" 2>/dev/null || true
done

echo "=== 加载阶段1（15:30 健康检查+股票列表）==="
launchctl load -w "$PLIST_DIR/com.quant.daily_job_runner.stage1.plist" && echo "✅ stage1 loaded"

echo "=== 加载阶段2（17:45 日线行情导入）==="
launchctl load -w "$PLIST_DIR/com.quant.daily_job_runner.stage2.plist" && echo "✅ stage2 loaded"

echo "=== 加载阶段3（18:15 复权因子→补全→基本面→指标→形态→信号→宽表→Parquet）==="
launchctl load -w "$PLIST_DIR/com.quant.daily_job_runner.stage3.plist" && echo "✅ stage3 loaded"

echo ""
echo "=== 验证 ==="
launchctl list | grep com.quant.daily
echo ""
echo "✅ 全部加载完成"