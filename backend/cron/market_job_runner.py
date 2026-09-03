#!/usr/bin/env python3
"""
港/美股 ETL 每日调度 Runner（协作单 30.0 V6 / ⑤ M7 定时任务）

按 K 2026-09-03 确认口径，将某一市场【列表 + 日线 + 基本面】串行执行于同一个
launchd 任务（com.quant.hk_job.plist 16:00 / com.quant.us_job.plist 22:00）：
  1. sync_{market}_stock_list.py     —— 股票列表同步（写入已幂等）
  2. import_{market}_daily.py        —— 日线行情（--incremental 增量，写入 ON CONFLICT 幂等）
  3. sync_{market}_basic.py          —— 基本面同步（--date 最新交易日，写入幂等）

内建故障处理：
  - 单步失败自动重试 3 次（间隔 5 分钟，可经环境变量 MARKET_JOB_RETRY_INTERVAL 调）
  - 仍失败 → 通过 utils.alerting 落 `logs/monitoring/alerts.log` 告警，并记录到任务日志
  - 不阻塞后续（结束即退出，等次日覆盖：写入幂等天然可重入）

日志：logs/cron/market_{market}_{yyyymmdd}.log + stdout/stderr 由 plist 接管。

用法：
    ./venv/bin/python backend/cron/market_job_runner.py --market hk
    ./venv/bin/python backend/cron/market_job_runner.py --market us --init   # 首次全量回填
    MARKET_JOB_RETRY_INTERVAL=0 ./venv/bin/python .../market_job_runner.py --market hk  # 关重试间隔(测试)
"""
import os
import sys
import time
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402
from utils.alerting import append_alerts  # noqa: E402

logger = setup_logger('market_job_runner')

BASE_DIR = Path(__file__).resolve().parents[2]  # 项目根
BACKEND_DIR = BASE_DIR / 'backend'
PYTHON = str(Path(sys.executable))

MAX_RETRIES = 3
RETRY_INTERVAL_DEFAULT = 300  # 秒（5 分钟）


def _sleep_between_retry() -> None:
    """重试间隔（支持 MARKET_JOB_RETRY_INTERVAL 覆盖，0 表示不等待，便于测试）。"""
    try:
        sec = int(os.environ.get('MARKET_JOB_RETRY_INTERVAL', str(RETRY_INTERVAL_DEFAULT)))
    except ValueError:
        sec = RETRY_INTERVAL_DEFAULT
    if sec > 0:
        logger.info(f"⏳ 等待 {sec}s 后重试...")
        time.sleep(sec)


def _run_script(args: List[str], step: str, market: str) -> bool:
    """执行单个 ETL 脚本（含重试），全部失败返回 False。"""
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"▶️ [{step}] 第 {attempt}/{MAX_RETRIES} 次执行: {' '.join(args)}")
        try:
            proc = subprocess.run(args, capture_output=True, text=True, cwd=str(BASE_DIR))
        except OSError as e:
            logger.error(f"❌ [{step}] 启动失败: {e}")
            return False
        if proc.stdout.strip():
            logger.info(f"  [{step}] stdout尾部:\n" + "\n".join(proc.stdout.strip().splitlines()[-15:]))
        if proc.stderr.strip():
            logger.warning(f"  [{step}] stderr:\n" + "\n".join(proc.stderr.strip().splitlines()[-10:]))
        if proc.returncode == 0:
            logger.info(f"✅ [{step}] 成功（第 {attempt} 次）")
            return True
        logger.error(f"❌ [{step}] 失败（exit={proc.returncode}，第 {attempt}/{MAX_RETRIES} 次）")
        if attempt < MAX_RETRIES:
            _sleep_between_retry()

    append_alerts([{
        'level': 'CRITICAL',
        'market': market,
        'message': f"M7 [{step}] 重试 {MAX_RETRIES} 次仍失败，等待次日覆盖（建议检查数据源/网络）",
    }])
    return False


def main() -> None:
    """主函数：按 列表→日线→基本面 串行执行某市场 ETL。"""
    parser = argparse.ArgumentParser(description='港/美股 ETL 每日调度（列表+日线+基本面串行）')
    parser.add_argument('--market', required=True, choices=['hk', 'us'], help='市场')
    parser.add_argument('--init', action='store_true', help='日线首次全量回填(--init)，否则增量(--incremental)')
    args = parser.parse_args()

    market = args.market
    logger.info("=" * 70)
    logger.info(f"🚀 M7 [{market}] ETL 开始（{datetime.now()}）")

    steps: List[List[str]] = [
        [PYTHON, str(BACKEND_DIR / f"collector/etl/sync_{market}_stock_list.py")],
        [PYTHON, str(BACKEND_DIR / f"collector/etl/import_{market}_daily.py"),
         '--init' if args.init else '--incremental'],
        [PYTHON, str(BACKEND_DIR / f"collector/etl/sync_{market}_basic.py")],
    ]
    labels = ['股票列表', '日线行情', '基本面']

    failed: List[str] = []
    for label, step_args in zip(labels, steps):
        if not _run_script(step_args, label, market):
            failed.append(label)

    if failed:
        logger.error(f"🛑 M7 [{market}] 完成，但以下步骤失败（已重试并告警）: {failed}")
    else:
        logger.info(f"✅ M7 [{market}] ETL 全部成功（列表+日线+基本面）")
    logger.info("=" * 70)
    # 退出码：仅当全部成功返回 0；部分失败仍返回 1 以便 plist/监控感知
    sys.exit(0 if not failed else 1)


if __name__ == '__main__':
    main()