#!/usr/bin/env python3
"""
日线数据导入脚本
功能：
- 从数据源拉取日线K线（优先前复权源：Baostock，兜底不复权源：Tushare→pytdx）
- 不复权数据源（Tushare/pytdx）自动通过 stock_adj_factor 转换为前复权
- 写入 stock_quotes 表
- 利用 task_progress 记录状态
- 支持全量导入和增量导入
- 完整度熔断机制：防止数据拉取中断后产生"假成功"

数据源优先级链（全量导入直连模式）：
  Baostock (前复权, 主) → Tushare (不复权→转换, 备1)
  注：pytdx 仅通过 DataSourceManager 在增量/单只模式兜底，全量模式不启用（速度过慢）。
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse
import subprocess
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from typing import List, Tuple, Optional
from collector.datasource.base import DataSourceManager, SwitchStrategy
from collector.datasource.baostock import BaostockDataSource
from collector.datasource.tushare import TushareDataSource
from collector.datasource.pytdx import PytdxDataSource
from clean.processor.base_importer import BaseDataImporter
from utils.logger import setup_logger
from utils.stock_code_utils import normalize_code

logger = setup_logger('daily_import')

# 不复权数据源列表（需要转换为前复权）
NON_ADJUSTED_SOURCES = ('tushare', 'pytdx')


class DailyDataImporter(BaseDataImporter):
    """日线数据导入器 - 继承 BaseDataImporter"""

    # ========== 类常量集中管理 ==========
    CYCLE = '1d'
    ADJUST_TYPE = 'qfq'
    MIN_COMPLETENESS_THRESHOLD = 0.90        # 完整度阈值（<90% 触发清理重跑并告警）
    FULL_HISTORY_START = "1990-01-01"        # A股最早数据
    DEFAULT_START_DATE = "2015-01-01"        # 默认全量导入起始日期（兼容免费数据源长度限制）
    FALLBACK_LOOKBACK_DAYS = 30              # fallback 回溯天数
    FUTURE_DELIST_DATE = "2900-01-01"        # 占位退市日期阈值
    DB_CHECK_INTERVAL = 100                  # 数据库连接检查间隔

    def __init__(self):
        super().__init__()
        self.datasource_manager = DataSourceManager(
            sources=[
                {'source': BaostockDataSource(), 'weight': 1, 'priority': 0},    # 主: 前复权
                {'source': TushareDataSource(), 'weight': 1, 'priority': 1},     # 备1: 不复权→需转换
                {'source': PytdxDataSource(), 'weight': 1, 'priority': 2}        # 备2: 不复权→需转换
            ],
            strategy=SwitchStrategy.FAILOVER,
            auto_recovery=True
        )
        self.datasource_manager.connect()
        self._interrupted = False
        self._dry_run = False  # dry-run 模式

        # 全量导入时直接使用 Baostock → Tushare，避免 Failover 循环降级到 pytdx 导致极慢。
        # 复用 DataSourceManager 中已连接的实例，避免重复登录导致 Baostock 连接冲突。
        self.baostock_source = None
        self.tushare_source = None
        for src_info in self.datasource_manager.sources:
            src = src_info['source']
            if isinstance(src, BaostockDataSource):
                self.baostock_source = src
            elif isinstance(src, TushareDataSource):
                self.tushare_source = src
        if self.baostock_source is None:
            logger.warning("⚠️ DataSourceManager 中未找到 Baostock 数据源")
        if self.tushare_source is None:
            logger.warning("⚠️ DataSourceManager 中未找到 Tushare 数据源")

        # 运行时数据源健康状态：连续失败超过阈值则自动跳过，避免重试耗时
        self._baostock_fail_count = 0
        self._baostock_disabled = False
        self._tushare_fail_count = 0
        self._tushare_disabled = False
        self._source_disable_threshold = 10

    # ==================== 重写基类方法（避免使用 storage.conn） ====================
    def get_stock_list(self) -> List[str]:
        """
        获取所有未退市股票代码列表（重写基类，使用 transaction）
        过滤掉 delist_date 已过期（且非占位符）的股票，减少无意义请求
        """
        with self.storage.transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT code, delist_date FROM stock_basic
                    WHERE (delist_date IS NULL OR delist_date >= CURRENT_DATE OR delist_date > '2099-01-01')
                    ORDER BY code
                """)
                result = []
                for row in cursor.fetchall():
                    code, delist_date = row
                    if delist_date and self._is_valid_delisted(delist_date):
                        continue
                    result.append(code)
                return result

    def create_task(self, task_name: str, metadata: dict = None):
        """创建任务记录（覆盖基类，忽略 metadata 列）"""
        with self.storage.transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO task_progress (task_name, status, progress, created_at, updated_at)
                    VALUES (%s, 'pending', 0, NOW(), NOW())
                    RETURNING id
                """, (task_name,))
                task_id = cursor.fetchone()[0]
                self._task_id = task_id
                self._task_name = task_name
        logger.info(f"📋 创建任务: {task_name} (ID: {self._task_id})")

    def update_task_progress(self, status: str, progress: int, message: str = None):
        """更新任务进度（覆盖基类）"""
        if not hasattr(self, '_task_id'):
            logger.warning("⚠️ 未初始化任务ID，跳过更新")
            return
        with self.storage.transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE task_progress
                    SET status = %s, progress = %s, message = %s, updated_at = NOW()
                    WHERE id = %s
                """, (status, progress, message, self._task_id))

    # ==================== 连接管理辅助 ====================
    def _ensure_db_connected(self):
        """确保数据库连接池有效"""
        try:
            self.storage._ensure_connection()
        except Exception as e:
            logger.warning(f"⚠️ 数据库连接保活检查失败，尝试重连: {e}")
            try:
                self.storage.connect()
            except Exception as e2:
                logger.error(f"❌ 数据库重连失败: {e2}")

    def _fetch_with_retry(
        self,
        source,
        code: str,
        start_date: str,
        end_date: str,
        max_retries: int = 5,
        base_delay: float = 1.0,
    ) -> pd.DataFrame:
        """对指定数据源获取K线数据进行指数退避重试

        Args:
            source: 数据源实例（Baostock/Tushare）
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            max_retries: 最大重试次数
            base_delay: 基础延迟秒数

        Returns:
            DataFrame or None
        """
        import time

        last_exception = None
        err_msg = ""
        for attempt in range(1, max_retries + 1):
            try:
                df = source.get_kline(
                    code, cycle='daily', start_date=start_date, end_date=end_date
                )
                # 数据源正常响应但返回空数据：视为有效结果（可能是停牌/退市），不重试
                if df is not None:
                    return df
                logger.debug(f"  {code}: {source.name} 第 {attempt}/{max_retries} 次返回 None")
            except Exception as e:
                last_exception = e
                err_msg = str(e)
                logger.warning(f"  {code}: {source.name} 第 {attempt}/{max_retries} 次失败: {e}")

            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                # 频率超限：等待一个完整周期（60s），避免反复触发限流
                if '频率超限' in err_msg or '频次' in err_msg:
                    delay = max(delay, 60.0)
                    logger.warning(f"  {code}: 检测到 {source.name} 频率超限，等待 {delay:.0f}s 后重试...")
                logger.info(f"  {code}: {delay:.0f}s 后重试 {source.name}...")
                time.sleep(delay)

        # 全部重试均抛异常才返回 None；空数据返回空 DataFrame
        return None

    # ========== 不复权数据源 → 前复权转换 ==========

    @property
    def _current_source_needs_conversion(self) -> bool:
        """当前数据源是否返回不复权数据（Tushare/pytdx 需要转换）"""
        name = self.datasource_manager.current_source_name
        return name in NON_ADJUSTED_SOURCES

    def _apply_qfq_to_single(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        """将单只股票的不复权K线数据转换为前复权

        公式: adj_price = raw_price * (adj_factor_t / latest_adj_factor)
        """
        if df is None or df.empty:
            return df

        try:
            with self.storage.transaction() as conn:
                with conn.cursor() as cur:
                    # 获取该股票所有日期的复权因子
                    cur.execute("""
                        SELECT trade_date, adj_factor FROM stock_adj_factor
                        WHERE code = %s ORDER BY trade_date DESC
                    """, (code,))
                    rows = cur.fetchall()

                    if not rows:
                        logger.debug(f"  {code}: stock_adj_factor 无数据，跳过转换")
                        return df

                    latest_adj = float(rows[0][1]) if rows[0][1] else 1.0
                    adj_map = {str(row[0]): float(row[1]) for row in rows if row[1]}

            if latest_adj == 0 or latest_adj is None:
                return df

            df = df.copy()
            price_cols = ['open', 'high', 'low', 'close']
            if 'pre_close' in df.columns:
                price_cols.append('pre_close')

            for col in price_cols:
                if col in df.columns:
                    df[col] = df.apply(
                        lambda row: round(
                            float(row[col]) * adj_map.get(str(row['trade_date'])[:10], latest_adj) / latest_adj, 2
                        ),
                        axis=1
                    )

            return df

        except Exception as e:
            logger.error(f"  {code}: 复权转换失败: {e}")
            return df

    def _apply_qfq_to_batch(self, df: pd.DataFrame, trade_date: str) -> pd.DataFrame:
        """批量将不复权K线数据转换为前复权（向量化，适合单日全市场数据）"""
        if df is None or df.empty:
            return df

        codes = df['code'].unique().tolist()
        if not codes:
            return df

        try:
            batch_size = 1000
            date_adj_parts = []
            latest_adj_parts = []

            with self.storage.transaction() as conn:
                with conn.cursor() as cur:
                    for i in range(0, len(codes), batch_size):
                        batch = codes[i:i + batch_size]
                        placeholders = ','.join(['%s'] * len(batch))

                        cur.execute(f"""
                            SELECT code, adj_factor FROM stock_adj_factor
                            WHERE code IN ({placeholders}) AND trade_date = %s
                        """, batch + [trade_date])
                        date_adj_parts.extend(cur.fetchall())

                        cur.execute(f"""
                            SELECT DISTINCT ON (code) code, adj_factor
                            FROM stock_adj_factor
                            WHERE code IN ({placeholders})
                            ORDER BY code, trade_date DESC
                        """, batch)
                        latest_adj_parts.extend(cur.fetchall())

            date_adj_df = pd.DataFrame(date_adj_parts, columns=['code', 'adj_factor_date']) if date_adj_parts else pd.DataFrame(columns=['code', 'adj_factor_date'])
            latest_adj_df = pd.DataFrame(latest_adj_parts, columns=['code', 'adj_factor_latest']) if latest_adj_parts else pd.DataFrame(columns=['code', 'adj_factor_latest'])

            if date_adj_df.empty and latest_adj_df.empty:
                logger.debug("  stock_adj_factor 无数据，跳过批量转换")
                return df

            df = df.merge(date_adj_df, on='code', how='left')
            df = df.merge(latest_adj_df, on='code', how='left')

            df['adj_factor_date'] = df['adj_factor_date'].fillna(1.0).astype(float)
            df['adj_factor_latest'] = df['adj_factor_latest'].fillna(1.0).astype(float)

            ratio = df['adj_factor_date'] / df['adj_factor_latest'].replace(0, 1.0)

            price_cols = ['open', 'high', 'low', 'close']
            if 'pre_close' in df.columns:
                price_cols.append('pre_close')

            for col in price_cols:
                if col in df.columns:
                    df[col] = (df[col].astype(float) * ratio).round(2)

            df = df.drop(columns=['adj_factor_date', 'adj_factor_latest'], errors='ignore')
            return df

        except Exception as e:
            logger.error(f"  批量复权转换失败: {e}")
            return df

    # ========== 完整度熔断机制 ==========
    def _check_data_completeness(self, target_date: str) -> dict:
        """检查指定日期的数据完整度"""
        try:
            with self.storage.transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT COUNT(DISTINCT code) 
                        FROM stock_quotes 
                        WHERE trade_date = %s AND cycle = %s
                    """, (target_date, self.CYCLE))
                    existing_count = cursor.fetchone()[0]

                    cursor.execute("""
                        SELECT COUNT(*) 
                        FROM stock_basic 
                        WHERE delist_date IS NULL
                        AND code NOT LIKE '8%%'
                        AND code NOT LIKE '920%%'
                    """)
                    total_stocks = cursor.fetchone()[0]

                    completeness = (existing_count / total_stocks) if total_stocks > 0 else 0

                    return {
                        'is_complete': completeness >= self.MIN_COMPLETENESS_THRESHOLD,
                        'existing_count': existing_count,
                        'total_stocks': total_stocks,
                        'completeness': completeness
                    }
        except Exception as e:
            logger.error(f"数据完整度检查失败: {e}", exc_info=True)
            return {'is_complete': False, 'existing_count': 0, 'total_stocks': 0, 'completeness': 0.0}

    def _cleanup_incomplete_data(self, target_date: str) -> int:
        """清理指定日期的残缺数据（独立事务）"""
        total_deleted = 0

        # 1. 删除 stock_quotes
        try:
            with self.storage.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM stock_quotes WHERE trade_date = %s AND cycle = %s",
                        (target_date, self.CYCLE)
                    )
                    deleted_quotes = cur.rowcount
                    total_deleted += deleted_quotes
                    if deleted_quotes > 0:
                        logger.info(f"🗑️ 已清理 stock_quotes {deleted_quotes} 条 ({target_date})")
        except Exception as e:
            logger.error(f"❌ 清理 stock_quotes 失败: {e}", exc_info=True)

        # 2. 删除 stock_daily_snapshot（可选）
        try:
            with self.storage.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM stock_daily_snapshot WHERE trade_date = %s",
                        (target_date,)
                    )
                    deleted_snapshot = cur.rowcount
                    total_deleted += deleted_snapshot
                    if deleted_snapshot > 0:
                        logger.info(f"🗑️ 已清理 stock_daily_snapshot {deleted_snapshot} 条 ({target_date})")
        except Exception as e:
            logger.debug(f"stock_daily_snapshot 清理跳过（表可能不存在）: {e}")

        return total_deleted

    def import_by_trade_date(self, trade_date: str) -> Tuple[int, int]:
        """使用 Tushare 批量接口导入指定日期数据（自动转换为前复权）"""
        if self._dry_run:
            logger.info(f"[DRY-RUN] 将导入 {trade_date} 的日线数据")
            return 0, 0

        logger.info(f"🚀 使用批量模式导入 {trade_date} 的日线数据（Tushare 不复权 → 自动转换前复权）")
        try:
            tushare_source = None
            for src_info in self.datasource_manager.sources:
                if isinstance(src_info['source'], TushareDataSource):
                    tushare_source = src_info['source']
                    break

            if not tushare_source:
                raise RuntimeError("未找到 Tushare 数据源")

            if not tushare_source.connected:
                tushare_source.connect()

            df = tushare_source.batch_get_daily(trade_date)
            if df is None or df.empty:
                logger.warning(f"⚠️  {trade_date} 没有数据")
                return 0, 1

            logger.info(f"✅ 获取到 {len(df)} 条原始数据")
            df = self._process_batch_kline_data(df)
            if df is None or df.empty:
                logger.warning(f"⚠️  {trade_date} 数据处理后为空")
                return 0, 1

            # Tushare 返回不复权数据，转换为前复权
            df = self._apply_qfq_to_batch(df, trade_date)

            count = self.storage.save_quotes(df)
            logger.info(f"✅ 成功导入 {count} 条记录（已转换为前复权）")
            return count, 0

        except Exception as e:
            logger.error(f"❌ 批量导入失败: {e}")
            return 0, 1

    def _normalize_kline_df(self, df: pd.DataFrame, is_batch: bool = False) -> pd.DataFrame:
        """公共K线数据清洗逻辑"""
        if df is None or df.empty:
            return df

        if is_batch:
            rename_map = {'ts_code': 'code', 'vol': 'volume'}
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
            df['code'] = df['code'].apply(lambda x: normalize_code(x) or x)
            df['trade_date'] = df['trade_date'].str.replace(r'(\d{4})(\d{2})(\d{2})', r'\1-\2-\3', regex=True)

        numeric_cols = ['open', 'high', 'low', 'close', 'amount']
        if 'pre_close' in df.columns:
            numeric_cols.append('pre_close')
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

        if is_batch:
            df['volume'] = df['volume'] * 100

        # 过滤无效数据
        price_cols = ['open', 'high', 'low', 'close']
        mask = (df[price_cols] > 0).all(axis=1) & df['volume'].notna() & (df['volume'] > 0)
        df = df[mask].copy()

        if is_batch:
            from utils.stock_code_utils import filter_out_bse
            original_len = len(df)
            df, _ = filter_out_bse(df)
            if len(df) < original_len:
                logger.warning(f"⚠️ 过滤掉 {original_len - len(df)} 条北交所股票数据（8/920开头）")

        df['volume'] = df['volume'].round().astype('Int64')

        # 补充 pre_close（部分数据源不返回该字段）：按股票排序后，pre_close = 前一日 close
        if 'pre_close' not in df.columns:
            if 'code' in df.columns:
                df['pre_close'] = df.groupby('code')['close'].shift(1)
                # 每只股票第一根K线：pre_close 取 open（与前端 fillPreClose 一致）
                first_mask = df.groupby('code').cumcount() == 0
                df.loc[first_mask, 'pre_close'] = df.loc[first_mask, 'open']
            else:
                df['pre_close'] = df['close'].shift(1)
                df.loc[df.index[0], 'pre_close'] = df.loc[df.index[0], 'open']

        if 'pct_change' not in df.columns:
            if 'code' in df.columns:
                df['pct_change'] = df.groupby('code')['close'].pct_change() * 100
            else:
                df['pct_change'] = df['close'].pct_change() * 100

        df = df.dropna(subset=['open', 'close'])
        return df

    def _process_batch_kline_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理批量获取的K线数据"""
        df = self._normalize_kline_df(df, is_batch=True)
        if df is None or df.empty:
            return df

        df['cycle'] = self.CYCLE
        df['adjust_type'] = self.ADJUST_TYPE
        cols = ['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close',
                'pre_close', 'volume', 'amount', 'adjust_type', 'ah_vol', 'ah_amount']
        return df[[c for c in cols if c in df.columns]]

    def _process_kline_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理单只股票K线数据"""
        return self._normalize_kline_df(df, is_batch=False)

    def close(self):
        """关闭连接"""
        # DataSourceManager 已包含 Baostock/Tushare/pytdx 实例，统一断开即可，
        # 避免对同一 Baostock 连接重复 logout 触发 Bad file descriptor 错误。
        try:
            self.datasource_manager.disconnect()
        except Exception:
            pass
        self.disconnect()

    def import_stock_data(self, code: str, start_date: str, end_date: str,
                          df: pd.DataFrame = None, source_name: str = None) -> int:
        """导入单只股票日线数据

        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            df: 可选，已获取的K线数据；传入时不再调用数据源
            source_name: 可选，df 对应的数据源名称，用于判断是否需前复权转换
        """
        if self._dry_run:
            logger.info(f"[DRY-RUN] 将导入 {code} ({start_date} ~ {end_date})")
            return 0

        if code.startswith('8') or code.startswith('920'):
            logger.warning(f"⚠️ 跳过北交所股票 {code}")
            return 0

        try:
            if df is None:
                df = self.retry_on_network_error(
                    self.datasource_manager.get_kline,
                    code, cycle='daily', start_date=start_date, end_date=end_date,
                    max_retries=3, initial_delay=5, max_delay=30
                )
                source_name = self.datasource_manager.current_source_name
            if df is None or df.empty:
                return 0

            # 不复权数据源 → 转换为前复权
            needs_conversion = source_name in NON_ADJUSTED_SOURCES if source_name else self._current_source_needs_conversion
            if needs_conversion:
                logger.debug(f"  {code}: 数据源 {source_name or self.datasource_manager.current_source_name} 返回不复权数据，正在转换...")
                df = self._apply_qfq_to_single(df, code)

            df = self._process_kline_data(df)
            if df is None or df.empty:
                return 0

            df['code'] = self._format_code(code)
            df['cycle'] = self.CYCLE
            df['adjust_type'] = self.ADJUST_TYPE
            cols = ['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close',
                    'pre_close', 'volume', 'amount', 'adjust_type']
            df = df[[c for c in cols if c in df.columns]]

            count = self.storage.save_quotes(df)
            logger.debug(f"导入 {code}: {count} 条记录")
            return count

        except (ConnectionError, OSError) as e:
            logger.error(f"❌ {code} 网络异常，跳过该股票: {e}")
            return 0
        except Exception as e:
            logger.error(f"❌ 导入 {code} 失败: {e}")
            return 0

    # ========== 批量查询优化 ==========
    def _get_last_date_in_range(self, codes: List[str],
                                 start_date: Optional[str],
                                 end_date: str) -> dict:
        """批量获取股票在指定日期范围内的最大交易日期（O(n) 优化）"""
        result = {}
        if not codes:
            return result

        # 标准化代码
        code_mapping = {}
        numeric_codes = []
        for code in codes:
            numeric_code = code.replace('SZ.', '').replace('sz.', '') \
                              .replace('SH.', '').replace('sh.', '')
            code_mapping[code] = numeric_code
            numeric_codes.append(numeric_code)

        numeric_to_orig = {v: k for k, v in code_mapping.items()}

        batch_size = 500
        for i in range(0, len(numeric_codes), batch_size):
            batch_codes = numeric_codes[i:i + batch_size]
            placeholders = ','.join(['%s'] * len(batch_codes))

            if start_date:
                sql = f"""
                    SELECT code, MAX(trade_date)::text as max_date
                    FROM stock_quotes
                    WHERE code IN ({placeholders}) 
                      AND cycle = %s 
                      AND trade_date >= %s 
                      AND trade_date <= %s
                    GROUP BY code
                """
                params = tuple(batch_codes) + (self.CYCLE, start_date, end_date)
            else:
                sql = f"""
                    SELECT code, MAX(trade_date)::text as max_date
                    FROM stock_quotes
                    WHERE code IN ({placeholders}) AND cycle = %s
                    GROUP BY code
                """
                params = tuple(batch_codes) + (self.CYCLE,)

            try:
                with self.storage.transaction() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(sql, params)
                        for row in cursor.fetchall():
                            orig = numeric_to_orig.get(row[0])
                            if orig:
                                result[orig] = row[1]
            except Exception as e:
                logger.error(f"批量查询最大日期失败: {e}")

        return result

    def _is_valid_delisted(self, delist_date) -> bool:
        """判断是否真正退市（排除占位日期）"""
        if not delist_date:
            return False
        if isinstance(delist_date, str):
            try:
                dt = datetime.strptime(delist_date[:10], "%Y-%m-%d").date()
                return dt < datetime.strptime(self.FUTURE_DELIST_DATE, "%Y-%m-%d").date()
            except Exception:
                return False
        elif isinstance(delist_date, date):
            return delist_date < datetime.strptime(self.FUTURE_DELIST_DATE, "%Y-%m-%d").date()
        return False

    def full_import(self, codes: List[str], start_date: str = None, end_date: str = None):
        """全量导入（支持断点续传）"""
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        total_stocks = len(codes)
        success_count = 0
        fail_count = 0
        skip_count = 0
        total_records = 0
        self._interrupted = False

        logger.info("⏩ 全量模式：预批量查询已有数据的股票...")
        last_date_cache = self._get_last_date_in_range(codes, start_date, end_date)
        logger.info(f"✅ 预查询完成，{len(last_date_cache)} 只股票有历史记录")

        # 快速检测 Baostock 实际可用性：用一只常见股票请求 5 天数据
        if self.baostock_source and not self._baostock_disabled:
            try:
                test_df = self.baostock_source.get_kline(
                    '000001', cycle='daily', start_date='2026-07-14', end_date='2026-07-20'
                )
                if test_df is None or test_df.empty:
                    raise RuntimeError("返回空数据")
                logger.info("✅ Baostock 快速检测通过")
            except Exception as e:
                self._baostock_disabled = True
                logger.warning(f"⚠️ Baostock 快速检测失败 ({e})，全量导入将跳过 Baostock")

        for i, code in enumerate(codes, 1):
            if self._interrupted:
                logger.info(f"检测到中断信号，停止导入")
                break

            if i % self.DB_CHECK_INTERVAL == 0:
                self._ensure_db_connected()

            formatted_code = self._format_code(code)
            if not formatted_code:
                logger.warning(f"[{i}/{total_stocks}] {code} 格式无效，跳过")
                continue

            # 查询 list_date / delist_date，用于调整请求范围
            try:
                with self.storage.transaction() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT list_date, delist_date FROM stock_basic WHERE code = %s",
                                      (formatted_code,))
                        row = cursor.fetchone()
            except Exception:
                row = None
            list_date = row[0] if row and row[0] else None
            delist_date = row[1] if row and row[1] else None

            # 已退市股票：以退市日为结束日，无需拉到最新日期
            effective_end_date = end_date
            if delist_date and self._is_valid_delisted(delist_date):
                if isinstance(delist_date, date):
                    effective_end_date = delist_date.strftime('%Y-%m-%d')
                else:
                    effective_end_date = str(delist_date)[:10]

            last_date = last_date_cache.get(code)
            if last_date and last_date >= effective_end_date:
                skip_count += 1
                if skip_count <= 5 or skip_count % 500 == 0:
                    logger.info(f"[{i}/{total_stocks}] {code} 数据已完整({last_date})，跳过")
                continue

            if last_date:
                current_start = (datetime.strptime(last_date, "%Y-%m-%d") +
                                 timedelta(days=1)).strftime('%Y-%m-%d')
            elif start_date:
                current_start = start_date
            else:
                # 默认从 2015-01-01 开始，平衡历史长度与免费数据源限制；
                # 若上市日晚于默认值，则从上市日开始。
                if list_date:
                    if isinstance(list_date, date):
                        list_date_str = list_date.strftime('%Y-%m-%d')
                    else:
                        list_date_str = str(list_date)
                    current_start = max(list_date_str, self.DEFAULT_START_DATE)
                else:
                    current_start = self.DEFAULT_START_DATE

            # 统一日期格式为字符串，避免 Baostock 等数据源报"日期格式不正确"
            if isinstance(current_start, date):
                current_start = current_start.strftime('%Y-%m-%d')

            # 扩展请求窗口至少 30 天：避免短期停牌/除息导致 Baostock 返回空数据，
            # 同时保证老股票的历史数据也能被完整拉取。
            current_start_dt = datetime.strptime(current_start, '%Y-%m-%d').date()
            end_date_dt = datetime.strptime(effective_end_date, '%Y-%m-%d').date()
            min_window_start_dt = end_date_dt - timedelta(days=30)
            if current_start_dt > min_window_start_dt:
                current_start_dt = min_window_start_dt
                current_start = current_start_dt.strftime('%Y-%m-%d')

            logger.info(f"[{i}/{total_stocks}] 正在导入 {code} (从 {current_start} 到 {effective_end_date})")

            # 全量导入直连优先级：Baostock(前复权) → Tushare(不复权→转换)
            # 均失败后跳过。pytdx 不在全量模式使用（速度过慢）。
            # 若某数据源连续失败超过阈值，则自动禁用，避免无意义重试耗时。
            # 注：数据源返回空数据视为正常（停牌/退市），不累计失败计数。
            df_bs = None
            bs_failed = False
            if self.baostock_source and not self._baostock_disabled:
                df_bs = self._fetch_with_retry(
                    self.baostock_source, code, current_start, effective_end_date,
                    max_retries=2, base_delay=2.0
                )
                if df_bs is None:
                    bs_failed = True
                    self._baostock_fail_count += 1
                    if self._baostock_fail_count >= self._source_disable_threshold:
                        self._baostock_disabled = True
                        logger.warning(f"⚠️ Baostock 连续失败 {self._source_disable_threshold} 次，后续股票跳过 Baostock")
                else:
                    self._baostock_fail_count = 0

            if df_bs is not None:
                count = self.import_stock_data(code, current_start, effective_end_date, df=df_bs, source_name='baostock')
                # 数据源正常但无数据：视为成功（停牌/退市），不增加失败计数
                if count == 0 and (df_bs.empty):
                    success_count += 1
                    continue
            elif self.tushare_source and not self._tushare_disabled:
                if self._baostock_disabled:
                    logger.info(f"  {code}: Baostock 已禁用，直接使用 Tushare")
                elif bs_failed:
                    logger.warning(f"  {code}: Baostock 2 次重试失败，切换到 Tushare")
                df_ts = self._fetch_with_retry(
                    self.tushare_source, code, current_start, effective_end_date,
                    max_retries=2, base_delay=3.0
                )
                if df_ts is not None:
                    self._tushare_fail_count = 0
                    count = self.import_stock_data(code, current_start, effective_end_date, df=df_ts, source_name='tushare')
                    if count == 0 and (df_ts.empty):
                        success_count += 1
                        continue
                else:
                    self._tushare_fail_count += 1
                    if self._tushare_fail_count >= self._source_disable_threshold:
                        self._tushare_disabled = True
                        logger.warning(f"⚠️ Tushare 连续失败 {self._source_disable_threshold} 次，后续股票跳过 Tushare")
                    count = 0
                    logger.error(f"❌ {code}: Baostock/Tushare 均失败，跳过")
            else:
                count = 0
                logger.error(f"❌ {code}: Baostock/Tushare 均不可用，跳过")

            if count > 0:
                success_count += 1
                total_records += count
            else:
                fail_count += 1
                threshold = (datetime.now() - timedelta(days=365)).date()
                if current_start_dt < threshold:
                    logger.warning(f"⚠️ {code} 从 {current_start} 开始拉取失败")

            progress = int((i / total_stocks) * 100)
            self.update_task_progress('running', progress, f"已完成 {i}/{total_stocks} 只股票")

        logger.info(f"全量导入完成: 成功 {success_count}, 失败 {fail_count}, "
                   f"跳过 {skip_count}, 总记录 {total_records}")
        self.update_task_progress('completed', 100,
                                  f"全量导入完成: 成功 {success_count}, 失败 {fail_count}, "
                                  f"跳过 {skip_count}, 总记录 {total_records}")

    def incremental_import(self, parallel: bool = True) -> dict:
        """增量导入（带完整度熔断机制）

        优先使用 Tushare 批量接口（速度快），自动转换为前复权后存储。
        批量失败时回退到 DataSourceManager 单线程逐个导入（Baostock→Tushare→pytdx）。

        Returns:
            dict: 包含 rows_affected / extra_metrics 的运行统计
        """
        codes = self.get_stock_list()
        codes = [c for c in codes if not (c.startswith('8') or c.startswith('920'))]

        today = datetime.now().strftime('%Y-%m-%d')
        stats = {"mode": "parallel" if parallel else "single", "rows_affected": 0,
                 "batch_days": 0, "fallback_success": 0, "fallback_fail": 0,
                 "fallback_records": 0, "cleaned": 0}

        if parallel:
            logger.info("🚀 使用 Tushare 批量接口增量导入（不复权→自动转换前复权）")
            latest_date = self._get_latest_trade_date()
            logger.info(f"📅 数据库中最新数据日期: {latest_date or '无数据'}")

            if latest_date and latest_date >= today:
                check_date = latest_date if latest_date > today else today
                logger.info(f"🔍 检测到最新日期已是 {check_date}，执行完整度校验...")
                check_result = self._check_data_completeness(check_date)

                logger.info(f"📊 数据完整度: {check_result['existing_count']}/"
                           f"{check_result['total_stocks']} "
                           f"({check_result['completeness']:.1%})")

                if check_result['is_complete']:
                    logger.info("✅ 数据已是最新且完整，无需增量导入")
                    print(f'TASK_RESULT:{json.dumps({"rows_affected": 0, "extra_metrics": stats})}')
                    return stats
                else:
                    logger.warning(f"⚠️ 数据完整度仅 {check_result['completeness']:.1%}，"
                                 f"低于阈值 {self.MIN_COMPLETENESS_THRESHOLD:.0%}")
                    logger.warning(f"⚠️ 疑似上次拉取中断，自动清理 {check_date} 的残缺数据...")

                    deleted_count = self._cleanup_incomplete_data(check_date)
                    stats["cleaned"] = deleted_count
                    logger.warning(f"🗑️ 已清理 {deleted_count} 条残缺数据，强制重新拉取...")

                    latest_date = self._get_latest_trade_date()
                    logger.info(f"📅 清理后最新数据日期回退至: {latest_date or '无数据'}")

            batch_success = False
            if latest_date:
                logger.info(f"📤 从 {latest_date} 之后开始批量导入...")
                cursor_date = latest_date
                while cursor_date < today:
                    next_date = self._increment_date(cursor_date)
                    if not next_date or next_date > today:
                        break

                    logger.info(f"📥 批量导入 {next_date}...")
                    success, fail = self.import_by_trade_date(next_date)
                    if success > 0:
                        batch_success = True
                        stats["rows_affected"] += success
                        stats["batch_days"] += 1
                        logger.info(f"✅ {next_date} 导入 {success} 条")
                    else:
                        logger.info(f"⏭️  {next_date} 无数据（非交易日或已收盘）")

                    cursor_date = next_date
            else:
                logger.info("📥 无历史数据，尝试导入今日数据...")
                success, fail = self.import_by_trade_date(today)
                if success > 0:
                    batch_success = True
                    stats["rows_affected"] += success
                    stats["batch_days"] += 1

            if not batch_success:
                logger.warning("⚠️  Tushare 批量接口未获取到数据，"
                             f"回退到单线程逐个导入 (Baostock→Tushare→pytdx, 最近 {self.FALLBACK_LOOKBACK_DAYS} 天)")
                fallback_start = (datetime.now() -
                                 timedelta(days=self.FALLBACK_LOOKBACK_DAYS)).strftime('%Y-%m-%d')
                sc, fc, tr = self._single_thread_incremental(codes, today, min_start_date=fallback_start)
                stats["fallback_success"] = sc
                stats["fallback_fail"] = fc
                stats["fallback_records"] = tr
                stats["rows_affected"] += tr
        else:
            logger.info("📦 使用单线程增量导入模式")
            sc, fc, tr = self._single_thread_incremental(codes, today)
            stats["fallback_success"] = sc
            stats["fallback_fail"] = fc
            stats["fallback_records"] = tr
            stats["rows_affected"] += tr

        print(f'TASK_RESULT:{json.dumps({"rows_affected": stats["rows_affected"], "extra_metrics": stats})}')
        return stats

    def _get_latest_trade_date(self) -> Optional[str]:
        """查询 stock_quotes 表中最新交易日"""
        try:
            with self.storage.transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT MAX(trade_date)::text FROM stock_quotes WHERE cycle = %s",
                                  (self.CYCLE,))
                    result = cursor.fetchone()
                    if result and result[0]:
                        return result[0]
                    return None
        except Exception as e:
            logger.warning(f"查询最新交易日失败: {e}")
            return None

    def _increment_date(self, date_str: str) -> str:
        dt = datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)
        return dt.strftime('%Y-%m-%d')

    def _single_thread_incremental(self, codes: List[str], today: str,
                                    min_start_date: Optional[str] = None) -> Tuple[int, int, int]:
        """单线程增量导入（备用），返回 (success_count, fail_count, total_records)"""
        total_stocks = len(codes)
        success_count = 0
        fail_count = 0
        total_records = 0

        logger.info("⏩ 增量模式：预批量查询所有股票的最后交易日...")
        last_date_cache = self._get_last_date_in_range(codes, None, today)
        logger.info("✅ 预查询完成")

        for i, code in enumerate(codes, 1):
            # 退市判断
            try:
                with self.storage.transaction() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT delist_date FROM stock_basic WHERE code = %s", (code,))
                        result = cursor.fetchone()
                        if result and self._is_valid_delisted(result[0]):
                            logger.debug(f"{code} 已退市（退市日期: {result[0]}），跳过")
                            continue
            except Exception:
                pass

            last_date = last_date_cache.get(code)
            if last_date:
                start_date = (datetime.strptime(last_date, '%Y-%m-%d') +
                             timedelta(days=1)).strftime('%Y-%m-%d')
                if start_date > today:
                    logger.debug(f"{code} 数据已是最新，跳过")
                    continue
            else:
                try:
                    with self.storage.transaction() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT list_date FROM stock_basic WHERE code = %s", (code,))
                            result = cursor.fetchone()
                            start_date = result[0] if result and result[0] else self.FULL_HISTORY_START
                except Exception:
                    start_date = self.FULL_HISTORY_START

            if min_start_date and start_date < min_start_date:
                start_date = min_start_date

            logger.info(f"[{i}/{total_stocks}] 增量导入 {code}，从 {start_date} 开始")
            count = self.import_stock_data(code, start_date, today)
            if count > 0:
                success_count += 1
                total_records += count
            else:
                fail_count += 1

            progress = int((i / total_stocks) * 100)
            self.update_task_progress('running', progress, f"增量导入 {i}/{total_stocks} 只股票")

        self.update_task_progress('completed', 100,
                                  f"增量导入完成: 成功 {success_count}, 失败 {fail_count}, "
                                  f"总记录 {total_records}")
        logger.info(f"增量导入完成: 成功 {success_count}, 失败 {fail_count}, 总记录 {total_records}")
        return success_count, fail_count, total_records


def main():
    parser = argparse.ArgumentParser(description='日线数据导入脚本')
    parser.add_argument('--code', type=str, help='股票代码（如 000001），不指定则导入全部')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--date', type=str, help='指定交易日（YYYY-MM-DD），使用 Tushare 批量导入')
    parser.add_argument('--incremental', action='store_true', help='增量导入模式')
    parser.add_argument('--no-parallel', action='store_true', help='跳过 Tushare 批量接口')
    parser.add_argument('--skip-health-check', action='store_true', help='跳过前置条件检查')
    parser.add_argument('--dry-run', action='store_true', help='试运行模式（只检查不写入）')
    parser.add_argument('--full-history', action='store_true', help='导入完整历史数据（从上市日/A股最早日期开始），默认从2015-01-01开始')
    args = parser.parse_args()

    if not args.skip_health_check:
        logger.info('🔍 执行前置条件检查...')
        health_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'collector', 'etl', 'pipeline_health_check.py'
        )
        if os.path.exists(health_script):
            ret = subprocess.run([sys.executable, health_script, '--pre-import'],
                                capture_output=False)
            if ret.returncode != 0:
                logger.error('❌ 前置条件检查未通过！')
                sys.exit(1)

    importer = None
    try:
        importer = DailyDataImporter()
        importer._dry_run = args.dry_run

        if args.dry_run:
            logger.info("🔍 [DRY-RUN] 试运行模式，不会实际写入数据")

        if args.date:
            task_name = f"日线数据导入_批量_{args.date}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            importer.create_task(task_name, {'mode': 'batch', 'date': args.date})
            success, fail = importer.import_by_trade_date(args.date)
            importer.update_task_progress('completed', 100, f"批量导入完成: 成功 {success} 条记录")
            print(f'TASK_RESULT:{json.dumps({"rows_affected": success, "extra_metrics": {"failed": fail}})}')
            return

        if args.incremental:
            task_name = f"日线数据导入_增量_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            importer.create_task(task_name, {'mode': 'incremental'})
            importer.incremental_import(parallel=not args.no_parallel)
        else:
            if args.code:
                task_name = f"日线数据导入_单股_{args.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                importer.create_task(task_name, {'mode': 'single', 'code': args.code})
                count = importer.import_stock_data(args.code, args.start, args.end)
                importer.update_task_progress('completed', 100, f"导入完成: {count} 条记录")
                print(f'TASK_RESULT:{json.dumps({"rows_affected": count, "extra_metrics": {"code": args.code, "start": args.start, "end": args.end}})}')
            else:
                task_name = f"日线数据导入_全量_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                importer.create_task(task_name, {'mode': 'full'})
                codes = importer.get_stock_list()
                codes = [c for c in codes if not (c.startswith('8') or c.startswith('920'))]
                start_date = args.start
                if args.full_history and not start_date:
                    start_date = importer.FULL_HISTORY_START
                    logger.info(f"📜 完整历史模式：从 {start_date} 开始导入")
                else:
                    logger.info(f"📅 默认全量模式：从 {importer.DEFAULT_START_DATE} 开始导入（可用 --full-history 导入完整历史）")
                logger.info(f"开始全量导入: {len(codes)} 只股票")
                importer.full_import(codes, start_date, args.end)

    except (KeyboardInterrupt, SystemExit):
        if importer:
            importer._interrupted = True
            importer.update_task_progress('interrupted', 0, "任务被用户中断")
            logger.info("⚠️ 下载任务已被中断，已下载数据已保存")
    except Exception as e:
        logger.error(f"程序异常: {e}")
        raise
    finally:
        if importer:
            importer.close()


if __name__ == '__main__':
    main()