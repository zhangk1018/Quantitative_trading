#!/bin/bash
# ============================================================
# 日线数据全流程管道（优化版：按依赖关系并行执行）
# ============================================================
# 执行策略（最大化并行）：
#
# Phase 1 (16:30) — 前置检查 → K线导入 + 基本面同步（并行）
#   前置检查快速通过后，K线导入与基本面同步互不依赖，同时跑
#
# Phase 2 (16:45) — 技术指标计算 + 复权因子同步（并行）
#   两个都依赖 K线数据，但彼此独立
#
# Phase 3 (17:05) — 信号预计算 + 缺失值填充（并行）
#   信号依赖技术指标，缺失值依赖全部，可同时开始
# ============================================================

set -euo pipefail

PROJECT_DIR="/Users/zhangk/workspace/Quantitative_trading"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
LOG_DIR="$PROJECT_DIR/logs/scheduler"
TODAY=$(date +%Y-%m-%d)
PIPELINE_LOG="$LOG_DIR/daily_pipeline_${TODAY}.log"

mkdir -p "$LOG_DIR"

# ---- 日志函数 ----
log() {
    local level=$1
    local msg=$2
    local ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] [$level] $msg" | tee -a "$PIPELINE_LOG"
}

# ---- 阶段执行函数（同步） ----
run_step() {
    local step_name=$1
    local script_path=$2
    local extra_args=${3:-}

    log "STEP" "开始: $step_name"

    START_TS=$(date +%s)

    if cd "$PROJECT_DIR" && $VENV_PYTHON "$script_path" $extra_args >> "$PIPELINE_LOG" 2>&1; then
        END_TS=$(date +%s)
        DURATION=$((END_TS - START_TS))
        log "DONE" "完成: $step_name (耗时 ${DURATION}s)"
    else
        END_TS=$(date +%s)
        DURATION=$((END_TS - START_TS))
        log "FAIL" "失败: $step_name (耗时 ${DURATION}s)"
        return 1
    fi
}

# ---- 并行执行函数 ----
# 用法: run_parallel "阶段名" "任务1名" "脚本1路径" "任务2名" "脚本2路径"
run_parallel() {
    local phase_name=$1
    local task1_name=$2
    local task1_script=$3
    local task1_args=${4:-}
    local task2_name=$5
    local task2_script=$6
    local task2_args=${7:-}

    log "PARL" "开始并行阶段: $phase_name"
    log "PARL" "  任务1: $task1_name"
    log "PARL" "  任务2: $task2_name"

    local pid1 pid2
    local START_TS=$(date +%s)

    # 后台运行任务1
    (
        if cd "$PROJECT_DIR" && $VENV_PYTHON "$task1_script" $task1_args >> "$PIPELINE_LOG" 2>&1; then
            log "DONE" "  ✅ $task1_name 完成"
        else
            log "FAIL" "  ❌ $task1_name 失败"
        fi
    ) &
    pid1=$!

    # 后台运行任务2
    (
        if cd "$PROJECT_DIR" && $VENV_PYTHON "$task2_script" $task2_args >> "$PIPELINE_LOG" 2>&1; then
            log "DONE" "  ✅ $task2_name 完成"
        else
            log "FAIL" "  ❌ $task2_name 失败"
        fi
    ) &
    pid2=$!

    # 等待两个都完成
    wait $pid1 $pid2 || true

    local END_TS=$(date +%s)
    local DURATION=$((END_TS - START_TS))
    log "PARL" "并行阶段完成: $phase_name (耗时 ${DURATION}s)"
}

# ============================================================
# 主流程
# ============================================================
log "START" "==================== 日线数据管道开始 ===================="
log "START" "日期: $TODAY"
log "START" "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
PIPELINE_START=$(date +%s)

# -------------------------------------------------------
# Phase 1: 前置检查（必须通过）→ 并行执行：K线导入 + 基本面同步
# -------------------------------------------------------
log "PHASE" "==== Phase 1: 前置检查 + K线导入 + 基本面同步 ===="

run_step "前置条件检查" "backend/collector/etl/pipeline_health_check.py"

# K线导入 与 基本面同步 互不依赖，并行执行
run_parallel \
    "数据获取(Fetch)" \
    "K线数据导入" "backend/collector/etl/import_daily_data.py" "--incremental" \
    "基本面数据同步" "backend/collector/etl/sync_daily_basic.py" "--date $TODAY"

# -------------------------------------------------------
# Phase 2: 技术指标计算 + 复权因子同步（并行，都依赖 K线数据）
# -------------------------------------------------------
log "PHASE" "==== Phase 2: 技术指标计算 + 复权因子同步 ===="

run_parallel \
    "指标与复权(Compute)" \
    "技术指标计算" "backend/clean/etl/compute_indicators_daily.py" \
    "复权因子同步" "backend/collector/etl/sync_adj_factor.py" "--incremental"

# -------------------------------------------------------
# Phase 3: 信号预计算 + 缺失值填充（并行，都依赖前面完成）
# -------------------------------------------------------
log "PHASE" "==== Phase 3: 信号预计算 + 缺失值填充 ===="

run_parallel \
    "信号与补全(Post)" \
    "信号预计算" "backend/clean/etl/signal_precompute.py" \
    "缺失值处理" "backend/clean/etl/missing_value_fix.py"

# ============================================================
# 完成
# ============================================================
PIPELINE_END=$(date +%s)
TOTAL_DURATION=$((PIPELINE_END - PIPELINE_START))

log "END" "==================== 日线数据管道完成 ===================="
log "END" "总耗时: ${TOTAL_DURATION}s ($((TOTAL_DURATION / 60))分$((TOTAL_DURATION % 60))秒)"
log "END" "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
log "END" "日志文件: $PIPELINE_LOG"