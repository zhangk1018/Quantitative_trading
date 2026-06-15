#!/usr/bin/env python3
"""用 Baostock 获取完整股票列表并补充 stock_basic"""
import os
import sys
import logging

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
project_dir = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, os.path.join(project_dir, 'src'))

from dotenv import load_dotenv
load_dotenv(os.path.join(project_dir, '.env'))

import psycopg2
from psycopg2.extras import execute_values
import baostock as bs
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def get_connection():
    return psycopg2.connect(
        host=os.environ.get('PG_HOST', 'localhost'),
        port=int(os.environ.get('PG_PORT', 5432)),
        database=os.environ.get('PG_DATABASE', 'quant_trading'),
        user=os.environ.get('PG_USER', 'quant_user'),
        password=os.environ.get('PG_PASSWORD', '')
    )


def fetch_stock_list_from_baostock():
    """从 Baostock 获取完整股票列表（含科创板、北交所）"""
    lg = bs.login()
    if lg.error_code != '0':
        logger.error(f"Baostock 登录失败: {lg.error_msg}")
        return pd.DataFrame()

    rs = bs.query_stock_basic()
    rows = []
    while rs.error_code == '0' and rs.next():
        rows.append(rs.get_row_data())

    bs.logout()

    if not rows:
        logger.error("Baostock 返回空数据")
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=['code', 'code_name', 'ipoDate', 'outDate', 'type', 'status'])
    logger.info(f"Baostock 总记录数: {len(df)}")

    # 只保留上市状态
    listed = df[df['status'] == '1'].copy()
    logger.info(f"上市股票: {len(listed)}")

    # 提取纯数字代码
    listed['pure_code'] = listed['code'].apply(lambda x: x.split('.')[-1] if '.' in x else x)

    # 提取交易所
    listed['exchange_prefix'] = listed['code'].apply(lambda x: x.split('.')[0].upper() if '.' in x else '')

    # 只保留 A 股（排除指数、基金等）
    # type=1 表示股票
    a_stocks = listed[listed['type'] == '1'].copy()
    logger.info(f"A股股票: {len(a_stocks)}")

    # 过滤 B 股（900xxx, 200xxx）
    a_stocks = a_stocks[~a_stocks['pure_code'].str.match(r'^9\d{5}$')]  # 900xxx
    a_stocks = a_stocks[~a_stocks['pure_code'].str.match(r'^2\d{5}$')]  # 200xxx
    logger.info(f"过滤B股后: {len(a_stocks)}")

    # 构建结果
    result = pd.DataFrame({
        'code': a_stocks['pure_code'],
        'name': a_stocks['code_name'],
        'exchange': a_stocks['exchange_prefix'].map({'SH': 'SH', 'SZ': 'SZ'}).fillna('BJ'),
        'industry': '',
        'list_date': a_stocks['ipoDate'].apply(lambda x: x if x and x.strip() else None),
        'delist_date': a_stocks['outDate'].apply(lambda x: x if x and x.strip() else None),
    })

    # Baostock 的北交所代码前缀是 sh.920xxx 或 bj.920xxx
    # 920xxx 和 8xxxxx 都是北交所
    result.loc[result['code'].str.startswith('920'), 'exchange'] = 'BJ'
    result.loc[result['code'].str.match(r'^8\d{5}$'), 'exchange'] = 'BJ'

    # 统计
    def classify(code):
        p = code[:3]
        if p in ['600', '601', '602', '603', '604', '605']: return '沪主板'
        if p in ['688', '689']: return '科创板'
        if p in ['000', '001']: return '深主板'
        if p in ['002', '003']: return '中小板'
        if p in ['300', '301']: return '创业板'
        if p == '920': return '北交所920'
        if code[0] == '8': return '北交所8'
        return '其他'

    result['market'] = result['code'].apply(classify)
    market_counts = result['market'].value_counts().to_dict()
    logger.info(f"市场分布: {market_counts}")

    return result


def sync_to_stock_basic(conn, stock_df):
    """将股票列表同步到 stock_basic 表"""
    if stock_df.empty:
        logger.error("股票列表为空，跳过同步")
        return

    cursor = conn.cursor()

    # 获取当前 stock_basic 中的代码
    cursor.execute("SELECT code FROM stock_basic")
    existing_codes = {row[0] for row in cursor.fetchall()}
    logger.info(f"stock_basic 现有: {len(existing_codes)} 只")

    # 找出需要新增的股票
    new_stocks = stock_df[~stock_df['code'].isin(existing_codes)]
    logger.info(f"需要新增: {len(new_stocks)} 只")

    if not new_stocks.empty:
        # 统计新增股票的市场分布
        new_market_counts = new_stocks['market'].value_counts().to_dict()
        logger.info(f"新增市场分布: {new_market_counts}")

        values = []
        for _, row in new_stocks.iterrows():
            list_date = row.get('list_date')
            if list_date and isinstance(list_date, str) and len(list_date) == 8:
                list_date = f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:8]}"
            elif list_date and isinstance(list_date, str) and len(list_date) == 10:
                pass  # already YYYY-MM-DD
            else:
                list_date = None

            delist_date = row.get('delist_date')
            if delist_date and isinstance(delist_date, str) and len(delist_date) == 8:
                delist_date = f"{delist_date[:4]}-{delist_date[4:6]}-{delist_date[6:8]}"
            elif delist_date and isinstance(delist_date, str) and len(delist_date) == 10:
                pass
            else:
                delist_date = None

            values.append((
                row['code'],
                row['name'],
                row['exchange'],
                row.get('industry') or None,
                list_date,
                delist_date
            ))

        insert_sql = """
            INSERT INTO stock_basic (code, name, exchange, industry, list_date, delist_date)
            VALUES %s
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                exchange = EXCLUDED.exchange,
                industry = COALESCE(EXCLUDED.industry, stock_basic.industry),
                list_date = COALESCE(EXCLUDED.list_date, stock_basic.list_date),
                updated_at = CURRENT_TIMESTAMP
        """
        execute_values(cursor, insert_sql, values)
        conn.commit()
        logger.info(f"成功插入/更新 {cursor.rowcount} 只股票")

    # 验证
    cursor.execute("SELECT COUNT(*) FROM stock_basic")
    total = cursor.fetchone()[0]
    logger.info(f"stock_basic 总数: {total}")

    # 按市场统计
    cursor.execute("""
        SELECT
            CASE
                WHEN substring(code, 1, 3) IN ('600','601','602','603','604','605') THEN '沪主板'
                WHEN substring(code, 1, 3) IN ('688','689') THEN '科创板'
                WHEN substring(code, 1, 3) IN ('000','001') THEN '深主板'
                WHEN substring(code, 1, 3) IN ('002','003') THEN '中小板'
                WHEN substring(code, 1, 3) IN ('300','301') THEN '创业板'
                WHEN substring(code, 1, 3) = '920' THEN '北交所920'
                WHEN substring(code, 1, 1) = '8' THEN '北交所8'
                ELSE '其他'
            END as market,
            COUNT(*)
        FROM stock_basic
        GROUP BY market
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        logger.info(f"  {row[0]}: {row[1]}")

    cursor.close()


def verify_coverage(conn):
    """验证覆盖率"""
    cursor = conn.cursor()

    # 最新交易日
    cursor.execute("SELECT MAX(trade_date)::date FROM stock_quotes")
    latest_date = cursor.fetchone()[0]

    # stock_basic 总数
    cursor.execute("SELECT COUNT(*) FROM stock_basic")
    total = cursor.fetchone()[0]

    # 覆盖数
    cursor.execute("""
        SELECT COUNT(DISTINCT q.code)
        FROM stock_quotes q
        WHERE q.trade_date::date = %s
    """, (latest_date,))
    covered = cursor.fetchone()[0]

    # 缺失
    cursor.execute("""
        SELECT COUNT(*) FROM stock_basic b
        WHERE NOT EXISTS (
            SELECT 1 FROM stock_quotes q
            WHERE q.code = b.code AND q.trade_date::date = %s
        )
    """, (latest_date,))
    missing = cursor.fetchone()[0]

    # 多出
    cursor.execute("""
        SELECT COUNT(DISTINCT q.code) FROM stock_quotes q
        WHERE q.trade_date::date = %s
        AND NOT EXISTS (SELECT 1 FROM stock_basic b WHERE b.code = q.code)
    """, (latest_date,))
    extra = cursor.fetchone()[0]

    rate = (covered / total * 100) if total > 0 else 0
    logger.info(f"最新交易日 {latest_date}:")
    logger.info(f"  stock_basic: {total} 只")
    logger.info(f"  stock_quotes 覆盖: {covered} 只")
    logger.info(f"  覆盖率: {rate:.2f}%")
    logger.info(f"  缺失: {missing} 只")
    logger.info(f"  多出: {extra} 只")

    cursor.close()


def main():
    logger.info("=" * 60)
    logger.info("Baostock 股票列表同步脚本")
    logger.info("=" * 60)

    conn = get_connection()
    try:
        # Step 1: 从 Baostock 获取完整股票列表
        logger.info("\n--- Step 1: 从 Baostock 获取股票列表 ---")
        stock_df = fetch_stock_list_from_baostock()

        # Step 2: 同步到 stock_basic
        logger.info("\n--- Step 2: 同步到 stock_basic ---")
        sync_to_stock_basic(conn, stock_df)

        # Step 3: 验证覆盖率
        logger.info("\n--- Step 3: 验证覆盖率 ---")
        verify_coverage(conn)

        logger.info("\n" + "=" * 60)
        logger.info("同步完成")
        logger.info("=" * 60)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
