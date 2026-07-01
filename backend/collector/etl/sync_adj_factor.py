#!/usr/bin/env python3
"""
sync_adj_factor.py - 复权因子同步脚本

从 Baostock 获取复权因子数据并更新到 stock_adj_factor 表。
Baostock query_adjust_factor 是按股票查询的，因此采用逐股票遍历方式。

使用说明：
  初次同步（全量历史）：python sync_adj_factor.py
  增量同步（最近30天）：python sync_adj_factor.py --incremental

注意：Tushare 免费版不支持 adj_factor 接口，已禁用。
"""

import sys
import os
import json
import argparse

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import baostock as bs
import pandas as pd
from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple, Optional

from collector.datasource.baostock import BaostockDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('sync_adj_factor')


# ==================== 辅助函数 ====================

def get_active_stocks_from_baostock(source: BaostockDataSource) -> pd.DataFrame:
    """从 Baostock 获取活跃股票列表（备用）"""
    try:
        stocks = source.get_stock_list()
        if stocks.empty:
            logger.error("❌ Baostock 返回空股票列表")
            return pd.DataFrame()
        logger.info(f"📋 从 Baostock 获取到 {len(stocks)} 只活跃股票")
        return stocks
    except Exception as e:
        logger.error(f"❌ 从 Baostock 获取股票列表失败: {e}")
        return pd.DataFrame()


def get_active_stocks_from_db(storage: PostgreSQLStorage) -> pd.DataFrame:
    """从数据库获取活跃股票列表（优先）"""
    try:
        with storage.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT code, exchange, list_date, delist_date
                    FROM stock_basic
                    WHERE delist_date IS NULL
                    AND code NOT LIKE '8%'
                    AND code NOT LIKE '920%'
                    ORDER BY code
                """)
                rows = cur.fetchall()
                if not rows:
                    logger.warning("⚠️ 数据库 stock_basic 表为空")
                    return pd.DataFrame()
                df = pd.DataFrame(rows, columns=['code', 'exchange', 'list_date', 'delist_date'])
                logger.info(f"📋 从数据库获取到 {len(df)} 只活跃股票")
                return df
    except Exception as e:
        logger.error(f"❌ 从数据库获取股票列表失败: {e}")
        return pd.DataFrame()


def get_active_stocks(storage: PostgreSQLStorage, source: BaostockDataSource) -> pd.DataFrame:
    """获取活跃股票列表（优先数据库，备用 Baostock）"""
    df = get_active_stocks_from_db(storage)
    if not df.empty:
        return df
    logger.warning("⚠️ 数据库股票列表为空，尝试从 Baostock 获取...")
    return get_active_stocks_from_baostock(source)


def get_last_adj_factors_batch(storage: PostgreSQLStorage, codes: List[str]) -> Dict[str, Tuple[Optional[date], Optional[float]]]:
    """
    批量获取所有股票的最新复权因子
    使用 DISTINCT ON 一次查询替代逐股票查询
    """
    if not codes:
        return {}
    try:
        with storage.transaction() as conn:
            with conn.cursor() as cur:
                placeholders = ','.join(['%s'] * len(codes))
                cur.execute(f"""
                    SELECT DISTINCT ON (code) code, trade_date, adj_factor
                    FROM stock_adj_factor
                    WHERE code IN ({placeholders})
                    ORDER BY code, trade_date DESC
                """, tuple(codes))
                rows = cur.fetchall()
                return {row[0]: (row[1], row[2]) for row in rows}
    except Exception as e:
        logger.error(f"批量获取最新复权因子失败: {e}")
        return {}


def get_last_known_adj_factor(storage: PostgreSQLStorage, code: str) -> Tuple[Optional[date], Optional[float]]:
    """获取单只股票最近一次的复权因子（备用）"""
    try:
        with storage.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT trade_date, adj_factor FROM stock_adj_factor "
                    "WHERE code = %s ORDER BY trade_date DESC LIMIT 1",
                    (code,)
                )
                row = cur.fetchone()
                if row:
                    return (row[0], row[1])
    except Exception as e:
        logger.debug(f"  {code}: 获取最新复权因子异常: {e}")
    return (None, None)


def fill_missing_dates(storage: PostgreSQLStorage, code: str, start_date: date,
                        end_date: date, last_adj_factor: float) -> int:
    """
    前向填充缺失日期的复权因子
    注意：复权因子只在分红/送股等事件时变化，无事件时保持恒定
    """
    if last_adj_factor is None:
        return 0

    try:
        with storage.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT trade_date FROM stock_adj_factor "
                    "WHERE code = %s AND trade_date >= %s AND trade_date <= %s",
                    (code, start_date, end_date)
                )
                existing_dates = {row[0] for row in cur.fetchall()}
    except Exception as e:
        logger.error(f"  [EXCEPTION] {code}: 查询已有日期失败: {e}")
        return 0

    # 生成需要填充的日期（排除已有）
    fill_dates = []
    current = start_date
    while current <= end_date:
        if current not in existing_dates:
            fill_dates.append(current)
        current += timedelta(days=1)

    if not fill_dates:
        return 0

    # 批量插入
    from psycopg2.extras import execute_values
    values = [(code, d, last_adj_factor) for d in fill_dates]
    try:
        with storage.transaction() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    "INSERT INTO stock_adj_factor (code, trade_date, adj_factor) "
                    "VALUES %s ON CONFLICT (code, trade_date) DO UPDATE SET adj_factor = EXCLUDED.adj_factor",
                    values
                )
        return len(fill_dates)
    except Exception as e:
        logger.error(f"  [EXCEPTION] {code}: 填充缺失日期失败: {e}")
        return 0


def sync_stock_adj_factor(source: BaostockDataSource, storage: PostgreSQLStorage,
                          code: str, exchange: str, start_date: date, end_date: date,
                          fill_missing: bool = True, skip_api: bool = False) -> int:
    """
    同步单只股票的复权因子数据
    Returns: 保存的记录数
    """
    bs_code = f"{exchange.lower()}.{code}"

    if skip_api:
        # 跳过 Baostock API，直接从 DB 前向填充
        if fill_missing:
            _, last_adj = get_last_known_adj_factor(storage, code)
            if last_adj is not None:
                return fill_missing_dates(storage, code, start_date, end_date, last_adj)
        return 0

    bs_start = start_date.strftime('%Y-%m-%d')
    bs_end = end_date.strftime('%Y-%m-%d')

    source._wait_for_rate_limit()

    try:
        rs = bs.query_adjust_factor(code=bs_code, start_date=bs_start, end_date=bs_end)

        if rs.error_code != '0':
            logger.debug(f"  ⚠️ {code}: 查询失败 {rs.error_msg}")
            return 0

        data_list = []
        while (rs.error_code == '0') and rs.next():
            row_data = rs.get_row_data()
            # row_data = [code, dividOperateDate, adjfactor, turn, parValue]
            if len(row_data) >= 3 and row_data[2] and row_data[2] != '':
                data_list.append({
                    'code': code,
                    'trade_date': row_data[1].replace('-', '') if '-' in str(row_data[1]) else str(row_data[1]),
                    'adj_factor': float(row_data[2])
                })

        if not data_list:
            # Baostock 返回空：可能是无分红事件
            if fill_missing:
                _, last_adj = get_last_known_adj_factor(storage, code)
                if last_adj is not None:
                    filled = fill_missing_dates(storage, code, start_date, end_date, last_adj)
                    if filled > 0:
                        logger.debug(f"  [FILL] {code}: 前向填充 {filled} 个缺失日期")
                    return filled
                logger.debug(f"  [SKIP] {code}: 无历史复权因子可填充")
            return 0

        df = pd.DataFrame(data_list)
        count = storage.save_adj_factor(df)
        return count

    except Exception as e:
        logger.error(f"  [EXCEPTION] {code}: 同步异常: {e}")
        return 0


def sync_adj_factor(incremental: bool = False):
    """同步复权因子数据（主流程）"""
    logger.info("=" * 60)
    logger.info("开始同步复权因子数据...")
    logger.info(f"模式: {'增量（最近30天）' if incremental else '全量历史'}")
    logger.info("=" * 60)

    # 初始化存储
    db_config = config.get('storage.postgresql', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', '990518')
    })
    if not storage.connect():
        logger.error("❌ 数据库连接失败")
        return
    storage.init_tables()

    # 连接 Baostock
    source = BaostockDataSource()
    if not source.connect():
        logger.error("❌ Baostock 连接失败")
        storage.disconnect()
        return

    try:
        # 1. 获取股票列表（优先数据库，备用 Baostock）
        all_stocks = get_active_stocks(storage, source)
        if all_stocks.empty:
            logger.error("❌ 无法获取股票列表，终止同步")
            return

        # 2. 确定日期范围
        today = datetime.now().date()
        if incremental:
            start_date = today - timedelta(days=30)
        else:
            start_date = date(2000, 1, 1)
        end_date = today

        logger.info(f"📅 日期范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")

        # 3. 批量获取所有股票的最新复权因子（优化）
        codes = all_stocks['code'].tolist()
        last_adj_factors = get_last_adj_factors_batch(storage, codes)
        logger.info(f"📊 已获取 {len(last_adj_factors)} 只股票的最新复权因子")

        # 4. 区分新股票和已有股票（增量模式）
        new_stocks = []
        existing_stocks = []
        if incremental:
            for s in all_stocks.itertuples():
                if s.code in last_adj_factors:
                    existing_stocks.append(s)
                else:
                    new_stocks.append(s)
            stocks_to_process = existing_stocks
            logger.info(f"  总股票: {len(all_stocks)}, DB 已有记录: {len(existing_stocks)}, 新上市股票: {len(new_stocks)}")
        else:
            stocks_to_process = list(all_stocks.itertuples())

        total_saved = 0
        total_with_data = 0
        total_skipped = 0
        total_stocks = len(stocks_to_process)
        skipped_log_count = 0
        MAX_SKIP_LOG = 5

        # 5. 逐股票同步
        for idx, s in enumerate(stocks_to_process):
            code = s.code
            exchange = getattr(s, 'exchange', 'SH' if code.startswith('6') else 'SZ')

            # 检查是否已是最新（增量模式）
            if incremental:
                last_info = last_adj_factors.get(code, (None, None))
                last_date = last_info[0]  # date 对象
                if last_date is not None and last_date >= end_date:
                    total_skipped += 1
                    if skipped_log_count < MAX_SKIP_LOG:
                        logger.debug(f"  [SKIP_UP2DATE] {code}: max_date={last_date} >= end_date={end_date}")
                        skipped_log_count += 1
                    continue

            # 智能决定是否跳过 API
            skip_api = incremental
            # 如果距离上次更新超过30天，强制刷新
            if incremental:
                last_info = last_adj_factors.get(code, (None, None))
                last_date = last_info[0]
                if last_date is None or (end_date - last_date).days > 30:
                    skip_api = False
                    logger.debug(f"  [FORCE_API] {code}: 超过30天未更新，强制刷新")

            count = sync_stock_adj_factor(
                source, storage, code, exchange,
                start_date, end_date,
                fill_missing=incremental,
                skip_api=skip_api
            )
            if count > 0:
                total_saved += count
                total_with_data += 1

            if (idx + 1) % 100 == 0:
                logger.info(f"  📊 进度: {idx+1}/{total_stocks} | "
                            f"已处理: {total_with_data} 只 | "
                            f"已跳过(最新): {total_skipped} 只 | "
                            f"总记录: {total_saved} 条")

        # 6. 处理新上市股票（增量模式下全量拉取）
        if new_stocks:
            logger.info(f"🆕 开始处理 {len(new_stocks)} 只新上市股票（全量拉取）...")
            new_saved = 0
            for idx, s in enumerate(new_stocks):
                code = s.code
                exchange = getattr(s, 'exchange', 'SH' if code.startswith('6') else 'SZ')
                # 新股票从上市日期开始
                stock_start = start_date
                if hasattr(s, 'list_date') and s.list_date:
                    try:
                        if isinstance(s.list_date, str):
                            list_dt = datetime.strptime(s.list_date[:10], '%Y-%m-%d').date()
                        else:
                            list_dt = s.list_date
                        stock_start = max(start_date, list_dt)
                    except Exception:
                        pass
                count = sync_stock_adj_factor(
                    source, storage, code, exchange,
                    stock_start, end_date,
                    fill_missing=False,
                    skip_api=False
                )
                if count > 0:
                    new_saved += count
                    total_with_data += 1
                if (idx + 1) % 100 == 0:
                    logger.info(f"  📊 新股票进度: {idx+1}/{len(new_stocks)} | 已处理: {new_saved} 条记录")
            logger.info(f"✅ 新股票处理完成: {len(new_stocks)} 只, 共 {new_saved} 条记录")
            total_saved += new_saved

        logger.info("=" * 60)
        logger.info("✅ 复权因子同步完成")
        logger.info(f"  处理股票: {total_with_data} 只")
        logger.info(f"  已跳过(最新): {total_skipped} 只")
        if new_stocks:
            logger.info(f"  新上市股票: {len(new_stocks)} 只")
        logger.info(f"  总记录数: {total_saved} 条")
        logger.info("=" * 60)

        print(f'TASK_RESULT:{json.dumps({"rows_affected": total_saved, "extra_metrics": {"total_stocks": total_with_data, "skipped": total_skipped, "new_stocks": len(new_stocks)}})}')

    except Exception as e:
        logger.error(f"❌ 同步复权因子失败: {e}", exc_info=True)
    finally:
        source.disconnect()
        storage.disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='同步复权因子数据')
    parser.add_argument('--incremental', action='store_true', help='增量模式（最近30天）')
    args = parser.parse_args()
    sync_adj_factor(incremental=args.incremental)