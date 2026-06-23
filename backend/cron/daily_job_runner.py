#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化交易 - 每日盘后线性任务调度脚本
任务顺序：A → B → C → D → E → F → G（前一个成功才执行下一个）
数据依赖：行情/基本面/复权因子 → 技术指标 → 信号 → 宽表 → Parquet导出
支持：断点续跑 + 自动重试（未全部成功则每15分钟重试，最多10次）
"""
import os
import sys
import re
import time
import subprocess
from datetime import datetime

# ===================== 配置项 =====================
# 项目根目录（backend/cron 的上级）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Python 解释器路径（项目 venv）
PYTHON = os.path.join(BASE_DIR, "venv", "bin", "python")
# 日志根目录
LOG_DIR = os.path.join(BASE_DIR, "logs", "cron")

# 重试配置
RETRY_INTERVAL_SEC = 15 * 60   # 重试间隔：15分钟
MAX_RETRIES = 10               # 最大重试次数

# 任务列表【严格按执行顺序填写】
TASKS = [
    # A 增量导入行情数据
    {
        "name": "daily_import",
        "script": os.path.join("backend", "collector", "etl", "import_daily_data.py"),
        "args": []
    },
    # B 日频基本面同步
    {
        "name": "daily_basic_sync",
        "script": os.path.join("backend", "collector", "etl", "sync_daily_basic.py"),
        "args": ["--latest"]
    },
    # C 复权因子同步
    {
        "name": "adj_factor_sync",
        "script": os.path.join("backend", "collector", "etl", "sync_adj_factor.py"),
        "args": ["--incremental"]
    },
    # D 技术指标计算
    {
        "name": "indicators_compute",
        "script": os.path.join("backend", "clean", "etl", "compute_indicators_daily.py"),
        "args": []
    },
    # E 信号预计算
    {
        "name": "signal_precompute",
        "script": os.path.join("backend", "clean", "etl", "signal_precompute.py"),
        "args": []
    },
    # F 宽表同步（依赖 stock_indicators 和 trade_signals，必须最后执行）
    {
        "name": "daily_sync",
        "script": os.path.join("backend", "collector", "etl", "daily_snapshot_sync.py"),
        "args": ["--latest"]
    },
    # G Parquet 导出（依赖 stock_daily_snapshot 宽表，必须最后执行）
    {
        "name": "parquet_export",
        "script": os.path.join("backend", "clean", "enrich", "export_parquet.py"),
        "args": []
    },
]


def check_task_status(task_name):
    """检查任务今日执行状态（断点续跑依据）"""
    log_path = os.path.join(LOG_DIR, f"{task_name}.log")
    today_str = datetime.now().strftime("%Y-%m-%d")

    if not os.path.exists(log_path):
        return "pending"

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return "unknown"

    # 找今日的所有执行块（严格过滤日期）
    blocks = list(re.finditer(
        rf'===== ({re.escape(today_str)} \d{{2}}:\d{{2}}:\d{{2}}) 开始执行 {re.escape(task_name)} =====',
        content
    ))
    if not blocks:
        return "pending"

    # 从后往前找有明确结果的块
    for bm in reversed(blocks):
        bc = content[bm.start():]
        if ('SUCCESS' in bc or '执行成功' in bc or '完成' in bc[-500:]):
            return "success"
        if ('FAILED' in bc and '=====' in bc) or ('EXCEPTION' in bc and '=====' in bc):
            return "failed"

    # 最后一个块无明确结果
    last_block = content[blocks[-1].start():]
    # 检查文件修改时间（5分钟内更新→可能正在运行）
    try:
        mtime = os.path.getmtime(log_path)
        if time.time() - mtime < 300:
            return "running"
    except Exception:
        pass
    return "unknown"


def run_task(task):
    """执行单个任务，返回是否成功"""
    task_name = task["name"]
    script_path = os.path.join(BASE_DIR, task["script"])
    log_path = os.path.join(LOG_DIR, f"{task_name}.log")
    cmd = [PYTHON, script_path] + task["args"]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] 开始执行任务: {task_name}")

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {now} 开始执行 {task_name} =====\n")
            f.flush()
            result = subprocess.run(
                cmd,
                cwd=BASE_DIR,
                stdout=f,
                stderr=subprocess.STDOUT,
                check=True,
            )
        with open(log_path, "a", encoding="utf-8") as f:
            elapsed = (datetime.now() - datetime.strptime(now, "%Y-%m-%d %H:%M:%S")).total_seconds()
            f.write(f"===== {task_name} SUCCESS | 耗时 {elapsed:.1f}s =====\n")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_name} 执行成功")
        return True

    except subprocess.CalledProcessError as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_name} 执行失败，错误码: {e.returncode}")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"===== {task_name} FAILED (exit code: {e.returncode}) =====\n")
        return False
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_name} 异常: {str(e)}")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"===== {task_name} EXCEPTION: {str(e)} =====\n")
        return False


def run_task_chain():
    """执行一次任务链（断点续跑），返回 (全部成功?, 失败任务名)"""
    completed = 0
    failed_task = None

    for i, task in enumerate(TASKS, 1):
        task_name = task["name"]

        # 断点续跑：跳过今日已成功的任务
        status = check_task_status(task_name)
        if status == "success":
            print(f"  [{i}/{len(TASKS)}] ⏭ {task_name} — 今日已成功，跳过")
            completed += 1
            continue

        if status == "running":
            print(f"  [{i}/{len(TASKS)}] ⏳ {task_name} — 正在运行中，跳过")
            failed_task = task_name
            break

        # 需要执行的任务
        print(f"\n--- [{i}/{len(TASKS)}] ---")
        success = run_task(task)
        if success:
            completed += 1
        else:
            failed_task = task_name
            print(f"\n!!! 任务链中断：{failed_task} 失败，停止后续任务 !!!")
            break

    all_success = (failed_task is None and completed == len(TASKS))
    return all_success, failed_task


def main():
    """主函数：断点续跑 + 自动重试"""
    os.makedirs(LOG_DIR, exist_ok=True)

    start_time = datetime.now()
    print("=" * 60)
    print(f"【每日盘后线性任务】开始 | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {PYTHON}")
    print(f"任务数: {len(TASKS)} | 重试间隔: {RETRY_INTERVAL_SEC // 60}分钟 | 最大重试: {MAX_RETRIES}次")
    print("=" * 60)

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print(f"\n{'=' * 60}")
            print(f"【第 {attempt}/{MAX_RETRIES} 次重试】| {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'=' * 60}")

        all_success, failed_task = run_task_chain()

        if all_success:
            elapsed = (datetime.now() - start_time).total_seconds()
            print("\n" + "=" * 60)
            print(f"【全部完成】{len(TASKS)}/{len(TASKS)} 任务成功 | 耗时 {elapsed:.1f}s | 第{attempt}轮")
            print("=" * 60)
            sys.exit(0)

        # 未全部成功，判断是否需要重试
        if attempt < MAX_RETRIES:
            next_time = datetime.now() + __import__('datetime').timedelta(seconds=RETRY_INTERVAL_SEC)
            print(f"\n⏸ 等待 {RETRY_INTERVAL_SEC // 60} 分钟后重试... | 下次: {next_time.strftime('%H:%M')} | 已用: {attempt}/{MAX_RETRIES}")
            time.sleep(RETRY_INTERVAL_SEC)

    # 达到最大重试次数仍未完成
    elapsed = (datetime.now() - start_time).total_seconds()
    print("\n" + "=" * 60)
    print(f"【达到最大重试次数】{MAX_RETRIES}次后仍未全部成功 | 在 [{failed_task}] 中断 | 总耗时 {elapsed:.1f}s")
    print("=" * 60)
    sys.exit(1)


if __name__ == "__main__":
    main()
