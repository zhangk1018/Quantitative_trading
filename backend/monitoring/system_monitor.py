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
            
            # 检查关键表的数据量
            tables_to_check = [
                ('stock_basic', '股票基础信息'),
                ('stock_quotes', '股票行情数据'),
                ('stock_indicators', '技术指标'),
                ('stock_adj_factor', '复权因子'),
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
            
            # 检查最新数据日期
            cursor.execute("""
                SELECT MAX(trade_date) 
                FROM stock_quotes 
                WHERE cycle = '1d'
            """)
            latest_date = cursor.fetchone()[0]
            if latest_date:
                result["latest_trade_date"] = str(latest_date)
                
                # 检查数据是否及时更新
                today = datetime.now().date()
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
        """检查数据覆盖率"""
        result = {
            "coverage_rate": 0,
            "covered_stocks": 0,
            "total_stocks": 0,
            "missing_stocks": 0,
            "latest_date": None
        }
        
        try:
            if not self.conn or self.conn.closed:
                return result
            
            cursor = self.conn.cursor()
            
            # 获取最新交易日
            cursor.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
            latest_date = cursor.fetchone()[0]
            if latest_date:
                result["latest_date"] = str(latest_date)
                
                # 计算覆盖率
                cursor.execute("""
                    SELECT COUNT(DISTINCT q.code)
                    FROM stock_quotes q
                    WHERE q.cycle = '1d' AND q.trade_date = %s
                      AND EXISTS (
                        SELECT 1 FROM stock_basic b
                        WHERE b.code = q.code
                      )
                """, (latest_date,))
                covered = cursor.fetchone()[0] or 0
                
                cursor.execute("SELECT COUNT(*) FROM stock_basic")
                total = cursor.fetchone()[0] or 0
                
                result["covered_stocks"] = covered
                result["total_stocks"] = total
                result["coverage_rate"] = round(covered / total * 100, 2) if total > 0 else 0
                
                # 计算缺失的股票数量
                cursor.execute("""
                    SELECT COUNT(*) FROM stock_basic b
                    WHERE NOT EXISTS (
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
    
    def get_system_summary(self) -> Dict[str, Any]:
        """获取系统摘要信息"""
        summary = {
            "timestamp": datetime.now().isoformat(),
            "database": self.check_database_status(),
            "coverage": self.check_data_coverage()
        }
        
        # 计算整体健康度
        db_status = summary["database"]["status"]
        coverage_rate = summary["coverage"]["coverage_rate"]
        
        if db_status == "healthy" and coverage_rate > 90:
            summary["overall_health"] = "excellent"
        elif db_status == "healthy" and coverage_rate > 50:
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
        
        print("\n=== 数据覆盖率检查 ===")
        coverage = monitor.check_data_coverage()
        print(f"最新交易日：{coverage.get('latest_date', 'N/A')}")
        print(f"覆盖率：{coverage['coverage_rate']}%")
        print(f"已覆盖股票：{coverage['covered_stocks']}")
        print(f"总股票数：{coverage['total_stocks']}")
        print(f"缺失股票：{coverage['missing_stocks']}")
        
        print("\n=== 系统健康度 ===")
        summary = monitor.get_system_summary()
        print(f"整体健康度：{summary['overall_health']}")
        
    finally:
        monitor.disconnect()


if __name__ == "__main__":
    main()
