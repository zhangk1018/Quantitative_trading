"""
每日定时任务调度守护进程。

替代 launchd plist，在后台运行，按 schedule 自动执行三个阶段任务。
- 阶段1: 周一至周五 15:30 (健康检查 + 股票列表 + 复权因子)
- 阶段2: 周一至周五 17:30 (日线导入)
- 阶段3: 周一至周五 18:15 (补全→基本面→指标→形态→信号→宽表→Parquet)

用法:
    nohup ./venv/bin/python backend/cron/scheduler_daemon.py >> logs/cron/scheduler.log 2>&1 &
"""

import os
import sys
import time
import subprocess
import logging
from datetime import datetime, date
from pathlib import Path

# --- 配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python"
RUNNER = PROJECT_ROOT / "backend" / "cron" / "daily_job_runner.py"
LOG_DIR = PROJECT_ROOT / "logs" / "cron"

# 阶段调度时间 (hour, minute)
SCHEDULE: dict[int, tuple[int, int]] = {
    1: (15, 30),
    2: (17, 30),
    3: (18, 15),
}

CHECK_INTERVAL = 60  # 秒


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "scheduler.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def is_weekday() -> bool:
    """周一至周五返回 True。"""
    return datetime.now().weekday() < 5


def run_stage(stage: int) -> None:
    """执行指定阶段。"""
    stage_names = {1: "阶段1(健康检查+股票列表+复权因子)", 2: "阶段2(日线导入)", 3: "阶段3(补全→基本面→指标→信号→宽表→Parquet)"}
    name = stage_names.get(stage, f"阶段{stage}")
    logging.info(f"触发 {name}")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["APP_ENV"] = "dev"

    try:
        result = subprocess.run(
            [str(VENV_PYTHON), str(RUNNER), "--stage", str(stage)],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=7200,  # 最长 2 小时
        )
        if result.returncode == 0:
            logging.info(f"{name} 完成 (exit={result.returncode})")
        else:
            logging.error(f"{name} 失败 (exit={result.returncode}): {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        logging.error(f"{name} 超时 (>2h)")
    except Exception as e:
        logging.error(f"{name} 异常: {e}")


def main() -> None:
    setup_logging()
    logging.info("调度守护进程启动")
    logging.info(
        f"调度时间: 阶段1={SCHEDULE[1][0]:02d}:{SCHEDULE[1][1]:02d}, "
        f"阶段2={SCHEDULE[2][0]:02d}:{SCHEDULE[2][1]:02d}, "
        f"阶段3={SCHEDULE[3][0]:02d}:{SCHEDULE[3][1]:02d}"
    )
    logging.info(f"工作日: 周一至周五 | 检查间隔: {CHECK_INTERVAL}s")

    # 今日已执行标记
    today_executed: dict[int, bool] = {}

    while True:
        now = datetime.now()
        today = now.date()

        # 新的一天，重置标记
        if date.today() != today:
            today_executed.clear()

        if not is_weekday():
            time.sleep(CHECK_INTERVAL)
            continue

        for stage, (hour, minute) in SCHEDULE.items():
            if today_executed.get(stage):
                continue

            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # 在预定时间的前后 5 分钟内触发
            if abs((now - scheduled).total_seconds()) < 300:
                today_executed[stage] = True
                run_stage(stage)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()