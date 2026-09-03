#!/usr/bin/env python3
"""
指数探针 check_index_integrity.py（协作单 30.0 V6 / P0 数据质量监控）

每日独立拉取港股恒生指数（^HSI）与美股标普500（^GSPC），校验指数数据完整性，
作为行情数据管道的独立探针——指数不依赖本地 stock_quotes，可独立判断数据源可用性：
  1. 最新交易日有收盘价（今日非 NaN）
  2. 最新收盘价 ≠ 前一交易日（避免重复/陈旧值）
  3. 近 N 日（默认 5）无异常跳变（|日收益率| 超阈值告警，指数极少单日 >阈值）
  4. 数据新鲜度：最新交易日不得早于今天超过 max_stale_days（容忍节假日/周末）

异常统一走 utils.alerting 落 `logs/monitoring/alerts.log`，供看板与晨检读取。

用法：
    ./venv/bin/python backend/monitoring/check_index_integrity.py            # 全部市场（hk/us）
    ./venv/bin/python backend/monitoring/check_index_integrity.py --market hk
    ./venv/bin/python backend/monitoring/check_index_integrity.py --jump-threshold 0.10
"""
import sys
import os
import argparse
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402
from utils.alerting import append_alerts  # noqa: E402
from collector.datasource.yahoo import YahooDataSource  # noqa: E402

logger = setup_logger('index_integrity')
BASE_DIR = Path(__file__).resolve().parents[1]


# 各市场探针指数（Yahoo 符号，须直接传入 download_single，勿经 normalize_code）
INDEX_MAP: Dict[str, Dict[str, str]] = {
    'hk': {'symbol': '^HSI', 'desc': '恒生指数'},
    'us': {'symbol': '^GSPC', 'desc': '标普500'},
}


def _pull_index(market: str, symbol: str, period: str) -> Optional[pd.DataFrame]:
    """拉取指数近一段日线（period 取 3mo 以上，绕开 ^HSI 元数据缓存导致的短周期失败）。"""
    try:
        src = YahooDataSource(market=market)
        src.connect()
        # 指数不规范化代码，直接传 Yahoo 符号；period 用 3mo 拿足样本供近5日判断
        df = src.download_single(symbol, market=market, period=period)
        if df is None or df.empty:
            logger.warning(f"⚠️ {symbol}（{INDEX_MAP[market]['desc']}）拉取为空")
            return None
        return df
    except Exception as e:
        logger.error(f"❌ {symbol} 拉取异常: {e}")
        return None


def _close_series(df: pd.DataFrame) -> pd.Series:
    """提取收盘价序列（优先 Close，其次 Adj Close），丢弃 NaN。"""
    col = next((c for c in ('Close', 'Adj Close') if c in df.columns), None)
    if col is None:
        return pd.Series(dtype=float)
    s = df[col].dropna()
    return pd.to_numeric(s, errors='coerce').dropna()


def check_market(market: str, period: str, jump_threshold: float,
                 max_stale_days: int, lookback: int) -> List[Dict[str, str]]:
    """对单一市场执行指数完整性检查，返回异常告警列表（正常返回空）。"""
    info = INDEX_MAP[market]
    symbol = info['symbol']
    alerts: List[Dict[str, str]] = []

    def _warn(message: str, level: str = 'WARNING') -> None:
        alerts.append({'level': level, 'market': market, 'message': f"{info['desc']}({symbol}) {message}"})

    df = _pull_index(market, symbol, period)
    if df is None or df.empty:
        _warn(f"指数数据拉取为空/失败，数据源可能不可用", 'CRITICAL')
        return alerts

    close = _close_series(df)
    if close.empty:
        _warn(f"无有效收盘价（全 NaN），指数数据异常", 'CRITICAL')
        return alerts

    latest_val = float(close.iloc[-1])
    latest_date = pd.Timestamp(df.index[-1]).date()

    # ① 今日/最新非 NaN ✅（latest_val 已由 dropna 保证非 NaN）
    # ② 最新≠前一日（>0 即视为有变化）
    prev_val = float(close.iloc[-2]) if len(close) >= 2 else None
    if prev_val is not None and abs(latest_val - prev_val) < 1e-9:
        _warn(f"最新收盘价与前一日重复（{prev_val}），疑似数据未更新/陈旧", 'WARNING')

    # ③ 近 N 日异常跳变（|日收益率| 阈值）
    tail = close.tail(lookback)
    if len(tail) >= 3:
        rets = tail.pct_change().dropna().abs()
        max_ret = float(rets.max())
        if max_ret > jump_threshold:
            max_date = pd.Timestamp(rets.idxmax()).date()
            _warn(f"出现异常跳变：{max_date} 日收益率 {max_ret:.2%} 超过阈值 {jump_threshold:.0%}（指数单日罕见此幅）", 'WARNING')
        logger.info(f"📈 {info['desc']} 近{lookback}日最大|日收益率| = {max_ret:.4%}（阈值 {jump_threshold:.0%}）")

    # ④ 数据新鲜度：最新交易日不得早于今天超过 max_stale_days
    today = pd.Timestamp.now().date()
    stale = (today - latest_date).days
    if stale > max_stale_days:
        _warn(f"数据存续 {stale} 天未更新（最新 {latest_date}，今天 {today}，阈值 {max_stale_days} 天）", 'WARNING')

    logger.info(
        f"🌐 [{market}] {info['desc']}({symbol}) 最新 {latest_date} 收 {latest_val:.2f}"
        f"{'，前值 '+f'{prev_val:.2f}' if prev_val is not None else ''}，存续 {stale} 天"
    )
    return alerts


def main() -> None:
    """主函数：遍历市场执行指数探针，异常写告警日志。"""
    parser = argparse.ArgumentParser(description='指数完整性探针（^HSI / ^GSPC）')
    parser.add_argument('--market', default='', help='只检查指定市场(hk/us)，空=全部')
    parser.add_argument('--period', default='3mo', help='Yahoo 拉取周期（默认 3mo）')
    parser.add_argument('--jump-threshold', type=float, default=0.15, help='异常跳变阈值（默认0.15=15%）')
    parser.add_argument('--max-stale-days', type=int, default=10, help='数据最久可存续天数（默认10，容忍长假期）')
    parser.add_argument('--days', type=int, default=5, help='近N日跳变检测窗口（默认5）')
    args = parser.parse_args()

    markets = [args.market] if args.market else list(INDEX_MAP.keys())
    all_alerts: List[Dict[str, str]] = []
    logger.info("=" * 70)
    logger.info(f"🚀 开始指数完整性探针（{', '.join(markets)}）")
    for m in markets:
        if m not in INDEX_MAP:
            logger.error(f"❌ 未知市场 {m}，仅支持 {list(INDEX_MAP.keys())}")
            continue
        all_alerts.extend(check_market(m, args.period, args.jump_threshold, args.max_stale_days, args.days))

    if all_alerts:
        append_alerts(all_alerts)
        logger.warning(f"🌡️ 指数探针发现 {len(all_alerts)} 条异常，已写入 alerts.log")
    else:
        logger.info("✅ 指数完整性检查全部通过，无异常")
    logger.info("=" * 70)


if __name__ == '__main__':
    main()