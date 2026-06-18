#!/usr/bin/env python3
"""
Tushare daily_basic 同步脚本
拉取 dv_ratio/dv_ttm/float_share/ps/ps_ttm 补充 stock_daily_basic
限速: 5次/天（Tushare Pro 官方限制），每天配额有限，超限后直接跳过不抛异常
"""
import time
import logging
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import tushare as ts
except ImportError:
    logger.error("请安装 tushare: pip install tushare")
    raise

TOKEN = '6d5d9f045ba55813c8583e08eca3061eab07bbf69b044078b7a19c52'
FIELDS = 'ts_code,trade_date,dv_ratio,dv_ttm,float_share,ps,ps_ttm'

# Tushare 频率超限错误码
RATE_LIMIT_CODES = ('QFWQ00111', 'QPMT00113')


def get_tushare_pro():
    return ts.pro_api(TOKEN)


def sync_tushare_daily_basic(target_date: str = None, db_session=None) -> int:
    """同步指定日期的 Tushare daily_basic 数据到 stock_daily_basic"""
    from collector.db.database import get_db_session

    if target_date is None:
        target_date = (date.today() - timedelta(days=1)).strftime('%Y%m%d')

    trade_date_fmt = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]}"
    logger.info(f"📥 拉取 Tushare daily_basic {target_date} ...")

    pro = get_tushare_pro()
    df = None
    last_err = None

    for attempt in range(3):
        try:
            df = pro.daily_basic(trade_date=target_date, fields=FIELDS)
            break
        except Exception as e:
            last_err = e
            err_str = str(e)
            # 频率超限：直接跳过，不重试
            if any(code in err_str for code in RATE_LIMIT_CODES):
                logger.warning(f"Tushare daily_basic 配额耗尽（{attempt+1}/3）：{e}")
                return 0
            if attempt < 2:
                logger.warning(f"第 {attempt+1} 次失败: {e}，等待 65 秒重试...")
                time.sleep(65)
            # else: 最后一次失败，跳到下方统一处理

    if df is None or len(df) == 0:
        logger.warning(f"拉取失败或无数据: {target_date}，错误: {last_err}")
        return 0

    logger.info(f"获取 {len(df)} 条记录")

    # 转换列名: ts_code -> code, trade_date 格式
    df = df.rename(columns={
        'ts_code': 'code',
        'dv_ratio': 'dv_ratio',
        'dv_ttm': 'dv_ttm',
        'float_share': 'float_share',
        'ps': 'ps',
        'ps_ttm': 'ps_ttm',
    })
    # trade_date 转为 date 类型
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date

    # 过滤北交所股票：项目数据范围不包含北交所
    from utils.stock_code_utils import filter_out_bse
    df, _ = filter_out_bse(df)
    if df.empty:
        logger.info("过滤北交所后无数据")
        return 0

    # 转换为字典列表
    records = df.to_dict('records')

    # UPSERT 到 stock_daily_basic
    upsert_sql = text("""
        INSERT INTO stock_daily_basic (
            code, trade_date, dv_ratio, dv_ttm, float_share, ps, ps_ttm
        )
        VALUES (
            :code, :trade_date, :dv_ratio, :dv_ttm, :float_share, :ps, :ps_ttm
        )
        ON CONFLICT (code, trade_date) DO UPDATE SET
            dv_ratio = EXCLUDED.dv_ratio,
            dv_ttm = EXCLUDED.dv_ttm,
            float_share = EXCLUDED.float_share,
            ps = EXCLUDED.ps,
            ps_ttm = EXCLUDED.ps_ttm
    """)

    if db_session is None:
        with get_db_session() as session:
            session.execute(upsert_sql, records)
            session.commit()
    else:
        db_session.execute(upsert_sql, records)
        db_session.commit()

    logger.info(f"✅ 写入 stock_daily_basic {trade_date_fmt}，{len(records)} 条")
    return len(records)


if __name__ == '__main__':
    import sys
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None  # YYYYMMDD
    count = sync_tushare_daily_basic(date_arg)
    print(f"写入 {count} 条")
