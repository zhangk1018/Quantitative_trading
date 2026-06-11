#!/usr/bin/env python3
"""
信号预计算脚本

功能：
- 预计算所有股票的 MACD 金叉/死叉信号
- 预计算 RSI 超买/超卖信号
- 预计算 BOLL 突破信号
- 支持全量计算和增量更新
- 信号写入 trade_signals 表，供 API 查询使用

用法：
    python backend/clean/tools/precompute_signals.py --all              # 全量计算
    python backend/clean/tools/precompute_signals.py --code 000001      # 单只股票
    python backend/clean/tools/precompute_signals.py --incremental      # 增量（最近30天）
    python backend/clean/tools/precompute_signals.py --incremental --days 60
"""

import argparse
import sys
import os
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pandas as pd
import numpy as np
from utils.config import config
from collector.storage.postgresql_storage import PostgreSQLStorage


def _ema(series: pd.Series, span: int) -> pd.Series:
    """计算指数移动平均"""
    return series.ewm(span=span, adjust=False).mean()


def _sma(series: pd.Series, window: int) -> pd.Series:
    """计算简单移动平均"""
    return series.rolling(window=window, min_periods=1).mean()


def compute_macd(close: pd.Series, span_fast=12, span_slow=26, span_signal=9):
    """计算 MACD 指标"""
    ema_fast = _ema(close, span_fast)
    ema_slow = _ema(close, span_slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, span_signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_rsi(close: pd.Series, period=6):
    """计算 RSI 指标"""
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_boll(close: pd.Series, period=20, num_std=2):
    """计算 BOLL 指标"""
    mid = _sma(close, period)
    std = close.rolling(window=period, min_periods=1).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def extract_signals(df: pd.DataFrame) -> pd.DataFrame:
    """从日线数据中提取 MACD/RSI/BOLL 信号"""
    if df is None or len(df) < 26:
        return pd.DataFrame()

    df = df.sort_values('trade_date').reset_index(drop=True)
    close = df['close'].astype(float)

    # 计算指标
    macd_line, signal_line, macd_hist = compute_macd(close)
    rsi = compute_rsi(close)
    boll_upper, boll_mid, boll_lower = compute_boll(close)

    signals = []

    for i in range(1, len(df)):
        trade_date = df['trade_date'].iloc[i]
        curr_close = close.iloc[i]

        # MACD 金叉/死叉
        if not pd.isna(macd_line.iloc[i]) and not pd.isna(signal_line.iloc[i]):
            prev_macd = macd_line.iloc[i - 1]
            prev_signal = signal_line.iloc[i - 1]
            curr_macd_val = macd_line.iloc[i]
            curr_signal_val = signal_line.iloc[i]

            if prev_macd <= prev_signal and curr_macd_val > curr_signal_val:
                signals.append({
                    'code': df['code'].iloc[i],
                    'cycle': 'daily',
                    'trade_date': trade_date,
                    'signal_type': 'macd_golden_cross',
                    'signal_value': round(curr_macd_val, 4),
                    'signal_strength': 3,
                    'description': f'MACD金叉: MACD={curr_macd_val:.4f}, Signal={curr_signal_val:.4f}'
                })
            elif prev_macd >= prev_signal and curr_macd_val < curr_signal_val:
                signals.append({
                    'code': df['code'].iloc[i],
                    'cycle': 'daily',
                    'trade_date': trade_date,
                    'signal_type': 'macd_death_cross',
                    'signal_value': round(curr_macd_val, 4),
                    'signal_strength': 3,
                    'description': f'MACD死叉: MACD={curr_macd_val:.4f}, Signal={curr_signal_val:.4f}'
                })

        # RSI 超买/超卖
        if not pd.isna(rsi.iloc[i]):
            curr_rsi = rsi.iloc[i]
            prev_rsi = rsi.iloc[i - 1]

            if prev_rsi >= 80 and curr_rsi < 80:
                signals.append({
                    'code': df['code'].iloc[i],
                    'cycle': 'daily',
                    'trade_date': trade_date,
                    'signal_type': 'rsi_overbought',
                    'signal_value': round(curr_rsi, 2),
                    'signal_strength': 2,
                    'description': f'RSI超买回落: RSI={curr_rsi:.2f}'
                })
            elif prev_rsi <= 20 and curr_rsi > 20:
                signals.append({
                    'code': df['code'].iloc[i],
                    'cycle': 'daily',
                    'trade_date': trade_date,
                    'signal_type': 'rsi_oversold',
                    'signal_value': round(curr_rsi, 2),
                    'signal_strength': 2,
                    'description': f'RSI超卖反弹: RSI={curr_rsi:.2f}'
                })

        # BOLL 突破
        if not pd.isna(boll_upper.iloc[i]) and not pd.isna(boll_lower.iloc[i]):
            curr_upper = boll_upper.iloc[i]
            curr_lower = boll_lower.iloc[i]
            prev_close = close.iloc[i - 1]
            prev_upper = boll_upper.iloc[i - 1]
            prev_lower = boll_lower.iloc[i - 1]

            if prev_close <= prev_upper and curr_close > curr_upper:
                signals.append({
                    'code': df['code'].iloc[i],
                    'cycle': 'daily',
                    'trade_date': trade_date,
                    'signal_type': 'boll_break_upper',
                    'signal_value': round(curr_close, 2),
                    'signal_strength': 2,
                    'description': f'突破BOLL上轨: Price={curr_close:.2f}, Upper={curr_upper:.2f}'
                })
            elif prev_close >= prev_lower and curr_close < curr_lower:
                signals.append({
                    'code': df['code'].iloc[i],
                    'cycle': 'daily',
                    'trade_date': trade_date,
                    'signal_type': 'boll_break_lower',
                    'signal_value': round(curr_close, 2),
                    'signal_strength': 2,
                    'description': f'跌破BOLL下轨: Price={curr_close:.2f}, Lower={curr_lower:.2f}'
                })

    if not signals:
        return pd.DataFrame()
    return pd.DataFrame(signals)


def get_stock_codes(storage) -> list:
    """获取所有股票代码"""
    df = storage.get_quotes(code=None, cycle='daily')
    if df.empty:
        return []
    return sorted(df['code'].unique())


def load_stock_quotes(storage, code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """加载单只股票的日线数据"""
    df = storage.get_quotes(code=code, cycle='daily', start_date=start_date, end_date=end_date)
    if df.empty:
        return pd.DataFrame()
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
    return df


def clear_stock_signals(storage, code: str, since_date: str = None):
    """清除某只股票的旧信号"""
    try:
        cursor = storage.conn.cursor()
        if since_date:
            cursor.execute(
                "DELETE FROM trade_signals WHERE code = %s AND cycle = 'daily' AND trade_date >= %s",
                (code, since_date)
            )
        else:
            cursor.execute(
                "DELETE FROM trade_signals WHERE code = %s AND cycle = 'daily'",
                (code,)
            )
        storage.conn.commit()
        cursor.close()
    except Exception as e:
        print(f"    ⚠️  清除旧信号失败: {e}")


def run_stock(storage, code: str, start_date: str = None, end_date: str = None, clear_first: bool = True):
    """处理单只股票"""
    df = load_stock_quotes(storage, code, start_date, end_date)
    if df.empty:
        return 0

    signals = extract_signals(df)
    if signals.empty:
        return 0

    if clear_first:
        clear_stock_signals(storage, code, start_date)

    count = storage.save_signals(signals)
    return count


def run_all(storage, start_date: str = None, end_date: str = None):
    """全量计算所有股票"""
    codes = get_stock_codes(storage)
    total = len(codes)
    print(f"📊 共 {total} 只股票")

    success = 0
    total_signals = 0
    for i, code in enumerate(codes, 1):
        try:
            n = run_stock(storage, code, start_date, end_date, clear_first=False)
            if n > 0:
                total_signals += n
            success += 1
        except Exception as e:
            print(f"  ❌ [{i}/{total}] {code} 失败: {e}")

        if i % 200 == 0 or i == total:
            print(f"  ✅ [{i}/{total}] 成功 {success}, 信号 {total_signals}")

    print(f"\n✅ 全量计算完成: 成功 {success}/{total}, 共 {total_signals} 个信号")


def run_incremental(storage, days: int = 30):
    """增量更新最近 N 天"""
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    print(f"📅 增量范围: {start} ~ {end}")
    run_all(storage, start, end)


def main():
    parser = argparse.ArgumentParser(description='信号预计算脚本（MACD/RSI/BOLL）')
    parser.add_argument('--all', action='store_true', help='全量计算所有股票')
    parser.add_argument('--code', type=str, help='单只股票代码')
    parser.add_argument('--incremental', action='store_true', help='增量更新')
    parser.add_argument('--start', type=str, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=30, help='增量更新天数')
    args = parser.parse_args()

    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', ''),
    })

    print("=" * 50)
    print("🔧 信号预计算脚本")
    print("=" * 50)

    if not storage.connect():
        print("❌ 数据库连接失败")
        return 1

    # 确保表存在
    storage.init_tables()
    print("✅ 确保 trade_signals 表存在")

    if args.all:
        run_all(storage, args.start, args.end)
    elif args.code:
        n = run_stock(storage, args.code, args.start, args.end)
        print(f"✅ {args.code}: 生成 {n} 个信号")
    elif args.incremental:
        run_incremental(storage, args.days)
    else:
        parser.print_help()
        print("\n请指定运行模式：--all, --code 或 --incremental")

    storage.disconnect()


if __name__ == '__main__':
    main()
