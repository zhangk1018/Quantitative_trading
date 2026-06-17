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

            # 创建复权因子表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_adj_factor (
                    code VARCHAR(10) NOT NULL,
                    trade_date DATE NOT NULL,
                    adj_factor NUMERIC(10, 4) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (code, trade_date)
                )
            """)
            logger.info("✅ stock_adj_factor 表已就绪")

            # 创建日频基本面数据表（PE/PB/换手率/市值/dv/ps等）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_daily_basic (
                    code VARCHAR(10) NOT NULL,
                    trade_date DATE NOT NULL,
                    close NUMERIC(10, 2),
                    turnover_rate NUMERIC(10, 4),
                    volume_ratio NUMERIC(10, 4),
                    pe NUMERIC(14, 4),
                    pe_ttm NUMERIC(14, 4),
                    pb NUMERIC(14, 4),
                    total_mv NUMERIC(18, 2),
                    circ_mv NUMERIC(18, 2),
                    dv_ratio NUMERIC(10, 4),
                    dv_ttm    NUMERIC(10, 4),
                    ps        NUMERIC(10, 2),
                    ps_ttm    NUMERIC(10, 2),
                    float_share NUMERIC(18, 4),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (code, trade_date)
                )
            """)
            logger.info("✅ stock_daily_basic 表已就绪")

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

            # 创建交易信号表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_signals (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(10) NOT NULL,
                    cycle VARCHAR(10) NOT NULL,
                    trade_date DATE NOT NULL,
                    signal_type VARCHAR(50) NOT NULL,
                    signal_value NUMERIC(10, 4),
                    signal_strength INTEGER,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(code, cycle, trade_date, signal_type)
                )
            """)
            logger.info("✅ trade_signals 表已就绪")

            # 创建股票列表表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_list (
                    id SERIAL PRIMARY KEY,
                    ts_code VARCHAR(50) NOT NULL UNIQUE,
                    name VARCHAR(100) NOT NULL,
                    code VARCHAR(10),
                    industry VARCHAR(100),
                    market VARCHAR(20),
                    market_name VARCHAR(50),
                    list_date DATE,
                    out_date DATE,
                    type VARCHAR(20),
                    status VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✅ stock_list 表已就绪")

            # 创建股票每日快照宽表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_daily_snapshot (
                    id BIGSERIAL PRIMARY KEY,
                    code VARCHAR(10) NOT NULL,
                    stock_name VARCHAR(50),
                    listed_board VARCHAR(20),
                    industry VARCHAR(50),
                    sub_industry VARCHAR(50),
                    trade_date DATE NOT NULL,
                    open NUMERIC(10, 2),
                    high NUMERIC(10, 2),
                    low NUMERIC(10, 2),
                    close NUMERIC(10, 2),
                    pre_close NUMERIC(10, 2),
                    volume BIGINT,
                    amount NUMERIC(18, 2),
                    adjust_type VARCHAR(10) DEFAULT 'qfq',
                    change NUMERIC(10, 2),
                    change_pct NUMERIC(8, 2),
                    turnover_rate NUMERIC(8, 2),
                    pe NUMERIC(10, 2),
                    pb NUMERIC(10, 2),
                    market_cap NUMERIC(18, 2),
                    circ_mv NUMERIC(18, 2),
                    ma5 NUMERIC(10, 2),
                    ma10 NUMERIC(10, 2),
                    ma20 NUMERIC(10, 2),
                    v_ma5 BIGINT,
                    rsi_6 NUMERIC(6, 2),
                    macd NUMERIC(10, 4),
                    boll_upper NUMERIC(10, 2),
                    boll_mid NUMERIC(10, 2),
                    boll_lower NUMERIC(10, 2),
                    is_st BOOLEAN DEFAULT FALSE,
                    is_new BOOLEAN DEFAULT FALSE,
                    limit_up BOOLEAN DEFAULT FALSE,
                    limit_down BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (code, trade_date)
                )
            """)
            logger.info("✅ stock_daily_snapshot 表已就绪")

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_quotes_code_cycle ON stock_quotes(code, cycle)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_quotes_trade_date ON stock_quotes(trade_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_indicators_code_cycle ON stock_indicators(code, cycle)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_signals_trade_date ON trade_signals(trade_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_signals_signal_type ON trade_signals(signal_type)")

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
        """保存行情数据（支持 upsert：存在则更新，不存在则插入）"""
        if df.empty:
            return 0

        df = df.copy()
        df['adjust_type'] = adjust_type
        
        # 添加 trade_datetime 字段（非空字段）
        if 'trade_datetime' not in df.columns:
            df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta('15:00:00')
        
        # 确保 volume 列为整数类型（避免 COPY 时输出为浮点字符串）
        if 'volume' in df.columns:
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype(int)
        
        try:
            cursor = self.conn.cursor()
            
            # 使用临时表 + INSERT ON CONFLICT 实现 upsert
            from io import StringIO
            output = StringIO()
            df.to_csv(output, sep='\t', header=False, index=False)
            output.seek(0)
            
            # 先导入临时表
            cursor.execute("CREATE TEMP TABLE tmp_stock_quotes (LIKE stock_quotes INCLUDING DEFAULTS) ON COMMIT DROP")
            cursor.copy_from(
                output,
                'tmp_stock_quotes',
                columns=['code', 'cycle', 'trade_date', 'open', 'high', 'low', 
                         'close', 'pre_close', 'volume', 'amount', 'adjust_type',
                         'trade_datetime'],
                sep='\t'
            )
            
            # 从临时表 upsert 到目标表
            cursor.execute("""
                INSERT INTO stock_quotes (code, cycle, trade_date, open, high, low, 
                    close, pre_close, volume, amount, adjust_type, trade_datetime)
                SELECT code, cycle, trade_date, open, high, low, 
                    close, pre_close, volume, amount, adjust_type, trade_datetime
                FROM tmp_stock_quotes
                ON CONFLICT (code, cycle, trade_date)
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    pre_close = EXCLUDED.pre_close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    adjust_type = EXCLUDED.adjust_type,
                    trade_datetime = EXCLUDED.trade_datetime
            """)
            
            count = cursor.rowcount
            self.conn.commit()
            cursor.close()
            
            logger.debug(f"✅ 保存行情数据: {count} 条")
            return count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ 保存行情数据失败: {str(e)}")
            return 0

    def get_quotes(self, code: Optional[str] = None, cycle: str = 'daily',
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
            WHERE cycle = %s
        """
        params = [cycle]
        
        if code:
            query += " AND code = %s"
            params.append(code)

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
        """保存技术指标（使用 INSERT ON CONFLICT DO UPDATE 覆盖旧值）"""
        if df.empty:
            return 0

        try:
            cursor = self.conn.cursor()
            import_count = 0

            insert_sql = """
                INSERT INTO stock_indicators (
                    code, cycle, trade_date, ma5, ma10, ma20, ma60,
                    macd, dif, dea, rsi6, rsi12, rsi24,
                    trade_time, trade_datetime
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code, cycle, trade_date, trade_time) DO UPDATE SET
                    ma5 = EXCLUDED.ma5,
                    ma10 = EXCLUDED.ma10,
                    ma20 = EXCLUDED.ma20,
                    ma60 = EXCLUDED.ma60,
                    macd = EXCLUDED.macd,
                    dif = EXCLUDED.dif,
                    dea = EXCLUDED.dea,
                    rsi6 = EXCLUDED.rsi6,
                    rsi12 = EXCLUDED.rsi12,
                    rsi24 = EXCLUDED.rsi24,
                    trade_datetime = EXCLUDED.trade_datetime
            """

            params_list = []
            for _, row in df.iterrows():
                # trade_time 带时区 (Asia/Shanghai) 避免 timezone mismatch
                trade_time_ts = pd.Timestamp(row['trade_time']).tz_localize('Asia/Shanghai') \
                    if pd.notna(row.get('trade_time')) else None
                trade_dt_ts = pd.Timestamp(row['trade_datetime']).tz_localize('Asia/Shanghai') \
                    if pd.notna(row.get('trade_datetime')) else trade_time_ts
                params_list.append((
                    str(row['code']),
                    str(row['cycle']),
                    row['trade_date'],
                    float(row['ma5']) if pd.notna(row['ma5']) else 0.0,
                    float(row['ma10']) if pd.notna(row['ma10']) else 0.0,
                    float(row['ma20']) if pd.notna(row['ma20']) else 0.0,
                    float(row['ma60']) if pd.notna(row['ma60']) else 0.0,
                    float(row['macd']) if pd.notna(row['macd']) else 0.0,
                    float(row['dif']) if pd.notna(row['dif']) else 0.0,
                    float(row['dea']) if pd.notna(row['dea']) else 0.0,
                    float(row['rsi6']) if pd.notna(row['rsi6']) else 0.0,
                    float(row['rsi12']) if pd.notna(row['rsi12']) else 0.0,
                    float(row['rsi24']) if pd.notna(row['rsi24']) else 0.0,
                    trade_time_ts,
                    trade_dt_ts,
                ))

            # execute_batch 不会累加 rowcount，需要每条单独 execute 并累加
            import_count = 0
            for params in params_list:
                cursor.execute(insert_sql, params)
                # ON CONFLICT DO UPDATE 时 rowcount=1 (update) 或 1 (insert)
                # 唯一不变：失败时为 0
                if cursor.rowcount > 0:
                    import_count += 1
            self.conn.commit()
            cursor.close()

            logger.debug(f"✅ 保存技术指标: {import_count} 条")
            return import_count

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

    def save_adj_factor(self, df: pd.DataFrame) -> int:
        """保存复权因子数据"""
        if df.empty:
            return 0

        try:
            cursor = self.conn.cursor()
            success_count = 0

            for _, row in df.iterrows():
                try:
                    cursor.execute("""
                        INSERT INTO stock_adj_factor (code, trade_date, adj_factor)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (code, trade_date) DO UPDATE SET
                            adj_factor = EXCLUDED.adj_factor
                    """, (row['code'], row['trade_date'], row['adj_factor']))
                    success_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ 保存复权因子 {row.get('code')} {row.get('trade_date')} 失败: {e}")
                    self.conn.rollback()
                    continue

            self.conn.commit()
            cursor.close()
            logger.debug(f"✅ 保存复权因子: {success_count} 条")
            return success_count

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ 保存复权因子失败: {str(e)}")
            return 0

    def get_adj_factor(self, code: str, start_date: Optional[str] = None,
                       end_date: Optional[str] = None) -> pd.DataFrame:
        """获取复权因子数据"""
        query = "SELECT code, trade_date, adj_factor FROM stock_adj_factor WHERE code = %s"
        params = [code]

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
            logger.error(f"❌ 获取复权因子失败: {str(e)}")
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

    def save_daily_basic(self, df: pd.DataFrame) -> int:
        """保存日频基本面数据（PE/PB/换手率/市值）"""
        if df.empty:
            return 0

        try:
            cursor = self.conn.cursor()
            success_count = 0

            for _, row in df.iterrows():
                try:
                    cursor.execute("""
                        INSERT INTO stock_daily_basic
                        (code, trade_date, close, turnover_rate, volume_ratio,
                         pe, pe_ttm, pb, total_mv, circ_mv,
                         dv_ratio, dv_ttm, ps, ps_ttm, float_share)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (code, trade_date) DO UPDATE SET
                            close = EXCLUDED.close,
                            turnover_rate = EXCLUDED.turnover_rate,
                            volume_ratio = EXCLUDED.volume_ratio,
                            pe = EXCLUDED.pe,
                            pe_ttm = EXCLUDED.pe_ttm,
                            pb = EXCLUDED.pb,
                            total_mv = EXCLUDED.total_mv,
                            circ_mv = EXCLUDED.circ_mv,
                            dv_ratio = EXCLUDED.dv_ratio,
                            dv_ttm = EXCLUDED.dv_ttm,
                            ps = EXCLUDED.ps,
                            ps_ttm = EXCLUDED.ps_ttm,
                            float_share = EXCLUDED.float_share
                    """, (
                        row['code'], row['trade_date'], row.get('close'),
                        row.get('turnover_rate'), row.get('volume_ratio'),
                        row.get('pe'), row.get('pe_ttm'), row.get('pb'),
                        row.get('total_mv'), row.get('circ_mv'),
                        row.get('dv_ratio'), row.get('dv_ttm'),
                        row.get('ps'), row.get('ps_ttm'),
                        row.get('float_share')
                    ))
                    success_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ 保存 {row.get('code')} {row.get('trade_date')} 基本面失败: {e}")
                    self.conn.rollback()
                    continue

            self.conn.commit()
            cursor.close()
            logger.debug(f"✅ 保存日频基本面: {success_count} 条")
            return success_count

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ 保存日频基本面失败: {str(e)}")
            return 0

    def get_daily_basic(self, code: Optional[str] = None,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None) -> pd.DataFrame:
        """获取日频基本面数据"""
        query = "SELECT * FROM stock_daily_basic WHERE 1=1"
        params = []

        if code:
            query += " AND code = %s"
            params.append(code)
        if start_date:
            query += " AND trade_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= %s"
            params.append(end_date)

        query += " ORDER BY trade_date DESC, code"

        try:
            df = pd.read_sql(query, self.conn, params=params)
            return df
        except Exception as e:
            logger.error(f"❌ 获取日频基本面失败: {str(e)}")
            return pd.DataFrame()

    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表"""
        query = "SELECT code, name, exchange, industry FROM stock_basic ORDER BY code"

        try:
            df = pd.read_sql(query, self.conn)
            return df
        except Exception as e:
            logger.error(f"❌ 获取股票列表失败: {str(e)}")
            return pd.DataFrame()

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

    def save_signals(self, df: pd.DataFrame) -> int:
        """保存交易信号"""
        if df.empty:
            return 0

        try:
            cursor = self.conn.cursor()

            insert_sql = """
                INSERT INTO trade_signals (
                    code, cycle, trade_date, signal_type, signal_direction,
                    signal_value, signal_strength, description
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code, trade_date, signal_type) DO UPDATE SET
                    cycle = EXCLUDED.cycle,
                    signal_direction = EXCLUDED.signal_direction,
                    signal_value = EXCLUDED.signal_value,
                    signal_strength = EXCLUDED.signal_strength,
                    description = EXCLUDED.description
            """

            params_list = []
            for _, row in df.iterrows():
                params_list.append((
                    str(row['code']),
                    str(row.get('cycle', '1d')),
                    row['trade_date'],
                    str(row['signal_type']),
                    str(row.get('signal_direction', '')) if pd.notna(row.get('signal_direction')) else None,
                    float(row['signal_value']) if pd.notna(row.get('signal_value')) else None,
                    int(row['signal_strength']) if pd.notna(row.get('signal_strength')) else None,
                    str(row.get('description', '')) if pd.notna(row.get('description')) else None,
                ))

            import_count = 0
            for params in params_list:
                cursor.execute(insert_sql, params)
                if cursor.rowcount > 0:
                    import_count += 1
            self.conn.commit()
            cursor.close()

            logger.debug(f"✅ 保存交易信号: {import_count} 条")
            return import_count

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ 保存交易信号失败: {str(e)}")
            return 0

    def get_signals(self, code: Optional[str] = None,
                   cycle: str = '1d',
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None,
                   signal_type: Optional[str] = None) -> pd.DataFrame:
        """获取交易信号"""
        query = """
            SELECT code, cycle, trade_date, signal_type, signal_direction, signal_value, signal_strength, trigger_price, description
            FROM trade_signals
            WHERE cycle = %s
        """
        params = [cycle]

        if code:
            query += " AND code = %s"
            params.append(code)
        if start_date:
            query += " AND trade_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= %s"
            params.append(end_date)
        if signal_type:
            query += " AND signal_type = %s"
            params.append(signal_type)

        query += " ORDER BY trade_date DESC, code"

        try:
            df = pd.read_sql(query, self.conn, params=params)
            return df
        except Exception as e:
            logger.error(f"❌ 获取交易信号失败: {str(e)}")
            return pd.DataFrame()

    def get_kline_with_indicators(self, code: str, cycle: str = 'daily', 
                                  start_date: Optional[str] = None, 
                                  end_date: Optional[str] = None, 
                                  limit: int = 100) -> pd.DataFrame:
        """
        获取包含行情、基本面和技术指标的完整 K 线数据
        通过 SQL JOIN 复用数据库已有数据，避免 Python 重复计算
        """
        if not self.conn:
            logger.error("❌ 数据库未连接")
            return pd.DataFrame()

        # cycle 映射
        cycle_map = {'daily': '1d', '1d': '1d', 'weekly': '1w', 'monthly': '1m'}
        cycle_val = cycle_map.get(cycle.lower(), cycle)

        query = """
            SELECT 
                q.trade_date, q.open, q.high, q.low, q.close, q.volume, q.amount,
                b.pe_ttm, b.pb, b.circ_mv, b.turnover_rate,
                i.ma5, i.ma10, i.ma20, i.ma60,
                i.dif, i.dea, i.macd, i.rsi6, i.rsi12, i.rsi24
            FROM stock_quotes q
            LEFT JOIN stock_daily_basic b ON q.code = b.code AND q.trade_date = b.trade_date
            LEFT JOIN stock_indicators i ON q.code = i.code AND q.trade_date = i.trade_date AND q.cycle = i.cycle
            WHERE q.code = %s AND q.cycle = %s
        """
        params = [code, cycle_val]

        if start_date:
            query += " AND q.trade_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND q.trade_date <= %s"
            params.append(end_date)

        query += " ORDER BY q.trade_date DESC LIMIT %s"
        params.append(limit)

        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            colnames = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            cursor.close()
            
            if not rows:
                return pd.DataFrame()
            
            df = pd.DataFrame(rows, columns=colnames)
            # 按日期正序排列，方便前端画图和指标计算
            return df.sort_values('trade_date').reset_index(drop=True)
            
        except Exception as e:
            logger.error(f"❌ 获取带指标 K 线数据失败: {str(e)}")
            return pd.DataFrame()