#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前复权重建（协作单 45.0 订正）单测。

背景：港股 `stock_quotes.close` 存新浪**后复权** hfq，且 hfq 为仿射口径
`hfq = a·raw + b`；新浪前复权为**乘性**口径，二者不可互相换算。修复方案是从
库内 raw_*/adj_*/adj_share 精确重建前复权：把每个除权日的加性调整 `Δb` 还原为
每股调整额 `d = Δb/a`，再取乘性因子 `f = (p − d)/p`，累计后续因子即得倍率。

测试全部离线（假数据），不联网。
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector.utils.adj_adjust import compute_qfq_prices  # noqa: E402


def _frame(raw, hfq, share):
    n = len(raw)
    return pd.DataFrame({
        'trade_date': pd.date_range('2020-01-01', periods=n, freq='D').date,
        'raw_open': raw, 'raw_high': raw, 'raw_low': raw, 'raw_close': raw,
        'adj_close': hfq,
        'adj_share': share,
    })


class TestNoAdjustment:
    def test_no_dividend_degrades_to_raw(self):
        """无任何除权（Δb 恒为 0）→ 前复权 == 原始价。"""
        raw = [10.0, 10.5, 9.8, 11.2]
        out = compute_qfq_prices(_frame(raw, raw, [1.0] * 4))
        assert out['qfq_close'].tolist() == pytest.approx(raw)
        assert out['adj_cum'].tolist() == pytest.approx([1.0] * 4)

    def test_last_row_always_equals_raw(self):
        """最新一行前复权 == 原始价（前复权锚定最新日）。"""
        out = compute_qfq_prices(_frame([5.0, 6.0, 7.0], [5.0, 6.1, 7.3], [1.0] * 3))
        assert float(out['qfq_close'].iloc[-1]) == pytest.approx(7.0)


class TestDividendAdjustment:
    def test_single_dividend_shifts_history_down(self):
        """a=1、第 3 日 b 跳 0.1（每股分红 0.1，昨收 1.0 → 因子 0.9）→ 更早历史 ×0.9。"""
        raw = [1.0, 1.0, 0.9, 1.0]
        hfq = [1.0, 1.0, 1.0, 1.1]          # b = hfq - raw = [0, 0, 0.1, 0.1]
        out = compute_qfq_prices(_frame(raw, hfq, [1.0] * 4))
        assert out['qfq_close'].tolist() == pytest.approx([0.9, 0.9, 0.9, 1.0])

    def test_factor_applies_to_ohlc_too(self):
        """同一倍率同时作用于 OHLC（整根 K 线一致缩放）。"""
        df = pd.DataFrame({
            'trade_date': pd.date_range('2020-01-01', periods=2).date,
            'raw_open': [1.0, 1.0], 'raw_high': [1.2, 1.1],
            'raw_low': [0.9, 0.95], 'raw_close': [1.0, 1.0],
            'adj_close': [1.0, 2.0], 'adj_share': [1.0, 1.0],
        })   # 第 2 日 b 跳 1.0 → 因子 (1-1)/1 = 0.0 → 守卫为 1.0，不至于产生 0 价
        out = compute_qfq_prices(df)
        assert (out['qfq_open'] > 0).all()
        # 倍率在 OHLC 间一致
        ratio = out['qfq_high'] / out['raw_high']
        assert ratio.nunique() == 1

    def test_share_regime_change_not_treated_as_dividend(self):
        """股本因子变更（拆股/送股）当日因子 = 1（raw 已拆股调整，无需再折）。"""
        raw = [10.0, 10.0, 10.0, 10.0]
        hfq = [10.0, 10.0, 10.0, 10.0]      # 连续；a 由 1 → 5，b 相应跳变
        out = compute_qfq_prices(_frame(raw, hfq, [1.0, 1.0, 5.0, 5.0]))
        assert out['qfq_close'].tolist() == pytest.approx(raw)
        assert out['adj_cum'].tolist() == pytest.approx([1.0] * 4)


class TestGuards:
    def test_empty_frame(self):
        out = compute_qfq_prices(pd.DataFrame(
            columns=['raw_close', 'adj_close', 'adj_share']))
        assert out.empty

    def test_single_row_degrades_to_raw(self):
        """单行（增量窗口）无昨收可比 → 前复权 = 原始价，不抛异常。"""
        out = compute_qfq_prices(_frame([0.183], [5.4245], [1.066667]))
        assert float(out['qfq_close'].iloc[0]) == pytest.approx(0.183)

    def test_missing_adj_share_still_positive(self):
        df = _frame([1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [None, None, None])
        out = compute_qfq_prices(df)
        assert (out['qfq_close'] > 0).all()

    def test_oversized_dividend_never_yields_nonpositive_price(self):
        raw = [0.2, 0.2, 0.2]
        hfq = [0.2, 0.2, 5.0]               # 荒诞的 b 跳变（d > p）
        out = compute_qfq_prices(_frame(raw, hfq, [1.0] * 3))
        assert (out['qfq_close'] > 0).all()

    def test_penny_stock_rounding_noise_does_not_explode(self):
        """仙股（raw≈0.03、b≈1 远大于价格）的 4 位小数舍入噪声不得累积成天量倍率。

        回归：0007.HK 曾因逐日 Δb 噪声长链累积使 `qfq_close` 溢出 NUMERIC(12,4)
        （numeric field overflow）。
        """
        n = 3000
        rng = np.random.default_rng(11)
        raw = np.round(0.03 * (1 + rng.uniform(-0.03, 0.03, n)), 3)
        # b 在 1.0 附近带 ±5e-5 舍入噪声（adj_close 仅 4 位小数）
        hfq = np.round(raw + 1.0 + rng.uniform(-5e-5, 5e-5, n), 4)
        out = compute_qfq_prices(_frame(raw.tolist(), hfq.tolist(), [1.0] * n))
        assert out['qfq_close'].notna().all()
        assert (out['qfq_close'] < 1e3).all()
        # 无真实事件 → 前复权应贴合原始价
        assert float(out['qfq_close'].iloc[-1]) == pytest.approx(float(raw[-1]), rel=1e-3)


class TestSinaAlignmentSample:
    """与新浪 `adjust='qfq'` 的离线对齐样本（2025+ 实测误差 0）。

    样本取自 2007.HK 实测（a=1.066667 恒定、最近一年无分红），最近一年前复权价
    与原始价逐日相等，验证重建不会把正常序列错误折价。
    """

    def test_recent_period_equals_raw_when_no_recent_dividend(self):
        dates = pd.date_range('2026-06-01', periods=5, freq='D').date
        raw = [0.201, 0.195, 0.188, 0.190, 0.183]
        df = pd.DataFrame({
            'trade_date': dates,
            'raw_open': raw, 'raw_high': raw, 'raw_low': raw, 'raw_close': raw,
            'adj_close': [raw[i] * 1.066667 + 5.2293 for i in range(5)],
            'adj_share': [1.066667] * 5,
        })
        out = compute_qfq_prices(df)
        assert out['qfq_close'].tolist() == pytest.approx(raw)
