#!/usr/bin/env python3
"""
fill_pe_ttm_eastmoney.py - 亏损股 pe_ttm 补全脚本

Tushare 和 Baostock 均不提供亏损股的 pe_ttm（负值），导致约 1500 只股票 pe_ttm 缺失，
覆盖率仅 ~72%。此脚本调用东方财富 API 逐个查询亏损股 pe_ttm 并写入 stock_daily_basic 表。

用法：
    python fill_pe_ttm_eastmoney.py              # 补全最新交易日
    python fill_pe_ttm_eastmoney.py --date 2026-07-22  # 补全指定日期
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
import time
import requests
from psycopg2.extras import execute_values
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('fill_pe_ttm_em')

# 东方财富 API 请求间隔（秒），避免被限流
REQUEST_INTERVAL = 0.05


class PeTtmFiller:
    """亏损股 pe_ttm 补全器"""

    def __init__(self):
        db_config = config.get('storage.postgresql') or {
            'host': os.getenv('PG_HOST', 'localhost'),
            'port': int(os.getenv('PG_PORT', 5432)),
            'database': os.getenv('PG_DATABASE', 'quant_trading'),
            'username': os.getenv('PG_USER', 'quant_user'),
            'password': os.getenv('PG_PASSWORD', ''),
        }
        self.storage = PostgreSQLStorage(db_config)

    def connect(self):
        self.storage.connect()
        logger.info("数据库连接成功")

    def close(self):
        try:
            self.storage.disconnect()
        except Exception:
            pass

    def get_latest_date(self) -> str:
        """获取最新交易日"""
        with self.storage.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(trade_date) FROM stock_daily_basic")
                latest = cur.fetchone()[0]
                return latest.strftime('%Y-%m-%d') if hasattr(latest, 'strftime') else str(latest)

    def fill(self, trade_date: str) -> int:
        """补全指定日期的 pe_ttm 缺失值"""
        # 获取缺失股票列表
        with self.storage.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT code FROM stock_daily_basic WHERE trade_date = %s AND pe_ttm IS NULL",
                    (trade_date,)
                )
                missing_codes = [row[0] for row in cur.fetchall()]

        if not missing_codes:
            logger.info(f"{trade_date}: pe_ttm 已完整，无需补全")
            return 0

        logger.info(f"{trade_date}: 发现 {len(missing_codes)} 只股票 pe_ttm 缺失，开始东方财富 API 补全")

        updates = []
        fetched = 0
        failed = 0

        for i, code in enumerate(missing_codes):
            market = '1' if code.startswith('6') else '0'
            try:
                resp = requests.get(
                    'https://push2.eastmoney.com/api/qt/stock/get',
                    params={
                        'secid': f'{market}.{code}',
                        'fields': 'f57,f164',
                        'fltt': '2',
                    },
                    timeout=5,
                )
                data = resp.json().get('data')
                if data is None:
                    failed += 1
                    continue

                pe_ttm_val = data.get('f164')
                if pe_ttm_val is None:
                    failed += 1
                    continue

                val = float(pe_ttm_val)
                if val == 0:
                    failed += 1
                    continue

                updates.append((val, code, trade_date))
                fetched += 1
            except Exception:
                failed += 1

            if (i + 1) % 200 == 0:
                logger.info(f"  进度: {i+1}/{len(missing_codes)} (已获取:{fetched} 失败:{failed})")
            time.sleep(REQUEST_INTERVAL)

        logger.info(f"  API 调用完成: 获取 {fetched} 只, 失败 {failed} 只")

        # 批量更新数据库
        if updates:
            pos_count = sum(1 for v, _, _ in updates if v > 0)
            neg_count = sum(1 for v, _, _ in updates if v < 0)
            logger.info(f"  正值: {pos_count}, 负值（亏损）: {neg_count}")

            with self.storage.transaction() as conn:
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        "UPDATE stock_daily_basic SET pe_ttm = data.v::numeric "
                        "FROM (VALUES %s) AS data(v, code, trade_date) "
                        "WHERE stock_daily_basic.code = data.code "
                        "AND stock_daily_basic.trade_date = data.trade_date::date",
                        updates,
                        page_size=1000,
                    )
                conn.commit()
            logger.info(f"  数据库更新完成: {len(updates)} 条")

        return len(updates)


def main():
    parser = argparse.ArgumentParser(description='亏损股 pe_ttm 补全脚本')
    parser.add_argument('--date', type=str, help='补全指定日期（YYYY-MM-DD），默认最新交易日')
    args = parser.parse_args()

    filler = PeTtmFiller()
    filler.connect()

    try:
        trade_date = args.date if args.date else filler.get_latest_date()
        logger.info(f"目标日期: {trade_date}")
        count = filler.fill(trade_date)
        print(f'TASK_RESULT:{json.dumps({"rows_affected": count})}')
    finally:
        filler.close()


if __name__ == '__main__':
    main()