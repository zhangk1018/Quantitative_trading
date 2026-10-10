#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性回填：港股 stock_quotes 主价格列改为**前复权**（协作单 45.0 订正）。

背景：港股库内主价格列（open/high/low/close）原先存**后复权**（hfq，仿射口径
`hfq = a·raw + b`），导致：
  - 选股表/个股头部/自选股显示 HK$5.42（碧桂园 2007.HK 真值 0.183）；
  - K 线图按「乘性重标定」换算后把历史压平（2025-12 真实 0.415 显示成 0.19）。

修复：主价格列改存**前复权**，直接采用新浪 `adjust='qfq'`（乘性口径，无法由仿射后复权
精确换算）。`raw_*` 保留不复权、`adj_*` 保留后复权 hfq（供 `backward` 消费方）。
amount 同步改为真实成交额 `raw_close × volume`。

抓取失败时**兜底**用 `compute_qfq_prices`（由库内 raw_*/adj_*/adj_share 近似重建，
对多数股票精确、少数含并股/供股的仙股有偏差）并告警，保证不中断。

执行后必须重跑（否则派生数据仍是旧口径）：
  1. hk 周/月线聚合（bar_aggregation --market hk --rebuild）
  2. 宽表 / stock_daily_snapshot 同步
  3. 选股 parquet 导出
  4. 快照缓存 CACHE_VERSION bump + 重建

用法：
    ./venv/bin/python backend/scripts/backfill_hk_qfq.py [--code 2007.HK] [--limit N] [--dry-run]
"""
import argparse
import logging
import os
import sys
import time
from typing import Optional

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector.etl.import_hk_daily import _load_dotenv, _connect, _list_hk_codes  # noqa: E402
from collector.utils.adj_adjust import compute_qfq_prices  # noqa: E402

logger = logging.getLogger('backfill_hk_qfq')

# 主价格列精度上限（stock_quotes.open/high/low/close 为 NUMERIC(12,4)）
_PRICE_MAX = 1e8

_SELECT = """
    SELECT trade_date, raw_open, raw_high, raw_low, raw_close,
           adj_close, adj_share, volume, close AS cur_close
    FROM stock_quotes
    WHERE market = 'hk' AND code = %s AND cycle = '1d'
      AND raw_close IS NOT NULL AND raw_close > 0
    ORDER BY trade_date
"""

_UPDATE = """
    UPDATE stock_quotes q SET
        open = v.open, high = v.high, low = v.low, close = v.close,
        pre_close = v.pre_close, amount = v.amount
    FROM (VALUES %s) AS v(market, code, trade_date, open, high, low, close, pre_close, amount)
    WHERE q.market = v.market AND q.code = v.code AND q.cycle = '1d'
      AND q.trade_date = v.trade_date
      AND (q.close IS DISTINCT FROM v.close
           OR q.open IS DISTINCT FROM v.open
           OR q.high IS DISTINCT FROM v.high
           OR q.low IS DISTINCT FROM v.low
           OR q.pre_close IS DISTINCT FROM v.pre_close)
"""


def _fetch_sina_qfq(code: str, timeout: int = 30) -> Optional[pd.DataFrame]:
    """抓取新浪前复权 OHLC（index=交易日）。失败/超时返回 None。

    用 **daemon 线程 + join 超时** 做硬超时：`akshare`（requests）内部未设超时，
    半死 socket 会**永久阻塞**（SIGALRM 无法打断 C 层 socket read，实测卡死 >9 分钟）。
    超时后放弃该线程（daemon，不阻塞进程退出），继续下一只。
    """
    import threading

    box: dict = {}

    def _do() -> None:
        try:
            import akshare as ak
            box['df'] = ak.stock_hk_daily(symbol=code.split('.')[0].zfill(5), adjust='qfq')
        except Exception as e:  # noqa: BLE001 - 网络/解析错误一律走兜底
            box['err'] = e

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        logger.warning('  %s: 新浪 qfq 抓取超时（%ds，socket 阻塞）→ 跳过', code, timeout)
        return None
    if 'err' in box:
        logger.warning('  %s: 新浪 qfq 抓取异常: %s', code, box['err'])
        return None
    df = box.get('df')
    if df is None or df.empty:
        return None
    df = df.set_index(pd.to_datetime(df['date']))
    df = df[~df.index.duplicated(keep='last')]
    return df[['open', 'high', 'low', 'close']].apply(pd.to_numeric, errors='coerce')


def refresh_one(conn, code: str, dry_run: bool = False,
                fallback_reconstruct: bool = False) -> Optional[int]:
    """重算单只港股主价格列（前复权）。返回变更行数；抓取失败且未启用兜底时返回 None。"""
    from psycopg2.extras import execute_values
    with conn.cursor() as cur:
        cur.execute(_SELECT, (code,))
        rows = cur.fetchall()
    if not rows:
        return 0
    df = pd.DataFrame(rows, columns=[
        'trade_date', 'raw_open', 'raw_high', 'raw_low', 'raw_close',
        'adj_close', 'adj_share', 'volume', 'cur_close'])
    df['td'] = pd.to_datetime(df['trade_date'])

    sina = _fetch_sina_qfq(code)
    if sina is not None:
        # 注意：reindex 后索引为交易日，需 reset_index 以按**位置**与 df 对齐（否则整列 NaN）
        s = sina.reindex(df['td'].values).ffill().bfill().reset_index(drop=True)
        for c in ('open', 'high', 'low', 'close'):
            df['q_' + c] = pd.to_numeric(s[c], errors='coerce').fillna(
                df['raw_' + c].reset_index(drop=True))
    elif fallback_reconstruct:
        logger.warning('  %s: 新浪 qfq 不可得 → 兜底重建（可能对并股/供股标的偏差）', code)
        rec = compute_qfq_prices(df)
        for c in ('open', 'high', 'low', 'close'):
            df['q_' + c] = rec['qfq_' + c].reset_index(drop=True)
    else:
        # 网络抖动/超时：跳过（不写近似值），留待重跑；避免把不可靠口径落库
        logger.warning('  %s: 新浪 qfq 不可得 → 跳过（不写近似值）', code)
        return None

    # 合理性掩码：新浪 qfq 个别标的早期行有垃圾值（实测 0286.HK open=3.18e8，
    # 超出 NUMERIC(12,4) 上限 → 「numeric field overflow」整只失败）；这类单元格
    # 回退原始价（raw_*），保证写入可行且不破坏同段其余行的口径。
    n_junk = 0
    for c in ('open', 'high', 'low', 'close'):
        col = pd.to_numeric(df['q_' + c], errors='coerce')
        bad = ~np.isfinite(col) | (col <= 0) | (col >= _PRICE_MAX)
        if c == 'close':
            n_junk = int(bad.sum())
        df['q_' + c] = col.mask(bad, df['raw_' + c].reset_index(drop=True))
    if n_junk:
        logger.warning('  %s: 新浪 qfq 有 %d 行越界/非法值 → 回退原始价', code, n_junk)

    df['q_pre_close'] = df['q_close'].shift(1).fillna(df['q_open'])
    vol = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
    df['q_amount'] = (pd.to_numeric(df['raw_close'], errors='coerce') * vol).round(2)

    changed = int((df['q_close'].astype(float)
                   != pd.to_numeric(df['cur_close'], errors='coerce').astype(float)).sum())
    if changed == 0 or dry_run:
        return changed
    values = [
        ('hk', code, r['trade_date'], r['q_open'], r['q_high'], r['q_low'], r['q_close'],
         r['q_pre_close'], r['q_amount'])
        for r in df[['trade_date', 'q_open', 'q_high', 'q_low', 'q_close',
                     'q_pre_close', 'q_amount']].to_dict('records')
    ]
    try:
        with conn.cursor() as cur:
            execute_values(cur, _UPDATE, values, page_size=1000)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description='港股主价格列前复权回填（新浪 qfq）')
    parser.add_argument('--code', help='仅处理指定代码（如 2007.HK）')
    parser.add_argument('--limit', type=int, default=0, help='最多处理 N 只（调试用）')
    parser.add_argument('--dry-run', action='store_true', help='只统计不写库')
    parser.add_argument('--fallback-reconstruct', action='store_true',
                        help='新浪 qfq 不可得时用 compute_qfq_prices 近似兜底（默认跳过，不写近似值）')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    _load_dotenv()
    conn = _connect()
    codes = [args.code] if args.code else _list_hk_codes(conn)
    if args.limit:
        codes = codes[:args.limit]
    logger.info('港股待回填代码数: %d（dry_run=%s）', len(codes), args.dry_run)

    t0 = time.time()
    done = changed_total = skipped = 0
    failed = []
    for i, code in enumerate(codes, 1):
        try:
            n = refresh_one(conn, code, dry_run=args.dry_run,
                            fallback_reconstruct=args.fallback_reconstruct)
            if n is None:
                skipped += 1
            else:
                changed_total += n
                done += 1
        except Exception as e:  # noqa: BLE001 - 单只失败不阻断整体
            failed.append(code)
            logger.warning('  %s 回填失败: %s', code, e)
        if i % 100 == 0 or i == len(codes):
            logger.info('进度 %d/%d，累计变更 %d 行，跳过 %d，失败 %d，耗时 %.0fs',
                        i, len(codes), changed_total, skipped, len(failed), time.time() - t0)

    logger.info('✅ 回填完成：处理 %d 只，变更 %d 行，跳过 %d 只，失败 %d 只，耗时 %.0fs',
                done, changed_total, skipped, len(failed), time.time() - t0)
    if failed:
        logger.warning('失败列表（前 20）: %s', failed[:20])
    conn.close()
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
