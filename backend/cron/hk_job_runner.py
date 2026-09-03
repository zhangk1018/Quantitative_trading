#!/usr/bin/env python3
"""
港股 ETL 独立调度 Runner（协作单 30.0 V6，K 2026-09-03 调整口径）

港股为独立线性管道，当日 17:00 触发，串行执行：
  1. sync_hk_stock_list.py    —— 股票列表同步
  2. import_hk_daily.py       —— 日线行情（--incremental，写库 ON CONFLICT 幂等）
  3. sync_hk_basic.py         —— 基本面同步（--date 最新交易日）
  4. compute_indicators_daily.py --market hk    —— 指标
  5. pattern_precompute.py --market hk --latest —— 形态
  6. signal_precompute.py --market hk           —— 信号
  7. daily_snapshot_sync.py --market hk --latest —— 宽表
  8. export_parquet.py --market hk               —— Parquet

与美股 us_job_runner.py 相互独立（解耦），互不影响。单步失败自动重试 3 次
（间隔 5 分钟，可用 HKJOB_RETRY_INTERVAL 覆盖），仍失败落 alerts.log(market=hk)。

用法：
    ./venv/bin/python backend/cron/hk_job_runner.py
    HKJOB_RETRY_INTERVAL=0 ./venv/bin/python backend/cron/hk_job_runner.py  # 关重试间隔(测试)
"""
import os
import sys
import time
import subprocess
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402
from utils.alerting import append_alerts  # noqa: E402

logger = setup_logger('hk_job')

BASE_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = BASE_DIR / 'backend'
PYTHON = str(Path(sys.executable))
MARKET = 'hk'

load_dotenv(BASE_DIR / '.env')  # 显式加载数据库连接配置

MAX_RETRIES = 3
RETRY_INTERVAL_DEFAULT = 300  # 秒


def _get_engine():
    """构建 SQLAlchemy Engine（与 daily_job_runner 一致）。"""
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}"
        f"@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DATABASE')}",
        pool_pre_ping=True, pool_recycle=3600,
    )


def _log_start(task_name: str) -> int:
    """写 task_run_log running 行，返回 id（失败返回 -1）。"""
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            r = conn.execute(text(
                "INSERT INTO task_run_log (task_name, stage, start_time, status, data_date) "
                "VALUES (:tn, :st, :stt, 'running', :dd) RETURNING id"
            ), {"tn": task_name, "st": 8, "stt": datetime.now(), "dd": date.today()})
            conn.commit()
            return int(r.scalar())
    except OperationalError as e:
        logger.warning(f"⚠️ task_run_log 写入失败: {e}")
        return -1


def _log_end(log_id: int, success: bool, exit_code: int, error_message: Optional[str], rows: Optional[int]):
    """更新 task_run_log 结束状态。"""
    if log_id < 0:
        return
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            conn.execute(text(
                "UPDATE task_run_log SET end_time=:et, status=:st, exit_code=:ec, "
                "error_message=:em, rows_affected=:ra WHERE id=:id"
            ), {"et": datetime.now(), "st": "success" if success else "failed",
                "ec": exit_code, "em": error_message or None, "ra": rows, "id": log_id})
            conn.commit()
    except OperationalError as e:
        logger.warning(f"⚠️ task_run_log 更新失败: {e}")


def _run_script(args: List[str], step: str) -> int:
    """执行单个脚本，失败自动重试 MAX_RETRIES 次，最终失败落 alerts.log。返回最终退出码(0=成功)。"""
    last_code = -1
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"▶️ [{step}] 第 {attempt}/{MAX_RETRIES} 次: {' '.join(args)}")
        try:
            proc = subprocess.run(args, capture_output=True, text=True, cwd=str(BASE_DIR))
        except OSError as e:
            logger.error(f"❌ [{step}] 启动失败: {e}")
            last_code = -1
            break
        if proc.stdout.strip():
            logger.info(f"  [{step}] stdout:\n" + "\n".join(proc.stdout.strip().splitlines()[-15:]))
        if proc.stderr.strip():
            logger.warning(f"  [{step}] stderr:\n" + "\n".join(proc.stderr.strip().splitlines()[-10:]))
        last_code = proc.returncode
        if proc.returncode == 0:
            logger.info(f"✅ [{step}] 成功（第 {attempt} 次）")
            return 0
        logger.error(f"❌ [{step}] 失败（exit={proc.returncode}，第 {attempt}/{MAX_RETRIES} 次）")
        if attempt < MAX_RETRIES:
            sec = int(os.environ.get('HKJOB_RETRY_INTERVAL', str(RETRY_INTERVAL_DEFAULT)))
            if sec > 0:
                logger.info(f"⏳ 等待 {sec}s 后重试...")
                time.sleep(sec)

    append_alerts([{
        'level': 'CRITICAL',
        'market': MARKET,
        'message': f"[港股] [{step}] 重试 {MAX_RETRIES} 次仍失败，等待次日覆盖（检查数据源/网络/alerts.log）",
    }])
    return last_code


STEPS: List[tuple[str, List[str]]] = [
    ("股票列表", [PYTHON, str(BACKEND_DIR / "collector/etl/sync_hk_stock_list.py")]),
    ("日线清洗", [PYTHON, str(BACKEND_DIR / "collector/etl/import_hk_daily.py"), "--incremental"]),
    ("基本面", [PYTHON, str(BACKEND_DIR / "collector/etl/sync_hk_basic.py")]),
    ("指标", [PYTHON, str(BACKEND_DIR / "clean/etl/compute_indicators_daily.py"), "--market", MARKET]),
    ("形态", [PYTHON, str(BACKEND_DIR / "clean/etl/pattern_precompute.py"), "--market", MARKET, "--latest"]),
    ("信号", [PYTHON, str(BACKEND_DIR / "clean/etl/signal_precompute.py"), "--market", MARKET]),
    ("宽表", [PYTHON, str(BACKEND_DIR / "collector/etl/daily_snapshot_sync.py"), "--market", MARKET, "--latest"]),
    ("Parquet", [PYTHON, str(BACKEND_DIR / "clean/enrich/export_parquet.py"), "--market", MARKET]),
]


def main() -> None:
    """主函数：港股全链路串行执行。"""
    logger.info("=" * 70)
    logger.info(f"🚀 [港股] ETL 全链路开始（{datetime.now()}）")
    failed: List[str] = []
    for label, args in STEPS:
        task_name = f"hk:{label}"
        log_id = _log_start(task_name)
        code = _run_script(args, label)
        _log_end(log_id, success=(code == 0), exit_code=code, error_message=None, rows=None)
        if code != 0:
            failed.append(label)
    if failed:
        logger.error(f"🛑 [港股] 完成，失败步骤（已重试并告警）: {failed}")
    else:
        logger.info(f"✅ [港股] ETL 全链路成功（列表→日线→基本面→指标→形态→信号→宽表→Parquet）")
    logger.info("=" * 70)
    sys.exit(0 if not failed else 1)


if __name__ == '__main__':
    main()