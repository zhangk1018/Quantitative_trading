"""港股除权日（factor_date）检测修复测试（协作单 45.0）。

背景：K 反馈「碧桂园不可能天天除权」。核查发现新浪港股 `adjust='hfq'` 是**仿射**口径
（hfq = a*raw + b，a=累计股本因子、b=累计加性调整），而原实现按
`adj_factor = adj_close/close` 的**相对变化 >1%** 判定除权（隐含乘性假设）：

- 对 b≠0 的标的该比值随行情逐日抖动，几乎每天都命中（实测碧桂园 02007 近 19 年
  873/4596=19% 的交易日被误标；全市场 1954 只港股中 1129 只 >10% 交易日被误标）；
- 2025-04-07 全球大跌当天 1192 只港股同时被标「除权」，即普通波动触发。

修复：`detect_factor_dates` 改为按自适应模型检测**因子跳变**——
仿射口径用 `b = adj − a*raw`（a 逐段稳健估计，b 恒定、仅在除权日跳变），
乘性口径保留原比值法；并加「样本不足不标」「命中占比 >20% 整体不标」两道护栏。
同批修复**复权 O/H/L 价格**：由 `raw_x × (Adj Close/Close)`（隐含乘性）改为仿射式
`adj_x = a*raw_x + b`，数据源直供的 hfq O/H/L 优先；增量批量快照路径由「冻结乘性
锚点」同步改为仿射（依赖新列 `stock_quotes.adj_share`，协作单 45.0 迁移 V018）。

覆盖：
- 仿射（低价股，碧桂园式）：不再逐日误标；真实除权（b 跳变）仍被标出
- 仿射（拆股后 a=5，腾讯式）：不再误标；拆股日被标出
- 乘性（美股 qfq×锚点式）：口径判定保持乘性、原行为不回退、真实除权仍被标出
- 护栏：短窗口不检测；命中占比超限整体不标
- 复权 O/H/L：仿射折算 / 数据源直供优先 / 无股本因子退化为乘性 / 批量快照仿射换算
- 端到端：`clean_and_split` 不再产出逐日 factor 行

全部用例离线运行（合成数据，不访问网络/数据库）。

运行：
    cd backend && ../venv/bin/python -m pytest tests/test_adj_factor_dates.py -v
"""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.utils import adj_adjust as adj  # noqa: E402
from collector.utils.adj_adjust import (  # noqa: E402
    detect_factor_dates,
    estimate_share_factor,
    is_affine_model,
    split_raw_adj,
    compute_qfq_prices,
)
from collector.etl.import_hk_daily import clean_and_split, _snapshot_quotes_df  # noqa: E402

# 碧桂园 02007 实测口径：a≈1、b≈5.2415（raw ≈ 0.18 HKD 的仙股）
BG_A, BG_B, BG_RAW0 = 1.0, 5.2415, 0.183


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range('2024-01-01', periods=n)


def _affine_series(n: int = 250, a: float = BG_A, b: float = BG_B, raw0: float = BG_RAW0,
                   seed: int = 7, jump_at: int = None, jump: float = 0.0,
                   raw_tick: int = 3) -> pd.DataFrame:
    """合成仿射复权序列：raw 随机游走（按 raw_tick 位取整模拟 tick），adj = a*raw + b。

    jump_at 指定某日 b 阶跃 jump（模拟现金分红）。
    """
    rng = np.random.default_rng(seed)
    r, bb = raw0, b
    raws, adjs = [], []
    for i in range(n):
        r = round(r * (1 + rng.uniform(-0.03, 0.03)), raw_tick)
        if jump_at is not None and i == jump_at:
            bb = b + jump
        raws.append(r)
        adjs.append(round(a * r + bb, 4))
    return pd.DataFrame({
        'trade_date': _dates(n),
        'raw_close': raws,
        'adj_close': adjs,
    })


def _multiplicative_series(n: int = 60, k: float = 0.5, switch_at: int = None,
                           k2: float = 0.4) -> pd.DataFrame:
    """合成乘性复权序列：raw 整百递变，adj = k*raw（倍率恒为 k，无浮点噪声）。"""
    raws = [1000 + 100 * i for i in range(n)]
    adjs = [int(k * x) if (switch_at is None or i < switch_at) else int(k2 * x)
            for i, x in enumerate(raws)]
    return pd.DataFrame({
        'trade_date': _dates(n),
        'raw_close': raws,
        'adj_close': adjs,
    })


def _flagged(df: pd.DataFrame, out: pd.DataFrame) -> int:
    return int(out['factor_date'].notna().sum())


class TestReportedBugRegression:
    """K 反馈的「碧桂园天天除权」必须不再复现。"""

    def test_additive_penny_stock_no_daily_false_flags(self):
        df = _affine_series(n=250, jump_at=None)
        # 复现旧口径：比值相对变化 >1% 的天数（旧实现即按此判除权）
        ratio = df['adj_close'] / df['raw_close']
        old_flags = int(((ratio / ratio.shift(1) - 1).abs() > 0.01).sum())
        assert old_flags > 100, f"合成数据未复现旧实现的误标风暴（{old_flags}）"

        out = detect_factor_dates(df)
        assert _flagged(df, out) == 0, out.loc[out['factor_date'].notna(), 'trade_date'].tolist()

    def test_affine_after_split_no_false_flags(self):
        """拆股后股本因子 a=5（腾讯式）：b 恒定 → 不应误标。"""
        df = _affine_series(n=250, a=5.0, b=278.93, raw0=420.0, raw_tick=1)
        out = detect_factor_dates(df)
        assert _flagged(df, out) == 0

    def test_real_dividend_still_detected_on_affine(self):
        """真实现金分红（b 阶跃 0.05）必须仍被标出，且只标那一天。"""
        df = _affine_series(n=120, jump_at=80, jump=0.05)
        out = detect_factor_dates(df)
        flagged = out.loc[out['factor_date'].notna(), 'trade_date'].tolist()
        assert len(flagged) == 1, flagged
        assert flagged[0] == df['trade_date'].iloc[80]

    def test_share_split_change_detected(self):
        """股本因子由 1 变 5（拆股）：该日应被标为除权日，且不产生风暴。"""
        n = 160
        rng = np.random.default_rng(3)
        r, raws, adjs = 20.0, [], []
        for i in range(n):
            r = round(r * (1 + rng.uniform(-0.03, 0.03)), 2)
            raws.append(r)
            adjs.append(round((1.0 if i < 100 else 5.0) * r, 4))
        df = pd.DataFrame({'trade_date': _dates(n), 'raw_close': raws, 'adj_close': adjs})
        out = detect_factor_dates(df)
        flagged = out.loc[out['factor_date'].notna(), 'trade_date'].tolist()
        assert len(flagged) <= 3, flagged
        assert df['trade_date'].iloc[100] in flagged


class TestMultiplicativeUnchanged:
    """乘性口径（美股 qfq×锚点式）保持原行为，不回退。"""

    def test_model_detected_as_multiplicative(self):
        df = _multiplicative_series(n=60)
        assert is_affine_model(df['raw_close'], df['adj_close']) is False

    def test_no_false_flags_when_ratio_constant(self):
        df = _multiplicative_series(n=60)
        assert _flagged(df, detect_factor_dates(df)) == 0

    def test_ratio_step_detected(self):
        df = _multiplicative_series(n=60, switch_at=40)
        out = detect_factor_dates(df)
        flagged = out.loc[out['factor_date'].notna(), 'trade_date'].tolist()
        assert flagged == [df['trade_date'].iloc[40]]


class TestGuards:
    """两道护栏：样本不足不标；命中占比超限整体不标（防误标风暴）。"""

    def test_short_window_not_detected(self):
        df = _affine_series(n=adj.FACTOR_MIN_ROWS - 1, jump_at=3, jump=0.5)
        assert _flagged(df, detect_factor_dates(df)) == 0

    def test_storm_guard_suppresses_all(self, monkeypatch, caplog):
        df = _affine_series(n=120, jump_at=60, jump=0.05)   # 正常情况下恰好 1 天命中
        monkeypatch.setattr(adj, 'MAX_FLAG_RATIO', 0.0)     # 令占比护栏必然触发
        with caplog.at_level('WARNING'):
            out = detect_factor_dates(df)
        assert _flagged(df, out) == 0
        assert any('命中占比异常' in r.getMessage() for r in caplog.records)


class TestEstimators:
    """`estimate_share_factor` / `is_affine_model` 单元。"""

    def test_estimate_share_factor_affine(self):
        df = _affine_series(n=120, a=5.0, b=278.93, raw0=420.0, raw_tick=1)
        a = estimate_share_factor(df['raw_close'], df['adj_close'])
        assert a == pytest.approx(5.0, rel=0.02)

    def test_estimate_share_factor_too_few_pairs(self):
        raw = pd.Series([1.0, 1.1])
        adj = pd.Series([6.0, 6.1])
        assert estimate_share_factor(raw, adj) is None

    def test_is_affine_model_positive_for_penny_stock(self):
        df = _affine_series(n=120)
        assert is_affine_model(df['raw_close'], df['adj_close']) is True


class TestAffineAdjustedOhlc:
    """复权 O/H/L 按仿射口径折算（协作单 45.0）。"""

    # 碧桂园 02007 实测：a=1、b=5.2415（raw≈0.18）
    _BG = pd.DataFrame({
        'Open': [0.179, 0.189], 'High': [0.185, 0.190],
        'Low': [0.176, 0.179], 'Close': [0.183, 0.179],
        'Adj Close': [0.183 + BG_B, 0.179 + BG_B],   # = raw_close + b（a=1）
        'Adj Share': [BG_A, BG_A],
    })

    def test_affine_synthesis_restores_true_intraday_range(self):
        """给定股本因子 → adj_x = a*raw_x + b，日内波幅与原始价同量级。"""
        out = split_raw_adj(self._BG.copy())
        assert out['adj_open'].iloc[0] == pytest.approx(0.179 + BG_B, abs=1e-4)
        assert out['adj_close'].iloc[0] == pytest.approx(0.183 + BG_B, abs=1e-4)
        assert out['adj_high'].iloc[0] - out['adj_low'].iloc[0] == pytest.approx(0.009, abs=1e-4)
        assert out['adj_share'].iloc[0] == pytest.approx(BG_A)

    def test_old_multiplicative_would_inflate_range_30x(self):
        """对照旧口径：按当日倍率 raw×(Adj Close/Close) 会把日内波幅放大 ~30 倍。"""
        df = self._BG.copy()
        ratio = df['Adj Close'] / df['Close']
        old_range = (df['High'] - df['Low']) * ratio
        new_range = (split_raw_adj(df)['adj_high'] - split_raw_adj(df)['adj_low'])
        assert old_range.iloc[0] / new_range.iloc[0] == pytest.approx(29.6, rel=0.05)

    def test_source_adj_ohlc_takes_priority(self):
        """数据源直供复权 O/H/L 时直接采用（最忠实，不做折算）。"""
        df = pd.DataFrame({
            'Open': [0.179], 'High': [0.185], 'Low': [0.176], 'Close': [0.183],
            'Adj Open': [5.4205], 'Adj High': [5.4265], 'Adj Low': [5.4175],
            'Adj Close': [5.4245], 'Adj Share': [BG_A],
        })
        out = split_raw_adj(df)
        assert out['adj_open'].iloc[0] == pytest.approx(5.4205)
        assert out['adj_high'].iloc[0] == pytest.approx(5.4265)
        assert out['adj_low'].iloc[0] == pytest.approx(5.4175)

    def test_missing_source_cell_falls_back_to_affine(self):
        """直供列个别缺失单元格按仿射式补（其余行仍用直供值）。"""
        df = pd.DataFrame({
            'Open': [0.179, 0.189], 'High': [0.185, 0.190],
            'Low': [0.176, 0.179], 'Close': [0.183, 0.179],
            'Adj High': [np.nan, 5.4315],
            'Adj Close': [5.4245, 5.4205], 'Adj Share': [BG_A, BG_A],
        })
        out = split_raw_adj(df)
        assert out['adj_high'].iloc[0] == pytest.approx(0.185 + BG_B, abs=1e-4)  # 仿射补
        assert out['adj_high'].iloc[1] == pytest.approx(5.4315)                  # 直供

    def test_without_share_degrades_to_multiplicative(self):
        """无股本因子列（美股乘性口径）→ 退化为 raw × 当日倍率，行为不变。"""
        df = pd.DataFrame({
            'Open': [100.0], 'High': [105.0], 'Low': [99.0],
            'Close': [100.0], 'Adj Close': [90.0],
        })
        out = split_raw_adj(df)
        assert out['adj_open'].iloc[0] == pytest.approx(90.0)
        assert out['adj_high'].iloc[0] == pytest.approx(94.5)
        assert out['adj_share'].iloc[0] == pytest.approx(0.9)


class TestSnapshotAffineConversion:
    """增量批量快照按仿射式换算（协作单 45.0）。"""

    _SNAP = pd.Series({
        'Open': 0.179, 'High': 0.185, 'Low': 0.176, 'Close': 0.183,
        'prev_close': 0.179, 'Volume': 1000,
    })
    _D = date(2026, 10, 12)

    def test_affine_when_share_present(self):
        df = _snapshot_quotes_df('2007.HK', self._SNAP, 0.183 + BG_B, 0.183, BG_A, self._D)
        row = df.iloc[0]
        # 主价格列存**前复权**（协作单 45.0 订正）：最新一日前复权 == 原始价
        assert row['close'] == pytest.approx(0.183, abs=1e-4)
        assert row['pre_close'] == pytest.approx(0.179, abs=1e-4)
        # 日内波幅与原始价同量级（旧实现为 ×30）
        assert float(row['high']) - float(row['low']) == pytest.approx(0.009, abs=1e-4)
        # 后复权参考列仍按仿射式
        assert row['adj_close'] == pytest.approx(0.183 + BG_B, abs=1e-4)
        assert float(row['adj_share']) == pytest.approx(BG_A)

    def test_multiplicative_fallback_without_share(self):
        """旧数据无 adj_share（NULL）→ 后复权参考列退化为乘性倍率；主价格列仍为原始价。"""
        c = 5.57 / 0.183
        df = _snapshot_quotes_df('2007.HK', self._SNAP, 5.57, 0.183, None, self._D)
        row = df.iloc[0]
        assert row['close'] == pytest.approx(0.183, abs=1e-4)
        assert row['adj_close'] == pytest.approx(0.183 * c, rel=1e-9)
        assert float(row['high']) - float(row['low']) == pytest.approx(0.009, abs=1e-4)
        assert float(row['adj_share']) == pytest.approx(c)

    def test_missing_price_returns_empty(self):
        snap = pd.Series({'Open': None, 'Close': None, 'Volume': 0})
        df = _snapshot_quotes_df('2007.HK', snap, 5.0, 0.2, BG_A, self._D)
        assert df.empty


class TestCleanAndSplitEndToEnd:
    """端到端：`clean_and_split` 不再为无除权的仿射标的产出 factor 行。"""

    @staticmethod
    def _fetch_like_frame(df: pd.DataFrame, share: float) -> pd.DataFrame:
        qfq = compute_qfq_prices(df)['qfq_close']
        return pd.DataFrame({
            'Date': df['trade_date'],
            'Open': df['raw_close'],
            'High': df['raw_close'],
            'Low': df['raw_close'],
            'Close': df['raw_close'],
            'Adj Close': df['adj_close'],
            'Adj Share': share,
            'Qfq Open': qfq,
            'Qfq High': qfq,
            'Qfq Low': qfq,
            'Qfq Close': qfq,
            'Volume': [1000] * len(df),
        })

    def test_no_factor_rows_for_plain_affine_stock(self):
        df = _affine_series(n=200)
        quotes, factor = clean_and_split(self._fetch_like_frame(df, BG_A), '2007.HK')
        assert quotes is not None and len(quotes) == 200
        assert factor is None or factor.empty

    def test_factor_row_written_for_real_dividend(self):
        df = _affine_series(n=200, jump_at=150, jump=0.05)
        quotes, factor = clean_and_split(self._fetch_like_frame(df, BG_A), '2007.HK')
        assert quotes is not None
        assert factor is not None and len(factor) == 1
        assert factor['factor_date'].iloc[0] == df['trade_date'].iloc[150].date()
        # 成交价列存**前复权**价（协作单 45.0 订正）：除权日之后（含最新一行）== 原始价
        assert quotes['close'].iloc[-1] == pytest.approx(df['raw_close'].iloc[-1], rel=1e-4)
        # 除权日之前的更早历史按分红因子 f=(p−jump)/p 折价
        assert quotes['close'].iloc[0] < df['raw_close'].iloc[0]
