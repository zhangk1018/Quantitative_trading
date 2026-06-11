#!/usr/bin/env python3
"""
backfill_daily_basic.py — 补全 dv/ps/float_share 历史数据

使用 PyWenCai（同花顺问财）数据源，重新抓取全市场日频基本面数据，
覆盖写入 stock_daily_basic 表，补齐 dv_ratio/dv_ttm/ps/ps_ttm/float_share 字段。
然后同步到 stock_daily_snapshot 中对应的字段。

数据流：PyWenCai → stock_daily_basic (UPSERT) → stock_daily_snapshot (UPDATE)

用法：
    python backfill_daily_basic.py                           # 补全最近 30 天
    python backfill_daily_basic.py --days 90                 # 补全最近 90 天
    python backfill_daily_basic.py --start 2026-01-01        # 补全指定范围
    python backfill_daily_basic.py --start 2026-01-01 --end 2026-06-10
    python backfill_daily_basic.py --dry-run                 # 仅统计，不执行
"""
import sys
import os
import time
import argparse
from datetime import datetime, timedelta
from typing import List, Optional

_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(os.path.dirname(_script_dir))
_project_root = os.path.dirname(_backend_dir)
for p in [_project_root, _backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd
from collector.datasource.base import DataSourceManager, SwitchStrategy
from collector.datasource.pywencai_ds import PyWencaiDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('backfill_daily_basic')


def get_db_conn():
    db_config = config.get('database', {})
    import psycopg2
    return psycopg2.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432),
        database=db_config.get('database', 'quant_trading'),
        user=db_config.get('username', db_config.get('user', 'quant_user')),
        password=db_config.get('password', ''),
    )


def get_missing_dates(conn, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[str]:
    """
    获取 stock_daily_snapshot 中 dv_ratio IS NULL 的交易日。
    这些日期需要补全 dv/ps/float_share。
    """
    where_clauses = ["q.cycle='1d'"]
    params = []

    if start_date:
        where_clauses.append("q.trade_date >= %s")
        params.append(start_date)
    if end_date:
        where_clauses.append("q.trade_date <= %s")
        params.append(end_date)

    where = " AND ".join(where_clauses)

    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT q.trade_date
        FROM stock_quotes q
        WHERE {where}
          AND q.trade_date NOT IN (
              SELECT DISTINCT trade_date FROM stock_daily_snapshot
              WHERE dv_ratio IS NOT NULL
          )
        ORDER BY q.trade_date
    """, params)

    dates = [row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0])
             for row in cur.fetchall()]
    cur.close()
    return dates


def get_existing_dates_to_refresh(conn, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[str]:
    """
    获取 stock_daily_basic 中已有记录但 dv_ratio IS NULL 的日期。
    这些 date 已经通过库存在 stock_daily_basic 但有 dv_ratio 为空（之前数据源不给）。
    也需要重跑覆盖。
    """
    where_clauses = ["s.dv_ratio IS NULL"]
    params = []

    if start_date:
        where_clauses.append("s.trade_date >= %s")
        params.append(start_date)
    if end_date:
        where_clauses.append("s.trade_date <= %s")
        params.append(end_date)

    where = " AND ".join(where_clauses)

    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT s.trade_date
        FROM stock_daily_basic s
        WHERE {where}
        ORDER BY s.trade_date
    """, params)

    dates = [row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0])
             for row in cur.fetchall()]
    cur.close()
    return dates


def sync_snapshot_for_date(conn, trade_date):
    """将 stock_daily_basic 的 dv/ps/float_share 同步到 stock_daily_snapshot 对应的日期"""
    cur = conn.cursor()
    cur.execute("""
        UPDATE stock_daily_snapshot s
        SET
            dv_ratio   = b.dv_ratio,
            dv_ttm     = b.dv_ttm,
            ps         = b.ps,
            ps_ttm     = b.ps_ttm,
            float_share = b.float_share
        FROM stock_daily_basic b
        WHERE b.code = s.code
          AND b.trade_date = s.trade_date
          AND b.trade_date = %s
          AND (
            s.dv_ratio IS DISTINCT FROM b.dv_ratio OR
            s.dv_ttm   IS DISTINCT FROM b.dv_ttm OR
            s.ps       IS DISTINCT FROM b.ps OR
            s.ps_ttm   IS DISTINCT FROM b.ps_ttm OR
            s.float_share IS DISTINCT FROM b.float_share
          )
    """, (trade_date,))
    updated = cur.rowcount
    conn.commit()
    cur.close()
    return updated


def main():
    parser = argparse.ArgumentParser(description='补全 dv/ps/float_share 历史数据')
    parser.add_argument('--start', type=str, help='起始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, help='截止日期 YYYY-MM-DD')
    parser.add_argument('--days', type=int, default=30, help='最近 N 天（默认 30）')
    parser.add_argument('--dry-run', action='store_true', help='仅统计，不执行')
    args = parser.parse_args()

    # 初始化数据源
    storage = PostgreSQLStorage(config.get('storage'))
    dsm = DataSourceManager(
        sources=[
            {'source': PyWencaiDataSource(), 'weight': 1, 'priority': 0},
        ],
        strategy=SwitchStrategy.FAILOVER,
        auto_recovery=True
    )
    storage.connect()
    dsm.connect()
    conn = storage.conn

    try:
        # 确定日期范围
        if args.start and args.end:
            start_date = args.start
            end_date = args.end
        elif args.start:
            start_date = args.start
            end_date = None
        elif args.end:
            start_date = None
            end_date = args.end
        else:
            # 默认：最近 N 天
            start = datetime.now() - timedelta(days=args.days)
            start_date = start.strftime('%Y-%m-%d')
            end_date = None

        # 获取缺失日期
        missing = get_missing_dates(conn, start_date, end_date)
        # 获取需要刷新的日期（已有记录但 dv_ratio IS NULL）
        to_refresh = get_existing_dates_to_refresh(conn, start_date, end_date)

        # 合并去重
        all_dates = sorted(set(missing + to_refresh))

        if not all_dates:
            logger.info("✅ 无需补全，dv/ps/float_share 已完整")
            return

        total = len(all_dates)
        logger.info(f"📋 待处理日期: {total} 个")
        if missing:
            logger.info(f"   - 缺失日期: {len(missing)} 个 (snapshot 中无该日期)")
        if to_refresh:
            logger.info(f"   - 需刷新:   {len(to_refresh)} 个 (已有记录但字段为空)")
        logger.info(f"   范围: {all_dates[0]} ~ {all_dates[-1]}")

        if args.dry_run:
            logger.info(f"🏁 Dry-run 模式，前 5 个日期: {all_dates[:5]} ...")
            return

        logger.info("=" * 60)
        logger.info("🚀 开始补全 dv/ps/float_share ...")
        logger.info("=" * 60)

        success = 0
        failed = 0
        total_snapshot_updated = 0
        start_ts = time.time()

        for i, trade_date in enumerate(all_dates):
            logger.info(f"[{i+1}/{total}] {trade_date} ...")

            try:
                # 通过 DataSourceManager 拉取 PyWenCai 数据
                df = dsm._execute_with_fallback(
                    'get_daily_basic',
                    trade_date=trade_date
                )

                if df is None or df.empty:
                    logger.warning(f"  ⚠️ 无数据")
                    failed += 1
                else:
                    # 保存到 stock_daily_basic（UPSERT 覆盖）
                    cnt = storage.save_daily_basic(df)
                    logger.info(f"  ✅ 保存到 stock_daily_basic: {cnt} 条")

                    # 同步到 stock_daily_snapshot
                    snapshot_updated = sync_snapshot_for_date(conn, trade_date)
                    total_snapshot_updated += snapshot_updated
                    logger.info(f"  ✅ 同步到 stock_daily_snapshot: {snapshot_updated} 条")

                    success += 1

                # 进度
                elapsed = time.time() - start_ts
                avg = elapsed / (i + 1)
                remaining = avg * (total - i - 1)
                logger.info(f"    进度: {i+1}/{total} | 已用 {elapsed/60:.1f}分 | 预计剩余 {remaining/60:.1f}分")

            except Exception as e:
                logger.error(f"  ❌ 失败: {e}")
                failed += 1

        elapsed_total = time.time() - start_ts
        logger.info("=" * 60)
        logger.info(f"✅ 补全完成")
        logger.info(f"   成功: {success} 天 | 失败: {failed} 天")
        logger.info(f"   同步到 snapshot: {total_snapshot_updated} 次更新")
        logger.info(f"   耗时: {elapsed_total/60:.1f} 分")
        logger.info("=" * 60)

    finally:
        dsm.disconnect()
        storage.disconnect()


if __name__ == '__main__':
    main()