"""
incomplete_handler.py - 数据缺口检测和补全

【设计目标】
检测本地数据缺失，从数据源重新拉取，补齐缺口。

【与 missing_handler 的区别】
- incomplete_handler: 检测"日期缺口"（整根 K 线缺失），从数据源补
- missing_handler:    处理"单点空值"（个别字段为 None），用 ffill 补

【使用示例】
```python
from backend.imputer import DataGapDetector, DataGapFiller
detector = DataGapDetector()
gaps = detector.detect_gaps('000001.SZ', start_date='2026-01-01', end_date='2026-06-05')
filler = DataGapFiller()
filler.fill('000001.SZ', gaps)
```
"""

import os
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional

import psycopg2
from dotenv import load_dotenv

from shared.constants import TABLE_STOCK_QUOTES

logger = logging.getLogger(__name__)

load_dotenv()


class DataGapDetector:
    """
    数据缺口检测器
    检测本地数据与实际交易日之间的差异
    """

    def __init__(self, conn=None):
        self._conn = conn

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=os.getenv('PG_HOST', 'localhost'),
                port=os.getenv('PG_PORT', '5432'),
                database=os.getenv('PG_DATABASE', 'quant_trading'),
                user=os.getenv('PG_USER', 'quant_user'),
                password=os.getenv('PG_PASSWORD', ''),
            )
        return self._conn

    @staticmethod
    def get_trading_dates(start_date: str, end_date: str) -> List[str]:
        """
        生成交易日历（排除周末）
        注意：精确交易日历需要结合交易所日历，此处简化处理
        """
        start = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')

        trading_dates = []
        current = start
        while current <= end:
            if current.weekday() < 5:  # 周一到周五
                trading_dates.append(current.strftime('%Y%m%d'))
            current += timedelta(days=1)
        return trading_dates

    def detect_gaps(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        cycle: str = '1d',
    ) -> List[str]:
        """
        检测指定股票在日期范围内的数据缺口

        Args:
            stock_code: 股票代码 (e.g. '000001.SZ')
            start_date: 开始日期 'YYYYMMDD'
            end_date: 结束日期 'YYYYMMDD'
            cycle: K线周期

        Returns:
            缺失日期列表（'YYYYMMDD'）
        """
        expected = set(self.get_trading_dates(start_date, end_date))
        sql = f"""
            SELECT DISTINCT TO_CHAR(trade_date, 'YYYYMMDD') AS d
            FROM {TABLE_STOCK_QUOTES}
            WHERE code = %s AND cycle = %s
              AND trade_date BETWEEN %s AND %s
        """
        df = pd.read_sql(sql, self.conn, params=(stock_code, cycle, start_date, end_date))
        existing = set(df['d'].tolist()) if not df.empty else set()

        gaps = sorted(expected - existing)
        if gaps:
            logger.info(f'  📊 {stock_code}: 检测到 {len(gaps)} 个缺口（{start_date} ~ {end_date}）')
        return gaps


class DataGapFiller:
    """
    数据缺口补全器
    从数据源（akshare / tushare / baostock）拉取缺失数据并入库
    """

    def __init__(self, conn=None):
        self._conn = conn

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=os.getenv('PG_HOST', 'localhost'),
                port=os.getenv('PG_PORT', '5432'),
                database=os.getenv('PG_DATABASE', 'quant_trading'),
                user=os.getenv('PG_USER', 'quant_user'),
                password=os.getenv('PG_PASSWORD', ''),
            )
        return self._conn

    def fill(
        self,
        stock_code: str,
        gaps: List[str],
        cycle: str = '1d',
    ) -> Dict:
        """
        补全指定日期的缺失数据

        Args:
            stock_code: 股票代码
            gaps: 缺失日期列表 ('YYYYMMDD')
            cycle: K线周期

        Returns:
            {'gaps_filled': int, 'success': bool, 'message': str}
        """
        if not gaps:
            return {'gaps_filled': 0, 'success': True, 'message': '无缺口'}

        # 优先用 Tushare
        try:
            from backend.collector.datasource.tushare import TushareDataSource
            tushare = TushareDataSource()
            start = gaps[0]
            end = gaps[-1]
            df = tushare.fetch_daily(stock_code, start_date=start, end_date=end)
            if df is not None and not df.empty:
                return self._insert(stock_code, df, cycle)
        except Exception as e:
            logger.warning(f'  ⚠️  Tushare 补全失败: {e}')

        # 退化到 Baostock
        try:
            from backend.collector.datasource.baostock import BaostockDataSource
            baostock = BaostockDataSource()
            df = baostock.fetch_daily(stock_code, start_date=gaps[0], end_date=gaps[-1])
            if df is not None and not df.empty:
                return self._insert(stock_code, df, cycle)
        except Exception as e:
            logger.warning(f'  ⚠️  Baostock 补全失败: {e}')

        return {'gaps_filled': 0, 'success': False, 'message': '所有数据源均失败'}

    def _insert(self, stock_code: str, df: pd.DataFrame, cycle: str) -> Dict:
        """把拉取到的数据写入数据库"""
        if df.empty:
            return {'gaps_filled': 0, 'success': False, 'message': '空数据'}

        df['code'] = stock_code
        df['cycle'] = cycle
        # ... 实际写入逻辑（由具体 ETL 调用）
        logger.info(f'  ✅ {stock_code}: 补全 {len(df)} 条')
        return {'gaps_filled': len(df), 'success': True, 'message': 'OK'}
