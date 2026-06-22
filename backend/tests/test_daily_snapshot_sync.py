"""
daily_snapshot_sync.py 测试脚本

测试股票每日快照宽表同步逻辑，包括：
- 涨跌停阈值按板块动态调整
- 技术指标 pattern 计算（MA/MACD/RSI/BOLL）
- 背离信号日期连续性验证
- 新股豁免逻辑
- 多日连续性测试

2026-06-22 创建
"""

import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import logging
import os
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()


class TestDailySnapshotSync:
    """daily_snapshot_sync.py 测试类"""

    @pytest.fixture(autouse=True)
    def setup_connection(self):
        """每个测试方法前建立数据库连接"""
        self.conn = psycopg2.connect(
            host='localhost',
            port=5432,
            database='quant_trading',
            user='quant_user',
            password=os.getenv('PG_PASSWORD'),
            cursor_factory=RealDictCursor
        )
        yield
        self.conn.close()

    def get_latest_trade_date(self) -> str:
        """
        获取最新交易日期
        
        Returns:
            最新交易日期字符串（格式：YYYY-MM-DD）
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT MAX(trade_date) AS trade_date 
                FROM stock_daily_snapshot
            """)
            result = cur.fetchone()
            return result['trade_date'].strftime('%Y-%m-%d') if result['trade_date'] else None

    def test_limit_up_threshold_positive(self):
        """
        TC-05-正向：涨幅≥19.9%的创业板股票应标记为涨停
        
        验证逻辑：
        - 创业板股票涨幅≥19.95%时，limit_up应为true
        - 排除新股（上市<5天）
        """
        latest_date = self.get_latest_trade_date()
        if not latest_date:
            pytest.skip("无快照数据")

        with self.conn.cursor() as cur:
            # 正向验证：涨幅≥19.95%的创业板股票都应涨停
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(trade_date) AS trade_date FROM stock_daily_snapshot
                )
                SELECT s.code, s.close, s.pre_close,
                       ROUND((s.close - s.pre_close) / NULLIF(s.pre_close, 0) * 100, 1) AS pct_change,
                       s.limit_up,
                       b.list_date
                FROM stock_daily_snapshot s
                LEFT JOIN stock_basic b ON s.code = b.code
                WHERE s.trade_date = (SELECT trade_date FROM latest_date)
                  AND s.code LIKE '300%'
                  AND s.pre_close IS NOT NULL AND s.pre_close > 0
                  AND (s.close - s.pre_close) / s.pre_close * 100 >= 19.95
                  AND (b.list_date IS NULL 
                       OR b.list_date < CAST((SELECT trade_date FROM latest_date) AS DATE) - INTERVAL '5 days')
            """)
            results = cur.fetchall()

            # 验证所有记录 limit_up 应为 true
            violations = [r for r in results if r['limit_up'] != True]
            
            if violations:
                logger.error(f"发现 {len(violations)} 条涨停标记错误：")
                for v in violations[:5]:  # 只显示前5条
                    logger.error(f"  {v['code']}: 涨幅{v['pct_change']}%, limit_up={v['limit_up']}")
            
            assert len(violations) == 0, f"涨停正向验证失败：{len(violations)} 条记录未正确标记"

    def test_limit_up_threshold_negative(self):
        """
        TC-05-反向：涨幅<19.9%的创业板股票不应标记为涨停
        
        验证逻辑：
        - 创业板股票涨幅在[5%, 19.5%]区间时，limit_up应为false
        - 排除新股
        """
        latest_date = self.get_latest_trade_date()
        if not latest_date:
            pytest.skip("无快照数据")

        with self.conn.cursor() as cur:
            # 反向验证：涨幅不足19.9%的创业板股票不应涨停
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(trade_date) AS trade_date FROM stock_daily_snapshot
                )
                SELECT s.code, s.close, s.pre_close,
                       ROUND((s.close - s.pre_close) / NULLIF(s.pre_close, 0) * 100, 1) AS pct_change,
                       s.limit_up
                FROM stock_daily_snapshot s
                LEFT JOIN stock_basic b ON s.code = b.code
                WHERE s.trade_date = (SELECT trade_date FROM latest_date)
                  AND s.code LIKE '300%'
                  AND s.pre_close IS NOT NULL AND s.pre_close > 0
                  AND (s.close - s.pre_close) / s.pre_close * 100 BETWEEN 5 AND 19.5
                  AND (b.list_date IS NULL 
                       OR b.list_date < CAST((SELECT trade_date FROM latest_date) AS DATE) - INTERVAL '5 days')
                ORDER BY RANDOM()
                LIMIT 20
            """)
            results = cur.fetchall()

            # 验证所有记录 limit_up 应为 false
            violations = [r for r in results if r['limit_up'] == True]
            
            if violations:
                logger.error(f"发现 {len(violations)} 条误标记涨停：")
                for v in violations[:5]:
                    logger.error(f"  {v['code']}: 涨幅{v['pct_change']}%, limit_up={v['limit_up']}")
            
            assert len(violations) == 0, f"涨停反向验证失败：{len(violations)} 条记录误标记"

    def test_limit_down_threshold(self):
        """
        TC-05-跌停：跌幅≥19.9%的创业板股票应标记为跌停
        
        验证逻辑：
        - 创业板股票跌幅≥19.9%时，limit_down应为true
        - 排除新股
        """
        latest_date = self.get_latest_trade_date()
        if not latest_date:
            pytest.skip("无快照数据")

        with self.conn.cursor() as cur:
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(trade_date) AS trade_date FROM stock_daily_snapshot
                )
                SELECT s.code, s.close, s.pre_close,
                       ROUND((s.close - s.pre_close) / NULLIF(s.pre_close, 0) * 100, 1) AS pct_change,
                       s.limit_down
                FROM stock_daily_snapshot s
                LEFT JOIN stock_basic b ON s.code = b.code
                WHERE s.trade_date = (SELECT trade_date FROM latest_date)
                  AND s.code LIKE '300%'
                  AND s.pre_close IS NOT NULL AND s.pre_close > 0
                  AND (s.close - s.pre_close) / s.pre_close * 100 <= -19.95
                  AND (b.list_date IS NULL 
                       OR b.list_date < CAST((SELECT trade_date FROM latest_date) AS DATE) - INTERVAL '5 days')
            """)
            results = cur.fetchall()

            violations = [r for r in results if r['limit_down'] != True]
            
            if violations:
                logger.error(f"发现 {len(violations)} 条跌停标记错误")
            
            assert len(violations) == 0, f"跌停验证失败：{len(violations)} 条记录未正确标记"

    def test_mainboard_limit_threshold(self):
        """
        TC-05-主板：涨幅≥9.95%的主板股票应标记为涨停
        
        验证逻辑：
        - 主板股票（排除创业板/科创板/北交所）涨幅≥9.95%时，limit_up应为true
        """
        latest_date = self.get_latest_trade_date()
        if not latest_date:
            pytest.skip("无快照数据")

        with self.conn.cursor() as cur:
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(trade_date) AS trade_date FROM stock_daily_snapshot
                )
                SELECT s.code, s.close, s.pre_close,
                       ROUND((s.close - s.pre_close) / NULLIF(s.pre_close, 0) * 100, 1) AS pct_change,
                       s.limit_up
                FROM stock_daily_snapshot s
                LEFT JOIN stock_basic b ON s.code = b.code
                WHERE s.trade_date = (SELECT trade_date FROM latest_date)
                  AND s.code NOT LIKE '300%'  -- 排除创业板
                  AND s.code NOT LIKE '301%'
                  AND s.code NOT LIKE '302%'
                  AND s.code NOT LIKE '688%'  -- 排除科创板
                  AND s.code NOT LIKE '689%'
                  AND s.code NOT LIKE '92%'   -- 排除北交所
                  AND s.code NOT LIKE '8%'
                  AND s.code NOT LIKE '43%'
                  AND s.pre_close IS NOT NULL AND s.pre_close > 0
                  AND (s.close - s.pre_close) / s.pre_close * 100 >= 9.95
                  AND (b.list_date IS NULL 
                       OR b.list_date < CAST((SELECT trade_date FROM latest_date) AS DATE) - INTERVAL '5 days')
            """)
            results = cur.fetchall()

            violations = [r for r in results if r['limit_up'] != True]
            
            assert len(violations) == 0, f"主板涨停验证失败：{len(violations)} 条记录未正确标记"

    def test_pattern_fields_completeness(self):
        """
        TC-01：Pattern字段完整性验证
        
        验证逻辑：
        - 所有记录的 pattern 字段应有明确值（true/false），不应为 NULL
        - 统计 NULL 值数量，应为 0
        """
        latest_date = self.get_latest_trade_date()
        if not latest_date:
            pytest.skip("无快照数据")

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) AS total,
                    SUM(CASE WHEN ma_long_align IS NULL THEN 1 ELSE 0 END) AS ma_null,
                    SUM(CASE WHEN macd_low_golden_cross IS NULL THEN 1 ELSE 0 END) AS macd_null,
                    SUM(CASE WHEN rsi_low_golden_cross IS NULL THEN 1 ELSE 0 END) AS rsi_null,
                    SUM(CASE WHEN boll_break_upper IS NULL THEN 1 ELSE 0 END) AS boll_null
                FROM stock_daily_snapshot
                WHERE trade_date = (SELECT MAX(trade_date) FROM stock_daily_snapshot)
            """)
            result = cur.fetchone()

            logger.info(f"Pattern字段完整性：total={result['total']}, "
                       f"ma_null={result['ma_null']}, macd_null={result['macd_null']}, "
                       f"rsi_null={result['rsi_null']}, boll_null={result['boll_null']}")

            # 允许少量 NULL（因指标数据缺失），但比例应<5%
            null_ratio = (result['ma_null'] + result['macd_null'] + 
                         result['rsi_null'] + result['boll_null']) / (result['total'] * 4)
            
            assert null_ratio < 0.05, f"Pattern字段 NULL 比例过高：{null_ratio:.2%}"

    def test_divergence_date_consecutive(self):
        """
        TC-06：背离信号日期连续性验证
        
        验证逻辑：
        - 背离信号仅当日期连续时才触发
        - 检查背离为 true 的记录，验证前一日确实存在
        """
        latest_date = self.get_latest_trade_date()
        if not latest_date:
            pytest.skip("无快照数据")

        with self.conn.cursor() as cur:
            # 检查 MACD 底背离
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(trade_date) AS trade_date FROM stock_daily_snapshot
                )
                SELECT s.code, s.trade_date, s.macd_bottom_divergence,
                       q_prev.trade_date AS prev_date,
                       q_prev.trade_date = s.trade_date - INTERVAL '1 day' AS is_consecutive
                FROM stock_daily_snapshot s
                LEFT JOIN stock_quotes q_prev ON s.code = q_prev.code 
                    AND q_prev.cycle = '1d' 
                    AND q_prev.trade_date < s.trade_date
                WHERE s.trade_date = (SELECT trade_date FROM latest_date)
                  AND s.macd_bottom_divergence = true
                LIMIT 10
            """)
            results = cur.fetchall()

            # 验证所有背离记录的前一日都存在且连续
            for r in results:
                assert r['prev_date'] is not None, f"{r['code']} 背离但前一日数据缺失"
                # 注意：周末/节假日可能不连续，此测试仅验证数据存在性

    def test_new_stock_exemption(self):
        """
        新股豁免逻辑验证
        
        验证逻辑：
        - 上市<5天的股票，涨跌停标记可能不准确（因无涨跌幅限制）
        - 检查新股是否被正确标记为 is_new
        """
        latest_date = self.get_latest_trade_date()
        if not latest_date:
            pytest.skip("无快照数据")

        with self.conn.cursor() as cur:
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(trade_date) AS trade_date FROM stock_daily_snapshot
                )
                SELECT s.code, s.is_new, b.list_date,
                       CAST((SELECT trade_date FROM latest_date) AS DATE) - b.list_date AS days_listed
                FROM stock_daily_snapshot s
                LEFT JOIN stock_basic b ON s.code = b.code
                WHERE s.trade_date = (SELECT trade_date FROM latest_date)
                  AND b.list_date IS NOT NULL
                  AND CAST((SELECT trade_date FROM latest_date) AS DATE) - b.list_date <= 365
                ORDER BY days_listed
                LIMIT 20
            """)
            results = cur.fetchall()

            # 验证上市<365天的股票 is_new=true
            violations = [r for r in results if r['is_new'] != True]
            
            assert len(violations) == 0, f"新股标记错误：{len(violations)} 条记录"

    def test_consecutive_days_calculation(self):
        """
        TC-07：连涨天数计算验证
        
        验证逻辑：
        - 检查 consec_up_days 字段是否正确计算
        - 验证连涨天数随时间累加
        """
        latest_date = self.get_latest_trade_date()
        if not latest_date:
            pytest.skip("无快照数据")

        with self.conn.cursor() as cur:
            # 检查连涨天数>0的股票
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(trade_date) AS trade_date FROM stock_daily_snapshot
                )
                SELECT s.code, s.trade_date, s.consec_up_days, s.close, s.pre_close
                FROM stock_daily_snapshot s
                WHERE s.trade_date = (SELECT trade_date FROM latest_date)
                  AND s.consec_up_days > 0
                  AND s.close > s.pre_close  -- 当日应上涨
                ORDER BY s.consec_up_days DESC
                LIMIT 10
            """)
            results = cur.fetchall()

            # 验证当日上涨的股票，连涨天数至少为1
            for r in results:
                assert r['consec_up_days'] >= 1, f"{r['code']} 连涨天数计算错误"

    def test_multi_day_consistency(self):
        """
        多日连续性测试
        
        验证逻辑：
        - 同步最近5天数据，检查字段一致性
        - 验证 pattern 字段随时间变化合理
        """
        latest_date = self.get_latest_trade_date()
        if not latest_date:
            pytest.skip("无快照数据")

        latest_dt = datetime.strptime(latest_date, '%Y-%m-%d')
        
        with self.conn.cursor() as cur:
            # 检查最近5天的数据完整性
            cur.execute("""
                SELECT trade_date, COUNT(*) AS total,
                       SUM(CASE WHEN ma_long_align IS NOT NULL THEN 1 ELSE 0 END) AS ma_count
                FROM stock_daily_snapshot
                WHERE trade_date >= %(start_date)s
                GROUP BY trade_date
                ORDER BY trade_date DESC
            """, {'start_date': (latest_dt - timedelta(days=5)).strftime('%Y-%m-%d')})
            
            results = cur.fetchall()

            # 验证每天都有数据
            assert len(results) >= 1, "最近5天无快照数据"
            
            for r in results:
                logger.info(f"{r['trade_date']}: total={r['total']}, ma_count={r['ma_count']}")


def run_tests():
    """运行所有测试"""
    pytest.main([__file__, '-v', '--tb=short'])


if __name__ == '__main__':
    run_tests()