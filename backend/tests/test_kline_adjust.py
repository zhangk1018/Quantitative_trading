"""`/api/kline` 复权换算单测（协作单 45.0 / 订正）。

背景（两轮）：
1. `kline_service` 原引用 `backend.imputer.Adjuster`，该模块已于 1978bcf 删除 →
   ImportError 被 `except` 吞掉 → **数据未换算却回显 `adj_method=forward`**（静默错误契约）。
2. 45.0 首版对港股用「乘性重标定 `k = raw_now/hfq_now`」把**仿射**后复权序列压平
   （碧桂园 2025-12 真实 0.415 被显示成 0.19）。

订正后：库内主价格列（open/high/low/close）**统一为前复权**（cn/hk/us），故：
- `forward`：三市场一律原样返回，**不再做任何重标定**；
- `none`：hk/us 改用 `raw_close`（原始成交价）；cn 无原始价 → 抛错（按实际口径回填）；
- `backward`：hk 改用 `adj_close`（后复权 hfq）；cn/us 无后复权序列 → 抛错。

全部离线（假数据，无需 storage）。
"""
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from core.service.kline_service import KlineService, _AdjustNotSupported  # noqa: E402


def _svc():
    svc = KlineService.__new__(KlineService)
    svc._storage = None
    return svc


def _df():
    """碧桂园式库内行：主价格列已是前复权（0.183 量级），adj_* 为后复权（5.42 量级）。"""
    return pd.DataFrame({
        'trade_date': ['2026-10-08', '2026-10-09'],
        'open': [0.1900, 0.1800],
        'high': [0.1950, 0.1850],
        'low': [0.1890, 0.1790],
        'close': [0.1890, 0.1830],
        'raw_open': [0.1900, 0.1800],
        'raw_high': [0.1950, 0.1850],
        'raw_low': [0.1890, 0.1790],
        'raw_close': [0.1890, 0.1830],
        'adj_open': [5.4309, 5.4202],
        'adj_high': [5.4319, 5.4266],
        'adj_low': [5.4202, 5.4170],
        'adj_close': [5.4202, 5.4245],
        'volume': [432486055, 232318000],
        'amount': [81720314.0, 42514194.0],
    })


def _df_cn():
    """A 股行：仅主价格列（无 raw_*/adj_*）。"""
    df = _df()
    return df.drop(columns=[c for c in df.columns if c.startswith(('raw_', 'adj_'))])


class TestForward:
    def test_hk_forward_returns_stored_qfq_unchanged(self):
        """港股 forward：库内已前复权 → 原样返回，不再乘任何系数。"""
        svc = _svc()
        df = _df()
        out, method, factor = svc._apply_adjust(df, '2007.HK', 'forward', '1d')
        assert method == 'forward'
        assert factor is None
        assert out['close'].tolist() == df['close'].tolist()
        assert float(out['close'].iloc[-1]) == pytest.approx(0.1830, abs=1e-9)

    def test_cn_forward_returns_stored_qfq_unchanged(self):
        svc = _svc()
        df = _df_cn()
        out, method, factor = svc._apply_adjust(df, '600519', 'forward', '1d')
        assert method == 'forward' and factor is None
        assert out['close'].tolist() == df['close'].tolist()

    def test_us_forward_returns_stored_qfq_unchanged(self):
        svc = _svc()
        df = _df()
        out, method, _ = svc._apply_adjust(df, 'AAPL', 'forward', '1d')
        assert method == 'forward'
        assert out['close'].tolist() == df['close'].tolist()


class TestNone:
    def test_hk_none_uses_raw_close(self):
        """港股 none：返回原始成交价（raw_*，不复权）。"""
        svc = _svc()
        out, method, _ = svc._apply_adjust(_df(), '2007.HK', 'none', '1d')
        assert method == 'none'
        assert float(out['close'].iloc[-1]) == pytest.approx(0.1830, abs=1e-9)
        assert float(out['high'].iloc[-1]) == pytest.approx(0.1850, abs=1e-9)

    def test_cn_none_not_supported(self):
        """A 股库内无原始价 → 抛错，且标注实际返回口径为 forward。"""
        svc = _svc()
        with pytest.raises(_AdjustNotSupported) as ei:
            svc._apply_adjust(_df_cn(), '600519', 'none', '1d')
        assert ei.value.eff_method == 'forward'


class TestBackward:
    def test_hk_backward_uses_adj_close_hfq(self):
        """港股 backward：改用后复权列 adj_close（hfq，5.42 量级）。"""
        svc = _svc()
        out, method, _ = svc._apply_adjust(_df(), '2007.HK', 'backward', '1d')
        assert method == 'backward'
        assert float(out['close'].iloc[-1]) == pytest.approx(5.4245, abs=1e-4)

    def test_cn_backward_not_supported(self):
        svc = _svc()
        with pytest.raises(_AdjustNotSupported) as ei:
            svc._apply_adjust(_df_cn(), '600519', 'backward', '1d')
        assert ei.value.eff_method == 'forward'

    def test_us_backward_not_supported(self):
        """美股库内 adj_close 即 qfq（非 hfq）→ 不得冒充后复权。"""
        svc = _svc()
        with pytest.raises(_AdjustNotSupported) as ei:
            svc._apply_adjust(_df(), 'AAPL', 'backward', '1d')
        assert ei.value.eff_method == 'forward'


class TestGuards:
    def test_unknown_method_rejected(self):
        svc = _svc()
        with pytest.raises(_AdjustNotSupported, match='未知复权方式') as ei:
            svc._apply_adjust(_df(), '2007.HK', 'magic', '1d')
        assert ei.value.eff_method == 'forward'

    def test_none_without_raw_price_column_downgrades(self):
        """缺 raw_* 列时不得假装给了不复权。"""
        svc = _svc()
        with pytest.raises(_AdjustNotSupported) as ei:
            svc._apply_adjust(_df_cn(), '2007.HK', 'none', '1d')
        assert ei.value.eff_method == 'forward'

    def test_stock_code_prefix_normalized(self):
        """sh./sz. 前缀应归一化后再判定市场（cn → forward 原样）。"""
        svc = _svc()
        df = _df_cn()
        out, method, _ = svc._apply_adjust(df, 'sz.000001', 'forward', '1d')
        assert method == 'forward'
        assert out['close'].tolist() == df['close'].tolist()


class TestPricePrecision:
    def test_ohlc_keeps_four_decimals(self):
        """价格列按 4 位小数输出（2 位会把碧桂园 0.183 退化为 0.18）。"""
        svc = _svc()
        out, _, _ = svc._apply_adjust(_df(), '2007.HK', 'forward', '1d')
        items = svc._convert_to_kline_items(out)
        assert items[-1].close == Decimal('0.183')
        assert items[-1].low == Decimal('0.179')
        assert items[-1].low != Decimal('0.18')
