#!/usr/bin/env python3
"""导出数据库数据到Parquet文件（包含14个技术指标pattern列）"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pathlib import Path
from datetime import datetime
import logging

import pandas as pd
from sqlalchemy import create_engine, text
from utils.config import load_config

logger = logging.getLogger(__name__)

# 项目根目录（与 DataLoader 使用同一路径）
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# 备份保留数量
MAX_BACKUPS = 3


def _write_task_run_log(engine, status: str, data_date: str, rows_affected: int,
                        error_message: str = None, extra_metrics: dict = None):
    """写入 task_run_log 表，确保监控看板能检测到导出状态"""
    try:
        with engine.connect() as conn:
            # 先检查是否已有今日记录（避免重复写入）
            existing = conn.execute(text("""
                SELECT id FROM task_run_log
                WHERE task_name = 'parquet_export' AND start_time >= CURRENT_DATE
                LIMIT 1
            """)).fetchone()
            if existing:
                conn.execute(text("""
                    UPDATE task_run_log
                    SET end_time = :end_time, status = :status, exit_code = :exit_code,
                        error_message = :error_message, rows_affected = :rows_affected,
                        extra_metrics = :extra_metrics, data_date = :data_date
                    WHERE id = :id
                """), {
                    "id": existing[0],
                    "end_time": datetime.now(),
                    "status": status,
                    "exit_code": 0 if status == "success" else 1,
                    "error_message": error_message,
                    "rows_affected": rows_affected,
                    "extra_metrics": json.dumps(extra_metrics) if extra_metrics else None,
                    "data_date": data_date,
                })
            else:
                conn.execute(text("""
                    INSERT INTO task_run_log (task_name, stage, start_time, end_time, status, exit_code,
                        error_message, rows_affected, extra_metrics, data_date)
                    VALUES ('parquet_export', 0, :start_time, :end_time, :status, :exit_code,
                        :error_message, :rows_affected, :extra_metrics, :data_date)
                """), {
                    "start_time": datetime.now(),
                    "end_time": datetime.now(),
                    "status": status,
                    "exit_code": 0 if status == "success" else 1,
                    "error_message": error_message,
                    "rows_affected": rows_affected,
                    "extra_metrics": json.dumps(extra_metrics) if extra_metrics else None,
                    "data_date": data_date,
                })
            conn.commit()
    except Exception as e:
        logger.warning(f"写入 task_run_log 失败（不影响导出）: {e}")


def export_to_parquet():
    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user@localhost:5432/quant_trading')
    output_path = str(PROJECT_ROOT / 'data' / 'price' / 'daily' / 'latest_quotes.parquet')

    print("📤 导出数据到Parquet...")

    try:
        engine = create_engine(db_url)
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        print(f'TASK_RESULT:{json.dumps({"rows_affected": 0, "extra_metrics": {"error": "db_connect_failed", "detail": str(e)}})}')
        return

    try:
        with engine.connect() as conn:
            # 获取最新交易日期
            result = conn.execute(text("""
                SELECT MAX(trade_date) as latest_date
                FROM stock_daily_snapshot
            """))
            latest_date = result.fetchone()[0]
            if latest_date is None:
                logger.error("stock_daily_snapshot 表为空")
                _write_task_run_log(engine, "failed", "unknown", 0, "stock_daily_snapshot 表为空")
                print(f'TASK_RESULT:{json.dumps({"rows_affected": 0, "extra_metrics": {"error": "empty_table"}})}')
                return

            print(f"📅 导出日期: {latest_date}")

            # 导出数据
            result = conn.execute(text(f"""
                SELECT * FROM stock_daily_snapshot
                WHERE trade_date = '{latest_date}'
            """))
            df = pd.DataFrame(result.fetchall(), columns=result.keys())

            if df.empty:
                logger.warning(f"{latest_date} 无数据")
                _write_task_run_log(engine, "failed", str(latest_date), 0, f"{latest_date} 无数据")
                print(f'TASK_RESULT:{json.dumps({"rows_affected": 0, "extra_metrics": {"error": "no_data", "date": str(latest_date)}})}')
                return

            # 转换日期格式为YYYYMMDD
            df['trade_date'] = df['trade_date'].apply(lambda x: x.strftime('%Y%m%d') if x else '')

            # 备份旧文件（如果存在）
            old_path = Path(output_path)
            if old_path.exists():
                _rotate_backups(output_path)

            # 保存
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            df.to_parquet(output_path, index=False)

    except Exception as e:
        logger.error(f"导出 Parquet 失败: {type(e).__name__}: {e}")
        try:
            data_date = str(latest_date)
        except NameError:
            data_date = "unknown"
        _write_task_run_log(engine, "failed", data_date, 0, f"{type(e).__name__}: {e}")
        print(f'TASK_RESULT:{json.dumps({"rows_affected": 0, "extra_metrics": {"error": "export_failed", "detail": str(e)}})}')
        return

    # 导出成功：写入 task_run_log
    extra = {"columns": len(df.columns), "date": str(latest_date)}
    _write_task_run_log(engine, "success", str(latest_date), len(df), extra_metrics=extra)

    print(f"✅ 导出完成: {output_path}")
    print(f"📊 导出记录数: {len(df)}")
    print(f"📋 列数: {len(df.columns)}")
    print(f'TASK_RESULT:{json.dumps({"rows_affected": len(df), "extra_metrics": extra})}')

    # 验证pattern列
    pattern_cols = [c for c in df.columns if any(x in c for x in ['ma_long', 'ma_short', 'macd_low', 'macd_high', 'boll_break', 'rsi_low', 'rsi_high'])]
    print(f"🔍 Pattern列数: {len(pattern_cols)}")
    for col in sorted(pattern_cols):
        count = df[col].sum() if df[col].dtype in ['int64', 'bool'] else 0
        print(f"  - {col}: {count}")


def _rotate_backups(filepath: str):
    """轮转备份旧 parquet 文件，保留最近 MAX_BACKUPS 个备份"""
    base = Path(filepath)
    for i in range(MAX_BACKUPS, 0, -1):
        old = base.with_suffix(f'.parquet.bak{i}')
        new = base.with_suffix(f'.parquet.bak{i + 1}')
        if i == MAX_BACKUPS:
            if old.exists():
                old.unlink()
        elif old.exists():
            old.rename(new)
    if base.exists():
        base.rename(base.with_suffix('.parquet.bak1'))


if __name__ == '__main__':
    export_to_parquet()
