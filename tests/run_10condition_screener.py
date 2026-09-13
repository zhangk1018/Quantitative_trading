#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
10条件选股 —— 逐日命中日期查询程序

说明
----
本程序调用自编指标「10条件选股」（附件 JSON 中导出的计算脚本）：
    - 输入：股票前复权 OHLCV（open/high/low/close/volume）
    - 输出：逐日得分 score ∈ [0,10]（满足条件的条数）
    - 命中规则：score >= threshold（算子 >=，defaultThreshold = 8）

即「命中」= 当日满足 ≥8 条选股条件。条件为：
    1) RSI(14) ∈ [50, 68]
    2) 1日动量 ∈ [1.5%, 4.5%]
    3) 20日波动率 ∈ [4.5%, 9.0%]
    4) 成交量 ∈ (20日均量×1.1, 20日均量×3.0)
    5) ADX(14) > 25
    6) EMA50 之上，且乖离率 < 6%（close ∈ (EMA50, EMA50×1.06)）
    7) MACD(12,26,9)：DIF > DEA
    8) 收盘价 < 最近5日最高价
    9) 实体阳线（实体占振幅比例 > 40%）
    10) 收盘价 > 20日箱体的 70% 分位价（上三分之一强势区）

用法
----
命令行参数（任选一种）：
    python tests/run_10condition_screener.py --start 2025-01-01 --code 002508
    python tests/run_10condition_screener.py --start 2025-01-01 --code 002508 --threshold 8 --table
    直接运行不带参数，则进入交互输入（输入 起始日期 与 股票代码）。

参数说明
    --start      起始日期 YYYY-MM-DD（含当日，输出该日及之后的命中日期）
    --code       股票代码（如 002508）
    --threshold  命中阈值，默认 8
    --table      额外打印每日得分明细表；不加则只打印命中日期列表
数据来源
    读取 PostgreSQL stock_quotes（cycle='1d'，前复权/收盘口径），与选股视图 K 线同源。
    程序会加载该股全部历史 OHLCV 以正确预热 EMA50/ADX/RSI 等，再输出 start 之后的命中日。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime

import numpy as np


# ============================================================
# 10条件选股 计算函数（与附件 JSON 的 formula 完全一致）
# ============================================================
def calculate(open_prices, high_prices, low_prices, close_prices, volumes):
    close = np.array(close_prices, dtype=float)
    high = np.array(high_prices, dtype=float)
    low = np.array(low_prices, dtype=float)
    open_p = np.array(open_prices, dtype=float)
    volume = np.array(volumes, dtype=float)

    n = len(close)
    if n < 50:
        return [0] * n

    score = np.zeros(n)

    def rolling_sma(arr, window):
        out = np.full(n, np.nan)
        cumsum = np.nancumsum(np.where(np.isnan(arr), 0, arr))
        cnt = np.cumsum(~np.isnan(arr))
        for i in range(window - 1, n):
            if cnt[i] >= window:
                out[i] = (cumsum[i] - (cumsum[i - window] if i >= window else 0)) / window
        return out

    def ema(arr, period):
        out = np.full(n, np.nan)
        alpha = 2.0 / (period + 1)
        valid_start = 0
        while valid_start < n and np.isnan(arr[valid_start]):
            valid_start += 1
        if valid_start >= n:
            return out
        out[valid_start] = arr[valid_start]
        for j in range(valid_start + 1, n):
            if np.isnan(arr[j]):
                out[j] = out[j - 1]
            else:
                out[j] = alpha * arr[j] + (1 - alpha) * out[j - 1]
        return out

    # 条件 1：RSI(14) 介于 50 ~ 68
    rsi_period = 14
    deltas = np.diff(close, prepend=np.nan)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    sma_gain = rolling_sma(gains, rsi_period)
    sma_loss = rolling_sma(losses, rsi_period)
    rsi = np.full(n, 100.0)
    with np.errstate(divide='ignore', invalid='ignore'):
        valid_rs = sma_loss > 0
        rsi[valid_rs] = 100.0 - 100.0 / (1.0 + sma_gain[valid_rs] / sma_loss[valid_rs])
    score[(rsi >= 50) & (rsi <= 68)] += 1

    # 条件 2：1日动量 介于 1.5% ~ 4.5%
    if n >= 2:
        momentum = np.full(n, np.nan)
        momentum[1:] = (close[1:] - close[:-1]) / close[:-1] * 100
        score[(momentum >= 1.5) & (momentum <= 4.5)] += 1

    # 条件 3：20日波动率 介于 4.5% ~ 9.0%
    if n >= 21:
        daily_ret = np.full(n, np.nan)
        daily_ret[1:] = (close[1:] - close[:-1]) / close[:-1]
        vol_arr = np.full(n, np.nan)
        for i in range(20, n):
            vol_arr[i] = np.std(daily_ret[i - 19:i + 1]) * 100
        score[(vol_arr >= 4.5) & (vol_arr <= 9.0)] += 1

    # 条件 4：成交量 > 20日均量 × 1.1 且 < 20日均量 × 3.0
    vol_sma = rolling_sma(volume, 20)
    score[(volume > vol_sma * 1.1) & (volume < vol_sma * 3.0)] += 1

    # 条件 5：ADX(14) > 25
    if n >= 28:
        high_low = high[1:] - low[1:]
        high_close_c = np.abs(high[1:] - close[:-1])
        low_close_c = np.abs(low[1:] - close[:-1])
        tr = np.maximum(high_low, np.maximum(high_close_c, low_close_c))
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        atr = np.full(len(tr), np.nan)
        atr[13] = np.mean(tr[:14])
        for i in range(14, len(tr)):
            atr[i] = (atr[i - 1] * 13 + tr[i]) / 14
        plus_di = np.full(len(tr), np.nan)
        minus_di = np.full(len(tr), np.nan)
        plus_di[13] = np.sum(plus_dm[:14]) / np.sum(tr[:14]) * 100 if np.sum(tr[:14]) != 0 else 0
        minus_di[13] = np.sum(minus_dm[:14]) / np.sum(tr[:14]) * 100 if np.sum(tr[:14]) != 0 else 0
        for i in range(14, len(tr)):
            plus_di[i] = (plus_di[i-1] * 13 + (plus_dm[i] / atr[i] * 100 if atr[i] != 0 else 0)) / 14
            minus_di[i] = (minus_di[i-1] * 13 + (minus_dm[i] / atr[i] * 100 if atr[i] != 0 else 0)) / 14
        dx = np.full(len(plus_di), np.nan)
        for i in range(13, len(plus_di)):
            denom = plus_di[i] + minus_di[i]
            dx[i] = np.abs(plus_di[i] - minus_di[i]) / denom * 100 if denom != 0 else 0
        adx = np.full(len(dx), np.nan)
        adx[27] = np.mean(dx[14:28])
        for i in range(28, len(dx)):
            adx[i] = (adx[i-1] * 13 + dx[i]) / 14
        adx_aligned = np.full(n, np.nan)
        for j in range(27, len(adx)):
            adx_aligned[j + 1] = adx[j]
        score[adx_aligned > 25] += 1

    # 条件 6：close ∈ (EMA50, EMA50 × 1.06)
    ema50 = ema(close, 50)
    cond6 = (close > ema50) & (close < 1.06 * ema50)
    score[cond6] += 1

    # 条件 7：MACD(12,26,9)：DIF > DEA
    ema12 = ema(close, 12)
    ema26 = ema(close, 26)
    dif = ema12 - ema26
    dea = ema(dif, 9)
    score[dif > dea] += 1

    # 条件 8：close < 最近5日最高价
    if n >= 5:
        max5 = np.full(n, np.nan)
        for i in range(4, n):
            max5[i] = np.max(high[i-4:i+1])
        score[close < max5] += 1

    # 条件 9：实体阳线（实体占振幅比例 > 40%）
    body = close - open_p
    range_hl = high - low
    with np.errstate(divide='ignore', invalid='ignore'):
        body_ratio = body / range_hl
    cond_body = (body > 0) & (range_hl > 0) & (body_ratio > 0.4)
    score[cond_body] += 1

    # 条件 10：close > 20日箱体 70% 分位价
    if n >= 20:
        highest_20 = np.full(n, np.nan)
        lowest_20 = np.full(n, np.nan)
        for i in range(19, n):
            highest_20[i] = np.max(high[i-19:i+1])
            lowest_20[i] = np.min(low[i-19:i+1])
        threshold_price = lowest_20 + 0.7 * (highest_20 - lowest_20)
        score[close > threshold_price] += 1

    result = np.where(np.isnan(score), 0, score).astype(int)
    return result.tolist()


# ============================================================
# 数据加载（PostgreSQL … stock_quotes，前复权/1d）
# ============================================================
def load_ohlcv(code: str, market: str = 'cn') -> tuple[list[date], list[float], list[float], list[float], list[float], list[float]]:
    """返回 (dates, opens, highs, lows, closes, volumes)，按交易日升序。"""
    from dotenv import load_dotenv
    import psycopg2

    load_dotenv('.env')
    conn = psycopg2.connect(
        host=os.getenv('PG_HOST'),
        port=os.getenv('PG_PORT'),
        dbname=os.getenv('PG_DATABASE'),
        user=os.getenv('PG_USER'),
        password=os.getenv('PG_PASSWORD'),
    )
    try:
        cur = conn.cursor()
        if market == 'cn':
            cur.execute(
                "SELECT trade_date, open, high, low, close, volume "
                "FROM stock_quotes WHERE code=%s AND cycle='1d' ORDER BY trade_date",
                (code,),
            )
        else:
            cur.execute(
                "SELECT trade_date, open, high, low, close, volume "
                "FROM stock_quotes WHERE code=%s AND cycle='1d' AND market=%s ORDER BY trade_date",
                (code, market),
            )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        raise SystemExit(f"未在 stock_quotes 找到 {code}（market={market}）的日线数据")

    dates = [r[0] for r in rows]
    opens = [float(r[1]) for r in rows]
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    vols = [float(r[5]) for r in rows]
    return dates, opens, highs, lows, closes, vols


# ============================================================
# 参数解析
# ============================================================
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='10条件选股 —— 逐日命中日期查询')
    parser.add_argument('--start', help='起始日期 YYYY-MM-DD（含当日）')
    parser.add_argument('--end', help='结束日期 YYYY-MM-DD（含当日，缺省为最新数据日）')
    parser.add_argument('--code', help='股票代码，如 002508（单只时使用）')
    parser.add_argument('--codes', help='多只股票代码，逗号分隔，如 002508,000001,600519')
    parser.add_argument('--market', default='cn', help='市场，默认 cn（cn/hk/us）')
    parser.add_argument('--threshold', type=int, default=8, help='命中阈值，默认 8')
    parser.add_argument('--table', action='store_true', help='额外输出每日得分明细表')
    parser.add_argument('--out', help='导出命中日期到文件（CSV：code,trade_date,score）')
    return parser


def normalize_codes(code: str | None, codes: str | None) -> list[str]:
    """把 --code / --codes 归并成代码列表；全空返回 []。"""
    result: list[str] = []
    for raw in (code, codes):
        if not raw:
            continue
        for c in raw.replace('，', ',').split(','):
            c = c.strip()
            if c and c not in result:
                result.append(c)
    return result


def parse_date(raw: str, field: str) -> date:
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        raise SystemExit(f"{field}日期格式错误：{raw!r}（应为 YYYY-MM-DD）")


# ============================================================
# 主流程
# ============================================================
def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    codes = normalize_codes(args.code, args.codes)
    start = args.start
    # 交互式输入（无 --code/--codes 也无 --start 时）
    if not codes:
        codes = [input('请输入股票代码（如 002508）：').strip()]
    if not start:
        start = input('请输入起始日期 YYYY-MM-DD（如 2025-01-01）：').strip()
    if not start:
        raise SystemExit("缺少起始日期参数 --start")

    start_date = parse_date(start, '起始')
    end_date = parse_date(args.end, '结束') if args.end else None

    if not (0 <= args.threshold <= 10):
        raise SystemExit(f"阈值越界：{args.threshold}（应在 0~10）")

    out_rows: list[tuple[str, date, int]] = []  # 导出行 (code, trade_date, score)

    for code in codes:
        dates, opens, highs, lows, closes, vols = load_ohlcv(code, args.market)
        scores = calculate(opens, highs, lows, closes, vols)

        matched = [(d, s) for d, s in zip(dates, scores)
                   if d >= start_date and (end_date is None or d <= end_date)]
        hits = [(d, s) for d, s in matched if s >= args.threshold]

        print(f"\n===== 股票 {code}｜市场 {args.market}｜数据 {len(dates)} 根K线"
              f"（{dates[0]} ~ {dates[-1]}） =====")
        print(f"阈值：score >= {args.threshold}｜区间 {start_date} ~ "
              f"{end_date or dates[-1]}｜共 {len(matched)} 个交易日，命中 {len(hits)} 个\n")

        if args.table:
            print("日期          得分   命中")
            print("-" * 26)
            for d, s in matched:
                mark = 'Y' if s >= args.threshold else '-'
                print(f"{d}  {s:>2}    {mark}")
            print("-" * 26)

        print(f"满足条件（score>= {args.threshold}）的日期列表：")
        if hits:
            for d, _ in hits:
                print(d)
        else:
            print("（无命中）")
        print(f"命中数：{len(hits)}")

        for d, s in hits:
            out_rows.append((code, d, s))

    if args.out:
        _export_csv(args.out, out_rows)
        print(f"\n已导出命中日期 -> {args.out}（{len(out_rows)} 条）")

    return 0


# ============================================================
# 导出
# ============================================================
def _export_csv(path: str, rows: list[tuple[str, date, int]]) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        f.write("code,trade_date,score\n")
        for code, d, s in rows:
            f.write(f"{code},{d},{s}\n")


if __name__ == '__main__':
    sys.exit(main())