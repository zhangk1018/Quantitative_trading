"""
数据同步容错工具模块 (v1.3 最终封版)
包含所有 RULE 和 ACTION/PATCH 的最终修正
"""
import logging
import pandas as pd
import numpy as np
import psycopg2
from psycopg2 import IntegrityError, OperationalError, InterfaceError
from psycopg2.extras import execute_values, Json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import time

logger = logging.getLogger(__name__)

class ErrorCode:
    MISSING_FIELD = 'ERR_MISSING_FIELD'
    PRICE_NULL = 'ERR_PRICE_NULL'
    HIGH_LT_LOW = 'ERR_HIGH_LT_LOW'
    HIGH_LT_OC = 'ERR_HIGH_LT_OC'
    LOW_GT_OC = 'ERR_LOW_GT_OC'
    PRICE_INVALID = 'ERR_PRICE_INVALID'
    VOLUME_INVALID = 'ERR_VOLUME_INVALID'
    AMOUNT_INVALID = 'ERR_AMOUNT_INVALID'

class DataValidator:
    @staticmethod
    def validate_quotes_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        if df.empty: return df, pd.DataFrame()
        
        n_rows = len(df)
        error_mask = np.zeros(n_rows, dtype=bool)
        error_codes: List[List[str]] = [[] for _ in range(n_rows)]
        
        required_columns = ['code', 'cycle', 'trade_datetime', 'open', 'high', 'low', 'close']
        for col in required_columns:
            if col in df.columns:
                mask = df[col].isna().values
                error_mask |= mask
                for i in np.where(mask)[0]: error_codes[i].append(ErrorCode.MISSING_FIELD)
        
        if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
            price_null_mask = (df['open'].isna() | df['high'].isna() | df['low'].isna() | df['close'].isna()).values
            error_mask |= price_null_mask
            for i in np.where(price_null_mask)[0]: error_codes[i].append(ErrorCode.PRICE_NULL)
            
            valid_price_mask = ~price_null_mask
            if valid_price_mask.any():
                hl_mask = valid_price_mask & (df['high'] < df['low']).values
                error_mask |= hl_mask
                for i in np.where(hl_mask)[0]: error_codes[i].append(ErrorCode.HIGH_LT_LOW)
                
                h_oc_mask = valid_price_mask & (df['high'] < df[['open', 'close']].max(axis=1)).values
                error_mask |= h_oc_mask
                for i in np.where(h_oc_mask)[0]: error_codes[i].append(ErrorCode.HIGH_LT_OC)
                
                l_oc_mask = valid_price_mask & (df['low'] > df[['open', 'close']].min(axis=1)).values
                error_mask |= l_oc_mask
                for i in np.where(l_oc_mask)[0]: error_codes[i].append(ErrorCode.LOW_GT_OC)
                
                for price_col in ['open', 'high', 'low', 'close']:
                    invalid_price_mask = valid_price_mask & (df[price_col] <= 0).values
                    error_mask |= invalid_price_mask
                    for i in np.where(invalid_price_mask)[0]: error_codes[i].append(f"{ErrorCode.PRICE_INVALID}:{price_col}")
        
        error_indices = np.where(error_mask)[0]
        valid_indices = np.where(~error_mask)[0]
        
        valid_df = df.iloc[valid_indices].copy()
        dirty_df = df.iloc[error_indices].copy()
        
        if not dirty_df.empty:
            dirty_df['error_type'] = 'validation_failed'
            dirty_df['error_codes'] = [','.join(error_codes[i]) for i in error_indices]
            dirty_df['error_message'] = [f"batch@row{error_indices[i]}" for i in range(len(error_indices))]
            dirty_df['discovery_time'] = datetime.now()
            
        return valid_df, dirty_df

class SyncCheckpointManager:
    def __init__(self, conn): self.conn = conn

    def update_checkpoint(self, code: str, cycle: str, last_sync_datetime: datetime, sync_count: int = 0, is_continuous: bool = True):
        try:
            cursor = self.conn.cursor()
            # [ACTION-1] 核心修复：若断层(is_continuous=False)，则保持原水位线不变，防止伪推进
            cursor.execute("""
                INSERT INTO sync_checkpoints (
                    code, cycle, last_sync_datetime, last_continuous_sync_datetime,
                    sync_count, is_continuous, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code, cycle) DO UPDATE SET
                    last_sync_datetime = CASE WHEN EXCLUDED.is_continuous THEN EXCLUDED.last_sync_datetime ELSE sync_checkpoints.last_sync_datetime END,
                    last_continuous_sync_datetime = CASE WHEN EXCLUDED.is_continuous THEN EXCLUDED.last_sync_datetime ELSE sync_checkpoints.last_continuous_sync_datetime END,
                    sync_count = sync_checkpoints.sync_count + EXCLUDED.sync_count,
                    is_continuous = EXCLUDED.is_continuous,
                    updated_at = EXCLUDED.updated_at
            """, (code, cycle, last_sync_datetime, last_sync_datetime, sync_count, is_continuous, datetime.now()))
            cursor.close()
        except Exception as e:
            logger.error(f"❌ 更新检查点失败: {str(e)}")
            raise

class DirtyDataHandler:
    def __init__(self, conn): self.conn = conn

    def save_dirty_data(self, df: pd.DataFrame) -> int:
        if df.empty: return 0
        try:
            cursor = self.conn.cursor()
            records = []
            base_cols = {'code', 'cycle', 'trade_datetime', 'error_type', 'error_message', 'error_codes', 'discovery_time'}
            sample_cols = [c for c in df.columns if c not in base_cols]
            
            for tup in df.itertuples(index=False, name=None):
                row_dict = dict(zip(df.columns, tup))
                raw_data = {col: (None if pd.isna(row_dict.get(col)) else row_dict.get(col)) for col in sample_cols}
                
                records.append((
                    row_dict.get('code'), row_dict.get('cycle'), row_dict.get('trade_datetime'),
                    Json(raw_data), # [PATCH-2.2] 使用 psycopg2.extras.Json 确保类型安全
                    row_dict.get('error_type', 'unknown'),
                    ','.join(row_dict.get('error_codes', []))
                ))
            
            execute_values(cursor, "INSERT INTO stock_quotes_dirty (code, cycle, trade_datetime, raw_data, error_type, error_message) VALUES %s", records, page_size=1000)
            return len(records)
        except Exception as e:
            logger.error(f"❌ 保存脏数据失败: {str(e)}")
            raise

class QuotesUpsertWriter:
    def __init__(self, conn): self.conn = conn

    def upsert_quotes(self, df: pd.DataFrame) -> Dict[str, int]:
        if df.empty: return {'inserted': 0, 'updated': 0, 'skipped': 0}
        result = {'inserted': 0, 'updated': 0, 'skipped': 0}
        
        try:
            cursor = self.conn.cursor()
            
            # [PATCH-1.3 & ACTION-5] 强制清理残留临时表，防止连接池复用报错
            cursor.execute("DROP TABLE IF EXISTS temp_quotes")
            cursor.execute("""
                CREATE TEMPORARY TABLE temp_quotes (
                    code VARCHAR(10), cycle VARCHAR(10), trade_datetime TIMESTAMPTZ,
                    open REAL, high REAL, low REAL, close REAL, volume BIGINT,
                    amount DOUBLE PRECISION, pct_chg REAL, turnover_rate REAL, adjust_type VARCHAR(10)
                ) ON COMMIT DROP
            """)
            
            # [ACTION-3] 启用 Pandas C 引擎转换，彻底废弃低效的 itertuples+zip 手动推导
            records_list = df.to_dict('records')
            records = []
            for row in records_list:
                records.append((
                    row.get('code'), row.get('cycle'), row.get('trade_datetime'),
                    row.get('open'), row.get('high'), row.get('low'), row.get('close'),
                    row.get('volume'), row.get('amount'), row.get('pct_chg'),
                    row.get('turnover_rate'), row.get('adjust_type') or 'qfq'
                ))
            
            execute_values(cursor, "INSERT INTO temp_quotes (code, cycle, trade_datetime, open, high, low, close, volume, amount, pct_chg, turnover_rate, adjust_type) VALUES %s", records, page_size=1000)
            
            cursor.execute("SELECT COUNT(*) FROM stock_quotes sq INNER JOIN temp_quotes tq ON sq.code = tq.code AND sq.cycle = tq.cycle AND sq.trade_datetime = tq.trade_datetime")
            conflict_count = cursor.fetchone()[0]
            
            cursor.execute("""
                INSERT INTO stock_quotes (code, cycle, trade_datetime, open, high, low, close, volume, amount, pct_chg, turnover_rate, adjust_type, update_time)
                SELECT code, cycle, trade_datetime, open, high, low, close, volume, amount, pct_chg, turnover_rate, adjust_type, %s
                FROM temp_quotes
                ON CONFLICT (code, cycle, trade_datetime) DO UPDATE SET
                    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close,
                    volume = EXCLUDED.volume, amount = EXCLUDED.amount, pct_chg = EXCLUDED.pct_chg,
                    turnover_rate = EXCLUDED.turnover_rate, adjust_type = EXCLUDED.adjust_type, update_time = EXCLUDED.update_time
            """, (datetime.now(),))
            
            result['updated'] = conflict_count
            result['inserted'] = cursor.rowcount - conflict_count
            cursor.close()
        except Exception as e:
            logger.error(f"❌ Upsert失败: {str(e)}")
            raise
        return result

class RetryHandler:
    @staticmethod
    def retry_with_backoff(func, max_retries=3, initial_delay=1.0, exceptions=(Exception,), connection_reset_callback=None):
        def wrapper(*args, **kwargs):
            retries, delay = 0, initial_delay
            while retries <= max_retries:
                try: return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries > max_retries: raise
                    if isinstance(e, (OperationalError, InterfaceError)) and connection_reset_callback:
                        connection_reset_callback()
                    time.sleep(delay)
                    delay = min(delay * 2.0, 60.0)
        return wrapper

class DataSyncOrchestrator:
    def __init__(self, conn):
        self.conn = conn
        self.validator = DataValidator()
        self.checkpoint_manager = SyncCheckpointManager(conn)
        self.dirty_handler = DirtyDataHandler(conn)
        self.upsert_writer = QuotesUpsertWriter(conn)

    def sync_stock_data(self, code: str, cycle: str, df: pd.DataFrame, expected_count: Optional[int] = None) -> Dict[str, Any]:
        result = {'code': code, 'cycle': cycle, 'success': False, 'is_continuous': True}
        if df.empty: return result
        
        valid_df, dirty_df = self.validator.validate_quotes_data(df)
        if not dirty_df.empty: self.dirty_handler.save_dirty_data(dirty_df)
        if valid_df.empty: return result
        
        try:
            with self.conn: # [RULE-2.1] 统一事务边界
                upsert_result = self.upsert_writer.upsert_quotes(valid_df)
                
                max_datetime = valid_df['trade_datetime'].max()
                is_continuous = True
                if expected_count is not None and len(valid_df) != expected_count:
                    is_continuous = False
                    
                self.checkpoint_manager.update_checkpoint(code, cycle, max_datetime, len(valid_df), is_continuous)
                result['success'] = True
                result['is_continuous'] = is_continuous
        except Exception as e:
            try: self.conn.rollback()
            except: pass
            logger.error(f"❌ 同步失败: {str(e)}")
        return result

class RobustDataSyncOrchestrator(DataSyncOrchestrator):
    def __init__(self, conn, pool=None):
        super().__init__(conn)
        self.db_pool = pool
        self._current_conn = conn

    def _reset_connection(self):
        if self.db_pool and self._current_conn:
            self.db_pool.discard_connection(self._current_conn)
            new_conn = self.db_pool.get_connection()
            self._current_conn = new_conn
            self.conn = new_conn
            self.checkpoint_manager = SyncCheckpointManager(new_conn)
            self.dirty_handler = DirtyDataHandler(new_conn)
            self.upsert_writer = QuotesUpsertWriter(new_conn)

    def sync_stock_data_with_retry(self, code: str, cycle: str, df: pd.DataFrame, expected_count: Optional[int] = None):
        @RetryHandler.retry_with_backoff(
            max_retries=3, exceptions=(OperationalError, InterfaceError),
            connection_reset_callback=self._reset_connection
        )
        def _retry_sync():
            # [PATCH-1.1] 显式传递 class 和 self，修复闭包 super() 丢失上下文问题
            return super(RobustDataSyncOrchestrator, self).sync_stock_data(code, cycle, df, expected_count)
        
        try: return _retry_sync()
        except IntegrityError: raise
        except Exception as e: logger.error(f"❌ 最终同步失败: {str(e)}"); raise