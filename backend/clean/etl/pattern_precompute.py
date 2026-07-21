#!/usr/bin/env python3
"""K 线形态 ETL: stock_quotes_<year> → stock_indicators_<year> (5 个 pattern_* 列).

K 2026-06-17 决策：
  - 真库: TA-Lib 0.6.8 (已在 .venv 装好)
  - 参数: penetration=0.3 (统一)
  - 输出值: -100/-80/0/80/100 (TA-Lib 原生, 含强度)

用法:
  python backend/clean/etl/pattern_precompute.py                    # 全年全市场
  python backend/clean/etl/pattern_precompute.py --latest           # 增量：仅最近 10 天
  python backend/clean/etl/pattern_precompute.py --latest --days 5  # 增量：最近 5 天
  python backend/clean/etl/pattern_precompute.py --code 000001      # 单只测试
"""
import os
import sys
import argparse
import logging
import time

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import psycopg2
import pandas as pd
import numpy as np
import talib
from utils.config import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('pattern_precompute')

PENETRATION = 0.3
PATTERN_COLS = [
    'pattern_morning_star',
    'pattern_evening_star',
    'pattern_bullish_engulfing',
    'pattern_bearish_engulfing',
    'pattern_hammer',
]


def compute_patterns_1d(open_, high_, low_, close_):
    """对单只股票 1D 数组算 5 个 pattern (TA-Lib 真库).

    返回 dict {pattern_xxx: int_array, ...} 与输入同长度, 未触发=0.
    """
    return {
        'pattern_morning_star':     talib.CDLMORNINGSTAR(open_, high_, low_, close_, penetration=PENETRATION),
        'pattern_evening_star':     talib.CDLEVENINGSTAR(open_, high_, low_, close_, penetration=PENETRATION),
        # 吞没: 正/负 拆成两列
        'pattern_bullish_engulfing': np.maximum(talib.CDLENGULFING(open_, high_, low_, close_), 0),
        'pattern_bearish_engulfing': np.minimum(talib.CDLENGULFING(open_, high_, low_, close_), 0),
        'pattern_hammer':           talib.CDLHAMMER(open_, high_, low_, close_),
    }


def process_stock(cur, code: str, year_table: str = 'stock_quotes_2026',
                  lookback_days: int = 0) -> int:
    """处理单只股票: 读 K 线 → 算 pattern → 批量 UPDATE stock_indicators_<year>.

    Args:
        cur: 数据库游标
        code: 股票代码
        year_table: 年份分区表名
        lookback_days: 仅更新最近 N 天 (0 = 全量)

    Returns:
        更新的行数
    """
    year = year_table.replace('stock_quotes_', '')
    ind_table = f'stock_indicators_{year}'

    if lookback_days > 0:
        # 增量模式：多读 30 天缓冲用于 TA-Lib 计算，但只更新最近 lookback_days 天
        cur.execute(f'''
            SELECT trade_date, open, high, low, close
            FROM "{year_table}"
            WHERE code=%s AND cycle='1d'
            ORDER BY trade_date DESC
            LIMIT %s
        ''', (code, lookback_days + 30))
        rows = cur.fetchall()
        rows.reverse()
    else:
        cur.execute(f'''
            SELECT trade_date, open, high, low, close
            FROM "{year_table}"
            WHERE code=%s AND cycle='1d'
            ORDER BY trade_date
        ''', (code,))
        rows = cur.fetchall()

    if len(rows) < 3:
        logger.debug(f'{code} 数据不足 3 天, 跳过')
        return 0

    df = pd.DataFrame(rows, columns=['trade_date', 'open', 'high', 'low', 'close'])
    for c in ['open', 'high', 'low', 'close']:
        df[c] = df[c].astype(float)

    patterns = compute_patterns_1d(
        df['open'].values, df['high'].values, df['low'].values, df['close'].values
    )
    df['pattern_morning_star']     = patterns['pattern_morning_star']
    df['pattern_evening_star']     = patterns['pattern_evening_star']
    df['pattern_bullish_engulfing'] = patterns['pattern_bullish_engulfing']
    df['pattern_bearish_engulfing'] = patterns['pattern_bearish_engulfing']
    df['pattern_hammer']           = patterns['pattern_hammer']

    # 增量模式：只取最后 lookback_days 天进行更新
    if lookback_days > 0:
        df = df.tail(lookback_days)

    # 批量 UPDATE (executemany)
    # 仅 update 有命中的行 (pattern != 0)
    update_rows = []
    for _, r in df.iterrows():
        if any(r[c] != 0 for c in PATTERN_COLS):
            update_rows.append((
                int(r['pattern_morning_star']),
                int(r['pattern_evening_star']),
                int(r['pattern_bullish_engulfing']),
                int(r['pattern_bearish_engulfing']),
                int(r['pattern_hammer']),
                code, r['trade_date'],
            ))

    if not update_rows:
        return 0

    cur.executemany(f'''
        UPDATE "{ind_table}" SET
            pattern_morning_star     = %s,
            pattern_evening_star     = %s,
            pattern_bullish_engulfing = %s,
            pattern_bearish_engulfing = %s,
            pattern_hammer           = %s
        WHERE code = %s AND trade_date = %s AND cycle = '1d'
    ''', update_rows)

    return len(update_rows)


def main():
    parser = argparse.ArgumentParser(description='K 线形态 ETL')
    parser.add_argument('--code', type=str, help='单只股票代码')
    parser.add_argument('--year', type=str, default='2026', help='年份 (默认 2026)')
    parser.add_argument('--limit', type=int, default=0, help='限制股票数 (测试用)')
    parser.add_argument('--latest', action='store_true', help='增量模式：仅计算最近 days 天')
    parser.add_argument('--days', type=int, default=10, help='增量模式回溯天数 (默认 10)')
    args = parser.parse_args()

    lookback_days = args.days if args.latest else 0

    db_config = config.get('database', {})
    conn = psycopg2.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432),
        dbname=db_config.get('database', 'quant_trading'),
        user=db_config.get('username', 'quant_user'),
        password=db_config.get('password', ''),
    )
    conn.set_session(autocommit=False)
    cur = conn.cursor()
    year_table = f'stock_quotes_{args.year}'

    if args.code:
        n = process_stock(cur, args.code, year_table, lookback_days=lookback_days)
        conn.commit()
        mode = f'增量(最近{args.days}天)' if args.latest else '全量'
        logger.info(f'✅ {args.code}: 更新 {n} 行 ({mode})')
        conn.close()
        return

    # 全市场
    if args.latest:
        # 增量模式：只查最近 days 天有交易的股票
        cur.execute(f'''
            SELECT DISTINCT code FROM "{year_table}"
            WHERE cycle='1d'
            AND trade_date >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY code
        ''', (args.days + 30,))
    else:
        cur.execute(f'SELECT DISTINCT code FROM "{year_table}" ORDER BY code')
    codes = [r[0] for r in cur.fetchall()]
    if args.limit:
        codes = codes[:args.limit]
    total = len(codes)
    mode = f'增量(最近{args.days}天)' if args.latest else '全量'
    logger.info(f'开始 {year_table} 全市场 K 线形态 ETL [{mode}]: {total} 只')

    success = 0
    fail = 0
    total_rows = 0
    t0 = time.time()
    for i, code in enumerate(codes):
        try:
            n = process_stock(cur, code, year_table, lookback_days=lookback_days)
            if n > 0:
                success += 1
            total_rows += n
            if (i + 1) % 200 == 0:
                conn.commit()
                elapsed = time.time() - t0
                speed = (i + 1) / elapsed
                eta = (total - i - 1) / speed
                logger.info(
                    f'进度: {i+1}/{total} ({(i+1)/total*100:.1f}%), '
                    f'成功 {success}, 失败 {fail}, 命中 {total_rows} 行, '
                    f'{speed:.1f}只/s, ETA {eta/60:.1f}分'
                )
        except Exception as e:
            conn.rollback()
            fail += 1
            logger.warning(f'{code} 失败: {e}')

    conn.commit()
    elapsed = time.time() - t0
    logger.info(
        f'✅ 完成: 成功 {success}, 失败 {fail}, 总命中 {total_rows} 行, '
        f'耗时 {elapsed/60:.1f}分'
    )
    conn.close()


if __name__ == '__main__':
    main()
