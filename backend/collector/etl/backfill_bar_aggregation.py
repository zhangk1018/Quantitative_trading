#!/usr/bin/env python3
"""
历史周线/月线数据回填脚本

遍历所有缺失的周/月最后交易日，使用 compute_bar_aggregation.py 逐日回填。
支持断点续跑（跳过已存在的）。

用法:
    # 回填全部周线历史
    ./venv/bin/python backend/collector/etl/backfill_bar_aggregation.py --cycle 1w

    # 回填全部月线历史
    ./venv/bin/python backend/collector/etl/backfill_bar_aggregation.py --cycle 1m

    # 回填最近 N 周
    ./venv/bin/python backend/collector/etl/backfill_bar_aggregation.py --cycle 1w --recent 52
"""
import os
import sys
import subprocess
import argparse
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

_script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _script_dir)

# 项目根目录 = _script_dir 的父目录（_script_dir 是 backend/）
PROJECT_ROOT = os.path.dirname(_script_dir)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

_venv = "venv" if os.path.isdir(os.path.join(PROJECT_ROOT, "venv")) else ".venv"
VENV_PYTHON = os.path.join(PROJECT_ROOT, _venv, "bin", "python")
SCRIPT = os.path.join(PROJECT_ROOT, "backend", "collector", "etl", "compute_bar_aggregation.py")


def get_missing_dates(cycle: str, recent: int = None) -> list:
    """获取缺失的周/月最后交易日列表"""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=os.getenv('PG_PORT', '5432'),
        database=os.getenv('PG_DATABASE', 'quant_trading'),
        user=os.getenv('PG_USER', 'quant_user'),
        password=os.getenv('PG_PASSWORD'),
    )
    cur = conn.cursor()

    if cycle == '1w':
        group_by = "DATE_TRUNC('week', cal_date + INTERVAL '1 day') - INTERVAL '1 day'"
    else:
        group_by = "DATE_TRUNC('month', cal_date)"

    # 获取最新日线日期作为上限
    cur.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
    max_daily = cur.fetchone()[0]

    # 已存在的日期
    cur.execute(f"SELECT DISTINCT trade_date FROM stock_quotes WHERE cycle = %s", (cycle,))
    existing = {row[0] for row in cur.fetchall()}

    # 所有可能的周期最后交易日
    cur.execute(f"""
        SELECT last_date FROM (
            SELECT MAX(cal_date) AS last_date
            FROM trade_calendar
            WHERE is_open = 1
            GROUP BY {group_by}
        ) sub
        WHERE last_date >= '2015-01-05' AND last_date <= %s
        ORDER BY last_date
    """, (max_daily,))
    all_dates = [row[0] for row in cur.fetchall()]

    cur.close()
    conn.close()

    missing = [d for d in all_dates if d not in existing]
    if recent and recent > 0:
        missing = missing[-recent:]
    return missing


def main():
    parser = argparse.ArgumentParser(description='历史周线/月线数据回填')
    parser.add_argument('--cycle', required=True, choices=['1w', '1m'],
                        help='计算周期: 1w=周线, 1m=月线')
    parser.add_argument('--recent', type=int, default=None,
                        help='仅回填最近 N 个周期 (默认: 全部缺失)')
    args = parser.parse_args()

    cycle = args.cycle
    cycle_label = '周线' if cycle == '1w' else '月线'

    print(f"=== {cycle_label}历史数据回填 ===")
    missing = get_missing_dates(cycle, args.recent)
    print(f"缺失周期数: {len(missing)}")

    if not missing:
        print("无缺失数据，跳过")
        return

    total = len(missing)
    success = 0
    fail = 0

    for i, d in enumerate(missing, 1):
        date_str = d.strftime('%Y-%m-%d')
        print(f"\n[{i}/{total}] 处理 {cycle_label}: {date_str} ...", end=' ', flush=True)

        env = os.environ.copy()
        env['PYTHONPATH'] = PROJECT_ROOT
        result = subprocess.run(
            [VENV_PYTHON, SCRIPT, '--cycle', cycle, '--date', date_str, '--force'],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode == 0:
            print(f"✅")
            success += 1
        else:
            print(f"❌ (exit={result.returncode})")
            print(f"   stderr: {result.stderr[-200:]}")
            fail += 1

    print(f"\n=== {cycle_label}回填完成 ===")
    print(f"总计: {total}, 成功: {success}, 失败: {fail}")


if __name__ == "__main__":
    main()