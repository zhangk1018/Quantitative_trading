# -*- coding: utf-8 -*-
"""除权当日快照行落库（P2-1，2026-11-02）。

背景：批量快照遇到除权标的会回退逐只，而新浪逐只历史滞后 1 个交易日，
导致除权当日（尤其现金分红）无法落库，形成 1 天缺口（10-30 缺 16 只、11-02 缺 27 只）。

修复：
- 港交所事件描述区分「现金分红（a 不变）」与「股本变动（a 需重写）」；
- 现金分红：用快照「除权后昨收」重建 T 日总收益因子
  `adj_close_T = adj_close_{T-1} * raw_close_T / prev_close_spot`，
  并更新加性偏移 b，使后复权序列在除权日连续；
- 股本变动/非 T-1 锚点/缺昨收 → 仍回退逐只（次日历史更新后自动补正）。

全部用例使用假连接/假写库，不访问网络与数据库。
"""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.etl import import_hk_daily as hk  # noqa: E402

SNAP = date(2026, 11, 2)
PREV = date(2026, 10, 30)


def _snap_row(**overrides) -> pd.Series:
    data = {
        'code': '0998.HK', 'Open': 7.60, 'High': 7.80, 'Low': 7.40, 'Close': 7.70,
        'prev_close': 7.50, 'Volume': 100, 'Amount': 770.0,
        'Timezone': 'Asia/Hong_Kong',
    }
    data.update(overrides)
    return pd.Series(data)


def _snap_df(**overrides) -> pd.DataFrame:
    row = _snap_row(**overrides).to_dict()
    return pd.DataFrame([row], index=pd.DatetimeIndex(['2026-11-02']))


class TestEventClassification:

    @pytest.mark.parametrize('desc,ratio,expected', [
        ('INTERIM (SEMI-ANNUAL) DIVIDEND HKD0.3 PER SHARE (Y.E. 31/12/2026)', 0.92, False),
        ('SPECIAL DIVIDEND HKD0.266 PER SHARE', 0.93, False),
        ('RIGHTS ISSUE: 3 RIGHTS SHARES FOR EVERY 10 SHARES', 0.80, True),
        ('SHARE SPLIT 2 FOR 1', 0.50, True),
        ('BONUS ISSUE 1 FOR 2', 0.67, True),
        ('CONSOLIDATION 1 FOR 10', 10.0, True),
        ('FINAL DIVIDEND HKD0.43 PER SHARE (WITH SCRIP OPTION)', 0.90, False),
    ])
    def test_description_keywords(self, desc, ratio, expected):
        assert hk._event_changes_share(desc, ratio) is expected

    def test_missing_description_falls_back_to_jump_ratio(self):
        assert hk._event_changes_share(None, 0.50) is True
        assert hk._event_changes_share('', 0.98) is False


class TestExrightSnapshotRow:

    def test_cash_dividend_row_keeps_hfq_continuity(self):
        """现金分红：a 不变，adj_close 按总收益因子衔接 T-1，并把分红加回 b。"""
        df = hk._snapshot_quotes_df_exright(
            '0998.HK', _snap_row(), anchor_adj_close=10.0, anchor_raw_close=8.0,
            share=1.0, trade_date=SNAP,
            description='INTERIM DIVIDEND HKD0.3 PER SHARE',
            anchor_trade_date=PREV, prev_trade_date=PREV,
        )
        assert not df.empty
        row = df.iloc[0]
        assert float(row['close']) == pytest.approx(7.70)
        assert float(row['pre_close']) == pytest.approx(7.50)
        # 仿射口径：adj_T = adj_{T-1} + a*(raw_T - 除权后昨收)（把分红加回）
        assert float(row['adj_close']) == pytest.approx(10.0 + 1.0 * (7.70 - 7.50))
        b_new = 10.0 + 1.0 * (7.70 - 7.50) - 1.0 * 7.70
        assert float(row['adj_open']) == pytest.approx(7.60 + b_new)
        assert float(row['adj_high']) == pytest.approx(7.80 + b_new)
        assert float(row['adj_low']) == pytest.approx(7.40 + b_new)
        assert float(row['adj_share']) == pytest.approx(1.0)
        assert int(row['volume']) == 100
        assert float(row['amount']) == pytest.approx(770.0)

    def test_affine_share_uses_same_a_and_new_b(self):
        """仿射标的（a=2, b=-6）：a 不变，b 随分红更新，adj 序列仍按 raw 收益比例连续。"""
        df = hk._snapshot_quotes_df_exright(
            '02007.HK', _snap_row(code='02007.HK'), anchor_adj_close=10.0,
            anchor_raw_close=8.0, share=2.0, trade_date=SNAP,
            description='INTERIM DIVIDEND HKD0.3 PER SHARE',
            anchor_trade_date=PREV, prev_trade_date=PREV,
        )
        row = df.iloc[0]
        assert float(row['adj_share']) == pytest.approx(2.0)
        assert float(row['adj_close']) == pytest.approx(10.0 + 2.0 * (7.70 - 7.50))
        # 仿射序列的日间增量 = a*(raw_T - 除权后昨收)，与源 hfq 口径一致
        assert float(row['adj_close']) - 10.0 == pytest.approx(2.0 * (7.70 - 7.50))

    def test_share_event_falls_back(self):
        """拆股/供股/送股：需要重写全历史 hfq，当日返回空由调用方回退。"""
        df = hk._snapshot_quotes_df_exright(
            '1351.HK', _snap_row(code='1351.HK'), 10.0, 8.0, 1.0, SNAP,
            description='RIGHTS ISSUE: 3 RIGHTS SHARES FOR EVERY 1 CONSOLIDATED SHARE',
            anchor_trade_date=PREV, prev_trade_date=PREV,
        )
        assert df.empty

    def test_anchor_must_be_previous_trade_date(self):
        """锚点不是 T-1（中间有缺口/长期停牌）→ 不落除权行，回退逐只。"""
        df = hk._snapshot_quotes_df_exright(
            '0998.HK', _snap_row(), 10.0, 8.0, 1.0, SNAP,
            description='INTERIM DIVIDEND HKD0.3 PER SHARE',
            anchor_trade_date=date(2026, 10, 29), prev_trade_date=PREV,
        )
        assert df.empty

    def test_missing_prev_close_falls_back(self):
        df = hk._snapshot_quotes_df_exright(
            '0998.HK', _snap_row(prev_close=None), 10.0, 8.0, 1.0, SNAP,
            description='INTERIM DIVIDEND HKD0.3 PER SHARE',
            anchor_trade_date=PREV, prev_trade_date=PREV,
        )
        assert df.empty

    def test_adj_factor_row_marks_factor_date(self):
        df = hk._snapshot_adj_factor_df('0998.HK', SNAP, 7.70, 10.2666)
        row = df.iloc[0]
        assert row['factor_date'] == SNAP
        assert float(row['adj_factor']) == pytest.approx(10.2666 / 7.70)
        assert row['market'] == 'hk'


class TestImportLoopWiring:

    def test_cash_exright_written_directly_without_per_stock(self):
        """官方除权+现金分红 → 当日快照行直接落库，并写 adj_factor，不触发 resolve_one。"""
        wrote = {}
        wrote_af = {}
        with patch.object(hk, '_hk_exright_events', return_value={'0998.HK': 'INTERIM DIVIDEND HKD0.3 PER SHARE'}), \
                patch.object(hk, '_hk_prev_trade_date', return_value=PREV), \
                patch.object(hk, '_hk_snapshot_latest', return_value=(10.0, 8.0, 1.0, PREV)), \
                patch.object(hk, 'write_quotes', side_effect=lambda _c, q, code: wrote.setdefault(code, q)), \
                patch.object(hk, 'write_adj_factor', side_effect=lambda _c, a, code: wrote_af.setdefault(code, a)), \
                patch.object(hk, 'resolve_one') as mock_one:
            stats = hk.import_hk_snapshot_daily(object(), object(), snapshot=_snap_df())

        mock_one.assert_not_called()
        assert stats['direct'] == 1
        assert stats['fallback'] == 0
        assert stats['exright_direct'] == 1
        assert stats['exright'] == 1
        assert '0998.HK' in wrote and '0998.HK' in wrote_af
        assert wrote_af['0998.HK'].iloc[0]['factor_date'] == SNAP

    def test_share_event_still_falls_back(self):
        """股本变动事件 → 仍回退逐只，但 exright 计数保留。"""
        with patch.object(hk, '_hk_exright_events', return_value={'1351.HK': 'RIGHTS ISSUE'}), \
                patch.object(hk, '_hk_prev_trade_date', return_value=PREV), \
                patch.object(hk, '_hk_snapshot_latest', return_value=(10.0, 8.0, 1.0, PREV)), \
                patch.object(hk, 'resolve_one') as mock_one:
            stats = hk.import_hk_snapshot_daily(object(), object(), snapshot=_snap_df(code='1351.HK'))

        mock_one.assert_called_once()
        assert stats['direct'] == 0
        assert stats['fallback'] == 1
        assert stats['exright'] == 1
        assert stats['exright_direct'] == 0
