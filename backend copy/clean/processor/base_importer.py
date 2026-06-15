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
from utils.stock_code_utils import normalize_code, is_a_stock

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
        """标准化股票代码格式，统一为6位纯数字
        
        委托 utils.stock_code_utils.normalize_code 实现，
        支持科创板(688xxx)、北交所(8xxxxx)等全市场代码。
        """
        return normalize_code(code)

    @staticmethod
    def validate_stock_code(code: str) -> bool:
        """校验股票代码是否为合法A股代码
        
        委托 utils.stock_code_utils.is_a_stock 实现，
        支持科创板(688xxx)、北交所(8xxxxx)等全市场代码。
        """
        return is_a_stock(code)

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
            except Exception as e:
                # 识别 Tushare 限频异常：1次/分钟 或 1次/小时
                msg = str(e)
                if '频率超限' in msg or 'rate limit' in msg.lower():
                    # 提取限制时间: 例如 "1次/小时" 或 "1次/分钟"
                    import re
                    m = re.search(r'(\d+)次/(\w+)', msg)
                    if m:
                        unit = m.group(2)
                        if '小时' in unit or 'hour' in unit.lower():
                            wait_sec = 3700  # 超过 1 小时
                        else:
                            wait_sec = 65
                    else:
                        wait_sec = 65

                    logger.warning(
                        f"⚠️  Tushare 限频 (第 {attempt}/{max_retries} 次): {msg}"
                    )
                    if attempt < max_retries:
                        logger.info(f"    {wait_sec}秒后重试...")
                        time.sleep(wait_sec)
                        continue
                    raise
                # token 无效等明确错误：直接抛出
                if 'token' in msg.lower() and ('invalid' in msg.lower() or '无效' in msg):
                    logger.error(f"❌ Tushare token 无效: {e}")
                    raise
                # 其他未知异常：不重试
                raise

        raise last_error

    @staticmethod
    def retry_with_failover(sources: list, method_name: str, max_total_attempts: int = 6,
                            initial_delay: int = 5, **kwargs):
        """多数据源故障切换重试（带指数退避）

        适用于 Baostock → Tushare 故障切换场景：
        1. 优先调用第 1 个数据源
        2. 失败后自动切换到下一个数据源
        3. 每个数据源内部走指数退避
        4. 全部失败时抛错

        Args:
            sources: 数据源列表（按优先级排序）
            method_name: 要调用的方法名
            max_total_attempts: 总尝试次数上限（所有源合计）
            initial_delay: 初始延迟
            **kwargs: 方法参数

        Returns:
            方法返回值

        Raises:
            最后一次重试仍失败的异常
        """
        import time

        attempts_left = max_total_attempts
        last_error = None
        delay = initial_delay
        tried = set()

        for idx, source in enumerate(sources):
            if attempts_left <= 0:
                break
            if idx in tried:
                continue
            tried.add(idx)

            try:
                method = getattr(source, method_name)
                # 对单数据源做退避重试
                for attempt in range(1, attempts_left + 1):
                    try:
                        return method(**kwargs)
                    except (ConnectionError, TimeoutError, OSError) as e:
                        last_error = e
                        logger.warning(
                            f"⚠️  [{source.name}] 网络异常 (第 {attempt}): {e}"
                        )
                        if attempt < attempts_left:
                            time.sleep(delay)
                            delay = min(delay * 2, 30)
                            attempts_left -= 1
                        else:
                            break
            except Exception as e:
                last_error = e
                msg = str(e)
                if '频率超限' in msg or 'rate limit' in msg.lower():
                    logger.warning(f"⚠️  [{source.name}] 限频，切换下一数据源")
                elif 'token' in msg.lower() and 'invalid' in msg.lower():
                    logger.warning(f"⚠️  [{source.name}] token 异常，切换下一数据源")
                else:
                    logger.warning(f"⚠️  [{source.name}] 异常: {e}，切换下一数据源")
                delay = initial_delay  # 切换后重置 delay
                continue

        if last_error:
            raise last_error
        raise RuntimeError("无可用数据源")

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