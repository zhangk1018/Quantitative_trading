#!/usr/bin/env python3
"""
信号预计算脚本

功能：
- 预计算所有股票的 MACD 金叉/死叉信号
- 支持全量计算和增量更新
- 信号写入 trade_signals 表，供 API 查询使用
- 规则：只写不读（预计算后写入数据库）

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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src'))

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from utils.config import load_config


SIGNAL_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS trade_signals (
    id SERIAL PRIMARY KEY,
    code VARCHAR(32) NOT NULL,
    trade_date DATE NOT NULL,
    signal_type VARCHAR(32) NOT NULL,   -- 'golden_cross' | 'death_cross'
    price NUMERIC(12, 4),
    macd NUMERIC(12, 4),
    macd_signal NUMERIC(12, 4),
    macd_hist NUMERIC(12, 4),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_trade_signals_code_date ON trade_signals(code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_trade_signals_type ON trade_signals(signal_type, trade_date DESC);
"""


def _ema(series: pd.Series, span: int) -> pd.Series:
    """计算指数移动平均"""
    return series.ewm(span=span, adjust=False).mean()


def compute_macd(close: pd.Series, span_fast=12, span_slow=26, span_signal=9):
    """计算 MACD 指标"""
    ema_fast = _ema(close, span_fast)
    ema_slow = _ema(close, span_slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, span_signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def extract_signals(df: pd.DataFrame) -> pd.DataFrame:
    """从日线数据中提取 MACD 金叉/死叉信号"""
    if df is None or len(df) < 26:
        return pd.DataFrame()

    df = df.sort_values('trade_date').reset_index(drop=True)
    close = df['close'].astype(float)
    macd_line, signal_line, _ = compute_macd(close)

    signals = []
    for i in range(1, len(df)):
        if pd.isna(macd_line.iloc[i]) or pd.isna(signal_line.iloc[i]):
            continue
        prev_macd = macd_line.iloc[i - 1]
        prev_signal = signal_line.iloc[i - 1]
        curr_macd = macd_line.iloc[i]
        curr_signal = signal_line.iloc[i]

        # 金叉：MACD 上穿信号线
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            signals.append({
                'trade_date': df['trade_date'].iloc[i],
                'signal_type': 'golden_cross',
                'price': round(float(df['close'].iloc[i]), 4),
                'macd': round(curr_macd, 4),
                'macd_signal': round(curr_signal, 4),
                'macd_hist': round(curr_macd - curr_signal, 4),
            })
        # 死叉：MACD 下穿信号线
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            signals.append({
                'trade_date': df['trade_date'].iloc[i],
                'signal_type': 'death_cross',
                'price': round(float(df['close'].iloc[i]), 4),
                'macd': round(curr_macd, 4),
                'macd_signal': round(curr_signal, 4),
                'macd_hist': round(curr_macd - curr_signal, 4),
            })

    if not signals:
        return pd.DataFrame()
    return pd.DataFrame(signals)


def ensure_table(engine):
    """确保 trade_signals 表存在"""
    with engine.connect() as conn:
        for stmt in SIGNAL_TABLE_DDL.split(';'):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()


def clear_stock_signals(engine, code: str, since_date: str = None):
    """清除某只股票的旧信号"""
    with engine.connect() as conn:
        if since_date:
            conn.execute(
                text("DELETE FROM trade_signals WHERE code = :code AND trade_date >= :since"),
                {'code': code, 'since': since_date}
            )
        else:
            conn.execute(
                text("DELETE FROM trade_signals WHERE code = :code"),
                {'code': code}
            )
        conn.commit()


def save_signals(engine, code: str, signals_df: pd.DataFrame):
    """批量保存信号"""
    if signals_df.empty:
        return 0

    rows = []
    for _, row in signals_df.iterrows():
        rows.append({
            'code': code,
            'trade_date': row['trade_date'],
            'signal_type': row['signal_type'],
            'price': row['price'],
            'macd': row['macd'],
            'macd_signal': row['macd_signal'],
            'macd_hist': row['macd_hist'],
        })

    with engine.connect() as conn:
        for r in rows:
            conn.execute(
                text("""
                    INSERT INTO trade_signals (code, trade_date, signal_type, price, macd, macd_signal, macd_hist)
                    VALUES (:code, :trade_date, :signal_type, :price, :macd, :macd_signal, :macd_hist)
                """),
                r
            )
        conn.commit()
    return len(rows)


def get_stock_codes(engine) -> list:
    """获取所有股票代码"""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT DISTINCT code FROM stock_quotes ORDER BY code")
        )
        return [row[0] for row in result.fetchall()]


def load_stock_quotes(engine, code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """加载单只股票的日线数据"""
    query = """
        SELECT code, trade_date, open, high, low, close, volume
        FROM stock_quotes
        WHERE code = :code
    """
    params = {'code': code}
    if start_date:
        query += " AND trade_date >= :start"
        params['start'] = start_date
    if end_date:
        query += " AND trade_date <= :end"
        params['end'] = end_date
    query += " ORDER BY trade_date ASC"

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        rows = result.fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=result.keys())
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        return df


def run_stock(engine, code: str, start_date: str = None, end_date: str = None, clear_first: bool = True):
    """处理单只股票"""
    df = load_stock_quotes(engine, code, start_date, end_date)
    if df.empty:
        return 0

    signals = extract_signals(df)
    if signals.empty:
        return 0

    if clear_first:
        clear_stock_signals(engine, code, start_date)

    count = save_signals(engine, code, signals)
    return count


def run_all(engine, start_date: str = None, end_date: str = None):
    """全量计算所有股票"""
    codes = get_stock_codes(engine)
    total = len(codes)
    print(f"📊 共 {total} 只股票")

    success = 0
    total_signals = 0
    for i, code in enumerate(codes, 1):
        try:
            n = run_stock(engine, code, start_date, end_date, clear_first=False)
            if n > 0:
                total_signals += n
            success += 1
        except Exception as e:
            print(f"  ❌ [{i}/{total}] {code} 失败: {e}")

        if i % 200 == 0 or i == total:
            print(f"  ✅ [{i}/{total}] 成功 {success}, 信号 {total_signals}")

    print(f"\n✅ 全量计算完成: 成功 {success}/{total}, 共 {total_signals} 个信号")


def run_incremental(engine, days: int = 30):
    """增量更新最近 N 天"""
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    print(f"📅 增量范围: {start} ~ {end}")
    run_all(engine, start, end)


def main():
    parser = argparse.ArgumentParser(description='信号预计算脚本（MACD 金叉/死叉）')
    parser.add_argument('--all', action='store_true', help='全量计算所有股票')
    parser.add_argument('--code', type=str, help='单只股票代码')
    parser.add_argument('--incremental', action='store_true', help='增量更新')
    parser.add_argument('--start', type=str, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=30, help='增量更新天数')
    args = parser.parse_args()

    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user:quant_password@localhost:5432/quant_trading')
    engine = create_engine(db_url)

    print("=" * 50)
    print("🔧 信号预计算脚本")
    print("=" * 50)

    # 确保表存在
    ensure_table(engine)
    print("✅ 确保 trade_signals 表存在")

    if args.all:
        run_all(engine, args.start, args.end)
    elif args.code:
        n = run_stock(engine, args.code, args.start, args.end)
        print(f"✅ {args.code}: 生成 {n} 个信号")
    elif args.incremental:
        run_incremental(engine, args.days)
    else:
        parser.print_help()
        print("\n请指定运行模式：--all, --code 或 --incremental")


if __name__ == '__main__':
    main()