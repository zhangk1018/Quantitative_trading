#!/usr/bin/env python3
"""针对缺失的5只股票定向补数据"""
import sys
# 添加 backend 目录作为项目根
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/backend')
import psycopg2
import pandas as pd
from collector.datasource.tushare import TushareDataSource
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 5只缺失的股票
MISSING_CODES = ['688121', '688189', '002160', '600717', '001331']


def main():
    env = {}
    for line in open('/Users/zhangk/workspace/Quantitative_trading/.env'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k] = v
    pg_password = env.get('PG_PASSWORD', '')

    conn = psycopg2.connect(host='localhost', port=5432, dbname='quant_trading',
                             user='quant_user', password=pg_password)
    cur = conn.cursor()

    ts = TushareDataSource()
    if not ts.connect():
        logger.error("Tushare 连接失败，请检查 Token")
        return

    for code in MISSING_CODES:
        # 判断市场（Tushare格式）
        if code.startswith('6'):
            ts_code = f"sh.{code}"
        else:
            ts_code = f"sz.{code}"

        try:
            # 获取最近5天数据
            df = ts.get_kline(ts_code, start_date='2026-06-05', end_date='2026-06-11')
            if df is not None and not df.empty:
                rows = 0
                for _, row in df.iterrows():
                    # Tushare 返回的 trade_date 格式是 YYYYMMDD 整数或字符串
                    td_val = str(row['trade_date'])[:8]
                    trade_date = f"{td_val[:4]}-{td_val[4:6]}-{td_val[6:8]}"
                    # 计算涨跌幅
                    close = float(row['close'])
                    pre_close = float(row['pre_close']) if pd.notna(row['pre_close']) else close
                    # 检查是否已存在
                    cur.execute(
                        "SELECT 1 FROM stock_quotes WHERE code=%s AND trade_date=%s AND cycle='1d' LIMIT 1",
                        (code, trade_date)
                    )
                    if not cur.fetchone():
                        from datetime import datetime
                        # Tushare 返回的 trade_date 格式是 YYYYMMDD 字符串
                        td = str(row['trade_date'])[:8]
                        trade_dt = datetime.strptime(td, '%Y%m%d').replace(hour=15, minute=0, second=0)
                        cur.execute("""
                            INSERT INTO stock_quotes (code, trade_date, cycle, open, high, low, close, volume, amount, pre_close, trade_datetime)
                            VALUES (%s, %s, '1d', %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (code, trade_date, cycle) DO UPDATE SET
                                open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                                close=EXCLUDED.close, volume=EXCLUDED.volume, amount=EXCLUDED.amount,
                                pre_close=EXCLUDED.pre_close, trade_datetime=EXCLUDED.trade_datetime
                        """, (code, trade_date,
                              row.get('open'), row.get('high'), row.get('low'), close,
                              row.get('volume'), row.get('amount'), pre_close, trade_dt))
                        rows += 1
                conn.commit()
                logger.info(f"✅ {code} 补入 {rows} 条数据（{list(df['trade_date'].values)}）")
            else:
                logger.warning(f"⚠️ {code} Tushare无数据")
        except Exception as e:
            logger.error(f"❌ {code} 失败: {e}")

    cur.close()
    conn.close()

    # 验证结果
    conn2 = psycopg2.connect(host='localhost', port=5432, dbname='quant_trading',
                              user='quant_user', password=pg_password)
    cur2 = conn2.cursor()
    print("\n验证补入结果:")
    for code in MISSING_CODES:
        cur2.execute("""
            SELECT trade_date FROM stock_quotes
            WHERE code=%s AND cycle='1d' AND trade_date >= '2026-06-08'
            ORDER BY trade_date DESC LIMIT 5
        """, (code,))
        dates = [str(r[0]) for r in cur2.fetchall()]
        print(f"  {code}: {dates}")
    cur2.close()
    conn2.close()


if __name__ == '__main__':
    main()
