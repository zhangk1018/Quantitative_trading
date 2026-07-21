#!/usr/bin/env python3
"""
sync_adj_factor.py - 复权因子同步脚本

从 Akshare 获取前复权因子数据并更新到 stock_adj_factor 表。
使用 Akshare stock_zh_a_daily(symbol=..., adjust='qfq-factor') 接口，
返回变更日复权因子，并展开为每日因子填充。

使用说明：
  初次同步（全量历史）：python sync_adj_factor.py
  增量同步（最近30天）：python sync_adj_factor.py --incremental

数据源：Akshare (stock_zh_a_daily, adjust='qfq-factor')
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

import akshare as ak

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('sync_adj_factor')


# ==================== 常量 ====================

AKSHARE_SYMBOL_PREFIX = {
    'SH': 'sh',
    'SZ': 'sz',
    'BJ': 'bj',
}

AKSHARE_START_DATE_FULL = date(2000, 1, 1)
AKSHARE_INCR_DAYS = 30


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
    """批量获取所有股票的最新复权因子（使用 LATERAL 索引查询，避免大表 IN 列表扫描）"""
    if not codes:
        return {}
    try:
        with storage.transaction() as conn:
            with conn.cursor() as cur:
                # 使用 LATERAL 子查询，对每只股票单独走 (code, trade_date) 索引取最新记录，
                # 在 5000 万级 stock_adj_factor 表上比 IN + DISTINCT ON 快 1-2 个数量级。
                cur.execute("""
                    SELECT s.code, f.trade_date, f.adj_factor
                    FROM stock_basic s
                    LEFT JOIN LATERAL (
                        SELECT trade_date, adj_factor
                        FROM stock_adj_factor f
                        WHERE f.code = s.code
                        ORDER BY trade_date DESC
                        LIMIT 1
                    ) f ON true
                    WHERE s.code = ANY(%s::text[])
                """, (codes,))
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


def ensure_adj_factor_index(storage: PostgreSQLStorage) -> bool:
    """确保 stock_adj_factor 表存在 (code, trade_date) 复合索引"""
    try:
        with storage.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_stock_adj_factor_code_date "
                    "ON stock_adj_factor (code, trade_date)"
                )
        logger.info("✅ 已确认 (code, trade_date) 复合索引存在")
        return True
    except Exception as e:
        logger.error(f"❌ 创建复合索引失败: {e}")
        return False


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

    BATCH_SIZE = 1000
    inserted = 0
    try:
        for i in range(0, len(values), BATCH_SIZE):
            batch = values[i:i + BATCH_SIZE]
            with storage.transaction() as conn:
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        "INSERT INTO stock_adj_factor (code, trade_date, adj_factor) "
                        "VALUES %s ON CONFLICT (code, trade_date) DO UPDATE SET adj_factor = EXCLUDED.adj_factor",
                        batch
                    )
            inserted += len(batch)
        return inserted
    except Exception as e:
        logger.error(f"  [EXCEPTION] {code}: 填充缺失日期失败: {e}")
        return inserted


def build_akshare_symbol(code: str, exchange: str) -> Optional[str]:
    """将内部 code + exchange 转换为 Akshare symbol"""
    if not code or not exchange:
        return None
    exchange_upper = str(exchange).upper()
    prefix = AKSHARE_SYMBOL_PREFIX.get(exchange_upper)
    if not prefix:
        logger.debug(f"  [SKIP] {code}: 不支持的交易所 {exchange}")
        return None
    return f"{prefix}{code}"


def expand_factor_to_daily(code: str, df: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    """
    将 Akshare 返回的变更日复权因子展开为每日复权因子（前向填充）。

    Args:
        code: 股票代码
        df: Akshare 返回的 DataFrame，列包含 date/qfq_factor
        start_date: 填充起始日期
        end_date: 填充结束日期

    Returns:
        包含 code/trade_date/adj_factor 的 DataFrame
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df['date'] = pd.to_datetime(df['date']).dt.date
    df = df.sort_values('date').reset_index(drop=True)

    records = []
    prev_date = start_date
    prev_factor = None

    for _, row in df.iterrows():
        change_date = row['date']
        current_factor = float(row['qfq_factor'])

        if prev_factor is not None:
            d = prev_date
            while d < change_date and d <= end_date:
                records.append({'code': code, 'trade_date': d, 'adj_factor': prev_factor})
                d += timedelta(days=1)

        prev_date = max(change_date, start_date)
        prev_factor = current_factor

    # 填充最后一个变更日到 end_date
    if prev_factor is not None:
        d = prev_date
        while d <= end_date:
            records.append({'code': code, 'trade_date': d, 'adj_factor': prev_factor})
            d += timedelta(days=1)

    return pd.DataFrame(records)


def sync_stock_adj_factor_akshare(storage: PostgreSQLStorage, code: str,
                                   symbol: str, start_date: date, end_date: date) -> int:
    """
    使用 Akshare 同步单只股票的复权因子。

    优先拉取变更日数据；若接口无返回，则使用数据库最新因子前向填充。
    """
    try:
        df = ak.stock_zh_a_daily(
            symbol=symbol,
            adjust='qfq-factor',
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'),
        )
    except Exception as e:
        logger.warning(f"  [WARN] {code}: Akshare 获取复权因子失败: {e}")
        df = pd.DataFrame()

    if df is None or df.empty:
        _, last_adj = get_last_known_adj_factor(storage, code)
        if last_adj is not None:
            filled = fill_missing_dates(storage, code, start_date, end_date, last_adj)
            if filled > 0:
                logger.debug(f"  [FILL] {code}: 前向填充 {filled} 个缺失日期")
            return filled
        logger.debug(f"  [SKIP] {code}: 无历史复权因子可填充")
        return 0

    result_df = expand_factor_to_daily(code, df, start_date, end_date)
    if result_df.empty:
        return 0

    count = storage.save_adj_factor(result_df)
    return count


def sync_adj_factor(incremental: bool = False):
    """同步复权因子数据（主流程）"""
    logger.info("=" * 60)
    logger.info("开始同步复权因子数据（数据源: Akshare）")
    logger.info(f"模式: {'增量（最近30天）' if incremental else '全量历史'}")
    logger.info("=" * 60)

    # 初始化存储：优先从配置读取，若未配置则从环境变量构建
    db_config = config.get('storage.postgresql')
    if not db_config:
        db_config = {
            'host': os.getenv('PG_HOST'),
            'port': int(os.getenv('PG_PORT', 5432)),
            'database': os.getenv('PG_DATABASE'),
            'username': os.getenv('PG_USER'),
            'password': os.getenv('PG_PASSWORD')
        }

    required_keys = ['host', 'port', 'database', 'username', 'password']
    missing_keys = [k for k in required_keys if k not in db_config or db_config[k] is None]
    if missing_keys:
        logger.error(f"❌ 数据库配置缺失字段: {missing_keys}")
        sys.exit(1)

    storage = PostgreSQLStorage(db_config)
    if not storage.connect():
        logger.error("❌ 数据库连接失败")
        sys.exit(1)
    storage.init_tables()
    if not ensure_adj_factor_index(storage):
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
            start_date = today - timedelta(days=AKSHARE_INCR_DAYS)
        else:
            start_date = AKSHARE_START_DATE_FULL
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
            exchange = s.exchange if hasattr(s, 'exchange') else None
            symbol = build_akshare_symbol(code, exchange)
            if not symbol:
                total_skipped += 1
                continue

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

            count = sync_stock_adj_factor_akshare(
                storage, code, symbol, start_date, end_date
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
                exchange = s.exchange if hasattr(s, 'exchange') else None
                symbol = build_akshare_symbol(code, exchange)
                if not symbol:
                    continue

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
                count = sync_stock_adj_factor_akshare(
                    storage, code, symbol, stock_start, end_date
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
        storage.disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='同步复权因子数据（Akshare）')
    parser.add_argument('--incremental', action='store_true', help='增量模式（最近30天）')
    args = parser.parse_args()
    sync_adj_factor(incremental=args.incremental)
