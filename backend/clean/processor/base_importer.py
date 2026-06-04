#!/usr/bin/env python3
"""
数据导入基类

功能：
- 统一处理DB连接、任务进度、股票代码格式化、股票列表获取
- 提供上下文管理器支持
- 所有Importer类应继承此类
- 支持 LRU 缓存优化高频查询

用法：
    from base_importer import BaseDataImporter

    class DailyDataImporter(BaseDataImporter):
        def import_stock_data(self, code: str, start_date: str, end_date: str) -> int:
            # 实现具体的数据导入逻辑
            pass
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import re
import pandas as pd
import numpy as np
from psycopg2.extras import execute_values
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
from functools import lru_cache

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('base_importer')


class BaseDataImporter(ABC):
    """数据导入器抽象基类"""

    def __init__(self):
        self._storage = None  # 惰性初始化
        self._storage_config = None
        self.task_id = None
        # 缓存字典，用于存储高频查询结果
        self._last_trade_time_cache = {}
        self._stock_list_cache = None
        self._cache_enabled = True

    def _init_storage(self) -> PostgreSQLStorage:
        """惰性初始化存储连接"""
        if self._storage is None:
            if self._storage_config is None:
                self._storage_config = config.storage.get('postgresql', {})
            self._storage = PostgreSQLStorage(self._storage_config)
            self._storage.connect()
            logger.debug(f"{self.__class__.__name__} 数据库连接已建立")
        return self._storage

    @property
    def storage(self) -> PostgreSQLStorage:
        """存储连接属性 - 惰性获取"""
        return self._init_storage()

    @storage.setter
    def storage(self, value: PostgreSQLStorage):
        """设置存储连接"""
        self._storage = value

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口 - 包含异常回滚逻辑"""
        if exc_type is not None:
            # 发生异常时回滚未提交的事务
            if self._storage and self._storage.conn:
                try:
                    self._storage.conn.rollback()
                    logger.warning(f"{self.__class__.__name__} 异常回滚事务")
                except Exception as e:
                    logger.error(f"回滚事务失败: {e}")
        self.disconnect()
        return False

    def _ensure_db_connected(self):
        """检查数据库连接状态，断开时自动重连（长任务保活）

        在 full_import 等长时间循环中定期调用，防止连接超时断开。
        """
        if self._storage is None:
            self._init_storage()
            return
        try:
            with self._storage.conn.cursor() as cur:
                cur.execute('SELECT 1')
        except Exception:
            logger.warning("⚠️ 数据库连接已断开，尝试重连...")
            try:
                self._storage.disconnect()
            except Exception:
                pass
            self._storage = None
            self._init_storage()
            logger.info("✅ 数据库重连成功")

    def update_task_progress(self, status: str, progress: int = None, message: str = None):
        """更新任务进度"""
        if not self.task_id:
            return

        update_fields = ['updated_at = CURRENT_TIMESTAMP']
        params = []

        valid_status = ['running', 'completed', 'failed']
        if status and status in valid_status:
            update_fields.append("status = %s")
            params.append(status)

        if progress is not None and isinstance(progress, int) and 0 <= progress <= 100:
            update_fields.append("progress = %s")
            params.append(progress)

        if message:
            message = message[:255]
            update_fields.append("message = %s")
            params.append(message)

        params.append(self.task_id)
        sql = f"UPDATE task_progress SET {', '.join(update_fields)} WHERE id = %s"

        try:
            cursor = self.storage.conn.cursor()
            cursor.execute(sql, tuple(params))
            self.storage.conn.commit()
        except Exception as e:
            logger.error(f"更新任务进度失败: {e}")

    def create_task(self, task_name: str, params: dict = None) -> int:
        """创建任务记录"""
        cursor = self.storage.conn.cursor()
        cursor.execute("""
            INSERT INTO task_progress (task_name, status, progress, created_at, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """, (task_name, 'running', 0))

        self.task_id = cursor.fetchone()[0]
        self.storage.conn.commit()
        logger.info(f"创建任务: {task_name}, id={self.task_id}")
        return self.task_id

    def get_stock_list(self) -> List[str]:
        """获取股票列表（排除已退市股票）- 子类可重写"""
        cursor = self.storage.conn.cursor()
        cursor.execute("SELECT code FROM stock_basic WHERE delist_date IS NULL ORDER BY code")
        rows = cursor.fetchall()
        return [row[0] for row in rows]

    @staticmethod
    def _format_code(code: str) -> Optional[str]:
        """标准化股票代码格式，统一为6位数字
        
        Args:
            code: 股票代码（支持多种格式：000001, sz000001, 000001.SZ, sh.600000）
        
        Returns:
            标准化后的6位数字代码，格式不合法返回None
        
        支持的输入格式：
            - 纯数字：600000
            - 带市场前缀：sh600000, sz000001
            - 带点分隔：600000.SH, 000001.SZ, sh.600000, sz.000001
        """
        if not code:
            return None
        
        code = str(code).strip()
        
        # 移除市场标识后缀/前缀
        code = code.replace('.SH', '').replace('.SZ', '').replace('.sh', '').replace('.sz', '')
        code = code.replace('SH', '').replace('SZ', '').replace('sh', '').replace('sz', '')
        code = code.replace('.', '')
        
        # 校验是否为6位数字
        if len(code) == 6 and code.isdigit():
            # 进一步校验A股代码范围
            # 支持的A股代码：
            # - 沪市主板：600xxx, 601xxx, 603xxx, 605xxx
            # - 深市主板：000xxx, 001xxx
            # - 中小板：002xxx
            # - 创业板：300xxx, 301xxx
            # 不支持：科创板(688xxx)、B股(900xxx/200xxx)、北交所(8xxx)
            if code.startswith('60') and not code.startswith('688'):  # 沪市主板（排除科创板）
                return code
            elif code.startswith('000') or code.startswith('001'):  # 深市主板
                return code
            elif code.startswith('002'):  # 中小板
                return code
            elif code.startswith('30'):  # 创业板（300xxx, 301xxx）
                return code
        
        logger.warning(f"股票代码格式不合法: {code}")
        return None

    @staticmethod
    def validate_stock_code(code: str) -> bool:
        """校验股票代码格式（6位数字，且符合A股代码规则）
        
        A股代码规则：
            - 60开头：上海证券交易所主板（排除688科创板）
            - 000/001开头：深圳证券交易所主板
            - 002开头：深圳证券交易所中小板
            - 30开头：深圳证券交易所创业板
        
        Returns:
            True表示格式合法，False表示格式不合法
        """
        if not code:
            return False
        
        code = str(code).strip()
        match = re.match(r'^\d{6}$', code)
        if not match:
            return False
        
        prefix = code[:2]
        # 60开头但不是688（科创板）
        if prefix == '60' and not code.startswith('688'):
            return True
        # 00开头（000/001/002）
        elif prefix == '00':
            return True
        # 30开头（创业板）
        elif prefix == '30':
            return True
        
        return False

    def get_last_trade_date(self, code: str) -> Optional[str]:
        """获取股票最后交易日"""
        cursor = self.storage.conn.cursor()
        cursor.execute("""
            SELECT MAX(trade_date) FROM stock_quotes
            WHERE code = %s AND cycle = '1d'
        """, (code,))
        result = cursor.fetchone()[0]
        return str(result) if result else None

    def batch_get_last_trade_date(self, codes: List[str]) -> Dict[str, Optional[str]]:
        """批量查询多只股票的最后交易日（减少数据库轮询）
        
        Args:
            codes: 股票代码列表（支持带前缀如 SZ.000001 或纯数字 000001）
            
        Returns:
            股票代码到最后交易日的映射字典（保留原始输入格式）
        """
        result = {}
        if not codes:
            return result
        
        # 构建代码映射：原始代码 -> 纯数字代码（用于查询）
        code_mapping = {}
        numeric_codes = []
        for code in codes:
            # 去除前缀 SZ. 或 sh. 等
            numeric_code = code.replace('SZ.', '').replace('sz.', '').replace('SH.', '').replace('sh.', '')
            code_mapping[code] = numeric_code
            numeric_codes.append(numeric_code)
            
        placeholders = ','.join(['%s'] * len(numeric_codes))
        sql = f"""
            SELECT code, MAX(trade_date) 
            FROM stock_quotes
            WHERE code IN ({placeholders}) AND cycle = '1d'
            GROUP BY code
        """
        
        with self.storage.conn.cursor() as cursor:
            cursor.execute(sql, tuple(numeric_codes))
            rows = cursor.fetchall()
            
            # 构建数值代码到日期的映射
            numeric_result = {row[0]: str(row[1]) if row[1] else None for row in rows}
            
            # 将结果映射回原始代码格式
            for original_code, numeric_code in code_mapping.items():
                result[original_code] = numeric_result.get(numeric_code)
        
        logger.debug(f"批量查询日数据最后交易日完成: {len(codes)} 只股票")
        return result

    @abstractmethod
    def import_stock_data(self, code: str, start_date: str, end_date: str) -> int:
        """导入单只股票数据 - 子类必须实现"""
        pass

    def disconnect(self):
        """手动断开连接（带状态校验）"""
        if self._storage is not None:
            try:
                # 检查连接是否仍处于打开状态
                if hasattr(self._storage, 'conn') and self._storage.conn is not None:
                    self._storage.disconnect()
                    logger.info(f"{self.__class__.__name__} 数据库连接已关闭")
            except Exception as e:
                logger.error(f"断开数据库连接失败: {e}")
            finally:
                self._storage = None
        
        # 断开连接时清空缓存
        self.clear_cache()

    def clear_cache(self):
        """清空所有缓存"""
        self._last_trade_time_cache.clear()
        self._stock_list_cache = None
        logger.debug(f"{self.__class__.__name__} 缓存已清空")

    def enable_cache(self, enabled: bool = True):
        """启用或禁用缓存"""
        self._cache_enabled = enabled
        if not enabled:
            self.clear_cache()
        logger.debug(f"{self.__class__.__name__} 缓存状态: {'启用' if enabled else '禁用'}")

    def get_cached_last_trade_time(self, code: str, cycle: str) -> Optional[datetime]:
        """获取缓存的最新交易时间（高频查询优化）
        
        Args:
            code: 股票代码
            cycle: 周期
            
        Returns:
            最新交易时间，如果缓存中不存在则从数据库查询
        """
        if not self._cache_enabled:
            return self._get_last_trade_time_from_db(code, cycle)
        
        cache_key = f"{code}_{cycle}"
        if cache_key in self._last_trade_time_cache:
            cached_time = self._last_trade_time_cache[cache_key]
            logger.debug(f"缓存命中: {cache_key} -> {cached_time}")
            return cached_time
        
        # 缓存未命中，从数据库查询
        result = self._get_last_trade_time_from_db(code, cycle)
        self._last_trade_time_cache[cache_key] = result
        return result

    def _get_last_trade_time_from_db(self, code: str, cycle: str) -> Optional[datetime]:
        """从数据库获取最新交易时间（实际查询）"""
        with self.storage.conn.cursor() as cursor:
            cursor.execute("""
                SELECT MAX(trade_time) FROM stock_quotes_minute
                WHERE code = %s AND cycle = %s
            """, (code, cycle))
            row = cursor.fetchone()
        return row[0] if row and row[0] else None

    def get_cached_stock_list(self) -> List[str]:
        """获取缓存的股票列表（高频查询优化）"""
        if not self._cache_enabled:
            return self.get_stock_list()
        
        if self._stock_list_cache is not None:
            logger.debug(f"股票列表缓存命中: {len(self._stock_list_cache)} 只股票")
            return self._stock_list_cache
        
        # 缓存未命中，从数据库查询
        self._stock_list_cache = self.get_stock_list()
        logger.debug(f"股票列表缓存已更新: {len(self._stock_list_cache)} 只股票")
        return self._stock_list_cache

    def batch_get_last_trade_time(self, codes: List[str], cycle: str) -> Dict[str, Optional[datetime]]:
        """批量查询多只股票的最新交易时间（减少数据库轮询）
        
        Args:
            codes: 股票代码列表
            cycle: 周期
            
        Returns:
            股票代码到最新交易时间的映射字典
        """
        result = {}
        
        # 先检查缓存
        uncached_codes = []
        for code in codes:
            cache_key = f"{code}_{cycle}"
            if self._cache_enabled and cache_key in self._last_trade_time_cache:
                result[code] = self._last_trade_time_cache[cache_key]
            else:
                uncached_codes.append(code)
        
        # 批量查询未缓存的股票
        if uncached_codes:
            placeholders = ','.join(['%s'] * len(uncached_codes))
            sql = f"""
                SELECT code, MAX(trade_time) 
                FROM stock_quotes_minute
                WHERE code IN ({placeholders}) AND cycle = %s
                GROUP BY code
            """
            
            with self.storage.conn.cursor() as cursor:
                cursor.execute(sql, tuple(uncached_codes) + (cycle,))
                rows = cursor.fetchall()
                
                for code, last_time in rows:
                    result[code] = last_time
                    if self._cache_enabled:
                        self._last_trade_time_cache[f"{code}_{cycle}"] = last_time
                
                # 处理数据库中没有记录的股票
                for code in uncached_codes:
                    if code not in result:
                        result[code] = None
                        if self._cache_enabled:
                            self._last_trade_time_cache[f"{code}_{cycle}"] = None
        
        logger.debug(f"批量查询完成: {len(codes)} 只股票，缓存命中 {len(codes) - len(uncached_codes)} 只")
        return result

    @staticmethod
    def validate_cycles(cycles: List[str]) -> List[str]:
        """校验周期参数是否合法
        
        Args:
            cycles: 周期列表
            
        Returns:
            校验通过的周期列表
            
        Raises:
            ValueError: 发现非法周期
        """
        valid_cycles = {'1m', '5m', '15m', '30m', '60m', '1d', '1w', '1M'}
        if not cycles:
            return []
            
        invalid_cycles = [c for c in cycles if c not in valid_cycles]
        if invalid_cycles:
            raise ValueError(f"非法周期: {invalid_cycles}，有效值: {sorted(valid_cycles)}")
            
        return cycles

    @staticmethod
    def validate_date(date_str: str) -> str:
        """校验日期格式是否为 YYYY-MM-DD

        Args:
            date_str: 日期字符串

        Returns:
            校验通过的日期字符串

        Raises:
            ValueError: 日期格式非法
        """
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
        except ValueError:
            raise ValueError(f"日期格式非法: {date_str}，请使用 YYYY-MM-DD")

    @staticmethod
    def retry_on_network_error(func, *args, max_retries: int = 3, initial_delay: int = 5,
                               max_delay: int = 30, **kwargs):
        """网络请求重试装饰器/包装器（指数退避）

        Args:
            func: 需要重试的函数
            *args: 函数位置参数
            max_retries: 最大重试次数，默认3次
            initial_delay: 初始延迟秒数，默认5秒
            max_delay: 最大延迟秒数，默认30秒
            **kwargs: 函数关键字参数

        Returns:
            函数返回值

        Raises:
            最后一次重试仍然失败的异常

        用法:
            # 作为装饰器
            @BaseDataImporter.retry_on_network_error(max_retries=3)
            def fetch_data(code):
                ...

            # 作为包装器
            result = BaseDataImporter.retry_on_network_error(
                some_function, arg1, arg2, max_retries=3
            )
        """
        import time

        delay = initial_delay
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                return func(*args, **kwargs)
            except (ConnectionError, TimeoutError, OSError) as e:
                last_error = e
                logger.warning(
                    f"⚠️  网络异常 (第 {attempt}/{max_retries} 次): {e}"
                )
                if attempt < max_retries:
                    logger.info(f"    {delay}秒后重试...")
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)
                else:
                    logger.error(f"❌ 重试 {max_retries} 次后仍失败")
                    raise

        raise last_error

    @staticmethod
    def validate_date_range(start_date: str, end_date: str) -> None:
        """校验日期范围是否合法 (start <= end)
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Raises:
            ValueError: 日期范围非法
        """
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        if start > end:
            raise ValueError(f"日期范围非法: {start_date} > {end_date}")

    def batch_write_to_db(self, df: pd.DataFrame, table: str, write_cols: List[str],
                           update_cols: List[str], max_batch_size: int = 5000) -> int:
        """通用批量写入数据库方法（支持 ON CONFLICT 更新）
        
        Args:
            df: 待写入的数据
            table: 目标表名
            write_cols: 写入列列表
            update_cols: 冲突时更新列列表
            max_batch_size: 单批次最大写入条数
            
        Returns:
            成功写入的记录总数
        """
        if df is None or df.empty:
            return 0

        df_write = df[write_cols].copy()
        # 向量化替换 NaN/Inf -> None，Psycopg2 原生支持
        df_write = df_write.replace({np.nan: None, np.inf: None, -np.inf: None, pd.NaT: None})
        values = df_write.values.tolist()

        update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_cols])

        sql = f"""
            INSERT INTO {table} ({', '.join(write_cols)})
            VALUES %s
            ON CONFLICT (code, cycle, trade_date, trade_time)
            DO UPDATE SET {update_clause}, created_at = CURRENT_TIMESTAMP
        """

        total_written = 0
        try:
            with self.storage.conn.cursor() as cursor:
                for i in range(0, len(values), max_batch_size):
                    batch = values[i: i + max_batch_size]
                    execute_values(cursor, sql, batch, page_size=1000)
                    self.storage.conn.commit()
                    total_written += len(batch)
            return total_written
        except Exception as e:
            self.storage.conn.rollback()
            logger.error(f"批量写入 {table} 失败: {e}")
            return total_written