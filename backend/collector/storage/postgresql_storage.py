#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL 存储实现 (v6.8.5 - 自动确保唯一约束存在)
v6.8.5 修改：
- save_quotes 在插入前检查并创建唯一约束（若缺失）
- 解决 "there is no unique or exclusion constraint matching the ON CONFLICT specification" 错误
- 使用类级别的 _constraint_checked 标记，避免重复检查
"""
import logging
import threading
import time
import functools
import warnings
from decimal import Decimal
from contextlib import contextmanager
from typing import Optional, Dict, Any, List, Tuple, Generator
from datetime import datetime
from io import StringIO

import numpy as np
import pandas as pd
import psycopg2
from psycopg2 import OperationalError, pool, sql, errors
from psycopg2.extras import execute_batch, execute_values

from .base_storage import BaseStorage

DEFAULT_TZ = 'Asia/Shanghai'
logger = logging.getLogger(__name__)


# ==================== 重试装饰器 ====================
def _retry_on_error(max_retries: int = 3, delay: float = 0.5, backoff: float = 2.0):
    """自动重试数据库操作（幂等操作）"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except (OperationalError, psycopg2.InterfaceError) as e:
                    last_exc = e
                    if attempt == max_retries - 1:
                        raise
                    wait = delay * (backoff ** attempt)
                    logger.warning(f"⚠️ 操作失败 (尝试 {attempt+1}/{max_retries})，{wait:.2f}s 后重试: {e}")
                    time.sleep(wait)

                    # 重置当前线程连接，强制下次获取新连接
                    if hasattr(self._thread_local, 'conn') and self._thread_local.conn:
                        try:
                            # 尝试归还并关闭
                            if self._pool and not self._pool_closed:
                                try:
                                    self._pool.putconn(self._thread_local.conn, close=True)
                                except TypeError:
                                    self._pool.putconn(self._thread_local.conn)
                        except Exception:
                            pass
                        self._thread_local.conn = None
                        if hasattr(self._conn_acquire_time, 'time'):
                            delattr(self._conn_acquire_time, 'time')

                    # 重新连接池（若已关闭）
                    self._ensure_connection()
            raise last_exc
        return wrapper
    return decorator


# ========== Engine 适配器（保留兼容） ==========
class _ConnectionContext:
    def __init__(self, storage):
        self.storage = storage
        self.conn = None

    def __enter__(self):
        self.conn = self.storage._get_conn()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.storage._return_conn(self.conn)


class _Engine:
    def __init__(self, storage):
        self.storage = storage

    def connect(self):
        return _ConnectionContext(self.storage)


class PostgreSQLStorage(BaseStorage):
    """PostgreSQL 存储实现 (生产级)"""

    # 类变量：用于记录是否已经检查过约束（所有实例共享）
    _constraint_checked = False
    _constraint_lock = threading.Lock()

    def __init__(self, config: Dict[str, Any]):
        self.host = config.get('host', 'localhost')
        self.port = config.get('port', 5432)
        self.database = config.get('database', 'quant_trading')
        self.username = config.get('username', 'quant_user')
        self.password = config.get('password', 'quant_password')
        self.min_pool = config.get('min_pool', 1)
        self.max_pool = config.get('max_pool', 10)
        self.connect_timeout = config.get('connect_timeout', 10)
        self.max_lifetime = config.get('max_lifetime', 3600)

        self._pool = None
        self._pool_closed = False
        self._thread_local = threading.local()
        self._conn_acquire_time = threading.local()
        self.engine = _Engine(self)

    @property
    def conn(self):
        """兼容层属性：返回当前线程的连接。

        为兼容使用 ``storage.conn.cursor()`` 的旧代码（如 BaseDataImporter），
        若当前线程已持有连接则直接返回，否则从连接池获取一个新连接。
        注意：通过该属性获取的连接不会自动归还，调用方需负责在 finally 中
        调用 ``_return_conn()`` 或等待连接池超时回收。
        """
        if hasattr(self._thread_local, 'conn') and self._thread_local.conn:
            return self._thread_local.conn
        return self._get_conn()

    def __del__(self):
        # 仅警告，不自动关闭
        if hasattr(self._thread_local, 'conn') and self._thread_local.conn:
            warnings.warn("⚠️ 连接池中存在未归还的连接，请确保在 with 块或 finally 中归还。")
        self.disconnect()

    # ========== 连接管理 ==========
    def connect(self) -> bool:
        """建立连接池（幂等）"""
        if self._pool and not self._pool_closed:
            return True
        try:
            self._pool = pool.ThreadedConnectionPool(
                minconn=self.min_pool,
                maxconn=self.max_pool,
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.username,
                password=self.password,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
                connect_timeout=self.connect_timeout
            )
            self._pool_closed = False
            logger.info(f"✅ PostgreSQL 连接池建立成功: {self.host}:{self.port}/{self.database} "
                        f"(池大小: {self.min_pool}-{self.max_pool}, max_lifetime={self.max_lifetime}s)")
            return True
        except OperationalError as e:
            logger.error(f"❌ PostgreSQL 连接池建立失败: {str(e)}")
            return False

    def disconnect(self):
        """安全关闭连接池（幂等）"""
        if self._pool is None or self._pool_closed:
            return
        try:
            # 归还当前线程连接
            if hasattr(self._thread_local, 'conn') and self._thread_local.conn:
                try:
                    self._pool.putconn(self._thread_local.conn)
                except Exception:
                    pass
                self._thread_local.conn = None
                if hasattr(self._conn_acquire_time, 'time'):
                    delattr(self._conn_acquire_time, 'time')

            # 关闭池
            try:
                self._pool.closeall()
            except Exception as e:
                logger.debug(f"关闭池时出现异常（可忽略）: {e}")

            self._pool_closed = True
            logger.info("✅ PostgreSQL 连接池已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭连接池失败: {str(e)}")

    def _ensure_connection(self):
        """确保连接池可用，若关闭则重建"""
        if self._pool is None or self._pool_closed:
            self.connect()
        # 若连接仍不可用，抛出异常
        if self._pool is None or self._pool_closed:
            raise RuntimeError("无法建立数据库连接")

    def _get_conn(self, timeout: int = 30):
        """从池中获取当前线程的连接（自动重连）"""
        self._ensure_connection()

        # 检查线程本地连接是否有效
        if hasattr(self._thread_local, 'conn') and self._thread_local.conn:
            conn = self._thread_local.conn
            # 检查连接是否过期
            if hasattr(self._conn_acquire_time, 'time') and \
               (time.time() - self._conn_acquire_time.time) > self.max_lifetime:
                try:
                    try:
                        self._pool.putconn(conn, close=True)
                    except TypeError:
                        self._pool.putconn(conn)
                except Exception:
                    pass
                self._thread_local.conn = None
            else:
                # 验证连接有效性
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                    return conn
                except OperationalError:
                    self._thread_local.conn = None

        # 从池中获取新连接
        try:
            conn = self._pool.getconn(timeout=timeout)
        except TypeError:
            conn = self._pool.getconn()

        self._thread_local.conn = conn
        self._conn_acquire_time.time = time.time()
        return conn

    def _return_conn(self, conn=None):
        """归还连接到池中"""
        if conn is None:
            conn = getattr(self._thread_local, 'conn', None)

        if conn and self._pool and not self._pool_closed:
            try:
                self._pool.putconn(conn)
            except Exception as e:
                logger.debug(f"归还连接时出现警告（可忽略）: {e}")

            if hasattr(self._thread_local, 'conn') and self._thread_local.conn == conn:
                self._thread_local.conn = None
                if hasattr(self._conn_acquire_time, 'time'):
                    delattr(self._conn_acquire_time, 'time')

    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接池状态（仅用于监控）"""
        if self._pool is None or self._pool_closed:
            return {}
        try:
            used = getattr(self._pool, '_used', 0)
            pool_list = getattr(self._pool, '_pool', [])
            available = len(pool_list) if isinstance(pool_list, list) else 0
            return {
                'min': self.min_pool,
                'max': self.max_pool,
                'used': used,
                'available': available,
                'thread_local_conn': hasattr(self._thread_local, 'conn') and self._thread_local.conn is not None
            }
        except Exception:
            return {}

    # ========== 上下文管理器 ==========
    def __enter__(self):
        self._ensure_connection()
        if not hasattr(self._thread_local, 'conn') or self._thread_local.conn is None:
            self._get_conn()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self._thread_local, 'conn') and self._thread_local.conn:
            try:
                if self._pool and not self._pool_closed:
                    self._pool.putconn(self._thread_local.conn)
            except Exception as e:
                logger.warning(f"⚠️ 归还连接失败: {str(e)}")
            finally:
                self._thread_local.conn = None
                if hasattr(self._conn_acquire_time, 'time'):
                    delattr(self._conn_acquire_time, 'time')

    @contextmanager
    def transaction(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """事务上下文（自动提交/回滚）"""
        conn = self._get_conn()
        if conn is None:
            raise RuntimeError("无法获取数据库连接")
        try:
            conn.autocommit = False
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.autocommit = True
            self._return_conn(conn)

    # ========== 实现 BaseStorage 抽象方法 ==========
    def save_task_metrics(self, task_name: str, metrics: Dict[str, Any]) -> bool:
        logger.info(f"📊 任务指标 [{task_name}]: {metrics}")
        return True

    # ========== 通用工具方法 ==========
    CYCLE_MAP = {
        'daily': '1d', '1d': '1d', 'day': '1d',
        'weekly': '1w', '1w': '1w', 'week': '1w',
        'monthly': '1m', '1m': '1m', 'month': '1m'
    }

    def _normalize_cycle(self, cycle: str) -> str:
        return self.CYCLE_MAP.get(cycle.lower(), cycle) if cycle else cycle

    def _to_tz_aware(self, ts):
        if pd.isna(ts):
            return None
        dt = pd.to_datetime(ts)
        if dt.tz is None:
            return dt.tz_localize(DEFAULT_TZ)
        else:
            return dt.tz_convert(DEFAULT_TZ)

    def _table_exists(self, table_name: str) -> bool:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                    (table_name,)
                )
                return cur.fetchone()[0]
        finally:
            self._return_conn(conn)

    def _is_partitioned(self, table_name: str) -> bool:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT relkind = 'p' FROM pg_class WHERE relname = %s", (table_name,))
                result = cur.fetchone()
                return result[0] if result else False
        finally:
            self._return_conn(conn)

    def _get_partition_years(self, start_year: int = 2010) -> List[int]:
        current_year = datetime.now().year
        return list(range(start_year, current_year + 3))

    def _ensure_partitions(self, conn, table_name: str = 'stock_quotes', start_year: int = 2010):
        """创建缺失的分区"""
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT substring(relname FROM 'stock_quotes_([0-9]{4})') AS year
                FROM pg_class WHERE relname ~ '^stock_quotes_[0-9]{4}$'
            """)
            existing_years = {int(row[0]) for row in cur.fetchall() if row[0]}
            target_years = set(self._get_partition_years(start_year))
            missing_years = target_years - existing_years

            for year in sorted(missing_years):
                logger.debug(f"📦 创建分区 stock_quotes_{year}")
                try:
                    cur.execute(sql.SQL("""
                        CREATE TABLE IF NOT EXISTS {} PARTITION OF stock_quotes
                        FOR VALUES FROM (%s) TO (%s)
                    """).format(sql.Identifier(f"stock_quotes_{year}")), (f"{year}-01-01", f"{year+1}-01-01"))
                except errors.DuplicateTable:
                    pass

            if missing_years:
                conn.commit()

    # ========== 表初始化与迁移 ==========
    def init_tables(self):
        self._ensure_connection()
        conn = self._get_conn()
        try:
            with conn.cursor() as cursor:
                # 1. stock_basic
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

                # 2. stock_quotes (分区表)
                if self._table_exists('stock_quotes') and not self._is_partitioned('stock_quotes'):
                    logger.info("📦 检测到普通表 stock_quotes，准备迁移到分区表...")
                    self._migrate_to_partitioned_quotes(conn)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS stock_quotes (
                        id SERIAL,
                        code VARCHAR(10) NOT NULL,
                        cycle VARCHAR(10) NOT NULL,
                        trade_date DATE NOT NULL,
                        open NUMERIC(10, 2),
                        high NUMERIC(10, 2),
                        low NUMERIC(10, 2),
                        close NUMERIC(10, 2),
                        pre_close NUMERIC(10, 2),
                        volume BIGINT,
                        amount NUMERIC(18, 2),
                        adjust_type VARCHAR(10) DEFAULT 'qfq',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        trade_datetime TIMESTAMP WITH TIME ZONE,
                        UNIQUE(code, cycle, trade_date, adjust_type)
                    ) PARTITION BY RANGE (trade_date)
                """)
                self._ensure_partitions(conn, 'stock_quotes')

                # 确保唯一约束存在（针对已存在的表）
                self._ensure_quotes_unique_constraint(conn)

                # 3. stock_indicators
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
                        boll_upper NUMERIC(10, 2),
                        boll_mid NUMERIC(10, 2),
                        boll_lower NUMERIC(10, 2),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        trade_time TIMESTAMP WITH TIME ZONE,
                        trade_datetime TIMESTAMP WITH TIME ZONE,
                        UNIQUE(code, cycle, trade_date, trade_datetime)
                    )
                """)

                # 4. stock_adj_factor
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS stock_adj_factor (
                        code VARCHAR(10) NOT NULL,
                        trade_date DATE NOT NULL,
                        adj_factor NUMERIC(10, 4) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (code, trade_date)
                    )
                """)

                # 5. stock_daily_basic
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
                        dv_ttm NUMERIC(10, 4),
                        ps NUMERIC(10, 2),
                        ps_ttm NUMERIC(10, 2),
                        float_share NUMERIC(18, 4),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (code, trade_date)
                    )
                """)

                # 6. trade_calendar
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trade_calendar (
                        cal_date DATE PRIMARY KEY,
                        is_open INTEGER NOT NULL,
                        holiday_name VARCHAR(100),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 7. trade_signals
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trade_signals (
                        id SERIAL PRIMARY KEY,
                        code VARCHAR(10) NOT NULL,
                        cycle VARCHAR(10) NOT NULL,
                        trade_date DATE NOT NULL,
                        signal_type VARCHAR(50) NOT NULL,
                        signal_direction VARCHAR(10),
                        signal_value NUMERIC(10, 4),
                        signal_strength INTEGER,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 清理重复数据（如果有）
                cursor.execute("""
                    SELECT code, cycle, trade_date, signal_type, signal_direction, COUNT(*)
                    FROM trade_signals
                    GROUP BY code, cycle, trade_date, signal_type, signal_direction
                    HAVING COUNT(*) > 1
                """)
                duplicates = cursor.fetchall()
                if duplicates:
                    logger.warning(f"⚠️ 发现 {len(duplicates)} 组重复信号数据，将删除重复项（保留最小 id）")
                    for dup in duplicates:
                        code, cycle, trade_date, signal_type, signal_direction, cnt = dup
                        cursor.execute("""
                            DELETE FROM trade_signals
                            WHERE id NOT IN (
                                SELECT MIN(id) FROM trade_signals
                                WHERE code = %s AND cycle = %s AND trade_date = %s
                                AND signal_type = %s AND signal_direction = %s
                            )
                            AND code = %s AND cycle = %s AND trade_date = %s
                            AND signal_type = %s AND signal_direction = %s
                        """, (code, cycle, trade_date, signal_type, signal_direction,
                              code, cycle, trade_date, signal_type, signal_direction))
                    logger.info("✅ 重复信号数据已清理")

                # 创建唯一索引（用于 ON CONFLICT）
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_signals_unique
                    ON trade_signals (code, cycle, trade_date, signal_type, signal_direction)
                """)

                # 8. stock_daily_snapshot
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

                # 9. 索引
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_quotes_code_cycle ON stock_quotes(code, cycle)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_quotes_trade_date ON stock_quotes(trade_date)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_indicators_code_cycle ON stock_indicators(code, cycle)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_signals_trade_date ON trade_signals(trade_date)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_signals_signal_type ON trade_signals(signal_type)")

            conn.commit()
            logger.info("✅ 数据库表结构初始化完成")
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ 初始化表结构失败: {str(e)}")
            raise
        finally:
            self._return_conn(conn)

    def _migrate_to_partitioned_quotes(self, conn):
        """将旧表迁移到分区表（带保护）"""
        with conn.cursor() as cur:
            try:
                cur.execute("ALTER TABLE stock_quotes RENAME TO stock_quotes_old")
                cur.execute("""
                    CREATE TABLE stock_quotes (
                        id SERIAL,
                        code VARCHAR(10) NOT NULL,
                        cycle VARCHAR(10) NOT NULL,
                        trade_date DATE NOT NULL,
                        open NUMERIC(10, 2),
                        high NUMERIC(10, 2),
                        low NUMERIC(10, 2),
                        close NUMERIC(10, 2),
                        pre_close NUMERIC(10, 2),
                        volume BIGINT,
                        amount NUMERIC(18, 2),
                        adjust_type VARCHAR(10) DEFAULT 'qfq',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        trade_datetime TIMESTAMP WITH TIME ZONE,
                        UNIQUE(code, cycle, trade_date, adjust_type)
                    ) PARTITION BY RANGE (trade_date)
                """)
                for year in self._get_partition_years(2010):
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS stock_quotes_{year}
                        PARTITION OF stock_quotes
                        FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')
                    """)
                cur.execute("""
                    INSERT INTO stock_quotes (code, cycle, trade_date, open, high, low, close, pre_close,
                                              volume, amount, adjust_type, trade_datetime)
                    SELECT code, cycle, trade_date, open, high, low, close, pre_close,
                           volume, amount,
                           COALESCE(adjust_type, 'qfq') AS adjust_type,
                           trade_datetime
                    FROM stock_quotes_old
                """)
                cur.execute("DROP TABLE stock_quotes_old")
                logger.info(f"📦 迁移 stock_quotes 完成: {cur.rowcount} 条数据")
            except Exception as e:
                logger.error(f"迁移失败: {e}")
                raise

    def _ensure_quotes_unique_constraint(self, conn):
        """
        确保 stock_quotes 表上存在唯一约束 (code, cycle, trade_date, adjust_type)
        若不存在则创建。
        """
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM pg_constraint
                WHERE conname = 'stock_quotes_code_cycle_trade_date_adjust_type_key'
                AND conrelid = 'stock_quotes'::regclass
            """)
            exists = cur.fetchone()
            if not exists:
                logger.info("🔧 为 stock_quotes 添加唯一约束 (code, cycle, trade_date, adjust_type)")
                try:
                    cur.execute("""
                        ALTER TABLE stock_quotes
                        ADD CONSTRAINT stock_quotes_code_cycle_trade_date_adjust_type_key
                        UNIQUE (code, cycle, trade_date, adjust_type)
                    """)
                    conn.commit()
                    logger.info("✅ 唯一约束添加成功")
                except Exception as e:
                    logger.warning(f"添加约束失败（可能已有重复数据）: {e}")
                    # 如果存在重复数据，可能需要清理，但我们先不处理，让 ON CONFLICT 失败时再处理
                    # 这里仅仅记录警告，后续插入时仍可能失败
            else:
                logger.debug("✅ 唯一约束已存在")

    # ==================== 数据保存方法 ====================
    @_retry_on_error(max_retries=3)
    def save_quotes(self, df: pd.DataFrame, adjust_type: str = 'qfq') -> int:
        """
        保存行情数据（使用 execute_values 批量插入）
        首先确保唯一约束存在，然后执行 upsert
        """
        if df.empty:
            return 0
        self._ensure_connection()

        # --- 确保唯一约束存在（仅检查一次，线程安全） ---
        if not PostgreSQLStorage._constraint_checked:
            with PostgreSQLStorage._constraint_lock:
                if not PostgreSQLStorage._constraint_checked:
                    conn = self._get_conn()
                    try:
                        self._ensure_quotes_unique_constraint(conn)
                        PostgreSQLStorage._constraint_checked = True
                    except Exception as e:
                        logger.error(f"检查/创建约束失败: {e}")
                    finally:
                        self._return_conn(conn)

        df = df.copy()
        if 'cycle' in df.columns:
            df['cycle'] = df['cycle'].apply(self._normalize_cycle)
        else:
            df['cycle'] = '1d'
        df['adjust_type'] = adjust_type
        if 'pre_close' not in df.columns:
            df['pre_close'] = df.get('close', 0)
        if 'trade_datetime' not in df.columns:
            df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta('15:00:00')
        df['trade_datetime'] = df['trade_datetime'].apply(self._to_tz_aware)
        if 'volume' in df.columns:
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype(int)
        if 'ah_vol' in df.columns:
            df['ah_vol'] = pd.to_numeric(df['ah_vol'], errors='coerce').fillna(0).astype(int)

        numeric_cols = ['open', 'high', 'low', 'close', 'pre_close', 'amount', 'ah_amount']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: Decimal(str(x)) if pd.notnull(x) else None)

        # 确保所有需要列存在
        required_cols = ['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close',
                         'pre_close', 'volume', 'amount', 'adjust_type', 'trade_datetime',
                         'ah_vol', 'ah_amount']
        for c in required_cols:
            if c not in df.columns:
                df[c] = np.nan
        df = df.where(pd.notnull(df), None)
        # 转换为元组列表，按顺序
        values = [tuple(row) for row in df[required_cols].itertuples(index=False, name=None)]

        conn = self._get_conn()
        try:
            self._ensure_partitions(conn)
            with conn.cursor() as cursor:
                # 使用 execute_values 批量插入，每批 5000 条
                execute_values(cursor, """
                    INSERT INTO stock_quotes (code, cycle, trade_date, open, high, low, close, pre_close,
                                              volume, amount, adjust_type, trade_datetime, ah_vol, ah_amount)
                    VALUES %s
                    ON CONFLICT (code, cycle, trade_date, adjust_type) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        pre_close = EXCLUDED.pre_close,
                        volume = EXCLUDED.volume,
                        amount = EXCLUDED.amount,
                        ah_vol = EXCLUDED.ah_vol,
                        ah_amount = EXCLUDED.ah_amount,
                        trade_datetime = EXCLUDED.trade_datetime
                """, values, page_size=5000)
            conn.commit()
            logger.info(f"✅ 保存行情数据: 处理/覆盖 {len(df)} 条")
            return len(df)
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ 保存行情数据失败: {str(e)}")
            return 0
        finally:
            self._return_conn(conn)

    @_retry_on_error()
    def save_stock_basic(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        self._ensure_connection()
        df = df.where(pd.notnull(df), None)
        cols = ['code', 'name', 'exchange', 'industry', 'list_date', 'delist_date']
        for c in cols:
            if c not in df.columns:
                df[c] = None
        values = list(df[cols].itertuples(index=False, name=None))

        conn = self._get_conn()
        try:
            with conn.cursor() as cursor:
                execute_values(cursor, """
                    INSERT INTO stock_basic (code, name, exchange, industry, list_date, delist_date)
                    VALUES %s
                    ON CONFLICT (code) DO UPDATE SET
                        name = EXCLUDED.name,
                        exchange = EXCLUDED.exchange,
                        industry = EXCLUDED.industry,
                        list_date = EXCLUDED.list_date,
                        delist_date = EXCLUDED.delist_date,
                        updated_at = CURRENT_TIMESTAMP
                """, values, page_size=5000)
            conn.commit()
            logger.info(f"✅ 保存股票基本信息: {len(values)} 条")
            return len(values)
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ 保存股票基本信息失败: {str(e)}")
            return 0
        finally:
            self._return_conn(conn)

    @_retry_on_error()
    def save_indicators(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        self._ensure_connection()
        df = df.copy()
        if 'cycle' in df.columns:
            df['cycle'] = df['cycle'].apply(self._normalize_cycle)
        else:
            df['cycle'] = '1d'

        df['trade_time'] = df['trade_time'].apply(self._to_tz_aware)
        df['trade_datetime'] = df['trade_datetime'].apply(self._to_tz_aware)
        df['trade_datetime'] = df['trade_datetime'].combine_first(df['trade_time'])

        numeric_cols = ['ma5', 'ma10', 'ma20', 'ma60', 'macd', 'dif', 'dea',
                        'rsi6', 'rsi12', 'rsi24', 'boll_upper', 'boll_mid', 'boll_lower',
                        'ema5', 'ema10', 'ema20', 'ema60', 'atr', 'vol_ratio', 'turnover_rate',
                        'kdj_k', 'kdj_d', 'kdj_j']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: Decimal(str(x)) if pd.notnull(x) else None)
            else:
                df[col] = None

        cols = ['code', 'cycle', 'trade_date'] + numeric_cols + ['trade_time', 'trade_datetime']
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df.where(pd.notnull(df), None)
        values = list(df[cols].itertuples(index=False, name=None))

        conn = self._get_conn()
        try:
            with conn.cursor() as cursor:
                execute_values(cursor, """
                    INSERT INTO stock_indicators (
                        code, cycle, trade_date, ma5, ma10, ma20, ma60,
                        macd, dif, dea, rsi6, rsi12, rsi24,
                        boll_upper, boll_mid, boll_lower,
                        ema5, ema10, ema20, ema60, atr, vol_ratio, turnover_rate,
                        kdj_k, kdj_d, kdj_j,
                        trade_time, trade_datetime
                    ) VALUES %s
                    ON CONFLICT (code, cycle, trade_date, trade_datetime) DO UPDATE SET
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
                        boll_upper = EXCLUDED.boll_upper,
                        boll_mid = EXCLUDED.boll_mid,
                        boll_lower = EXCLUDED.boll_lower,
                        ema5 = EXCLUDED.ema5,
                        ema10 = EXCLUDED.ema10,
                        ema20 = EXCLUDED.ema20,
                        ema60 = EXCLUDED.ema60,
                        atr = EXCLUDED.atr,
                        vol_ratio = EXCLUDED.vol_ratio,
                        turnover_rate = EXCLUDED.turnover_rate,
                        kdj_k = EXCLUDED.kdj_k,
                        kdj_d = EXCLUDED.kdj_d,
                        kdj_j = EXCLUDED.kdj_j
                """, values, page_size=5000)
            conn.commit()
            logger.info(f"✅ 保存技术指标: {len(values)} 条")
            return len(values)
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ 保存技术指标失败: {str(e)}")
            return 0
        finally:
            self._return_conn(conn)

    @_retry_on_error()
    def get_float_shares(self, code: str) -> Optional[float]:
        """
        获取最新流通股本（股）。

        从 stock_daily_basic 表查询最新一条记录的 float_share 字段。

        Args:
            code: 股票代码（纯数字，如 '000001'）

        Returns:
            流通股本（股），若无法获取则返回 None
        """
        self._ensure_connection()
        conn = self._get_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT float_share FROM stock_daily_basic "
                    "WHERE code = %s ORDER BY trade_date DESC LIMIT 1",
                    (code,),
                )
                row = cursor.fetchone()
                return float(row[0]) if row and row[0] else None
        except Exception as e:
            logger.warning(f"获取 {code} 流通股本失败: {e}")
            return None
        finally:
            self._return_conn(conn)

    @_retry_on_error()
    def save_adj_factor(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        self._ensure_connection()
        df = df.where(pd.notnull(df), None)
        if 'adj_factor' not in df.columns:
            df['adj_factor'] = None
        df['adj_factor'] = df['adj_factor'].apply(lambda x: Decimal(str(x)) if pd.notnull(x) else None)
        values = list(df[['code', 'trade_date', 'adj_factor']].itertuples(index=False, name=None))

        conn = self._get_conn()
        try:
            with conn.cursor() as cursor:
                execute_values(cursor, """
                    INSERT INTO stock_adj_factor (code, trade_date, adj_factor)
                    VALUES %s
                    ON CONFLICT (code, trade_date) DO UPDATE SET
                        adj_factor = EXCLUDED.adj_factor
                """, values, page_size=5000)
            conn.commit()
            logger.info(f"✅ 保存复权因子: {len(values)} 条")
            return len(values)
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ 保存复权因子失败: {str(e)}")
            return 0
        finally:
            self._return_conn(conn)

    @_retry_on_error()
    def save_trade_calendar(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        self._ensure_connection()
        df = df.where(pd.notnull(df), None)
        if 'holiday_name' not in df.columns:
            df['holiday_name'] = None
        values = list(df[['cal_date', 'is_open', 'holiday_name']].itertuples(index=False, name=None))

        conn = self._get_conn()
        try:
            with conn.cursor() as cursor:
                execute_values(cursor, """
                    INSERT INTO trade_calendar (cal_date, is_open, holiday_name)
                    VALUES %s
                    ON CONFLICT (cal_date) DO UPDATE SET
                        is_open = EXCLUDED.is_open,
                        holiday_name = EXCLUDED.holiday_name
                """, values, page_size=5000)
            conn.commit()
            logger.info(f"✅ 保存交易日历: {len(values)} 条")
            return len(values)
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ 保存交易日历失败: {str(e)}")
            return 0
        finally:
            self._return_conn(conn)

    @_retry_on_error()
    def save_daily_basic(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        self._ensure_connection()
        df = df.where(pd.notnull(df), None)
        numeric_cols = ['close', 'turnover_rate', 'volume_ratio', 'pe', 'pe_ttm', 'pb',
                        'total_mv', 'circ_mv', 'dv_ratio', 'dv_ttm', 'ps', 'ps_ttm', 'float_share']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: Decimal(str(x)) if pd.notnull(x) else None)

        cols = ['code', 'trade_date'] + numeric_cols
        for c in cols:
            if c not in df.columns:
                df[c] = None
        values = list(df[cols].itertuples(index=False, name=None))

        conn = self._get_conn()
        try:
            with conn.cursor() as cursor:
                execute_values(cursor, """
                    INSERT INTO stock_daily_basic (
                        code, trade_date, close, turnover_rate, volume_ratio,
                        pe, pe_ttm, pb, total_mv, circ_mv,
                        dv_ratio, dv_ttm, ps, ps_ttm, float_share
                    ) VALUES %s
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
                """, values, page_size=5000)
            conn.commit()
            logger.info(f"✅ 保存日频基本面: {len(values)} 条")
            return len(values)
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ 保存日频基本面失败: {str(e)}")
            return 0
        finally:
            self._return_conn(conn)

    @_retry_on_error()
    def save_signals(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        self._ensure_connection()
        df = df.copy()
        if 'cycle' not in df.columns:
            df['cycle'] = '1d'
        else:
            df['cycle'] = df['cycle'].apply(self._normalize_cycle)
        if 'signal_direction' not in df.columns:
            df['signal_direction'] = None

        df['code'] = df['code'].astype(str)
        df['signal_type'] = df['signal_type'].astype(str)
        if 'signal_value' in df.columns:
            df['signal_value'] = df['signal_value'].apply(lambda x: Decimal(str(x)) if pd.notnull(x) else None)

        cols = ['code', 'cycle', 'trade_date', 'signal_type', 'signal_direction',
                'signal_value', 'signal_strength', 'description']
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df.where(pd.notnull(df), None)
        values = list(df[cols].itertuples(index=False, name=None))

        conn = self._get_conn()
        try:
            with conn.cursor() as cursor:
                execute_values(cursor, """
                    INSERT INTO trade_signals (
                        code, cycle, trade_date, signal_type, signal_direction,
                        signal_value, signal_strength, description
                    ) VALUES %s
                    ON CONFLICT (code, trade_date, signal_type) DO UPDATE SET
                        signal_value = EXCLUDED.signal_value,
                        signal_strength = EXCLUDED.signal_strength,
                        description = EXCLUDED.description
                """, values, page_size=5000)
            conn.commit()
            logger.info(f"✅ 保存交易信号: {len(values)} 条")
            return len(values)
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ 保存交易信号失败: {str(e)}")
            return 0
        finally:
            self._return_conn(conn)

    @_retry_on_error()
    def save_signals_batch(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        self._ensure_connection()
        required_cols = ['code', 'cycle', 'trade_date', 'signal_type', 'signal_direction',
                         'signal_value', 'signal_strength', 'description']
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            logger.error(f"❌ 缺少必需字段: {missing_cols}")
            return 0

        df = df.copy()
        if 'cycle' in df.columns:
            df['cycle'] = df['cycle'].apply(self._normalize_cycle)
        if 'signal_value' in df.columns:
            df['signal_value'] = df['signal_value'].apply(lambda x: Decimal(str(x)) if pd.notnull(x) else None)
        df = df.where(pd.notnull(df), None)
        values = list(df[required_cols].itertuples(index=False, name=None))

        total_processed = 0
        batch_size = 100000
        conn = self._get_conn()
        try:
            with conn.cursor() as cursor:
                for i in range(0, len(values), batch_size):
                    batch = values[i:i+batch_size]
                    execute_values(cursor, """
                        INSERT INTO trade_signals (
                            code, cycle, trade_date, signal_type, signal_direction,
                            signal_value, signal_strength, description
                        ) VALUES %s
                        ON CONFLICT (code, trade_date, signal_type) DO UPDATE SET
                            signal_value = EXCLUDED.signal_value,
                            signal_strength = EXCLUDED.signal_strength,
                            description = EXCLUDED.description
                    """, batch, page_size=5000)
                    total_processed += len(batch)
                    logger.debug(f"  批次 {i//batch_size + 1}: 处理 {len(batch)} 条")
            conn.commit()
            logger.info(f"✅ 批量保存交易信号: 处理/覆盖 {total_processed} 条")
            return total_processed
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ 批量保存交易信号失败: {str(e)}", exc_info=True)
            return 0
        finally:
            self._return_conn(conn)

    # ==================== 数据查询方法 ====================
    def get_stock_basic(self, code: Optional[str] = None) -> pd.DataFrame:
        self._ensure_connection()
        query = """
            SELECT code, name, exchange, industry, list_date, delist_date,
                   created_at, updated_at
            FROM stock_basic
        """
        params = []
        if code:
            query += " WHERE code = %s"
            params.append(code)
        query += " ORDER BY code"

        conn = self._get_conn()
        try:
            df = pd.read_sql(query, conn, params=params)
            for col in ['list_date', 'delist_date']:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
            return df
        except Exception as e:
            logger.error(f"❌ 获取股票基本信息失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_quotes(self, code: Optional[str] = None, cycle: str = 'daily',
                   start_date: Optional[str] = None, end_date: Optional[str] = None,
                   limit: int = 10000) -> pd.DataFrame:
        self._ensure_connection()
        cycle = self._normalize_cycle(cycle)
        query = """
            SELECT code, cycle, trade_date, open, high, low, close, pre_close,
                   volume, amount, adjust_type
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
        query += " ORDER BY trade_date LIMIT %s"
        params.append(limit)

        conn = self._get_conn()
        try:
            df = pd.read_sql(query, conn, params=params)
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            return df
        except Exception as e:
            logger.error(f"❌ 获取行情数据失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_quotes_batch(self, codes: List[str], cycle: str = 'daily',
                         start_date: Optional[str] = None, end_date: Optional[str] = None,
                         limit: int = 10000) -> pd.DataFrame:
        if not codes:
            return pd.DataFrame()
        self._ensure_connection()
        cycle = self._normalize_cycle(cycle)
        query = """
            SELECT code, cycle, trade_date, open, high, low, close, pre_close,
                   volume, amount, adjust_type
            FROM stock_quotes
            WHERE cycle = %s AND code = ANY(%s)
        """
        params = [cycle, codes]
        if start_date:
            query += " AND trade_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= %s"
            params.append(end_date)
        query += " ORDER BY code, trade_date LIMIT %s"
        params.append(limit)

        conn = self._get_conn()
        try:
            df = pd.read_sql(query, conn, params=params)
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            return df
        except Exception as e:
            logger.error(f"❌ 批量获取行情数据失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_indicators(self, code: str, cycle: str = 'daily',
                       start_date: Optional[str] = None, end_date: Optional[str] = None,
                       limit: int = 10000) -> pd.DataFrame:
        self._ensure_connection()
        cycle = self._normalize_cycle(cycle)
        query = """
            SELECT code, cycle, trade_date, ma5, ma10, ma20, ma60, macd, dif, dea,
                   rsi6, rsi12, rsi24, boll_upper, boll_mid, boll_lower,
                   ema5, ema10, ema20, ema60, atr, vol_ratio, turnover_rate,
                   kdj_k, kdj_d, kdj_j
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
        query += " ORDER BY trade_date LIMIT %s"
        params.append(limit)

        conn = self._get_conn()
        try:
            df = pd.read_sql(query, conn, params=params)
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            return df
        except Exception as e:
            logger.error(f"❌ 获取技术指标失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_indicators_batch(self, codes: List[str], cycle: str = 'daily',
                             start_date: Optional[str] = None, end_date: Optional[str] = None,
                             limit: int = 10000) -> pd.DataFrame:
        if not codes:
            return pd.DataFrame()
        self._ensure_connection()
        cycle = self._normalize_cycle(cycle)
        query = """
            SELECT code, cycle, trade_date, ma5, ma10, ma20, ma60, macd, dif, dea,
                   rsi6, rsi12, rsi24, boll_upper, boll_mid, boll_lower,
                   ema5, ema10, ema20, ema60, atr, vol_ratio, turnover_rate,
                   kdj_k, kdj_d, kdj_j
            FROM stock_indicators
            WHERE code = ANY(%s) AND cycle = %s
        """
        params = [codes, cycle]
        if start_date:
            query += " AND trade_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= %s"
            params.append(end_date)
        query += " ORDER BY code, trade_date LIMIT %s"
        params.append(limit)

        conn = self._get_conn()
        try:
            df = pd.read_sql(query, conn, params=params)
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            return df
        except Exception as e:
            logger.error(f"❌ 批量获取技术指标失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_indicators_with_quotes_batch(self, codes: List[str], cycle: str = 'daily',
                                         start_date: Optional[str] = None,
                                         end_date: Optional[str] = None) -> pd.DataFrame:
        if not codes:
            return pd.DataFrame()
        self._ensure_connection()
        db_cycle = self._normalize_cycle(cycle)
        query = """
            SELECT i.code, i.cycle, i.trade_date,
                   i.ma5, i.ma10, i.ma20, i.ma60,
                   i.dif, i.dea, i.macd,
                   i.rsi6, i.rsi12, i.rsi24,
                   i.boll_upper, i.boll_mid, i.boll_lower,
                   q.close, q.volume
            FROM stock_indicators i
            LEFT JOIN stock_quotes q
                ON i.code = q.code
                AND i.trade_date = q.trade_date
                AND i.cycle = q.cycle
            WHERE i.code = ANY(%s) AND i.cycle = %s
        """
        params = [codes, db_cycle]
        if start_date:
            query += " AND i.trade_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND i.trade_date <= %s"
            params.append(end_date)
        query += " ORDER BY i.code, i.trade_date"

        conn = self._get_conn()
        try:
            df = pd.read_sql(query, conn, params=params)
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            return df
        except Exception as e:
            logger.error(f"❌ 批量获取指标和行情数据失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_pattern_markers(self, code: str, start_date: str, end_date: str) -> List[Dict]:
        """查询指定股票在时间范围内的K线形态标记（TA-Lib预计算结果）

        Args:
            code: 股票代码（标准化格式，如 600000）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            形态标记列表，格式为 [{"date": "2026-07-03", "patterns": ["hammer"]}, ...]
            日期按升序排列，全零日期不返回
        """
        self._ensure_connection()
        pattern_fields = [
            ('pattern_hammer', 'hammer'),
            ('pattern_morning_star', 'morning_star'),
            ('pattern_evening_star', 'evening_star'),
            ('pattern_bullish_engulfing', 'bullish_engulfing'),
            ('pattern_bearish_engulfing', 'bearish_engulfing'),
        ]

        cases = [f"CASE WHEN {col} != 0 THEN '{name}' END AS p_{name}" for col, name in pattern_fields]
        conditions = ' OR '.join([f'{col} != 0' for col, _ in pattern_fields])

        sql = f"""
            SELECT trade_date, {', '.join(cases)}
            FROM stock_indicators
            WHERE code = %(code)s
              AND cycle = '1d'
              AND trade_date BETWEEN %(start_date)s AND %(end_date)s
              AND ({conditions})
            ORDER BY trade_date ASC
        """
        params = {'code': code, 'start_date': start_date, 'end_date': end_date}

        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                col_names = [desc[0] for desc in cur.description]

            markers = []
            for row in rows:
                row_dict = dict(zip(col_names, row))
                patterns = []
                for _, name in pattern_fields:
                    p_col = f'p_{name}'
                    if p_col in row_dict and row_dict[p_col] is not None:
                        patterns.append(name)
                if patterns:
                    markers.append({
                        'date': str(row_dict['trade_date']),
                        'patterns': patterns,
                    })
            return markers
        except Exception as e:
            logger.warning(f"pattern_markers 查询失败 (code={code}): {e}")
            return []
        finally:
            self._return_conn(conn)

    def get_adj_factor(self, code: str, start_date: Optional[str] = None,
                       end_date: Optional[str] = None, limit: int = 10000) -> pd.DataFrame:
        self._ensure_connection()
        query = "SELECT code, trade_date, adj_factor FROM stock_adj_factor WHERE code = %s"
        params = [code]
        if start_date:
            query += " AND trade_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= %s"
            params.append(end_date)
        query += " ORDER BY trade_date LIMIT %s"
        params.append(limit)

        conn = self._get_conn()
        try:
            df = pd.read_sql(query, conn, params=params)
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            return df
        except Exception as e:
            logger.error(f"❌ 获取复权因子失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_trade_calendar(self, start_date: Optional[str] = None,
                           end_date: Optional[str] = None,
                           is_open: Optional[int] = None,
                           limit: int = 10000) -> pd.DataFrame:
        self._ensure_connection()
        query = "SELECT cal_date, is_open, holiday_name FROM trade_calendar WHERE 1=1"
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
        query += " ORDER BY cal_date LIMIT %s"
        params.append(limit)

        conn = self._get_conn()
        try:
            df = pd.read_sql(query, conn, params=params)
            df['cal_date'] = pd.to_datetime(df['cal_date']).dt.date
            return df
        except Exception as e:
            logger.error(f"❌ 获取交易日历失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_daily_basic(self, code: Optional[str] = None,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None,
                        limit: int = 10000) -> pd.DataFrame:
        self._ensure_connection()
        query = """
            SELECT code, trade_date, close, turnover_rate, volume_ratio,
                   pe, pe_ttm, pb, total_mv, circ_mv,
                   dv_ratio, dv_ttm, ps, ps_ttm, float_share
            FROM stock_daily_basic
            WHERE 1=1
        """
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
        query += " ORDER BY trade_date DESC, code LIMIT %s"
        params.append(limit)

        conn = self._get_conn()
        try:
            df = pd.read_sql(query, conn, params=params)
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            return df
        except Exception as e:
            logger.error(f"❌ 获取日频基本面失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_stock_list(self) -> pd.DataFrame:
        self._ensure_connection()
        query = "SELECT code, name, exchange, industry FROM stock_basic ORDER BY code"
        conn = self._get_conn()
        try:
            return pd.read_sql(query, conn)
        except Exception as e:
            logger.error(f"❌ 获取股票列表失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_latest_trade_date(self) -> Optional[str]:
        self._ensure_connection()
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
                result = cur.fetchone()
                return str(result[0]) if result and result[0] else None
        except Exception as e:
            logger.error(f"❌ 获取最新交易日期失败: {str(e)}")
            return None
        finally:
            self._return_conn(conn)

    def get_stock_count(self, cycle: str = 'daily') -> int:
        self._ensure_connection()
        cycle = self._normalize_cycle(cycle)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle = %s", (cycle,))
                result = cur.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"❌ 获取股票数量失败: {str(e)}")
            return 0
        finally:
            self._return_conn(conn)

    def get_data_count(self, cycle: str = 'daily') -> int:
        self._ensure_connection()
        cycle = self._normalize_cycle(cycle)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM stock_quotes WHERE cycle = %s", (cycle,))
                result = cur.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"❌ 获取数据条数失败: {str(e)}")
            return 0
        finally:
            self._return_conn(conn)

    def get_signals(self, code: Optional[str] = None, cycle: str = 'daily',
                    start_date: Optional[str] = None, end_date: Optional[str] = None,
                    signal_type: Optional[str] = None, limit: int = 10000) -> pd.DataFrame:
        self._ensure_connection()
        cycle = self._normalize_cycle(cycle)
        query = """
            SELECT code, cycle, trade_date, signal_type, signal_direction,
                   signal_value, signal_strength, description
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
        query += " ORDER BY trade_date DESC, code LIMIT %s"
        params.append(limit)

        conn = self._get_conn()
        try:
            df = pd.read_sql(query, conn, params=params)
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            return df
        except Exception as e:
            logger.error(f"❌ 获取交易信号失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)

    def get_last_signal_date(self, code: str, cycle: str = 'daily') -> Optional[datetime]:
        self._ensure_connection()
        cycle = self._normalize_cycle(cycle)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(trade_date) FROM trade_signals WHERE code = %s AND cycle = %s",
                    (code, cycle)
                )
                result = cur.fetchone()
                return result[0] if result and result[0] else None
        except Exception as e:
            logger.error(f"❌ 获取最后信号日期失败 {code}: {str(e)}")
            return None
        finally:
            self._return_conn(conn)

    def get_last_signal_dates_batch(self, codes: List[str], cycle: str = 'daily') -> Dict[str, Optional[datetime]]:
        if not codes:
            return {}
        self._ensure_connection()
        cycle = self._normalize_cycle(cycle)
        conn = self._get_conn()
        try:
            query = """
                SELECT code, MAX(trade_date) as last_date
                FROM trade_signals
                WHERE code = ANY(%s) AND cycle = %s
                GROUP BY code
            """
            df = pd.read_sql(query, conn, params=(codes, cycle))
            result_dict = df.set_index('code')['last_date'].to_dict()
            return {code: result_dict.get(code) for code in codes}
        except Exception as e:
            logger.error(f"❌ 批量获取最后信号日期失败: {str(e)}")
            return {code: None for code in codes}
        finally:
            self._return_conn(conn)

    def get_kline_with_indicators(self, code: str, cycle: str = 'daily',
                                  start_date: Optional[str] = None,
                                  end_date: Optional[str] = None,
                                  limit: int = 100) -> pd.DataFrame:
        self._ensure_connection()
        cycle_val = self._normalize_cycle(cycle)
        query = """
            SELECT q.trade_date, q.open, q.high, q.low, q.close, q.volume, q.amount,
                   b.pe_ttm, b.pb, b.circ_mv, b.turnover_rate,
                   i.ma5, i.ma10, i.ma20, i.ma60, i.dif, i.dea, i.macd,
                   i.rsi6, i.rsi12, i.rsi24
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

        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                colnames = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                if not rows:
                    return pd.DataFrame()
                df = pd.DataFrame(rows, columns=colnames)
                df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
                return df.sort_values('trade_date').reset_index(drop=True)
        except Exception as e:
            logger.error(f"❌ 获取带指标 K 线数据失败: {str(e)}")
            return pd.DataFrame()
        finally:
            self._return_conn(conn)