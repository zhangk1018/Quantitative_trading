#!/usr/bin/env python3
"""
日线数据导入脚本
功能：
- 从数据源（baostock/tushare）拉取日线K线
- 写入 stock_quotes 表
- 利用 task_progress 记录状态
- 支持全量导入和增量导入
- 【新增】完整度熔断机制：防止数据拉取中断后产生"假成功"
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import argparse
import subprocess
import pandas as pd
from datetime import datetime, timedelta, date
from typing import List, Tuple, Optional
from collector.datasource.base import DataSourceManager, SwitchStrategy
from collector.datasource.tushare import TushareDataSource
from collector.datasource.baostock import BaostockDataSource
from clean.processor.base_importer import BaseDataImporter
from utils.logger import setup_logger
from utils.stock_code_utils import normalize_code

logger = setup_logger('daily_import')


class DailyDataImporter(BaseDataImporter):
    """日线数据导入器 - 继承 BaseDataImporter"""

    # ========== 类常量集中管理 ==========
    CYCLE = '1d'
    ADJUST_TYPE = 'qfq'
    MIN_COMPLETENESS_THRESHOLD = 0.80        # 完整度阈值
    FULL_HISTORY_START = "1990-01-01"        # A股最早数据
    FALLBACK_LOOKBACK_DAYS = 30              # fallback 回溯天数
    FUTURE_DELIST_DATE = "2900-01-01"        # 占位退市日期阈值
    DB_CHECK_INTERVAL = 100                  # 数据库连接检查间隔

    def __init__(self):
        super().__init__()
        self.datasource_manager = DataSourceManager(
            sources=[
                {'source': TushareDataSource(), 'weight': 1, 'priority': 0},
                {'source': BaostockDataSource(), 'weight': 1, 'priority': 1}
            ],
            strategy=SwitchStrategy.FAILOVER,
            auto_recovery=True
        )
        self.datasource_manager.connect()
        self._interrupted = False
        self._dry_run = False  # dry-run 模式

    # ==================== 重写基类方法（避免使用 storage.conn） ====================
    def get_stock_list(self) -> List[str]:
        """
        获取所有股票代码列表（重写基类，使用 transaction）
        返回所有股票代码，外部会自行过滤北交所等
        """
        with self.storage.transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT code FROM stock_basic ORDER BY code")
                return [row[0] for row in cursor.fetchall()]

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
        """使用 Tushare 批量接口导入指定日期数据"""
        if self._dry_run:
            logger.info(f"[DRY-RUN] 将导入 {trade_date} 的日线数据")
            return 0, 0

        logger.info(f"🚀 使用批量模式导入 {trade_date} 的日线数据")
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

            count = self.storage.save_quotes(df)
            logger.info(f"✅ 成功导入 {count} 条记录")
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
        try:
            self.datasource_manager.disconnect()
        except Exception:
            pass
        self.disconnect()

    def import_stock_data(self, code: str, start_date: str, end_date: str) -> int:
        """导入单只股票日线数据"""
        if self._dry_run:
            logger.info(f"[DRY-RUN] 将导入 {code} ({start_date} ~ {end_date})")
            return 0

        if code.startswith('8') or code.startswith('920'):
            logger.warning(f"⚠️ 跳过北交所股票 {code}")
            return 0

        try:
            df = self.retry_on_network_error(
                self.datasource_manager.get_kline,
                code, cycle='daily', start_date=start_date, end_date=end_date,
                max_retries=3, initial_delay=5, max_delay=30
            )
            if df is None or df.empty:
                return 0

            df = self._process_kline_data(df)
            if df is None or df.empty:
                return 0

            df['code'] = self._format_code(code)
            df['cycle'] = self.CYCLE
            df['adjust_type'] = self.ADJUST_TYPE
            df = df[['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close',
                     'pre_close', 'volume', 'amount', 'adjust_type']]

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

            last_date = last_date_cache.get(code)
            if last_date and last_date >= end_date:
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
                try:
                    with self.storage.transaction() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT list_date FROM stock_basic WHERE code = %s",
                                          (formatted_code,))
                            row = cursor.fetchone()
                            current_start = row[0] if row and row[0] else self.FULL_HISTORY_START
                except Exception:
                    current_start = self.FULL_HISTORY_START

            logger.info(f"[{i}/{total_stocks}] 正在导入 {code} (从 {current_start})")
            count = self.import_stock_data(code, current_start, end_date)
            if count > 0:
                success_count += 1
                total_records += count
            else:
                fail_count += 1
                if current_start < (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'):
                    logger.warning(f"⚠️ {code} 从 {current_start} 开始拉取失败")

            progress = int((i / total_stocks) * 100)
            self.update_task_progress('running', progress, f"已完成 {i}/{total_stocks} 只股票")

        logger.info(f"全量导入完成: 成功 {success_count}, 失败 {fail_count}, "
                   f"跳过 {skip_count}, 总记录 {total_records}")
        self.update_task_progress('completed', 100,
                                  f"全量导入完成: 成功 {success_count}, 失败 {fail_count}, "
                                  f"跳过 {skip_count}, 总记录 {total_records}")

    def incremental_import(self, parallel: bool = True):
        """增量导入（带完整度熔断机制）"""
        codes = self.get_stock_list()
        codes = [c for c in codes if not (c.startswith('8') or c.startswith('920'))]

        today = datetime.now().strftime('%Y-%m-%d')

        if parallel:
            logger.info("🚀 使用 Tushare 批量接口增量导入（优先）")
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
                    return
                else:
                    logger.warning(f"⚠️ 数据完整度仅 {check_result['completeness']:.1%}，"
                                 f"低于阈值 {self.MIN_COMPLETENESS_THRESHOLD:.0%}")
                    logger.warning(f"⚠️ 疑似上次拉取中断，自动清理 {check_date} 的残缺数据...")

                    deleted_count = self._cleanup_incomplete_data(check_date)
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
                        logger.info(f"✅ {next_date} 导入 {success} 条")
                    else:
                        logger.info(f"⏭️  {next_date} 无数据（非交易日或已收盘）")

                    cursor_date = next_date
            else:
                logger.info("📥 无历史数据，尝试导入今日数据...")
                success, fail = self.import_by_trade_date(today)
                if success > 0:
                    batch_success = True

            if not batch_success:
                logger.warning("⚠️  Tushare 批量接口未获取到数据，"
                             f"回退到单线程逐个导入（最近 {self.FALLBACK_LOOKBACK_DAYS} 天）")
                fallback_start = (datetime.now() -
                                 timedelta(days=self.FALLBACK_LOOKBACK_DAYS)).strftime('%Y-%m-%d')
                self._single_thread_incremental(codes, today, min_start_date=fallback_start)
        else:
            logger.info("📦 使用单线程增量导入模式")
            self._single_thread_incremental(codes, today)

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
                                    min_start_date: Optional[str] = None):
        """单线程增量导入（备用）"""
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
            else:
                task_name = f"日线数据导入_全量_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                importer.create_task(task_name, {'mode': 'full'})
                codes = importer.get_stock_list()
                codes = [c for c in codes if not (c.startswith('8') or c.startswith('920'))]
                logger.info(f"开始全量导入: {len(codes)} 只股票")
                importer.full_import(codes, args.start, args.end)

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