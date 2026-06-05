"""
PostgreSQL 存储实现
"""
import logging
import pandas as pd
import psycopg2
from psycopg2 import OperationalError, IntegrityError
from typing import Optional, Dict, Any

from .base_storage import BaseStorage

logger = logging.getLogger(__name__)

class PostgreSQLStorage(BaseStorage):
    """PostgreSQL 存储实现"""

    def __init__(self, config: Dict[str, Any]):
        self.host = config.get('host', 'localhost')
        self.port = config.get('port', 5432)
        self.database = config.get('database', 'quant_trading')
        self.username = config.get('username', 'quant_user')
        self.password = config.get('password', 'quant_password')
        self.conn = None

    def init_tables(self):
        """初始化数据库表结构"""
        if not self.conn:
            logger.error("❌ 未连接数据库")
            return

        try:
            cursor = self.conn.cursor()

            # 创建股票基本信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_basic (
                    code VARCHAR(10) PRIMARY KEY,
                    name VARCHAR(50) NOT NULL,
                    exchange VARCHAR(20),
                    industry VARCHAR(100),
                    list_date DATE,
                    delist_date DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建行情数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_quotes (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(10) NOT NULL,
                    cycle VARCHAR(10) NOT NULL,
                    trade_date DATE NOT NULL,
                    open NUMERIC(10, 2),
                    high NUMERIC(10, 2),
                    low NUMERIC(10, 2),
                    close NUMERIC(10, 2),
                    volume BIGINT,
                    amount NUMERIC(18, 2),
                    adjust_type VARCHAR(10) DEFAULT 'qfq',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(code, cycle, trade_date)
                )
            """)

            # 创建技术指标表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_indicators (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(10) NOT NULL,
                    cycle VARCHAR(10) NOT NULL,
                    trade_date DATE NOT NULL,
                    ma5 NUMERIC(10, 2),
                    ma10 NUMERIC(10, 2),
                    ma20 NUMERIC(10, 2),
                    ma60 NUMERIC(10, 2),
                    macd NUMERIC(10, 4),
                    dif NUMERIC(10, 4),
                    dea NUMERIC(10, 4),
                    rsi6 NUMERIC(6, 2),
                    rsi12 NUMERIC(6, 2),
                    rsi24 NUMERIC(6, 2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(code, cycle, trade_date)
                )
            """)

            # 创建交易日历表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_calendar (
                    cal_date DATE PRIMARY KEY,
                    is_open INTEGER NOT NULL,
                    holiday_name VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建任务进度表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_progress (
                    id SERIAL PRIMARY KEY,
                    task_name VARCHAR(100) NOT NULL,
                    code VARCHAR(10),
                    status VARCHAR(20) DEFAULT 'pending',
                    progress INTEGER DEFAULT 0,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建任务指标表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_metrics (
                    id SERIAL PRIMARY KEY,
                    task VARCHAR(100) NOT NULL,
                    date DATE NOT NULL,
                    stocks_total INTEGER DEFAULT 0,
                    stocks_success INTEGER DEFAULT 0,
                    stocks_fail INTEGER DEFAULT 0,
                    status VARCHAR(20),
                    latency_sec NUMERIC(10, 2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_quotes_code_cycle ON stock_quotes(code, cycle)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_quotes_trade_date ON stock_quotes(trade_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_indicators_code_cycle ON stock_indicators(code, cycle)")

            self.conn.commit()
            cursor.close()

            logger.info("✅ 数据库表结构初始化完成")

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ 初始化表结构失败: {str(e)}")
            raise

    def connect(self) -> bool:
        """连接数据库（带 TCP keepalive，防止长时间空闲断开）"""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.username,
                password=self.password,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
                connect_timeout=10
            )
            logger.info(f"✅ PostgreSQL 连接成功: {self.host}:{self.port}/{self.database}")
            return True
        except OperationalError as e:
            logger.error(f"❌ PostgreSQL 连接失败: {str(e)}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.conn:
            try:
                self.conn.close()
                logger.info("✅ PostgreSQL 连接已断开")
            except Exception as e:
                logger.error(f"❌ 断开连接失败: {str(e)}")

    def save_quotes(self, df: pd.DataFrame, adjust_type: str = 'qfq') -> int:
        """保存行情数据"""
        if df.empty:
            return 0

        df = df.copy()
        df['adjust_type'] = adjust_type
        
        # 添加 trade_datetime 字段（非空字段）
        if 'trade_datetime' not in df.columns:
            df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta('15:00:00')
        
        try:
            cursor = self.conn.cursor()
            
            # 使用 COPY 命令批量插入
            from io import StringIO
            output = StringIO()
            df.to_csv(output, sep='\t', header=False, index=False)
            output.seek(0)
            
            cursor.copy_from(
                output,
                'stock_quotes',
                columns=['code', 'cycle', 'trade_date', 'open', 'high', 'low', 
                         'close', 'pre_close', 'volume', 'amount', 'adjust_type',
                         'trade_datetime'],
                sep='\t'
            )
            
            self.conn.commit()
            cursor.close()
            
            count = len(df)
            logger.debug(f"✅ 保存行情数据: {count} 条")
            return count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ 保存行情数据失败: {str(e)}")
            return 0

    def get_quotes(self, code: str, cycle: str = 'daily',
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None) -> pd.DataFrame:
        """获取行情数据"""
        # cycle 字段映射: daily -> 1d, weekly -> 1w, monthly -> 1m
        cycle_map = {'daily': '1d', '1d': '1d', 'day': '1d',
                     'weekly': '1w', '1w': '1w', 'week': '1w',
                     'monthly': '1m', '1m': '1m', 'month': '1m'}
        cycle = cycle_map.get(cycle.lower(), cycle)
        
        # 使用 psycopg2 原生 execute + fetch 而非 pd.read_sql(params=...)
        # 因为 pd.read_sql 带 params 参数在 psycopg2 下不兼容，返回空结果
        query = """
            SELECT code, cycle, trade_date, open, high, low, close, pre_close, volume, amount, adjust_type
            FROM stock_quotes
            WHERE code = %s AND cycle = %s
        """
        params = [code, cycle]

        if start_date:
            query += " AND trade_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= %s"
            params.append(end_date)

        query += " ORDER BY trade_date"

        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            colnames = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            cursor.close()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows, columns=colnames)
        except Exception as e:
            logger.error(f"❌ 获取行情数据失败: {str(e)}")
            return pd.DataFrame()

    def save_stock_basic(self, df: pd.DataFrame) -> int:
        """保存股票基本信息"""
        if df.empty:
            return 0

        try:
            cursor = self.conn.cursor()
            success_count = 0
            
            for _, row in df.iterrows():
                try:
                    # 处理空日期字段
                    list_date = row.get('list_date')
                    delist_date = row.get('delist_date')
                    
                    # 将空字符串转换为 None
                    if list_date in (None, '', 'nan', 'NaT'):
                        list_date = None
                    if delist_date in (None, '', 'nan', 'NaT'):
                        delist_date = None
                    
                    cursor.execute("""
                        INSERT INTO stock_basic (code, name, exchange, industry, list_date, delist_date)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (code) DO UPDATE SET
                            name = EXCLUDED.name,
                            exchange = EXCLUDED.exchange,
                            industry = EXCLUDED.industry,
                            list_date = EXCLUDED.list_date,
                            delist_date = EXCLUDED.delist_date
                    """, (
                        row['code'], row['name'], row['exchange'],
                        row.get('industry'), list_date, delist_date
                    ))
                    success_count += 1
                except IntegrityError:
                    self.conn.rollback()
                    continue
                except Exception as e:
                    logger.warning(f"⚠️ 保存股票 {row['code']} 失败: {str(e)}")
                    self.conn.rollback()
                    continue
            
            self.conn.commit()
            cursor.close()
            
            logger.debug(f"✅ 保存股票基本信息: {success_count} 条")
            return success_count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ 保存股票基本信息失败: {str(e)}")
            return 0

    def get_stock_basic(self, code: Optional[str] = None) -> pd.DataFrame:
        """获取股票基本信息"""
        if code:
            query = "SELECT * FROM stock_basic WHERE code = %s"
            params = [code]
        else:
            query = "SELECT * FROM stock_basic ORDER BY code"
            params = []

        try:
            df = pd.read_sql(query, self.conn, params=params)
            return df
        except Exception as e:
            logger.error(f"❌ 获取股票基本信息失败: {str(e)}")
            return pd.DataFrame()

    def save_indicators(self, df: pd.DataFrame) -> int:
        """保存技术指标"""
        if df.empty:
            return 0

        try:
            cursor = self.conn.cursor()
            
            from io import StringIO
            output = StringIO()
            df.to_csv(output, sep='\t', header=False, index=False)
            output.seek(0)
            
            cursor.copy_from(
                output,
                'stock_indicators',
                columns=['code', 'cycle', 'trade_date', 'ma5', 'ma10', 'ma20', 'ma60',
                         'macd', 'dif', 'dea', 'rsi6', 'rsi12', 'rsi24'],
                sep='\t'
            )
            
            self.conn.commit()
            cursor.close()
            
            count = len(df)
            logger.debug(f"✅ 保存技术指标: {count} 条")
            return count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ 保存技术指标失败: {str(e)}")
            return 0

    def get_indicators(self, code: str, cycle: str = 'daily',
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None) -> pd.DataFrame:
        """获取技术指标"""
        query = """
            SELECT code, cycle, trade_date, ma5, ma10, ma20, ma60, macd, dif, dea, rsi6, rsi12, rsi24
            FROM stock_indicators
            WHERE code = %s AND cycle = %s
        """
        params = [code, cycle]

        if start_date:
            query += " AND trade_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= %s"
            params.append(end_date)

        query += " ORDER BY trade_date"

        try:
            df = pd.read_sql(query, self.conn, params=params)
            return df
        except Exception as e:
            logger.error(f"❌ 获取技术指标失败: {str(e)}")
            return pd.DataFrame()

    def save_trade_calendar(self, df: pd.DataFrame) -> int:
        """保存交易日历"""
        if df.empty:
            return 0

        try:
            cursor = self.conn.cursor()
            
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT INTO trade_calendar (cal_date, is_open, holiday_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (cal_date) DO UPDATE SET
                        is_open = EXCLUDED.is_open,
                        holiday_name = EXCLUDED.holiday_name
                """, (row['cal_date'], row['is_open'], row.get('holiday_name')))
            
            self.conn.commit()
            cursor.close()
            
            count = len(df)
            logger.debug(f"✅ 保存交易日历: {count} 条")
            return count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ 保存交易日历失败: {str(e)}")
            return 0

    def get_trade_calendar(self, start_date: Optional[str] = None,
                           end_date: Optional[str] = None,
                           is_open: Optional[int] = None) -> pd.DataFrame:
        """获取交易日历"""
        query = "SELECT * FROM trade_calendar WHERE 1=1"
        params = []

        if start_date:
            query += " AND cal_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND cal_date <= %s"
            params.append(end_date)
        if is_open is not None:
            query += " AND is_open = %s"
            params.append(is_open)

        query += " ORDER BY cal_date"

        try:
            df = pd.read_sql(query, self.conn, params=params)
            return df
        except Exception as e:
            logger.error(f"❌ 获取交易日历失败: {str(e)}")
            return pd.DataFrame()

    def save_task_metrics(self, metrics: Dict):
        """保存任务指标"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                INSERT INTO task_metrics 
                (task, date, stocks_total, stocks_success, stocks_fail, status, latency_sec)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                metrics.get('task'),
                metrics.get('date'),
                metrics.get('stocks_total'),
                metrics.get('stocks_success'),
                metrics.get('stocks_fail'),
                metrics.get('status'),
                metrics.get('latency_sec')
            ))
            
            self.conn.commit()
            cursor.close()
            logger.debug(f"✅ 保存任务指标: {metrics.get('task')}")
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ 保存任务指标失败: {str(e)}")

    def get_latest_trade_date(self) -> Optional[str]:
        """获取最新交易日期"""
        query = "SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = 'daily'"
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            result = cursor.fetchone()
            cursor.close()
            
            return str(result[0]) if result[0] else None
        except Exception as e:
            logger.error(f"❌ 获取最新交易日期失败: {str(e)}")
            return None

    def get_stock_count(self, cycle: str = 'daily') -> int:
        """获取股票数量"""
        query = "SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle = %s"
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, (cycle,))
            result = cursor.fetchone()
            cursor.close()
            
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"❌ 获取股票数量失败: {str(e)}")
            return 0

    def get_data_count(self, cycle: str = 'daily') -> int:
        """获取数据条数"""
        query = "SELECT COUNT(*) FROM stock_quotes WHERE cycle = %s"
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, (cycle,))
            result = cursor.fetchone()
            cursor.close()
            
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"❌ 获取数据条数失败: {str(e)}")
            return 0