"""港股/美股「复权序列滞后导致整行被丢弃」修复测试。

背景：新浪 `adjust='hfq'`（港股）/`'qfq'`（美股）与 `adjust=''` 是两次独立请求，
末日可能错位——不复权序列已含最新交易日 T，而复权序列止于 T-1。原实现
`adj.reindex(raw.index)` 在 T 日产出 NaN，随后 `clean_and_split` 的
`dropna(subset=[... 'adj_close'])` 把 **T 日整行丢弃**，形成「源有数据、库里缺该交易日」
的静默缺口（实测标的：00026.HK 缺 9/28）。

修复：`_fill_lagging_adj` 按最近可得复权倍率 `ratio = adj_close / raw_close`
（先 ffill 后 bfill，全缺退化 1.0）填补缺失日，再以 `raw_close × ratio` 还原复权价。

全部用例使用假 AkShare 数据源，不访问网络与数据库。

2026-09-29 创建
"""
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd
import pytest

# 保证 `collector.* / utils.*` 可解析（backend 为包根）
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.datasource import akshare as ak_mod  # noqa: E402
from collector.datasource.akshare import AkShareDataSource, _fill_lagging_adj  # noqa: E402
from collector.etl.import_hk_daily import clean_and_split  # noqa: E402


D1, D2, D3 = '2026-09-24', '2026-09-25', '2026-09-28'


def _frame(dates: List[str], closes: List[float]) -> pd.DataFrame:
    """构造新浪风格日线（date/open/high/low/close/volume）。"""
    return pd.DataFrame({
        'date': dates,
        'open': closes,
        'high': closes,
        'low': closes,
        'close': closes,
        'volume': [1000] * len(dates),
    })


class _FakeAk:
    """假 AkShare：不复权/后复权/前复权序列分别预置，可独立控制末日错位。

    `qfq` 缺省为 None → `_fetch_hk` 前复权列缺失时下游回退原始价。
    """

    def __init__(self, raw: Optional[pd.DataFrame], adj: Optional[pd.DataFrame],
                 qfq: Optional[pd.DataFrame] = None):
        self._raw = raw
        self._adj = adj
        self._qfq = qfq
        self.calls: List[tuple] = []

    def _pick(self, adjust: str) -> Optional[pd.DataFrame]:
        if adjust == 'qfq':
            df = self._qfq
        elif adjust == '':
            df = self._raw
        else:
            df = self._adj
        return None if df is None else df.copy()

    def stock_hk_daily(self, symbol: str, adjust: str = '') -> Optional[pd.DataFrame]:
        self.calls.append(('hk', symbol, adjust))
        return self._pick(adjust)

    def stock_us_daily(self, symbol: str, adjust: str = '') -> Optional[pd.DataFrame]:
        # 美股口径不变：'' 为不复权、其余（qfq 占位）为复权序列
        self.calls.append(('us', symbol, adjust))
        df = self._raw if adjust == '' else self._adj
        return None if df is None else df.copy()


def _src(market: str) -> AkShareDataSource:
    return AkShareDataSource(market=market)


# ==================== _fill_lagging_adj 单元 ====================
class TestFillLaggingAdj:
    """复权倍率前向填充的边界行为。"""

    def test_lagging_tail_filled_with_prev_ratio(self):
        raw = pd.Series([100.0, 110.0, 121.0], index=list('abc'))
        adj = pd.Series([90.0, 99.0, None], index=list('abc'))
        filled, n = _fill_lagging_adj(raw, adj)
        assert n == 1
        assert filled.iloc[-1] == pytest.approx(121.0 * 0.9)

    def test_no_missing_returns_unchanged(self):
        raw = pd.Series([100.0, 110.0], index=list('ab'))
        adj = pd.Series([90.0, 99.0], index=list('ab'))
        filled, n = _fill_lagging_adj(raw, adj)
        assert n == 0
        assert filled.tolist() == [90.0, 99.0]

    def test_missing_head_backfilled_with_next_ratio(self):
        raw = pd.Series([100.0, 110.0, 121.0], index=list('abc'))
        adj = pd.Series([None, None, 108.9], index=list('abc'))
        filled, n = _fill_lagging_adj(raw, adj)
        assert n == 2
        # 唯一可得倍率 = 108.9 / 121 = 0.9 → 前两日同样按 0.9 还原
        assert filled.iloc[0] == pytest.approx(90.0)
        assert filled.iloc[1] == pytest.approx(99.0)

    def test_all_adj_missing_degrades_to_factor_one(self):
        raw = pd.Series([100.0, 110.0], index=list('ab'))
        adj = pd.Series([None, None], index=list('ab'))
        filled, n = _fill_lagging_adj(raw, adj)
        assert n == 2
        assert filled.tolist() == [100.0, 110.0]

    def test_adj_series_none_degrades_to_raw(self):
        raw = pd.Series([100.0, 110.0], index=list('ab'))
        filled, n = _fill_lagging_adj(raw, None)
        assert n == 0
        assert filled.tolist() == [100.0, 110.0]

    def test_raw_missing_row_is_not_treated_as_lag(self):
        """不复权本身缺该日（停牌）→ 仍保持 NaN，交由下游按停牌剔除。"""
        raw = pd.Series([100.0, None, 121.0], index=list('abc'))
        adj = pd.Series([90.0, None, None], index=list('abc'))
        filled, n = _fill_lagging_adj(raw, adj)
        assert n == 1
        assert pd.isna(filled.iloc[1])
        assert filled.iloc[2] == pytest.approx(108.9)

    def test_non_positive_ratio_not_used(self):
        """脏倍率（<=0）被剔除后由其他有效日倍率补齐。"""
        raw = pd.Series([100.0, 100.0, 100.0], index=list('abc'))
        adj = pd.Series([-50.0, 90.0, None], index=list('abc'))
        filled, n = _fill_lagging_adj(raw, adj)
        assert n == 1
        assert filled.iloc[2] == pytest.approx(90.0)


# ==================== 适配器集成（港股） ====================
class TestFetchHkLaggingAdj:
    """港股 `_fetch_hk`：复权序列滞后时当日不再产出 NaN。"""

    def test_hfq_lagging_one_day_keeps_row(self, monkeypatch):
        raw = _frame([D1, D2, D3], [100.0, 110.0, 121.0])
        adj = _frame([D1, D2], [90.0, 99.0])   # hfq 滞后一天
        monkeypatch.setattr(ak_mod, 'ak', _FakeAk(raw, adj))
        out = _src('hk')._fetch_hk('00026', '0026.HK', None, None)
        assert out is not None and len(out) == 3
        assert not out['Adj Close'].isna().any()
        assert out['Close'].iloc[-1] == pytest.approx(121.0)
        assert out['Adj Close'].iloc[-1] == pytest.approx(108.9)

    def test_hfq_empty_degrades_to_raw(self, monkeypatch):
        raw = _frame([D1, D2], [100.0, 110.0])
        monkeypatch.setattr(ak_mod, 'ak', _FakeAk(raw, None))
        out = _src('hk')._fetch_hk('00026', '0026.HK', None, None)
        assert out is not None
        assert out['Adj Close'].tolist() == [100.0, 110.0]

    def test_adj_share_and_ohlc_transmitted_for_affine_stock(self, monkeypatch):
        """协作单 45.0：直供 hfq 的 O/H/L 与股本因子，供仿射折算/短窗口除权检测。"""
        d = [x.strftime('%Y-%m-%d') for x in pd.bdate_range('2026-09-01', periods=12)]
        raws = [round(0.18 + 0.006 * i, 3) for i in range(12)]
        raw = pd.DataFrame({'date': d, 'open': raws, 'high': [x + 0.004 for x in raws],
                            'low': [x - 0.003 for x in raws], 'close': raws,
                            'volume': [1000] * 12})
        adj = raw.copy()
        # 仿射：hfq = 1.0*raw + 5.2415（碧桂园式）
        for col in ('open', 'high', 'low', 'close'):
            adj[col] = (raw[col] + 5.2415).round(4)
        monkeypatch.setattr(ak_mod, 'ak', _FakeAk(raw, adj))
        out = _src('hk')._fetch_hk('02007', '2007.HK', None, None)
        assert out is not None
        assert out['Adj Share'].iloc[0] == pytest.approx(1.0, rel=0.02)
        # 直供复权 O/H/L：日内波幅与原始价同量级（而非按当日倍率放大 ~30 倍）
        assert out['Adj High'].iloc[-1] - out['Adj Low'].iloc[-1] == pytest.approx(0.007, abs=1e-4)
        assert out['Adj Close'].iloc[-1] == pytest.approx(raw['close'].iloc[-1] + 5.2415, abs=1e-4)


# ==================== 适配器集成（美股） ====================
class TestFetchUsLaggingAdj:
    """美股 `_fetch_us`：qfq 占位序列滞后时同样不得产出 NaN。"""

    def test_qfq_lagging_one_day_keeps_row(self, monkeypatch):
        raw = _frame([D1, D2, D3], [200.0, 210.0, 231.0])
        adj = _frame([D1, D2], [180.0, 189.0])
        monkeypatch.setattr(ak_mod, 'ak', _FakeAk(raw, adj))
        out = _src('us')._fetch_us('AAPL', 'AAPL', None, None)
        assert out is not None and len(out) == 3
        assert not out['Adj Close'].isna().any()
        assert out['Adj Close'].iloc[-1] == pytest.approx(231.0 * 0.9)


# ==================== 端到端（下游不再丢行） ====================
class TestCleanAndSplitKeepsLaggingDay:
    """`clean_and_split` 不再因 adj_close 缺失丢弃整行，且不误标除权日。"""

    def test_lagging_day_survives_to_quotes(self, monkeypatch):
        raw = _frame([D1, D2, D3], [100.0, 110.0, 121.0])
        adj = _frame([D1, D2], [90.0, 99.0])
        monkeypatch.setattr(ak_mod, 'ak', _FakeAk(raw, adj))
        df = _src('hk')._fetch_hk('00026', '0026.HK', None, None)

        quotes, adj_factor = clean_and_split(df, '0026.HK')
        assert quotes is not None
        assert len(quotes) == 3
        assert quotes['trade_date'].max() == date(2026, 9, 28)
        # 主价格列存**前复权**（协作单 45.0 订正）：本例未提供 qfq 序列 → 回退原始价
        assert quotes['close'].iloc[-1] == pytest.approx(121.0)
        assert quotes['raw_close'].iloc[-1] == pytest.approx(121.0)
        assert quotes['adj_close'].iloc[-1] == pytest.approx(108.9)
        # 倍率恒为 0.9 → 不是除权日，不应产生 factor_date
        assert adj_factor is None or adj_factor.empty

    def test_qfq_becomes_primary_price_column(self, monkeypatch):
        """数据源提供前复权序列时，主价格列取 qfq（而非后复权 hfq）。"""
        raw = _frame([D1, D2, D3], [0.200, 0.190, 0.183])
        hfq = _frame([D1, D2, D3], [5.4309, 5.4202, 5.4245])
        qfq = _frame([D1, D2, D3], [0.250, 0.230, 0.183])   # 前复权（历史更高价）
        monkeypatch.setattr(ak_mod, 'ak', _FakeAk(raw, hfq, qfq))
        df = _src('hk')._fetch_hk('02007', '2007.HK', None, None)

        quotes, _ = clean_and_split(df, '2007.HK')
        assert quotes is not None
        assert quotes['close'].iloc[-1] == pytest.approx(0.1830, abs=1e-4)
        assert quotes['close'].iloc[0] == pytest.approx(0.2500, abs=1e-4)   # 主价格 = qfq
        assert quotes['raw_close'].iloc[0] == pytest.approx(0.2000, abs=1e-4)
        assert quotes['adj_close'].iloc[0] == pytest.approx(5.4309, abs=1e-4)
