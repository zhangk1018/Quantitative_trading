"""
test_snapshot_history.py - /api/snapshot/history 历史逐日快照测试

覆盖（协作单 35.0 回测口径对齐）：
- 参数校验（codes 为空/超限、market 非法、日期格式、区间超限、行数上限）
- fields 白名单裁剪
- 真实 DB 集成：行数一致性、字段值与 stock_daily_snapshot 表逐字段一致、日期升序

运行：PG_PASSWORD=$PG_PASSWORD ./venv/bin/python -m pytest backend/tests/test_snapshot_history.py -v
"""

import os
import threading
import time
import datetime
from decimal import Decimal

import psycopg2
import psycopg2.pool
import pytest
from dotenv import load_dotenv

from core.service import snapshot_service as ss
from core.service.snapshot_service import (
    HISTORY_MAX_CODES,
    HISTORY_SNAPSHOT_FIELDS,
    SnapshotService,
)

load_dotenv()


def _make_service(pool) -> SnapshotService:
    """绕过 __init__（避免触发后台全量加载），仅装配历史查询所需状态"""
    svc = SnapshotService.__new__(SnapshotService)
    svc._pool = pool
    svc._ready = True
    svc._loading = False
    svc._load_error = None
    svc._state_lock = threading.Lock()
    svc._reload_mutex = threading.Lock()
    svc._last_check_time = time.time()  # 防抖窗口内跳过 _refresh_if_needed
    svc._latest_trade_date = '2026-09-11'
    svc._cached_row_hash = 'stub'
    return svc


@pytest.fixture(scope="module")
def pg_pool():
    pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=3,
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5432')),
        database=os.getenv('PG_DATABASE', 'quant_trading'),
        user=os.getenv('PG_USER', 'quant_user'),
        password=os.getenv('PG_PASSWORD'),
        connect_timeout=10,
    )
    yield pool
    pool.closeall()


@pytest.fixture(scope="module")
def svc(pg_pool):
    return _make_service(pg_pool)


class TestHistoryParamValidation:
    """参数校验（查询前置，不触达 DB 数据）"""

    def test_empty_codes_raises(self, svc):
        with pytest.raises(ValueError, match="codes 不能为空"):
            svc.get_history_snapshots(codes=[])

    def test_blank_codes_raises(self, svc):
        with pytest.raises(ValueError, match="codes 不能为空"):
            svc.get_history_snapshots(codes=['  ', ''])

    def test_too_many_codes_raises(self, svc):
        codes = [f"{i:06d}" for i in range(HISTORY_MAX_CODES + 1)]
        with pytest.raises(ValueError, match="超过上限"):
            svc.get_history_snapshots(codes=codes, start_date='2026-09-01', end_date='2026-09-11')

    def test_invalid_market_raises(self, svc):
        with pytest.raises(ValueError, match="market 参数无效"):
            svc.get_history_snapshots(codes=['000001'], market='xx',
                                      start_date='2026-09-01', end_date='2026-09-11')

    def test_invalid_start_date_raises(self, svc):
        with pytest.raises(ValueError, match="start_date"):
            svc.get_history_snapshots(codes=['000001'], start_date='20260901', end_date='2026-09-11')

    def test_invalid_end_date_raises(self, svc):
        with pytest.raises(ValueError, match="end_date"):
            svc.get_history_snapshots(codes=['000001'], start_date='2026-09-01', end_date='bad')

    def test_start_after_end_raises(self, svc):
        with pytest.raises(ValueError, match="start_date 不能晚于"):
            svc.get_history_snapshots(codes=['000001'],
                                      start_date='2026-09-11', end_date='2026-09-01')

    def test_range_over_max_days_raises(self, svc):
        with pytest.raises(ValueError, match="超过上限"):
            svc.get_history_snapshots(codes=['000001'],
                                      start_date='2024-01-01', end_date='2026-09-11')

    def test_market_mismatch_codes_raises(self, svc):
        with pytest.raises(ValueError, match="无 hk 市场股票"):
            svc.get_history_snapshots(codes=['000001'], market='hk',
                                      start_date='2026-09-01', end_date='2026-09-11')


class TestHistoryFields:
    """fields 白名单裁剪逻辑"""

    def test_invalid_fields_fallback_to_all(self, svc, pg_pool):
        result = svc.get_history_snapshots(
            codes=['000001'],
            fields=['not_a_field', 'another_fake'],
            start_date='2026-09-07', end_date='2026-09-11',
        )
        assert result.fields == list(HISTORY_SNAPSHOT_FIELDS)

    def test_valid_fields_intersection(self, svc, pg_pool):
        result = svc.get_history_snapshots(
            codes=['000001'],
            fields=['close', 'rsi_6', 'fake_field', 'pattern_hammer'],
            start_date='2026-09-07', end_date='2026-09-11',
        )
        assert result.fields == ['close', 'rsi_6', 'pattern_hammer']
        for stock in result.stocks:
            for row in stock.rows:
                assert set(row.keys()) == {'trade_date', 'close', 'rsi_6', 'pattern_hammer'}


class TestHistoryIntegration:
    """真实 DB 集成校验"""

    START, END, CODE = '2026-08-20', '2026-09-11', '000001'

    @pytest.fixture(scope="class")
    def db_conn(self):
        conn = psycopg2.connect(
            host=os.getenv('PG_HOST', 'localhost'),
            port=int(os.getenv('PG_PORT', '5432')),
            database=os.getenv('PG_DATABASE', 'quant_trading'),
            user=os.getenv('PG_USER', 'quant_user'),
            password=os.getenv('PG_PASSWORD'),
            connect_timeout=10,
        )
        yield conn
        conn.close()

    def test_row_count_and_order_and_values(self, svc, db_conn):
        result = svc.get_history_snapshots(
            codes=[self.CODE], market='cn',
            start_date=self.START, end_date=self.END,
        )
        assert result.total_codes == 1
        stock = result.stocks[0]
        assert stock.code == self.CODE

        # DB 侧行数与日期集
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT trade_date, close, dif, dea, boll_upper, pe_ttm, market_cap, "
                "       turnover_rate, rsi_6, pattern_hammer, ma_long_align, is_st "
                "FROM stock_daily_snapshot WHERE code=%s AND market='cn' "
                "AND trade_date BETWEEN %s AND %s ORDER BY trade_date",
                (self.CODE, self.START, self.END),
            )
            db_rows = cur.fetchall()

        assert len(stock.rows) == len(db_rows) > 0
        # 交易日升序且与 DB 一致
        dates = [r['trade_date'] for r in stock.rows]
        assert dates == sorted(dates)
        assert dates == [r[0].strftime('%Y-%m-%d') for r in db_rows]

        # 逐字段一致（Decimal→float / bool 保持）
        for api_row, db_row in zip(stock.rows, db_rows):
            (db_date, db_close, db_dif, db_dea, db_boll, db_pe_ttm,
             db_mv, db_turn, db_rsi6, db_hammer, db_ma_long, db_is_st) = db_row
            assert api_row['close'] == float(db_close)
            assert api_row['dif'] == (None if db_dif is None else float(db_dif))
            assert api_row['dea'] == (None if db_dea is None else float(db_dea))
            assert api_row['boll_upper'] == (None if db_boll is None else float(db_boll))
            assert api_row['pe_ttm'] == (None if db_pe_ttm is None else float(db_pe_ttm))
            assert api_row['market_cap'] == (None if db_mv is None else float(db_mv))
            assert api_row['turnover_rate'] == (None if db_turn is None else float(db_turn))
            assert api_row['rsi_6'] == (None if db_rsi6 is None else float(db_rsi6))
            assert api_row['pattern_hammer'] == bool(db_hammer)
            assert api_row['ma_long_align'] == bool(db_ma_long)
            assert api_row['is_st'] == bool(db_is_st)

    def test_decimal_and_date_coercion(self, svc):
        """_coerce_history_value：Decimal→float / date→str / None→None / 其他原样"""
        coerce = SnapshotService._coerce_history_value
        assert coerce(Decimal('12.34')) == 12.34
        assert isinstance(coerce(Decimal('12.34')), float)
        assert coerce(datetime.date(2026, 9, 11)) == '2026-09-11'
        assert coerce(None) is None
        assert coerce(7) == 7
        assert coerce(True) is True

    def test_row_limit_guard(self, svc, monkeypatch):
        """行数超上限立即报错（内存保护）"""
        monkeypatch.setattr(ss, 'HISTORY_MAX_ROWS', 2)
        with pytest.raises(ValueError, match="超过上限"):
            svc.get_history_snapshots(codes=[self.CODE],
                                      start_date=self.START, end_date=self.END)
