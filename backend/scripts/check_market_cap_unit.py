#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hk/us 市值单位哨兵（协作单 50.0 观察期用，每日跑）。

**契约**：`stock_daily_basic.total_mv/circ_mv` 与 `stock_daily_snapshot.market_cap/circ_mv`
全市场统一为 **「万元」**（cn/hk/us 一致；`models.py`/`schemas.py`/`screener_service` 均声明万元）。

**为什么需要哨兵**：2026-10-11 发现 hk/us 市值在 V020 纠正确认后被再次缩小 1e4 倍
（`0700.HK` 386,253,900 → 38,625.39 万元），来源为**未登记的手工/临时写入**（`task_run_log`
显示窗口内无任何调度任务）。按「来源不确定 → 挂监控观察一周」处置，本脚本每日校验量级。

**判定**：
- 对每只股票取最近一个交易日的 `market_cap`，换算成「亿元」后应落在 [1e-2, 1e6]（1e-2亿=100万 ～ 1e6亿=100万亿）；
- 同时要求 **中位数 ≥ 1 亿元**（真实市场分布的下限经验值，防止整体被缩小 1e4 而“看起来还行”）；
- 任何一条不满足 → 退出码 1 并打印异常样本（供按 §5.3 自提单）。

用法：`./venv/bin/python backend/scripts/check_market_cap_unit.py [--market hk] [--market us]`
"""
import argparse
import os
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

# 单位：万元 → 亿元 = ÷1e4
MIN_YI, MAX_YI = 1e-2, 1e6      # 单只股票市值合理区间（亿元）
MIN_MEDIAN_YI = 1.0             # 全市场中位数下限（亿元）


def check_market(conn, market: str) -> Tuple[bool, List[str]]:
    """校验单市场最新交易日的 market_cap 量级是否落在「万元」口径。"""
    cur = conn.cursor()
    cur.execute("""
        WITH latest AS (
            SELECT max(trade_date) d FROM stock_daily_snapshot WHERE market = %s
        )
        SELECT code, market_cap
          FROM stock_daily_snapshot, latest
         WHERE market = %s AND trade_date = latest.d AND market_cap IS NOT NULL AND market_cap > 0
    """, (market, market))
    rows = cur.fetchall()
    if not rows:
        return False, [f'{market}: 无最新交易日市值数据（无法校验）']

    vals_yi = sorted(float(v) / 1e4 for _, v in rows)      # 万元 → 亿元
    med = vals_yi[len(vals_yi) // 2]
    bad = [(c, float(v) / 1e4) for c, v in rows if not (MIN_YI <= float(v) / 1e4 <= MAX_YI)]
    problems = []
    if bad:
        problems.append(f'{market}: {len(bad)} 只市值超出合理区间（亿元）{bad[:5]}')
    if med < MIN_MEDIAN_YI:
        problems.append(f'{market}: 市值中位数 {med:.4f} 亿元 < {MIN_MEDIAN_YI} 亿元 → 疑被整体缩小 1e4'
                        f'（正确口径应为「万元」）')
    return (not problems), problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--market', action='append', default=None,
                    help='市场（cn/hk/us），可多次；缺省校验 cn+hk+us')
    args = ap.parse_args()
    markets = args.market or ['cn', 'hk', 'us']

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), '.env'))
    conn = psycopg2.connect(
        host='localhost', port=5432, dbname=os.environ.get('PG_DATABASE', 'quant_trading'),
        user=os.environ.get('PG_USER', 'quant_user'), password=os.environ.get('PG_PASSWORD', ''))

    ok_all, msgs = True, []
    for m in markets:
        ok, msgs_m = check_market(conn, m)
        ok_all &= ok
        msgs += msgs_m
    conn.close()

    if ok_all:
        print(f'✅ hk/us 市值单位哨兵通过（市场：{",".join(markets)}）—— 均为「万元」口径')
        return 0
    print('❌ 市值单位哨兵告警：')
    for m in msgs:
        print('   -', m)
    return 1


if __name__ == '__main__':
    sys.exit(main())
