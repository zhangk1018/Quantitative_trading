"""
snapshot_service.py - 全量快照数据服务

提供全市场股票的 300 天 OHLCV + 最新交易日标准指标数据，
供前端全量计算架构使用。

【设计要点】
1. 内存预加载：启动时将 300 天 OHLCV 历史 + 最新交易日指标全部载入内存
2. OHLCV 列式二维数组：[[time, open, high, low, close, volume], ...]
3. 指标嵌套：indicators 字段内嵌套 ma/rsi/macd/boll 等标准指标
4. 增量同步：支持 since 参数返回指定日期之后的增量数据

【工单】
[6.12-SNAPSHOT-API-20260624] 前端全量计算架构后端支撑端点
"""

import time
import logging
from datetime import datetime, date
from typing import Dict, List, Optional

import pandas as pd
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from shared.schemas import (
    SnapshotAllData,
    SnapshotIncrementalData,
    SnapshotStock,
    SnapshotIndicators,
)

logger = logging.getLogger(__name__)


# OHLCV 列索引常量（与前端对齐）
OHLCV_TIME = 0
OHLCV_OPEN = 1
OHLCV_HIGH = 2
OHLCV_LOW = 3
OHLCV_CLOSE = 4
OHLCV_VOLUME = 5


class SnapshotService:
    """全量快照数据服务（内存缓存）"""

    HISTORY_DAYS = 300  # 历史数据天数

    def __init__(self, pg_pool: psycopg2.pool.ThreadedConnectionPool) -> None:
        """
        Args:
            pg_pool: PostgreSQL ThreadedConnectionPool 连接池
        """
        self._pool = pg_pool
        self._ohlcv_cache: Dict[str, List[List[float]]] = {}  # code -> ohlcv 列表
        self._snapshot_cache: Dict[str, dict] = {}  # code -> 最新交易日快照行
        self._latest_trade_date: Optional[str] = None
        self._load_time: float = 0
        self._cache_ttl = 300  # 缓存有效期 5 分钟

    def _check_reload(self) -> None:
        """检查缓存是否过期，过期则重新加载"""
        now = time.time()
        if not self._ohlcv_cache or (now - self._load_time) > self._cache_ttl:
            self._load_all()

    def _load_all(self) -> None:
        """从数据库全量加载：300天 OHLCV + 最新交易日宽表快照"""
        logger.info("📦 开始加载全量快照数据（300 天 OHLCV + 最新交易日指标）...")
        start = time.time()

        conn = self._pool.getconn()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # 1. 查询最新交易日期
            cur.execute("""
                SELECT MAX(trade_date) as latest FROM stock_daily_snapshot
            """)
            row = cur.fetchone()
            if not row or not row['latest']:
                raise RuntimeError("stock_daily_snapshot 表无数据")
            self._latest_trade_date = str(row['latest'])

            # 2. 加载 300 天 OHLCV 历史数据
            cur.execute("""
                SELECT code, trade_date, open, high, low, close, volume
                FROM stock_quotes
                WHERE cycle = '1d'
                  AND trade_date >= CAST(%(latest_date)s AS DATE) - INTERVAL %(history_days)s
                  AND trade_date <= %(latest_date)s
                ORDER BY code, trade_date
            """, {
                'latest_date': self._latest_trade_date,
                'history_days': f'{self.HISTORY_DAYS} days',
            })
            rows = cur.fetchall()

            ohlcv_dict: Dict[str, List[List[float]]] = {}
            for r in rows:
                code = r['code']
                if code not in ohlcv_dict:
                    ohlcv_dict[code] = []
                ts = int(datetime.combine(r['trade_date'], datetime.min.time()).timestamp())
                ohlcv_dict[code].append([
                    float(ts),
                    float(r['open']) if r['open'] is not None else 0.0,
                    float(r['high']) if r['high'] is not None else 0.0,
                    float(r['low']) if r['low'] is not None else 0.0,
                    float(r['close']) if r['close'] is not None else 0.0,
                    float(r['volume']) if r['volume'] is not None else 0.0,
                ])
            self._ohlcv_cache = ohlcv_dict

            # 3. 加载最新交易日宽表快照
            cur.execute("""
                SELECT
                    code, stock_name, listed_board, industry, trade_date,
                    close, change_pct, market_cap, turnover_rate, pe_ttm, pb,
                    ma5, ma10, ma20, ma60,
                    rsi_6, rsi_12, rsi_24,
                    dif, dea, macd,
                    boll_upper, boll_mid, boll_lower,
                    is_macd_golden_cross, is_macd_dead_cross
                FROM stock_daily_snapshot
                WHERE trade_date = %(latest_date)s
            """, {
                'latest_date': self._latest_trade_date,
            })
            snap_rows = cur.fetchall()
            self._snapshot_cache = {r['code']: dict(r) for r in snap_rows}

            cur.close()
        finally:
            self._pool.putconn(conn)

        self._load_time = time.time()
        elapsed = self._load_time - start
        logger.info(
            "✅ 全量快照数据加载完成：%d 只股票，耗时 %.2fs",
            len(self._snapshot_cache), elapsed,
        )

    def _build_indicators(self, row: dict) -> SnapshotIndicators:
        """从数据库行构建 SnapshotIndicators 对象"""
        return SnapshotIndicators(
            ma5=float(row['ma5']) if row['ma5'] is not None else None,
            ma10=float(row['ma10']) if row['ma10'] is not None else None,
            ma20=float(row['ma20']) if row['ma20'] is not None else None,
            ma60=float(row['ma60']) if row['ma60'] is not None else None,
            rsi_6=float(row['rsi_6']) if row['rsi_6'] is not None else None,
            rsi_12=float(row['rsi_12']) if row['rsi_12'] is not None else None,
            rsi_24=float(row['rsi_24']) if row['rsi_24'] is not None else None,
            macd_dif=float(row['dif']) if row['dif'] is not None else None,
            macd_dea=float(row['dea']) if row['dea'] is not None else None,
            macd=float(row['macd']) if row['macd'] is not None else None,
            boll_upper=float(row['boll_upper']) if row['boll_upper'] is not None else None,
            boll_mid=float(row['boll_mid']) if row['boll_mid'] is not None else None,
            boll_lower=float(row['boll_lower']) if row['boll_lower'] is not None else None,
            is_macd_golden_cross=bool(row['is_macd_golden_cross']) if row['is_macd_golden_cross'] is not None else False,
            is_macd_dead_cross=bool(row['is_macd_dead_cross']) if row['is_macd_dead_cross'] is not None else False,
        )

    def _build_stock_snapshot(self, code: str, row: dict, ohlcv: List[List[float]]) -> SnapshotStock:
        """构建单只股票的快照对象"""
        return SnapshotStock(
            code=code,
            name=row['stock_name'] or '',
            listed_board=row['listed_board'] or '',
            industry=row['industry'] or '',
            trade_date=row['trade_date'],
            close=float(row['close']) if row['close'] is not None else 0.0,
            change_pct=float(row['change_pct']) if row['change_pct'] is not None else None,
            market_cap=float(row['market_cap']) if row['market_cap'] is not None else None,
            turnover_rate=float(row['turnover_rate']) if row['turnover_rate'] is not None else None,
            pe_ttm=float(row['pe_ttm']) if row['pe_ttm'] is not None else None,
            pb=float(row['pb']) if row['pb'] is not None else None,
            indicators=self._build_indicators(row),
            ohlcv=ohlcv,
        )

    def get_all_snapshot(self, board: str | None = None, industry: str | None = None) -> SnapshotAllData:
        """获取全市场全量快照

        Args:
            board: 板块过滤（None=全部，main_board=主板，gem=创业板，beijing=北交所）
            industry: 行业名称过滤（None=全部）

        Returns:
            SnapshotAllData: 全量快照数据
        """
        self._check_reload()

        stocks = []
        for code, row in self._snapshot_cache.items():
            if board and row.get('listed_board', '') != board:
                continue
            if industry and row.get('industry', '') != industry:
                continue
            ohlcv = self._ohlcv_cache.get(code, [])
            stocks.append(self._build_stock_snapshot(code, row, ohlcv))

        return SnapshotAllData(
            latest_trade_date=self._latest_trade_date or '',
            total=len(stocks),
            stocks=stocks,
        )

    def get_incremental_snapshot(self, since: str, board: str | None = None, industry: str | None = None) -> SnapshotIncrementalData:
        """获取增量快照

        Args:
            since: 起始日期（YYYY-MM-DD，含当日）
            board: 板块过滤（None=全部）
            industry: 行业名称过滤（None=全部）

        Returns:
            SnapshotIncrementalData: 增量快照数据
        """
        self._check_reload()

        since_ts = int(datetime.strptime(since, '%Y-%m-%d').timestamp())

        stocks = []
        days_set = set()

        for code, row in self._snapshot_cache.items():
            if board and row.get('listed_board', '') != board:
                continue
            if industry and row.get('industry', '') != industry:
                continue
            ohlcv = self._ohlcv_cache.get(code, [])
            # 过滤 since 之后的 OHLCV
            inc_ohlcv = [bar for bar in ohlcv if bar[OHLCV_TIME] >= since_ts]
            if not inc_ohlcv:
                continue

            # 记录有数据的交易日
            for bar in inc_ohlcv:
                days_set.add(bar[OHLCV_TIME])

            stocks.append(self._build_stock_snapshot(code, row, inc_ohlcv))

        return SnapshotIncrementalData(
            since=since,
            latest_trade_date=self._latest_trade_date or '',
            days=len(days_set),
            stocks=stocks,
        )

    @property
    def latest_trade_date(self) -> Optional[str]:
        """最新交易日期"""
        self._check_reload()
        return self._latest_trade_date
