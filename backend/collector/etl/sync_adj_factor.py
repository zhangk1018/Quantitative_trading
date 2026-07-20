#!/usr/bin/env python3
"""
sync_adj_factor.py - 复权因子同步脚本

从 Baostock 获取前复权因子数据并更新到 stock_adj_factor 表。
使用 Baostock query_adjust_factor 接口，返回 foreAdjustFactor（前复权因子）。

使用说明：
  初次同步（全量历史）：python sync_adj_factor.py
  增量同步（最近30天）：python sync_adj_factor.py --incremental

数据源：Baostock (query_adjust_factor, 前复权因子)
"""

import sys
import os
import json
import argparse
import time

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import pandas as pd
from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple, Optional

from collector.datasource.baostock import BaostockDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('sync_adj_factor')


# ==================== 辅助函数 ====================

def get_active_stocks_from_db(storage: PostgreSQLStorage) -> pd.DataFrame:
    """从数据库获取活跃股票列表"""
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


def get_last_adj_factors_batch(storage: PostgreSQLStorage, codes: List[str]) -> Dict[str, Tuple[Optional[date], Optional[float]]]:
    """批量获取所有股票的最新复权因子"""
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
    """获取单只股票最近一次的复权因子"""
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
    """前向填充缺失日期的复权因子"""
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

    fill_dates = []
    current = start_date
    while current <= end_date:
        if current not in existing_dates:
            fill_dates.append(current)
        current += timedelta(days=1)

    if not fill_dates:
        return 0

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


def sync_stock_adj_factor_baostock(source: BaostockDataSource, storage: PostgreSQLStorage,
                                    code: str, start_date: date, end_date: date) -> int:
    """
    使用 Baostock 同步单只股票的复权因子

    Baostock query_adjust_factor 返回变更日数据（含 foreAdjustFactor）
    需要将因子值填充到变更日之后的所有日期（直到下一次变更）
    """
    try:
        # 获取复权因子变更日数据
        df = source.get_adj_factor_history(
            code=code,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
        )

        if df is None or df.empty:
            # 无分红事件：尝试从已有记录前向填充
            _, last_adj = get_last_known_adj_factor(storage, code)
            if last_adj is not None:
                filled = fill_missing_dates(storage, code, start_date, end_date, last_adj)
                if filled > 0:
                    logger.debug(f"  [FILL] {code}: 前向填充 {filled} 个缺失日期")
                return filled
            logger.debug(f"  [SKIP] {code}: 无历史复权因子可填充")
            return 0

        # 按日期升序排列
        df = df.sort_values('trade_date').reset_index(drop=True)

        # 将变更日因子展开为每日因子（前向填充）
        all_records = []
        prev_date = start_date
        prev_factor = None

        for _, row in df.iterrows():
            change_date = datetime.strptime(row['trade_date'], '%Y-%m-%d').date()
            current_factor = float(row['adj_factor'])

            if prev_factor is not None:
                # 填充 prev_date 到 change_date-1 的日期
                d = prev_date
                while d < change_date and d <= end_date:
                    all_records.append({
                        'code': code,
                        'trade_date': d.strftime('%Y-%m-%d'),
                        'adj_factor': prev_factor
                    })
                    d += timedelta(days=1)

            prev_date = max(change_date, start_date)
            prev_factor = current_factor

        # 填充最后一个变更日到 end_date
        if prev_factor is not None:
            d = prev_date
            while d <= end_date:
                all_records.append({
                    'code': code,
                    'trade_date': d.strftime('%Y-%m-%d'),
                    'adj_factor': prev_factor
                })
                d += timedelta(days=1)

        if not all_records:
            return 0

        result_df = pd.DataFrame(all_records)
        count = storage.save_adj_factor(result_df)
        return count

    except Exception as e:
        logger.error(f"  [EXCEPTION] {code}: Baostock 同步异常: {e}")
        return 0


def sync_adj_factor(incremental: bool = False):
    """同步复权因子数据（主流程）"""
    logger.info("=" * 60)
    logger.info("开始同步复权因子数据（数据源: Baostock）")
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
        sys.exit(1)
    storage.init_tables()

    # 连接 Baostock
    source = BaostockDataSource()
    if not source.connect():
        logger.error("❌ Baostock 连接失败")
        storage.disconnect()
        sys.exit(1)

    try:
        # 1. 获取股票列表
        all_stocks = get_active_stocks_from_db(storage)
        if all_stocks.empty:
            logger.error("❌ 无法获取股票列表，终止同步")
            sys.exit(1)

        # 2. 确定日期范围
        today = datetime.now().date()
        if incremental:
            start_date = today - timedelta(days=30)
        else:
            start_date = date(2000, 1, 1)
        end_date = today

        logger.info(f"📅 日期范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")

        # 3. 批量获取所有股票的最新复权因子
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
        t_start = time.time()
        for idx, s in enumerate(stocks_to_process):
            code = s.code

            # 检查是否已是最新（增量模式）
            if incremental:
                last_info = last_adj_factors.get(code, (None, None))
                last_date = last_info[0]
                if last_date is not None and last_date >= end_date:
                    total_skipped += 1
                    if skipped_log_count < MAX_SKIP_LOG:
                        logger.debug(f"  [SKIP_UP2DATE] {code}: max_date={last_date} >= end_date={end_date}")
                        skipped_log_count += 1
                    continue

            count = sync_stock_adj_factor_baostock(
                source, storage, code, start_date, end_date
            )
            if count > 0:
                total_saved += count
                total_with_data += 1

            if (idx + 1) % 200 == 0:
                elapsed = time.time() - t_start
                rate = (idx + 1) / elapsed
                eta = (total_stocks - idx - 1) / rate / 60
                logger.info(f"  📊 进度: {idx+1}/{total_stocks} | "
                            f"已处理: {total_with_data} 只 | "
                            f"已跳过: {total_skipped} 只 | "
                            f"总记录: {total_saved} 条 | "
                            f"速率: {rate:.1f}只/s | "
                            f"预计剩余: {eta:.0f}min")

        # 6. 处理新上市股票（增量模式下全量拉取）
        if new_stocks:
            logger.info(f"🆕 开始处理 {len(new_stocks)} 只新上市股票（全量拉取）...")
            new_saved = 0
            for idx, s in enumerate(new_stocks):
                code = s.code
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
                count = sync_stock_adj_factor_baostock(
                    source, storage, code, stock_start, end_date
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
        raise
    finally:
        source.disconnect()
        storage.disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='同步复权因子数据（Baostock）')
    parser.add_argument('--incremental', action='store_true', help='增量模式（最近30天）')
    args = parser.parse_args()
    sync_adj_factor(incremental=args.incremental)