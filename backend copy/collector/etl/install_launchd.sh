#!/bin/bash
# ============================================
# macOS 定时任务安装脚本
# 优先使用 launchd，如果不可用则使用 crontab
# ============================================
set -e

# 检测 launchd 是否可用
launchd_available() {
    launchctl load ~/Library/LaunchAgents/com.quant.test.plist 2>/dev/null
    return $?
}

# 获取脚本所在目录的绝对路径（修复：使用 readlink -f 确保获取真实路径）
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# 脚本位于 backend/collector/etl/，向上走3级到达项目根目录
PROJECT_DIR=$(cd "$SCRIPT_DIR/../../../" && pwd)
LAUNCH_DIR="$HOME/Library/LaunchAgents"
PLIST_DIR="$PROJECT_DIR/backend/collector/etl/launchd_plists"
LOG_DIR="$PROJECT_DIR/logs/etl"

mkdir -p "$LAUNCH_DIR" "$LOG_DIR" "$PLIST_DIR"

# 检测 venv
if [ -d "$PROJECT_DIR/venv" ]; then
    VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
elif [ -d "$PROJECT_DIR/backend/.venv" ]; then
    VENV_PYTHON="$PROJECT_DIR/backend/.venv/bin/python"
else
    VENV_PYTHON="$(which python3)"
fi

# 从 .env 提取环境变量
get_env_var() {
    local key="$1"
    if [ -f "$PROJECT_DIR/.env" ]; then
        grep "^${key}=" "$PROJECT_DIR/.env" | cut -d'=' -f2- | tr -d '"' | tr -d "'"
    fi
}

PG_PASSWORD=$(get_env_var "PG_PASSWORD")
TUSHARE_TOKEN=$(get_env_var "TUSHARE_TOKEN")

# 生成 plist 的辅助函数
generate_plist() {
    local label="$1"
    local script_path="$2"
    local hour="$3"
    local minute="$4"
    local weekday="$5"
    local log_name="$6"

    cat > "$PLIST_DIR/${label}.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.quant.${label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>${script_path}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PG_PASSWORD</key>
        <string>${PG_PASSWORD}</string>
        <key>TUSHARE_TOKEN</key>
        <string>${TUSHARE_TOKEN}</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${hour}</integer>
        <key>Minute</key>
        <integer>${minute}</integer>
EOF

    if [ -n "$weekday" ]; then
        cat >> "$PLIST_DIR/${label}.plist" <<EOF
        <key>Weekday</key>
        <integer>${weekday}</integer>
EOF
    fi

    cat >> "$PLIST_DIR/${label}.plist" <<EOF
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/${log_name}.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/${log_name}.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF
}

# ===== 生成各项任务 plist =====

# P0: 每日 16:05 增量导入行情（周一至周五）
cat > "$PLIST_DIR/daily_import.plist" <<'PLISTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.quant.daily_import</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>${PROJECT_DIR}/backend/collector/etl/import_daily_data.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>5</integer>
            <key>Weekday</key><integer>2</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>5</integer>
            <key>Weekday</key><integer>3</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>5</integer>
            <key>Weekday</key><integer>4</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>5</integer>
            <key>Weekday</key><integer>5</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>5</integer>
            <key>Weekday</key><integer>6</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/daily_import.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/daily_import.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLISTEOF

# P0: 每日 16:30 宽表同步
cat > "$PLIST_DIR/daily_snapshot_sync.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.quant.daily_snapshot_sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>${PROJECT_DIR}/backend/collector/etl/daily_snapshot_sync.py</string>
        <string>\$(date -v -1d '+%Y-%m-%d')</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>16</integer>
        <key>Minute</key><integer>30</integer>
        <key>Weekday</key><integer>2</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/daily_sync.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/daily_sync.err.log</string>
</dict>
</plist>
EOF

# P0: 每日 16:30 日频基本面同步（新增）
cat > "$PLIST_DIR/daily_basic_sync.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.quant.daily_basic_sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>${PROJECT_DIR}/backend/collector/etl/sync_daily_basic.py</string>
        <string>--latest</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>16</integer>
        <key>Minute</key><integer>35</integer>
        <key>Weekday</key><integer>2</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/daily_basic_sync.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/daily_basic_sync.err.log</string>
</dict>
</plist>
EOF

# P0: 每日 17:00 复权因子同步（新增，受 1次/小时 限频）
cat > "$PLIST_DIR/adj_factor_sync.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.quant.adj_factor_sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>${PROJECT_DIR}/backend/collector/etl/sync_adj_factor.py</string>
        <string>--latest</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>17</integer>
        <key>Minute</key><integer>0</integer>
        <key>Weekday</key><integer>2</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/adj_factor_sync.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/adj_factor_sync.err.log</string>
</dict>
</plist>
EOF

# P1: 每周日 02:00 更新股票基础信息
generate_plist "stock_basic_update" \
    "$PROJECT_DIR/backend/collector/etl/init_data.py" \
    2 0 1 "stock_basic_update"
# 修正 Weekday：周日是 1
sed -i '' 's|<integer>1</integer>|<integer>0</integer>|' "$PLIST_DIR/stock_basic_update.plist" 2>/dev/null || true

# P1: 每月 1 日 01:00 创建分区
cat > "$PLIST_DIR/partition_scheduler.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.quant.partition_scheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>${PROJECT_DIR}/backend/collector/etl/partition_scheduler.py</string>
        <string>--mode</string>
        <string>auto</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Day</key><integer>1</integer>
        <key>Hour</key><integer>1</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/partition_scheduler.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/partition_scheduler.err.log</string>
</dict>
</plist>
EOF

# P2: 每日 22:00 完整性检查
generate_plist "integrity_check" \
    "$PROJECT_DIR/backend/clean/quality/check_data_quality.py" \
    22 0 "" "integrity_check"

# ===== 安装 plist 到 LaunchAgents =====
echo "📦 复制 plist 到 ~/Library/LaunchAgents ..."
cp "$PLIST_DIR"/*.plist "$LAUNCH_DIR/"

# ===== 加载任务 =====
echo ""
echo "🚀 加载 launchd 任务..."
for plist in "$LAUNCH_DIR"/com.quant.*.plist; do
    if [ -f "$plist" ]; then
        label=$(basename "$plist" .plist)
        # 卸载旧任务（如果存在）
        launchctl unload "$plist" 2>/dev/null || true
        # 加载新任务
        launchctl load "$plist"
        echo "  ✅ 已加载: $label"
    fi
done

echo ""
echo "=" * 60
echo "✅ 全部任务已注册到 launchd"
echo "=" * 60
echo ""
echo "📋 任务列表:"
launchctl list | grep "com.quant" || echo "  （无）"
echo ""
echo "💡 常用命令:"
echo "  查看所有任务:   launchctl list | grep com.quant"
echo "  立即执行任务:   launchctl start com.quant.daily_import"
echo "  停止任务:       launchctl unload ~/Library/LaunchAgents/com.quant.daily_import.plist"
echo "  重新加载:       launchctl load ~/Library/LaunchAgents/com.quant.daily_import.plist"
echo ""
echo "📁 plist 文件:   $LAUNCH_DIR"
echo "📁 备份 plist:   $PLIST_DIR"
echo "📁 日志目录:     $LOG_DIR"

# 如果 launchd 加载失败，自动回退到 crontab
if ! launchctl list | grep -q "com.quant.daily_import"; then
    echo ""
    echo "⚠️  launchd 加载失败，自动回退到 crontab..."
    bash "$SCRIPT_DIR/install_cron.sh"
fi