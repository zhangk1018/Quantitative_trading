#!/usr/bin/env python3
"""
回补缺失指标股票的历史行情数据
目标：让这些股票有足够数据计算技术指标
"""
import sys, os, time, logging
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/backend')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

import akshare as ak
import pandas as pd
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

# 初始化数据库
db_config = config.get('database', {})
storage = PostgreSQLStorage({
    'host': db_config.get('host', 'localhost'),
    'port': db_config.get('port', 5432),
    'database': db_config.get('database', 'quant_trading'),
    'username': db_config.get('username', 'quant_user'),
    'password': db_config.get('password', ''),
})
storage.connect()
cur = storage.conn.cursor()

def get_missing_stocks():
    """获取有行情但缺指标的活跃股票"""
    cur.execute("""
        WITH active AS (
            SELECT DISTINCT code FROM stock_quotes
            WHERE cycle = '1d' AND trade_date = '2026-06-08'
        ),
        has_ind AS (
            SELECT DISTINCT code FROM stock_indicators WHERE cycle = '1d'
        )
        SELECT a.code, b.name, b.list_date,
               (SELECT COUNT(*) FROM stock_quotes q WHERE q.code = a.code AND q.cycle = '1d') as quote_days,
               (SELECT MIN(trade_date)::text FROM stock_quotes q WHERE q.code = a.code AND q.cycle = '1d') as min_date
        FROM active a
        JOIN stock_basic b ON a.code = b.code
        WHERE a.code NOT IN (SELECT code FROM has_ind)
        ORDER BY b.list_date DESC NULLS LAST
    """)
    return cur.fetchall()

def backfill_one(code, list_date):
    """用akshare回补单只股票"""
    try:
        # 确定起始日期
        start = '20250102'  # 2025年第一个交易日
        if list_date:
            ld = str(list_date)[:10].replace('-', '')
            if ld > start:
                start = ld

        # 调用akshare
        df = ak.stock_zh_a_hist(
            symbol=code,
            period='daily',
            start_date=start,
            end_date='20260608',
            adjust=''
        )

        if df is None or df.empty:
            return 0, "empty"

        # 转换为数据库格式
        result_df = pd.DataFrame({
            'code': code,
            'cycle': '1d',
            'trade_date': pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d'),
            'open': df['开盘'],
            'high': df['最高'],
            'low': df['最低'],
            'close': df['收盘'],
            'volume': df['成交量'].astype(int),
            'amount': df['成交额'],
            'turnover': df['换手率'],
        })

        # 去重保存
        storage.save_quotes(result_df)
        return len(result_df), "ok"

    except Exception as e:
        return 0, str(e)

def main():
    missing = get_missing_stocks()
    total = len(missing)
    logger.info(f"共 {total} 只股票缺指标，开始回补...")

    success = 0
    fail = 0
    skip = 0
    total_rows = 0

    for i, (code, name, list_date, quote_days, min_date) in enumerate(missing):
        # 已有足够数据的跳过
        if quote_days >= 60:
            logger.info(f"[{i+1}/{total}] {code} {name} - 已有{quote_days}天，跳过")
            skip += 1
            continue

        logger.info(f"[{i+1}/{total}] {code} {name} (上市:{list_date}, 现有:{quote_days}天)")
        rows, status = backfill_one(code, list_date)

        if status == "ok":
            success += 1
            total_rows += rows
            logger.info(f"  -> 回补 {rows} 条")
        else:
            fail += 1
            logger.warning(f"  -> 失败: {status}")

        time.sleep(0.25)  # 限流

    logger.info(f"\n===== 回补完成 =====")
    logger.info(f"成功: {success}, 失败: {fail}, 跳过(已有≥60天): {skip}")
    logger.info(f"总计新增: {total_rows} 条行情记录")

    # 验证
    cur.execute("""
        SELECT COUNT(DISTINCT code) as ind_count
        FROM stock_indicators WHERE cycle = '1d'
    """)
    current_ind = cur.fetchone()[0]
    logger.info(f"当前指标覆盖: {current_ind} 只股票")

    storage.disconnect()

if __name__ == '__main__':
    main()
