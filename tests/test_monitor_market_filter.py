#!/usr/bin/env python3
"""
监控任务链 market 过滤（方案A）单元测试。

背景：A股/港股/美股 ETL 将日线写入同一张 stock_quotes，仅靠 market 列区分。
修复前 monitor._check_task_from_db 的动态基准未按 market 过滤，宽表等任务会因
混入其他市场股票数而误报「数据不足」partial。本测试验证：
1. count 查询与动态基准均按 market 过滤（SQL 含 `market = %s`，参数为 market 值）
2. 覆盖率 100% 时返回 success（消除误报）
3. 港美股（market != 'cn'）忽略 A 股体量固定阈值 TASK_MIN_COUNTS，退化为自身动态基准
"""
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from core.api.router import monitor  # noqa: E402


class TestMarketFilter(unittest.TestCase):
    """_check_task_from_db 的 market 过滤与覆盖率计算"""

    def _run(self, task_key, market, dyn_ret, count_ret, config_min_value=None):
        calls = []

        def fake_scalar(sql, params=None, conn=None):
            calls.append((sql, tuple(params) if params else None))
            if "MAX(" in sql:
                return "2026-09-03"
            if sql.startswith("SELECT COUNT(DISTINCT code) FROM stock_quotes"):
                return dyn_ret
            if "COUNT(*)" in sql:
                return count_ret
            return 0

        with patch.object(monitor, "_query_one", return_value=None), \
             patch.object(monitor, "_query_scalar", side_effect=fake_scalar), \
             patch.object(monitor, "_get_last_trade_date", return_value="2026-09-03"):
            result = monitor._check_task_from_db(task_key, market=market)
        return result, calls

    def test_snapshot_cn_use_market_filter_and_success(self):
        """A股宽表：动态基准与 count 均按 market='cn' 过滤，覆盖 100% → success。"""
        result, calls = self._run("snapshot_sync", "cn", dyn_ret=5209, count_ret=5209)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data_count"], 5209)
        # 动态基准查询必须带 market 过滤
        dyn = [c for c in calls if c[0].startswith("SELECT COUNT(DISTINCT code) FROM stock_quotes")]
        self.assertEqual(len(dyn), 1)
        self.assertIn("market = %s", dyn[0][0])
        self.assertIn("cn", dyn[0][1])
        # count 查询必须带 market 过滤
        cnt = [c for c in calls if c[0].startswith("SELECT COUNT(*) FROM stock_daily_snapshot")]
        self.assertEqual(len(cnt), 1)
        self.assertIn("market = %s", cnt[0][0])
        self.assertIn("cn", cnt[0][1])

    def test_snapshot_hk_uses_hk_dynamic_baseline(self):
        """港股宽表：用自身动态基准（1766），而非 A 股固定 4000 阈值。"""
        result, calls = self._run("snapshot_sync", "hk", dyn_ret=1766, count_ret=1766)
        self.assertEqual(result["status"], "success")
        dyn = [c for c in calls if c[0].startswith("SELECT COUNT(DISTINCT code) FROM stock_quotes")]
        self.assertEqual(len(dyn), 1)
        self.assertIn("hk", dyn[0][1])

    def test_signal_hk_ignores_config_min(self):
        """港美股信号：忽略 TASK_MIN_COUNTS['signal_precompute']=100，退化为自身动态基准。"""
        # count=1766 == dynamic_min 1766 → 覆盖率100% success
        result, calls = self._run("signal_precompute", "hk", dyn_ret=1766, count_ret=1766)
        self.assertEqual(result["status"], "success")
        # 确认动态基准查询带 market='hk'
        dyn = [c for c in calls if c[0].startswith("SELECT COUNT(DISTINCT code) FROM stock_quotes")]
        self.assertEqual(len(dyn), 1)
        self.assertIn("hk", dyn[0][1])

    def test_latest_date_uses_market_filter(self):
        """无今日日志回退时：latest_date(MAX) 查询必须按 market 过滤，避免被 A 股最新日期污染。"""
        _, calls = self._run("daily_basic_sync", "hk", dyn_ret=2205, count_ret=3)
        max_q = [c for c in calls if "MAX(" in c[0]]
        self.assertEqual(len(max_q), 1)
        self.assertIn("market = %s", max_q[0][0])
        self.assertIn("hk", max_q[0][1])

    def test_lagging_market_reports_stale_not_empty(self):
        """港股数据滞后（自身最新日期 < 期望交易日）→ 报「数据未更新」，而非误报「今日无数据」。"""
        calls = []

        def fake_scalar(sql, params=None, conn=None):
            calls.append((sql, tuple(params) if params else None))
            if "MAX(" in sql:
                return "2026-09-02"  # 港股自身最新日期（滞后一天）
            return 0

        with patch.object(monitor, "_query_one", return_value=None), \
             patch.object(monitor, "_query_scalar", side_effect=fake_scalar), \
             patch.object(monitor, "_get_last_trade_date", return_value="2026-09-03"):
            result = monitor._check_task_from_db("daily_basic_sync", market="hk")
        self.assertEqual(result["status"], "pending")
        self.assertIn("数据未更新", result["message"])

    def test_non_market_table_no_filter(self):
        """stock_list 不在 _MARKET_FILTER_TABLES，latest_date 查询不应加 market 过滤。"""
        _, calls = self._run("stock_list_sync", "cn", dyn_ret=0, count_ret=0)
        max_q = [c for c in calls if "MAX(" in c[0]]
        self.assertEqual(len(max_q), 1)
        self.assertNotIn("market = %s", max_q[0][0])


class TestGetMarketsQuerySplit(unittest.TestCase):
    """get_markets 查询拆分：避免 MAX + COUNT(DISTINCT code) 合并导致的全表 hash 聚合超时（实测 43s）。"""

    def test_quotes_query_split(self):
        """校验 stock_quotes 拆分为 MAX 与按日 COUNT 两条查询，且不再出现合并查询。"""
        from datetime import date
        monitor._cache.clear()
        executes = []
        d = date(2026, 9, 3)
        # cn: MAX, COUNT, basic, ind_total, ind_ma5_null, ind_macd_null; hk: MAX, COUNT, basic; us: MAX, COUNT, basic
        fetches = iter([
            (d,), (5209,), (5235,), (1189774,), (154223,), (152123,),
            (d,), (2205,), (2798,),
            (d,), (186,), (211,),
        ])

        class FakeCur:
            def execute(self, sql, params=None):
                executes.append((sql, params))
            def fetchone(self):
                return next(fetches)
            def close(self):
                pass

        class FakeConn:
            def cursor(self):
                return FakeCur()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        with patch.object(monitor, "_get_db_conn", return_value=FakeConn()), \
             patch.object(monitor, "tail_alerts", return_value=[]):
            resp = monitor.get_markets()

        # 不再出现「MAX + COUNT(DISTINCT code)」合并的全表聚合查询
        for sql, _ in executes:
            self.assertFalse("MAX(" in sql and "COUNT(DISTINCT code)" in sql,
                             f"合并查询仍存在: {sql}")
        # 存在 3 条按日期过滤的 COUNT(DISTINCT code)
        cnt_sqls = [s for s, _ in executes if s.startswith("SELECT COUNT(DISTINCT code) FROM stock_quotes")]
        self.assertEqual(len(cnt_sqls), 3)
        for s in cnt_sqls:
            self.assertIn("trade_date=%s", s.replace(" ", ""))
        # 返回三市场且字段齐全
        markets = resp.data["markets"]
        self.assertEqual([m["market"] for m in markets], ["cn", "hk", "us"])
        self.assertEqual(markets[0]["quotes_latest"], "2026-09-03")
        self.assertEqual(markets[0]["quotes_covered"], 5209)


class TestRunningStaleDetection(unittest.TestCase):
    """running 僵死检测：task_run_log 残留 running 超时自动降级为疑似中断。"""

    def test_is_running_stale_basic(self):
        """超阈值 → True；未超 → False；None → False；字符串入参也支持。"""
        from datetime import timedelta
        now = monitor._now_beijing()
        self.assertTrue(monitor._is_running_stale(now - timedelta(hours=5)))
        self.assertFalse(monitor._is_running_stale(now - timedelta(minutes=30)))
        self.assertFalse(monitor._is_running_stale(None))
        stale_str = (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
        self.assertTrue(monitor._is_running_stale(stale_str))

    def test_market_chain_running_stale_downgrades(self):
        """get_market_chain：running 超时（父进程已死）→ 降级 failed 疑似中断。"""
        from datetime import timedelta
        stale = monitor._now_beijing() - timedelta(hours=5)
        # 注意：get_market_chain 用默认游标，fetchall 返回元组（非 dict）
        rows = [
            ("hk:日线清洗", "running", None, "2026-09-04", stale),
        ]
        with patch.object(monitor, "_get_db_conn") as mock_conn, \
             patch.object(monitor, "_check_task_from_db",
                          return_value={"status": "pending", "message": "", "data_date": None, "data_count": None}):
            mock_conn.return_value.cursor.return_value.fetchall.return_value = rows
            resp = monitor.get_market_chain(market="hk")
        tasks = {t["name"]: t for t in resp.data["tasks"]}
        self.assertEqual(tasks["日线清洗"]["status"], "failed")
        self.assertIn("疑似中断", tasks["日线清洗"]["message"])
        self.assertEqual(resp.data["overall"], "failed")

    def test_market_chain_running_recent_keeps_running(self):
        """get_market_chain：running 未超时（进程正常执行中）→ 仍显示 running。"""
        from datetime import timedelta
        fresh = monitor._now_beijing() - timedelta(minutes=10)
        rows = [
            ("hk:基本面", "running", None, "2026-09-04", fresh),
        ]
        with patch.object(monitor, "_get_db_conn") as mock_conn, \
             patch.object(monitor, "_check_task_from_db",
                          return_value={"status": "pending", "message": "", "data_date": None, "data_count": None}):
            mock_conn.return_value.cursor.return_value.fetchall.return_value = rows
            resp = monitor.get_market_chain(market="hk")
        tasks = {t["name"]: t for t in resp.data["tasks"]}
        self.assertEqual(tasks["基本面"]["status"], "running")
        self.assertEqual(resp.data["overall"], "running")

    def test_check_task_from_db_running_stale_downgrades(self):
        """_check_task_from_db：今日 running 记录超时 → 降级 failed 疑似中断。"""
        from datetime import timedelta
        stale = monitor._now_beijing() - timedelta(hours=5)
        log = {"status": "running", "start_time": stale, "data_date": "2026-09-04",
               "end_time": None, "rows_affected": None, "error_message": None}
        with patch.object(monitor, "_query_one", return_value=log), \
             patch.object(monitor, "_get_last_trade_date", return_value="2026-09-03"):
            result = monitor._check_task_from_db("daily_basic_sync", market="hk")
        self.assertEqual(result["status"], "failed")
        self.assertIn("疑似中断", result["message"])


if __name__ == "__main__":
    unittest.main()