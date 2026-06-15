#!/usr/bin/env python3
"""
fix_adj_factor_full.py - 快速全量同步复权因子历史数据

比 sync_adj_factor.py 更快（200 req/min vs 20 req/min），
只同步 stock_quotes 中有数据的股票，跳过无交易数据的标的。
"""
import sys
import os
import time

_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(os.path.dirname(_script_dir))
_project_root = os.path.dirname(_backend_dir)
for p in [_project_root, _backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import baostock as bs
import psycopg2
import time
from datetime import datetime
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('fix_adj_factor_full')


def get_db_conn():
    db_config = config.get('database', {})
    return psycopg2.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432),
        database=db_config.get('database', 'quant_trading'),
        user=db_config.get('username', db_config.get('user', 'quant_user')),
        password=db_config.get('password', ''),
    )


def get_stocks_with_quotes(conn):
    """获取 stock_quotes 中有交易数据的股票列表（从stock_basic获取交易所信息）"""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT sq.code, COALESCE(sb.exchange, 
            CASE WHEN sq.code ~ '^6' THEN 'SH' ELSE 'SZ' END) AS exchange
        FROM stock_quotes sq
        LEFT JOIN stock_basic sb ON sq.code = sb.code
        WHERE sq.trade_date >= '2015-01-01'
        ORDER BY sq.code
    """)
    stocks = cur.fetchall()
    cur.close()
    logger.info(f"📋 获取到 {len(stocks)} 只有交易数据的股票")
    return [{'code': r[0], 'exchange': r[1] if r[1] else ('SH' if r[0].startswith('6') else 'SZ')} for r in stocks]


def check_table_exists(conn, table_name):
    cur = conn.cursor()
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
    """, (table_name,))
    exists = cur.fetchone()[0]
    cur.close()
    return exists


def get_existing_records(conn, code):
    """查询该股票已有的复权因子交易日，避免重复插入"""
    cur = conn.cursor()
    cur.execute("""
        SELECT trade_date FROM stock_adj_factor
        WHERE code = %s
        ORDER BY trade_date
    """, (code,))
    existing = {r[0] for r in cur.fetchall()}
    cur.close()
    return existing


def save_adj_factor_batch(conn, records):
    """批量写入复权因子数据"""
    if not records:
        return 0
    cur = conn.cursor()
    saved = 0
    for rec in records:
        try:
            cur.execute("""
                INSERT INTO stock_adj_factor (code, trade_date, adj_factor)
                VALUES (%s, %s, %s)
                ON CONFLICT (code, trade_date) DO NOTHING
            """, (rec['code'], rec['trade_date'], rec['adj_factor']))
            if cur.rowcount > 0:
                saved += 1
        except Exception as e:
            conn.rollback()
            cur = conn.cursor()
    conn.commit()
    cur.close()
    return saved


def sync_adj_factor_fast():
    """快速全量同步复权因子"""
    logger.info("=" * 60)
    logger.info("🚀 开始快速全量同步复权因子")
    logger.info("=" * 60)

    conn = get_db_conn()
    if not conn:
        logger.error("❌ 数据库连接失败")
        return

    # 检查表是否存在
    if not check_table_exists(conn, 'stock_adj_factor'):
        logger.error("❌ stock_adj_factor 表不存在")
        conn.close()
        return

    # 获取有交易数据的股票
    stocks = get_stocks_with_quotes(conn)
    if not stocks:
        conn.close()
        return

    # 登录 baostock
    lg = bs.login()
    if lg.error_code != '0':
        logger.error(f"❌ Baostock 登录失败: {lg.error_msg}")
        conn.close()
        return

    today = '2026-06-08'
    start_date = '2000-01-01'
    total_stocks = len(stocks)
    total_saved = 0
    total_with_data = 0
    total_attempted = 0
    _start = time.time()

    try:
        for idx, stock in enumerate(stocks):
            code = stock['code']
            exchange = stock['exchange']
            bs_code = f"{exchange.lower()}.{code}"

            # 查询已有记录，避免重复
            existing_dates = get_existing_records(conn, code)

            # baostock 查询
            rs = bs.query_adjust_factor(code=bs_code, start_date=start_date, end_date=today)

            if rs.error_code != '0':
                logger.debug(f"  ⚠️ {code}: {rs.error_msg}")
                time.sleep(0.3)
                continue

            batch_records = []
            while (rs.error_code == '0') and rs.next():
                row = rs.get_row_data()
                # row = [code, dividOperateDate, adjfactor, turn, parValue]
                if len(row) >= 3 and row[2] and row[2] != '':
                    trade_date_obj = datetime.strptime(row[1], '%Y-%m-%d').date()
                    if trade_date_obj not in existing_dates:
                        batch_records.append({
                            'code': code,
                            'trade_date': trade_date_obj,
                            'adj_factor': float(row[2])
                        })

            if batch_records:
                saved = save_adj_factor_batch(conn, batch_records)
                if saved > 0:
                    total_saved += saved
                    total_with_data += 1
                    total_attempted += 1
            else:
                total_attempted += 1

            # 每100只股票打印进度
            if (idx + 1) % 100 == 0:
                elapsed = time.time() - _start
                logger.info(f"  📊 进度: {idx+1}/{total_stocks} | "
                            f"有数据: {total_with_data} 只 | "
                            f"总记录: {total_saved} 条")

            # 最小间隔 0.3 秒（约 200 次/分钟）
            time.sleep(0.3)

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 复权因子同步完成")
        logger.info(f"  处理股票: {total_stocks} 只")
        logger.info(f"  有复权因子: {total_with_data} 只")
        logger.info(f"  总记录数: {total_saved} 条")
        logger.info(f"{'='*60}")

    except Exception:
        logger.error(f"❌ 同步失败", exc_info=True)
    finally:
        bs.logout()
        conn.close()


if __name__ == '__main__':
    sync_adj_factor_fast()