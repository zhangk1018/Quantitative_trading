"""
系统状态及数据监控服务

提供系统健康检查、数据完整性验证、监控指标收集等功能
"""

import os
import sys
import psycopg2
from psycopg2 import OperationalError
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SystemMonitor:
    """系统状态监控器"""
    
    def __init__(self, db_config: Dict[str, str]):
        """
        初始化系统监控器
        
        Args:
            db_config: 数据库配置 {host, port, database, user, password}
        """
        self.db_config = db_config
        self.conn = None
    
    def connect(self) -> bool:
        """建立数据库连接"""
        try:
            self.conn = psycopg2.connect(
                host=self.db_config.get('host', 'localhost'),
                port=self.db_config.get('port', '5432'),
                database=self.db_config.get('database', 'quant_trading'),
                user=self.db_config.get('user', 'quant_user'),
                password=self.db_config.get('password')
            )
            # 自动提交模式，避免单条查询失败后事务进入 aborted 状态
            self.conn.autocommit = True
            logger.info("数据库连接成功")
            return True
        except OperationalError as e:
            logger.error(f"数据库连接失败：{e}")
            return False
    
    def disconnect(self):
        """断开数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")
    
    def check_database_status(self) -> Dict[str, Any]:
        """检查数据库状态"""
        result = {
            "status": "unknown",
            "connected": False,
            "tables": {},
            "error": None
        }
        
        try:
            if not self.conn or self.conn.closed:
                if not self.connect():
                    result["status"] = "disconnected"
                    result["error"] = "无法连接数据库"
                    return result
            
            result["connected"] = True
            cursor = self.conn.cursor()
            
            # 检查关键表的数据量（仅日级数据相关表）
            tables_to_check = [
                ('stock_basic', '股票基础信息'),
                ('stock_quotes', '股票行情数据'),
                ('stock_indicators', '技术指标'),
                ('stock_adj_factor', '复权因子'),
                ('stock_daily_snapshot', '每日快照宽表'),
                ('stock_daily_basic', '日频基本面'),
                ('trade_signals', '交易信号')
            ]

            for table, description in tables_to_check:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    result["tables"][table] = {
                        "description": description,
                        "row_count": count,
                        "status": "normal" if count > 0 else "empty"
                    }
                except Exception as e:
                    result["tables"][table] = {
                        "description": description,
                        "row_count": 0,
                        "status": "error",
                        "error": str(e)
                    }

            # stock_quotes 按周期统计（仅关注日线）
            try:
                cursor.execute("""
                    SELECT cycle, COUNT(*) as cnt
                    FROM stock_quotes
                    GROUP BY cycle
                    ORDER BY cycle
                """)
                cycle_counts = {row[0]: row[1] for row in cursor.fetchall()}
                result["cycle_counts"] = cycle_counts
            except Exception as e:
                result["cycle_counts"] = {}
                logger.error(f"周期统计失败：{e}")

            # 统一获取当前日期，供后续 freshness 计算使用
            today = datetime.now().date()

            # 检查最新数据日期（日线）
            cursor.execute("""
                SELECT MAX(trade_date)
                FROM stock_quotes
                WHERE cycle = '1d'
            """)
            latest_date = cursor.fetchone()[0]
            if latest_date:
                result["latest_trade_date"] = str(latest_date)

                # 检查数据是否及时更新
                days_diff = (today - latest_date).days
                result["data_freshness"] = {
                    "days_since_update": days_diff,
                    "status": "fresh" if days_diff <= 1 else "stale"
                }

            cursor.close()
            result["status"] = "healthy" if result["connected"] else "unhealthy"
            
        except Exception as e:
            logger.error(f"数据库状态检查失败：{e}")
            result["status"] = "error"
            result["error"] = str(e)
        
        return result
    
    def check_data_coverage(self) -> Dict[str, Any]:
        """检查数据覆盖率（排除已退市和北交所股票，避免误告警）"""
        result = {
            "coverage_rate": 0,
            "covered_stocks": 0,
            "total_stocks": 0,
            "missing_stocks": 0,
            "excluded_stocks": 0,
            "latest_date": None
        }

        try:
            if not self.conn or self.conn.closed:
                return result

            cursor = self.conn.cursor()

            # 获取最新交易日
            cursor.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
            latest_date = cursor.fetchone()[0]
            if not latest_date:
                cursor.close()
                return result

            result["latest_date"] = str(latest_date)

            # 有效股票口径：未退市 + 非北交所（8/920/43 开头）
            # 注意：psycopg2 使用 %s 作为参数占位符，SQL 字面量中的 % 必须转义为 %%
            active_stock_filter = """
                delist_date IS NULL
                AND code NOT LIKE '8%%'
                AND code NOT LIKE '920%%'
                AND code NOT LIKE '43%%'
            """
            active_stock_filter_b = """
                b.delist_date IS NULL
                AND b.code NOT LIKE '8%%'
                AND b.code NOT LIKE '920%%'
                AND b.code NOT LIKE '43%%'
            """

            # 被排除的股票数（数据透明）
            cursor.execute(f"""
                SELECT COUNT(*) FROM stock_basic
                WHERE NOT ({active_stock_filter})
            """)
            result["excluded_stocks"] = cursor.fetchone()[0] or 0

            # 有效股票总数
            cursor.execute(f"""
                SELECT COUNT(*) FROM stock_basic
                WHERE {active_stock_filter}
            """)
            total = cursor.fetchone()[0] or 0
            result["total_stocks"] = total

            # 已覆盖股票数
            cursor.execute(f"""
                SELECT COUNT(DISTINCT q.code)
                FROM stock_quotes q
                WHERE q.cycle = '1d' AND q.trade_date = %s
                  AND EXISTS (
                    SELECT 1 FROM stock_basic b
                    WHERE b.code = q.code
                      AND {active_stock_filter_b}
                  )
            """, (latest_date,))
            covered = cursor.fetchone()[0] or 0
            result["covered_stocks"] = covered

            # 覆盖率
            result["coverage_rate"] = round(covered / total * 100, 2) if total > 0 else 0

            # 缺失股票数（在有效股票口径内）
            cursor.execute(f"""
                SELECT COUNT(*) FROM stock_basic b
                WHERE {active_stock_filter_b}
                  AND NOT EXISTS (
                    SELECT 1 FROM stock_quotes q
                    WHERE q.cycle = '1d' AND q.trade_date = %s
                      AND b.code = q.code
                  )
            """, (latest_date,))
            result["missing_stocks"] = cursor.fetchone()[0] or 0

            cursor.close()

        except Exception as e:
            logger.error(f"数据覆盖率检查失败：{e}")

        return result
    
    def check_daily_data_quality(self, latest_date: Optional[Any] = None) -> Dict[str, Any]:
        """日级数据质量审计（关键字段完整性、表间一致性）"""
        result = {
            "quotes_field_coverage": {},
            "snapshot_vs_quotes_diff": None,
            "indicators_coverage": None,
            "daily_basic_coverage": None,
            "status": "unknown"
        }

        try:
            if not self.conn or self.conn.closed:
                return result

            cursor = self.conn.cursor()

            # 若未传入最新交易日，自动查询
            if latest_date is None:
                cursor.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
                latest_date = cursor.fetchone()[0]

            if not latest_date:
                cursor.close()
                return result

            result["latest_date"] = str(latest_date)

            # 1. stock_quotes 日线关键字段非空率
            cursor.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN open IS NOT NULL THEN 1 ELSE 0 END) AS open_cnt,
                       SUM(CASE WHEN high IS NOT NULL THEN 1 ELSE 0 END) AS high_cnt,
                       SUM(CASE WHEN low IS NOT NULL THEN 1 ELSE 0 END) AS low_cnt,
                       SUM(CASE WHEN close IS NOT NULL THEN 1 ELSE 0 END) AS close_cnt,
                       SUM(CASE WHEN volume IS NOT NULL THEN 1 ELSE 0 END) AS volume_cnt
                FROM stock_quotes
                WHERE cycle = '1d' AND trade_date = %s
            """, (latest_date,))
            row = cursor.fetchone()
            total = row[0] or 0
            if total > 0:
                result["quotes_field_coverage"] = {
                    "total": total,
                    "open": round(row[1] / total * 100, 2),
                    "high": round(row[2] / total * 100, 2),
                    "low": round(row[3] / total * 100, 2),
                    "close": round(row[4] / total * 100, 2),
                    "volume": round(row[5] / total * 100, 2)
                }

            # 2. stock_daily_snapshot 与 stock_quotes 日线记录数差异
            cursor.execute("""
                SELECT
                    (SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle = '1d' AND trade_date = %s) AS quotes_cnt,
                    (SELECT COUNT(*) FROM stock_daily_snapshot WHERE trade_date = %s) AS snapshot_cnt
            """, (latest_date, latest_date))
            row = cursor.fetchone()
            quotes_cnt, snapshot_cnt = row[0] or 0, row[1] or 0
            result["snapshot_vs_quotes_diff"] = {
                "quotes_stock_count": quotes_cnt,
                "snapshot_row_count": snapshot_cnt,
                "diff": quotes_cnt - snapshot_cnt
            }

            # 3. indicators 与 daily_basic 覆盖
            cursor.execute("""
                SELECT COUNT(DISTINCT code) FROM stock_indicators
                WHERE cycle = '1d' AND trade_date = %s
            """, (latest_date,))
            result["indicators_coverage"] = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM stock_daily_basic WHERE trade_date = %s
            """, (latest_date,))
            result["daily_basic_coverage"] = cursor.fetchone()[0] or 0

            cursor.close()

            # 判定质量状态：字段完整性均 >=95% 且 snapshot 与 quotes 差异 <=5 为 healthy
            field_cov = result["quotes_field_coverage"]
            all_fields_ok = all(v >= 95 for k, v in field_cov.items() if k != "total")
            snapshot_ok = abs(result["snapshot_vs_quotes_diff"]["diff"]) <= 5
            result["status"] = "healthy" if (all_fields_ok and snapshot_ok) else "warning"

        except Exception as e:
            logger.error(f"日级数据质量审计失败：{e}")
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def get_system_summary(self) -> Dict[str, Any]:
        """获取系统摘要信息"""
        latest_date = None
        try:
            if self.connect():
                cursor = self.conn.cursor()
                cursor.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
                latest_date = cursor.fetchone()[0]
                cursor.close()
        except Exception as e:
            logger.error(f"获取最新交易日失败：{e}")

        summary = {
            "timestamp": datetime.now().isoformat(),
            "database": self.check_database_status(),
            "coverage": self.check_data_coverage(),
            "daily_quality": self.check_daily_data_quality(latest_date)
        }

        # 计算整体健康度
        db_status = summary["database"]["status"]
        coverage_rate = summary["coverage"]["coverage_rate"]
        quality_status = summary["daily_quality"].get("status", "unknown")

        if db_status == "healthy" and coverage_rate > 95 and quality_status == "healthy":
            summary["overall_health"] = "excellent"
        elif db_status == "healthy" and coverage_rate > 90 and quality_status != "error":
            summary["overall_health"] = "good"
        elif db_status == "healthy":
            summary["overall_health"] = "fair"
        else:
            summary["overall_health"] = "poor"

        return summary


def main():
    """测试监控服务"""
    from dotenv import load_dotenv
    
    load_dotenv()
    
    db_config = {
        'host': os.getenv('PG_HOST', 'localhost'),
        'port': os.getenv('PG_PORT', '5432'),
        'database': os.getenv('PG_DATABASE', 'quant_trading'),
        'user': os.getenv('PG_USER', 'quant_user'),
        'password': os.getenv('PG_PASSWORD')
    }
    
    monitor = SystemMonitor(db_config)
    
    try:
        print("\n=== 系统状态检查 ===")
        db_status = monitor.check_database_status()
        print(f"数据库状态：{db_status['status']}")
        print(f"连接状态：{'已连接' if db_status['connected'] else '未连接'}")

        for table, info in db_status.get('tables', {}).items():
            print(f"  - {table}: {info['row_count']} 条记录 ({info['status']})")

        cycle_counts = db_status.get('cycle_counts', {})
        if cycle_counts:
            print("\n=== 行情周期分布 ===")
            for cycle, cnt in sorted(cycle_counts.items()):
                print(f"  - {cycle}: {cnt} 条记录")

        print(f"\n最新交易日：{db_status.get('latest_trade_date', 'N/A')}")
        print(f"日线新鲜度：{db_status.get('data_freshness', {}).get('status', 'N/A')} "
              f"({db_status.get('data_freshness', {}).get('days_since_update', 'N/A')} 天前)")

        print("\n=== 数据覆盖率检查 ===")
        coverage = monitor.check_data_coverage()
        print(f"最新交易日：{coverage.get('latest_date', 'N/A')}")
        print(f"有效股票总数（已剔除退市/北交所）：{coverage['total_stocks']}")
        print(f"已覆盖股票：{coverage['covered_stocks']}")
        print(f"覆盖率：{coverage['coverage_rate']}%")
        print(f"缺失股票：{coverage['missing_stocks']}")
        print(f"已排除股票（退市/北交所）：{coverage['excluded_stocks']}")

        print("\n=== 日级数据质量审计 ===")
        daily_quality = monitor.check_daily_data_quality()
        print(f"审计日期：{daily_quality.get('latest_date', 'N/A')}")
        print(f"质量状态：{daily_quality.get('status', 'N/A')}")

        field_cov = daily_quality.get('quotes_field_coverage', {})
        if field_cov:
            print(f"日线字段完整性（共 {field_cov.get('total', 0)} 条）：")
            for field in ['open', 'high', 'low', 'close', 'volume']:
                val = field_cov.get(field)
                if val is not None:
                    print(f"  - {field}: {val}%")

        snapshot_diff = daily_quality.get('snapshot_vs_quotes_diff')
        if snapshot_diff:
            print(f"行情表股票数：{snapshot_diff['quotes_stock_count']}")
            print(f"快照表记录数：{snapshot_diff['snapshot_row_count']}")
            print(f"差异：{snapshot_diff['diff']}")

        print(f"技术指标覆盖：{daily_quality.get('indicators_coverage', 'N/A')} 只")
        print(f"基本面覆盖：{daily_quality.get('daily_basic_coverage', 'N/A')} 条")

        if coverage['coverage_rate'] < 90:
            print(f"\n⚠️ 覆盖率 {coverage['coverage_rate']}% 低于 90%，缺失 {coverage['missing_stocks']} 只股票")

        print("\n=== 系统健康度 ===")
        summary = monitor.get_system_summary()
        print(f"整体健康度：{summary['overall_health']}")

    finally:
        monitor.disconnect()


if __name__ == "__main__":
    main()
