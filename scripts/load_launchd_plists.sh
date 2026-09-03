#!/bin/bash
# 加载项目全部 launchd 服务到用户 LaunchAgents（~/Library/LaunchAgents）
# 用户登录后 launchd 自动加载该目录所有 plist，无需 sudo
# 使用方式：bash scripts/load_launchd_plists.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_DIR="$SCRIPT_DIR/scripts/launchctl"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS"

echo "=== 复制 plist 到用户 LaunchAgents ==="
for f in "$PLIST_DIR"/com.quant.*.plist; do
    [ -f "$f" ] || continue
    cp "$f" "$LAUNCH_AGENTS/"
    echo "  ✅ $(basename "$f")"
done

echo ""
echo "=== 卸载旧任务（如有）==="
for f in "$LAUNCH_AGENTS"/com.quant.*.plist; do
    launchctl unload "$f" 2>/dev/null || true
done
# 清理旧版遗留条目（含 bar_aggregation 旧命名 weekly_kline/monthly_kline、已停用的 healthcheck/log-cleanup）
for label in com.quant.backend com.quant.backend.healthcheck com.quant.postgresql \
             com.quant.log-cleanup.monthly \
             com.quant.daily_job.stage1 com.quant.daily_job.stage2 \
             com.quant.bar-aggregation.weekly com.quant.bar-aggregation.monthly \
             com.quant.weekly_kline com.quant.monthly_kline com.quant.bar_aggregation; do
    launchctl remove "$label" 2>/dev/null || true
done

echo ""
echo "=== 数据库（用户域 launchd，登录后自动启动，KeepAlive）==="
launchctl load -w "$LAUNCH_AGENTS/com.quant.postgresql.plist" && echo "✅ postgresql loaded"

echo "=== 后端服务（用户域 launchd，KeepAlive 常驻）==="
echo "⚠️ 已停用 backend_watchdog.sh 与 backend.healthcheck（避免多套拉起抢端口）"
launchctl load -w "$LAUNCH_AGENTS/com.quant.backend.plist" && echo "✅ backend loaded"

echo "=== 阶段1（15:30 健康检查+股票列表）==="
launchctl load -w "$LAUNCH_AGENTS/com.quant.daily_job_runner.stage1.plist" && echo "✅ stage1 loaded"

echo "=== 阶段2（16:30 日线行情导入）==="
launchctl load -w "$LAUNCH_AGENTS/com.quant.daily_job_runner.stage2.plist" && echo "✅ stage2 loaded"

echo "=== 阶段3（17:30 复权因子→补全→基本面→指标→形态→信号→宽表→Parquet）==="
launchctl load -w "$LAUNCH_AGENTS/com.quant.daily_job_runner.stage3.plist" && echo "✅ stage3 loaded"

echo ""
echo "=== 周线聚合（18:30 交易日执行，脚本自动判断周最后交易日）==="
launchctl load -w "$LAUNCH_AGENTS/com.quant.bar_aggregation.weekly.plist" && echo "✅ weekly loaded"

echo "=== 月线聚合（18:45 交易日执行，脚本自动判断月最后交易日）==="
launchctl load -w "$LAUNCH_AGENTS/com.quant.bar_aggregation.monthly.plist" && echo "✅ monthly loaded"

echo "=== 港股 ETL（16:00，列表+日线+基本面串行）==="
launchctl load -w "$LAUNCH_AGENTS/com.quant.hk_job.plist" && echo "✅ hk_job loaded"

echo "=== 美股 ETL（22:00，列表+日线+基本面串行）==="
launchctl load -w "$LAUNCH_AGENTS/com.quant.us_job.plist" && echo "✅ us_job loaded"

echo ""
echo "=== 验证 ==="
launchctl list | grep com.quant || true
echo ""
echo "✅ 全部加载完成（用户 LaunchAgents，登录后自动启动）"
echo ""
echo "⚠️ 清理旧系统域服务（如需，避免双加载）:"
echo "  sudo launchctl unload /Library/LaunchDaemons/com.quant.backend.plist"
echo "  sudo launchctl unload /Library/LaunchDaemons/com.quant.daily_job_runner.stage1.plist"
echo "  sudo launchctl unload /Library/LaunchDaemons/com.quant.daily_job_runner.stage2.plist"
echo "  sudo launchctl unload /Library/LaunchDaemons/com.quant.daily_job_runner.stage3.plist"
echo "  sudo launchctl unload /Library/LaunchDaemons/com.quant.bar_aggregation.weekly.plist"
echo "  sudo launchctl unload /Library/LaunchDaemons/com.quant.bar_aggregation.monthly.plist"
echo "  sudo rm -f /Library/LaunchDaemons/com.quant.*.plist"
