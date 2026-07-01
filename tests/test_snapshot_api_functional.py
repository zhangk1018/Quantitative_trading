"""
test_snapshot_api_functional.py - 快照 API 功能测试

依赖环境：本地 PostgreSQL + FastAPI 后端
运行前需加载 .env 环境变量

测试内容：
1. GET /api/snapshot/all - 全量快照
2. GET /api/snapshot/incremental?since=YYYY-MM-DD - 增量同步
3. 响应格式、字段完整性、错误处理
"""

import os
import sys
import json
import time
import subprocess
import signal
import unittest
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_BASE = "http://localhost:8000"


class TestSnapshotAPI(unittest.TestCase):
    """快照后端 API 功能测试"""

    @classmethod
    def setUpClass(cls):
        """启动后端服务"""
        env_path = os.path.join(BASE_DIR, '.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k] = v

        cls.server_process = None
        cls._start_server()

    @classmethod
    def _start_server(cls):
        """启动 FastAPI 服务"""
        main_py = os.path.join(
            BASE_DIR, 'backend', 'core', 'api', 'main.py'
        )
        try:
            cls.server_process = subprocess.Popen(
                [sys.executable, main_py],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ,
            )
            # 等待服务启动
            for i in range(30):
                time.sleep(1)
                try:
                    resp = urllib.request.urlopen(f"{API_BASE}/api/snapshot/all", timeout=3)
                    resp.close()
                    print(f"✅ 后端服务启动成功（尝试 {i+1} 次）")
                    return
                except (urllib.error.URLError, ConnectionRefusedError):
                    continue
            raise RuntimeError("后端服务启动超时（30 秒）")
        except Exception as e:
            print(f"❌ 后端启动失败: {e}")
            if cls.server_process:
                cls.server_process.kill()
            raise

    @classmethod
    def tearDownClass(cls):
        """关闭后端服务"""
        if cls.server_process:
            cls.server_process.terminate()
            cls.server_process.wait(timeout=5)
            print("后端服务已关闭")

    def _get(self, path: str) -> dict:
        """GET 请求并返回 JSON"""
        url = f"{API_BASE}{path}"
        resp = urllib.request.urlopen(url, timeout=30)
        data = json.loads(resp.read().decode())
        return data

    # ============================================
    # 全量快照
    # ============================================

    def test_all_snapshot_status(self):
        """全量快照端点返回 200"""
        resp = self._get("/api/snapshot/all")
        self.assertEqual(resp.get('code'), 200)
        self.assertEqual(resp.get('message'), 'success')
        self.assertIn('data', resp)

    def test_all_snapshot_structure(self):
        """全量快照数据结构完整性"""
        resp = self._get("/api/snapshot/all")
        data = resp['data']
        # 顶层字段
        self.assertIn('latest_trade_date', data)
        self.assertIn('total', data)
        self.assertIn('stocks', data)
        self.assertIsInstance(data['total'], int)
        self.assertGreater(data['total'], 100)

        # 抽样验证第一个股票
        first = data['stocks'][0]
        self.assertIn('code', first)
        self.assertIn('name', first)
        self.assertIn('listed_board', first)
        self.assertIn('trade_date', first)
        self.assertIn('close', first)
        self.assertIn('indicators', first)
        self.assertIn('ohlcv', first)

    def test_all_snapshot_indicators(self):
        """全量快照指标字段完整性"""
        resp = self._get("/api/snapshot/all")
        first = resp['data']['stocks'][0]
        ind = first['indicators']
        # 均线
        self.assertIn('ma5', ind)
        self.assertIn('ma10', ind)
        self.assertIn('ma20', ind)
        self.assertIn('ma60', ind)
        self.assertIn('boll_mid', ind)
        # MACD
        self.assertIn('macd_dif', ind)
        self.assertIn('macd_dea', ind)
        self.assertIn('macd', ind)
        # 金叉死叉
        self.assertIn('is_macd_golden_cross', ind)
        self.assertIn('is_macd_dead_cross', ind)

    def test_all_snapshot_ohlcv_format(self):
        """OHLCV 列式二维数组格式"""
        resp = self._get("/api/snapshot/all")
        first = resp['data']['stocks'][0]
        ohlcv = first['ohlcv']
        self.assertGreater(len(ohlcv), 0)
        for row in ohlcv:
            self.assertEqual(len(row), 6)
            self.assertIsInstance(row[0], (int, float))  # time
            self.assertIsInstance(row[1], (int, float))  # open
            self.assertIsInstance(row[2], (int, float))  # high
            self.assertIsInstance(row[3], (int, float))  # low
            self.assertIsInstance(row[4], (int, float))  # close
            self.assertIsInstance(row[5], (int, float))  # volume

    def test_all_snapshot_reasonable_total(self):
        """全量快照股票数合理（5000-5600）"""
        resp = self._get("/api/snapshot/all")
        total = resp['data']['total']
        self.assertGreaterEqual(total, 5000)
        self.assertLessEqual(total, 5600)

    def test_all_snapshot_response_time(self):
        """全量快照响应时间 ≤ 5s"""
        start = time.time()
        self._get("/api/snapshot/all")
        elapsed = time.time() - start
        self.assertLess(elapsed, 5, f"响应时间 {elapsed:.2f}s 超过 5s 阈值")

    # ============================================
    # 增量同步
    # ============================================

    def test_incremental_snapshot_structure(self):
        """增量同步数据结构"""
        resp = self._get("/api/snapshot/incremental?since=2026-06-20")
        self.assertEqual(resp.get('code'), 200)
        data = resp['data']
        self.assertIn('since', data)
        self.assertIn('latest_trade_date', data)
        self.assertIn('days', data)
        self.assertIn('stocks', data)
        self.assertIsInstance(data['days'], int)
        self.assertGreaterEqual(data['days'], 1)

    def test_incremental_snapshot_ohlcv_filter(self):
        """增量 OHLCV 只返回 since 之后的数据"""
        since = "2026-06-25"
        resp = self._get(f"/api/snapshot/incremental?since={since}")
        data = resp['data']
        if data['stocks']:
            first = data['stocks'][0]
            ohlcv = first['ohlcv']
            if ohlcv:
                # time 应 >= since 的 Unix 时间戳
                since_ts = int(time.mktime(time.strptime(since, "%Y-%m-%d")))
                for row in ohlcv:
                    self.assertGreaterEqual(row[0], since_ts)

    def test_incremental_empty_result(self):
        """since 在未来日期时返回空"""
        resp = self._get("/api/snapshot/incremental?since=2099-12-31")
        self.assertEqual(resp.get('code'), 200)
        data = resp['data']
        self.assertEqual(data['days'], 0)
        self.assertEqual(data['stocks'], [])

    def test_incremental_invalid_date(self):
        """非法日期格式返回 400"""
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/snapshot/incremental?since=not-a-date")
        self.assertEqual(ctx.exception.code, 400)

    def test_incremental_missing_param(self):
        """缺少 since 参数返回 422"""
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/snapshot/incremental")
        self.assertEqual(ctx.exception.code, 422)


if __name__ == '__main__':
    unittest.main(verbosity=2)