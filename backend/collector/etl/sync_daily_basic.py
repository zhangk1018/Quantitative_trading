#!/usr/bin/env python3
"""
sync_daily_basic.py - 日频基本面数据同步脚本

从数据源拉取日频基本面数据（PE/PB/换手率/市值/dv/ps等），写入 stock_daily_basic 表。

数据源优先级（与项目规范一致）：
  1. Tushare Pro — 主用，全量基本面（含 pe_ttm/pb/dv_ratio/ps_ttm/float_share/市值等），限速 5次/天
  2. Baostock — 备用，逐只股票拉取 PE/PB/换手率（免费，接口不稳定）
  3. PyWenCai — 预留（待实现），全市场一次拉取

注意：Baostock 仅提供 pe、pb、turnover_rate；
      dv_ratio/ps/ps_ttm/float_share/市值 等字段优先由 Tushare Pro 提供。

用法：
    python scripts/sync_daily_basic.py --latest       # 同步最新交易日
    python scripts/sync_daily_basic.py --date 2026-06-04  # 同步指定日期
    python scripts/sync_daily_basic.py --incremental   # 增量同步
    python scripts/sync_daily_basic.py --start 2026-01-01 --end 2026-01-10  # 范围同步
"""
import sys
import os
import json
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
import signal
import pandas as pd
import baostock as bs
from typing import Optional, List

from collector.datasource.base import DataSourceManager, SwitchStrategy
from collector.datasource.tushare import TushareDataSource
from collector.datasource.baostock import BaostockDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('daily_basic_sync')

# Tushare daily_basic 限频 60次/分钟，每次间隔至少 1.1 秒
DAILY_BASIC_MIN_INTERVAL = 1.1

# Baostock 单只查询超时（秒）：Baostock 网络阻塞时无内置超时，需 signal 兜底
BAOSTOCK_QUERY_TIMEOUT = 10


class _BaostockTimeout(Exception):
    """Baostock 单次查询超时"""
    pass


def _timeout_handler(signum, frame):
    """SIGALRM 处理器：Baostock 查询超时抛出异常"""
    raise _BaostockTimeout(f"Baostock 查询超过 {BAOSTOCK_QUERY_TIMEOUT} 秒超时")


class DailyBasicSync:
    """日频基本面同步器"""

    def __init__(self):
        db_config = config.get('storage.postgresql')
        if not db_config:
            db_config = {
                'host': os.getenv('PG_HOST', 'localhost'),
                'port': int(os.getenv('PG_PORT', 5432)),
                'database': os.getenv('PG_DATABASE', 'quant_trading'),
                'username': os.getenv('PG_USER', 'quant_user'),
                'password': os.getenv('PG_PASSWORD', ''),
            }
        self.storage = PostgreSQLStorage(db_config)
        # 数据源优先级：Tushare Pro（主用，全量基本面）→ Baostock（备用，pe_ttm 补全）
        self.dsm = DataSourceManager(
            sources=[
                {'source': TushareDataSource(), 'weight': 1, 'priority': 0},
                {'source': BaostockDataSource(), 'weight': 1, 'priority': 1},
            ],
            strategy=SwitchStrategy.FAILOVER,
            auto_recovery=True
        )

    def connect(self):
        self.storage.connect()
        self.storage.init_tables()
        self.dsm.connect()
        logger.info("✅ 数据源和数据库连接完成")

    def close(self):
        try:
            self.dsm.disconnect()
        except Exception:
            pass
        try:
            self.storage.disconnect()
        except Exception:
            pass

    def get_trading_dates(self) -> List[str]:
        """从 stock_quotes 获取所有有数据的交易日期（降序）"""
        with self.storage.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT trade_date FROM stock_quotes WHERE cycle='1d' ORDER BY trade_date DESC"
                )
                dates = [row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0])
                         for row in cur.fetchall()]
        logger.info(f"📋 获取到 {len(dates)} 个交易日期")
        return dates

    def get_existing_trade_dates(self) -> set:
        """查询 stock_daily_basic 中已有的交易日期"""
        with self.storage.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT trade_date FROM stock_daily_basic")
                dates = {row[0] for row in cur.fetchall()}
        return dates

    def sync_date(self, trade_date: str) -> int:
        """同步指定交易日的全市场日频基本面数据"""
        try:
            df = self.dsm._execute_with_fallback(
                'get_daily_basic',
                trade_date=trade_date
            )
            if df is None or df.empty:
                logger.debug(f"  {trade_date}: 无数据")
                return 0

            count = self.storage.save_daily_basic(df)
            logger.info(f"  {trade_date}: 保存 {count} 条")

            # Tushare 成功后，补全 pe_ttm 缺失的股票（Baostock 兜底）
            filled = self._fill_pe_ttm_gaps(trade_date)
            if filled > 0:
                logger.info(f"  {trade_date}: Baostock 补全 pe_ttm {filled} 只")

            return count

        except NotImplementedError as e:
            logger.error(f"❌ 当前所有数据源均不支持 daily_basic 接口: {e}")
            return 0
        except Exception as e:
            logger.warning(f"⚠️ 同步 {trade_date} 日频基本面失败: {e}")
            return 0

    def _fill_pe_ttm_gaps(self, trade_date: str) -> int:
        """用 Baostock 逐只补全 Tushare 返回中 pe_ttm 为 NULL 的股票

        优化：使用独立的 Baostock 连接 + 自定义快速限速（0.2s/只），
        避免被 DataSource 的全局速率限制器（20只/分钟）拖慢。
        """

        with self.storage.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT code FROM stock_daily_basic "
                    "WHERE trade_date = %s AND pe_ttm IS NULL",
                    (trade_date,)
                )
                missing_codes = [row[0] for row in cur.fetchall()]

        if not missing_codes:
            return 0

        logger.info(f"  🔍 发现 {len(missing_codes)} 只股票 pe_ttm 缺失，尝试 Baostock 快速补全（0.2s/只）")

        # 直接使用 Baostock 库，绕过 DataSource 的速率限制（20只/分钟）
        lg = bs.login()
        if lg.error_code != '0':
            logger.warning(f"  ⚠️ Baostock 登录失败: {lg.error_msg}，跳过 pe_ttm 补全")
            return 0

        # 设置 SIGALRM 超时处理器（仅主线程可用；非主线程则跳过超时防护）
        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            _use_timeout = True
        except (ValueError, TypeError):
            logger.warning("  ⚠️ 非主线程，无法启用 Baostock 查询超时防护")
            _use_timeout = False

        filled = 0
        failed = 0
        consecutive_failures = 0
        max_consecutive_failures = 10  # 加重连容忍，避免 Baostock 波动中断
        retried = False
        updates = []
        # Baostock query_history_k_data_plus 要求日期为 YYYY-MM-DD（带横线），
        # 不能转成 YYYYMMDD，否则报「日期格式不正确」
        bs_date = trade_date
        t0 = time.time()

        logger.info(f"  🚀 开始快速补全，目标 {len(missing_codes)} 只，预计 {(len(missing_codes) * 0.2) / 60:.0f} 分钟")

        for i, code in enumerate(missing_codes):
            try:
                time.sleep(0.18)  # 自定义快速限速（0.18s/只，≈ 5.5只/秒）
                # Baostock 要求 code 格式为 sh.600000 或 sz.000001
                bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
                if _use_timeout:
                    signal.alarm(BAOSTOCK_QUERY_TIMEOUT)
                try:
                    rs = bs.query_history_k_data_plus(
                        bs_code, "date,code,peTTM",
                        start_date=bs_date, end_date=bs_date,
                        frequency="d", adjustflag="3"
                    )
                finally:
                    if _use_timeout:
                        signal.alarm(0)
                if rs is None or rs.error_code != '0':
                    failed += 1
                    consecutive_failures += 1
                else:
                    rows = []
                    while rs.error_code == '0' and rs.next():
                        rows.append(rs.get_row_data())
                    if rows and len(rows[0]) >= 3 and rows[0][2]:
                        pe_ttm_val = float(rows[0][2])
                        updates.append((pe_ttm_val, code, trade_date))
                        filled += 1
                        consecutive_failures = 0
                    else:
                        failed += 1
                        consecutive_failures += 1
            except _BaostockTimeout:
                if _use_timeout:
                    signal.alarm(0)
                failed += 1
                consecutive_failures += 1
                logger.warning(f"  ⏱️ {code} Baostock 查询超时（>{BAOSTOCK_QUERY_TIMEOUT}s），跳过")
            except Exception as e:
                failed += 1
                consecutive_failures += 1
                if consecutive_failures <= 3:
                    logger.debug(f"  pe_ttm 补全 {code} 失败: {type(e).__name__}: {e}")

            # 连续失败过多，重连一次再试
            if consecutive_failures >= max_consecutive_failures:
                if not retried:
                    logger.warning(f"  ⚠️ 连续失败 {consecutive_failures} 次，尝试重新连接 Baostock...")
                    try:
                        bs.logout()
                    except Exception:
                        pass
                    time.sleep(1)
                    lg = bs.login()
                    if lg.error_code == '0':
                        retried = True
                        consecutive_failures = 0
                        logger.info("  ✅ Baostock 重连成功，继续补全")
                        continue
                    else:
                        logger.warning(f"  ❌ Baostock 重连失败: {lg.error_msg}")
                logger.warning(
                    f"  ⚠️ Baostock pe_ttm 补全连续失败 {consecutive_failures} 次，"
                    f"停止补全（已补 {filled}/{len(missing_codes)}，剩余 {len(missing_codes) - i - 1} 只跳过）"
                )
                break

            if (i + 1) % 500 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / (elapsed if elapsed else 1)
                eta = (len(missing_codes) - i - 1) / rate if rate else 0
                logger.info(f"  pe_ttm 补全进度: {i+1}/{len(missing_codes)} "
                            f"(已补:{filled} 失败:{failed}) "
                            f"速率:{rate:.1f}只/秒 "
                            f"预计剩余:{eta/60:.0f}分钟")

        # 登出 Baostock
        try:
            bs.logout()
        except Exception:
            pass

        # 批量更新数据库
        if updates:
            with self.storage.transaction() as conn:
                with conn.cursor() as cur:
                    from psycopg2.extras import execute_values
                    execute_values(cur,
                        "UPDATE stock_daily_basic SET pe_ttm = data.v::numeric "
                        "FROM (VALUES %s) AS data(v, code, trade_date) "
                        "WHERE stock_daily_basic.code = data.code "
                        "AND stock_daily_basic.trade_date = data.trade_date::date",
                        updates, page_size=1000
                    )
                conn.commit()

        logger.info(f"  ✅ pe_ttm 补全完成: {filled} 只成功, {failed} 只失败")
        return filled

    def sync_latest(self) -> int:
        """仅同步最新交易日，返回同步条数"""
        dates = self.get_trading_dates()
        if not dates:
            logger.warning("⚠️ 无交易日期数据")
            return 0

        latest_date = dates[0]
        logger.info(f"🔄 同步最新交易日: {latest_date}")

        count = self.sync_date(latest_date)
        logger.info(f"✅ {latest_date} 同步完成: {count} 条记录")
        return count

    def sync_all(self, start_date: Optional[str] = None,
                 end_date: Optional[str] = None) -> int:
        """同步所有交易日的日频基本面（按日期遍历），返回总条数"""
        all_dates = self.get_trading_dates()

        if start_date:
            all_dates = [d for d in all_dates if d >= start_date]
        if end_date:
            all_dates = [d for d in all_dates if d <= end_date]

        total_dates = len(all_dates)
        if total_dates == 0:
            logger.info("⚠️ 无待同步交易日期")
            return 0

        logger.info(f"🔄 开始按日期同步日频基本面: {total_dates} 个交易日")

        total_records = 0
        for i, date in enumerate(all_dates):
            if i % 100 == 0 and i > 0:
                logger.info(f"📊 进度: {i}/{total_dates} ({i*100//total_dates}%)")

            count = self.sync_date(date)
            total_records += count

        logger.info(f"✅ 日频基本面同步完成，共 {total_records} 条记录")
        return total_records

    def sync_incremental(self) -> int:
        """增量同步：只同步 stock_daily_basic 中尚未存在的交易日，返回总条数"""
        all_dates = self.get_trading_dates()
        existing = self.get_existing_trade_dates()

        missing_dates = [d for d in all_dates if d not in existing]
        if not missing_dates:
            logger.info("✅ 日频基本面数据已完整，无需增量同步")
            return 0

        logger.info(f"📋 发现 {len(missing_dates)} 个待同步交易日")

        total_records = 0
        for date in missing_dates:
            count = self.sync_date(date)
            total_records += count

        logger.info(f"✅ 增量同步完成，共 {total_records} 条记录")
        return total_records


def main():
    parser = argparse.ArgumentParser(description='日频基本面数据同步脚本')
    parser.add_argument('--latest', action='store_true', help='同步最新交易日')
    parser.add_argument('--date', type=str, help='同步指定日期（YYYY-MM-DD）')
    parser.add_argument('--start', type=str, help='起始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--incremental', action='store_true', help='增量同步')

    args = parser.parse_args()

    syncer = DailyBasicSync()
    syncer.connect()

    try:
        count = 0
        if args.incremental:
            count = syncer.sync_incremental()
        elif args.start and args.end:
            count = syncer.sync_all(start_date=args.start, end_date=args.end)
        elif args.date:
            count = syncer.sync_date(args.date)
            logger.info(f"✅ {args.date} 同步完成: {count} 条记录")
        else:
            # 默认：同步最近交易日
            count = syncer.sync_latest()
        print(f'TASK_RESULT:{json.dumps({"rows_affected": count})}')
    finally:
        syncer.close()


if __name__ == '__main__':
    main()