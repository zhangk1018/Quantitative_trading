#!/usr/bin/env python3
"""
日线数据导入 - 交易日判断逻辑单元测试
覆盖 import_daily_data.py 新增的 _is_trade_day / _get_last_trade_day 兜底逻辑
"""
import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from collector.etl.import_daily_data import DailyDataImporter


class FakeCursor:
    """模拟数据库游标（支持上下文管理器）"""

    def __init__(self, result):
        self._result = result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return self._result


class FakeConn:
    """模拟数据库连接（事务上下文）"""

    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor


def make_importer(cursor_result):
    """构造不连接真实数据源的 importer 实例"""
    importer = DailyDataImporter.__new__(DailyDataImporter)
    cursor = FakeCursor(cursor_result)
    importer.storage = MagicMock()
    importer.storage.transaction.return_value = FakeConn(cursor)
    return importer


class TestTradeDayLogic(unittest.TestCase):
    """_is_trade_day / _get_last_trade_day 逻辑测试"""

    def test_is_trade_day_weekend_from_calendar(self):
        """交易日历标记 2026-08-22（周六）休市 → 非交易日"""
        importer = make_importer((0,))
        self.assertIs(importer._is_trade_day('2026-08-22'), False)

    def test_is_trade_day_trade_day_from_calendar(self):
        """交易日历标记 2026-08-21（周五）开市 → 交易日"""
        importer = make_importer((1,))
        self.assertIs(importer._is_trade_day('2026-08-21'), True)

    def test_is_trade_day_fallback_weekend(self):
        """交易日历无记录时按周末兜底：周六非交易日"""
        importer = make_importer(None)
        self.assertIs(importer._is_trade_day('2026-08-22'), False)

    def test_is_trade_day_fallback_workday(self):
        """交易日历无记录时按周末兜底：周一视为交易日"""
        importer = make_importer(None)
        self.assertIs(importer._is_trade_day('2026-08-24'), True)

    def test_is_trade_day_exception_fallback(self):
        """交易日历查询异常时按周末兜底：周日非交易日"""
        importer = DailyDataImporter.__new__(DailyDataImporter)
        importer.storage = MagicMock()
        importer.storage.transaction.side_effect = RuntimeError('db down')
        self.assertIs(importer._is_trade_day('2026-08-23'), False)

    def test_get_last_trade_day_returns_calendar_date(self):
        """从交易日历取最近交易日：08-22 之前最近为 08-21"""
        importer = make_importer(('2026-08-21',))
        self.assertEqual(importer._get_last_trade_day('2026-08-22'), '2026-08-21')

    def test_get_last_trade_day_fallback(self):
        """交易日历无记录时返回原日期"""
        importer = make_importer(None)
        self.assertEqual(importer._get_last_trade_day('2026-08-22'), '2026-08-22')


if __name__ == '__main__':
    unittest.main()
