#!/usr/bin/env python3
"""从 Tushare 获取行业和基本面数据"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from sqlalchemy import create_engine, text
from utils.config import load_config
import pandas as pd
import tushare as ts
import time

def main():
    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user:quant_password@localhost:5432/quant_trading')
    engine = create_engine(db_url)

    pro = ts.pro_api()

    print("=" * 60)
    print("📥 从 Tushare 获取行业和基本面数据")
    print("=" * 60)

    # 1. 获取股票列表（包含行业）
    print("\n📡 获取股票基础信息（包含行业）...")
    try:
        df_basic = pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,symbol,name,industry,market,list_date'
        )
        print(f"✅ 获取到 {len(df_basic)} 只股票的基础信息")

        # 转换为数据库格式
        df_basic['code'] = df_basic['ts_code'].str.replace('.SZ', '').str.replace('.SH', '')
        df_basic['exchange'] = df_basic['ts_code'].apply(lambda x: 'SZ' if x.endswith('.SZ') else 'SH')

        # 更新 stock_basic 表
        with engine.connect() as conn:
            for _, row in df_basic.iterrows():
                conn.execute(
                    text("""
                        UPDATE stock_basic
                        SET name = :name, industry = :industry, exchange = :exchange
                        WHERE RIGHT(code, 6) = :code
                    """),
                    {
                        'name': row['name'],
                        'industry': row['industry'] if pd.notna(row['industry']) else '',
                        'exchange': row['exchange'],
                        'code': row['symbol']
                    }
                )
            conn.commit()
        print("✅ stock_basic 表更新完成")
    except Exception as e:
        print(f"❌ 获取股票基础信息失败: {e}")

    # 2. 获取日线基本面数据
    print("\n📡 获取日线基本面数据...")
    trade_dates = ['20260529', '20260530', '20260601']

    for trade_date in trade_dates:
        try:
            print(f"  📅 获取 {trade_date} 数据...")
            df_daily = pro.daily_basic(
                trade_date=trade_date,
                fields='ts_code,trade_date,close,pe,pb,total_mv,circ_mv,turnover_rate'
            )

            if df_daily is None or len(df_daily) == 0:
                print(f"  ⚠️ {trade_date} 无数据")
                continue

            print(f"  ✅ 获取到 {len(df_daily)} 条记录")

            # 插入到 stock_fundamental_pit 表
            with engine.connect() as conn:
                for _, row in df_daily.iterrows():
                    ts_code = row['ts_code']
                    code = ts_code.replace('.SZ', '').replace('.SH', '')

                    conn.execute(
                        text("""
                            INSERT INTO stock_fundamental_pit
                            (code, report_date, announce_date, pe_ttm, pb, total_mv, circ_mv, turnover_rate)
                            VALUES (:code, :report_date, :announce_date, :pe, :pb, :total_mv, :circ_mv, :turnover_rate)
                            ON CONFLICT (code, report_date)
                            DO UPDATE SET
                                pe_ttm = EXCLUDED.pe_ttm,
                                pb = EXCLUDED.pb,
                                total_mv = EXCLUDED.total_mv,
                                circ_mv = EXCLUDED.circ_mv,
                                turnover_rate = EXCLUDED.turnover_rate
                        """),
                        {
                            'code': code,
                            'report_date': trade_date,
                            'announce_date': trade_date,
                            'pe': row['pe'] if pd.notna(row['pe']) else None,
                            'pb': row['pb'] if pd.notna(row['pb']) else None,
                            'total_mv': row['total_mv'] if pd.notna(row['total_mv']) else None,
                            'circ_mv': row['circ_mv'] if pd.notna(row['circ_mv']) else None,
                            'turnover_rate': row['turnover_rate'] if pd.notna(row['turnover_rate']) else None,
                        }
                    )
                conn.commit()
            print(f"  ✅ {trade_date} 数据入库完成")

            time.sleep(1)  # 避免频率限制

        except Exception as e:
            print(f"  ❌ 获取 {trade_date} 数据失败: {e}")

    print("\n" + "=" * 60)
    print("✅ 数据获取完成！")
    print("=" * 60)

if __name__ == '__main__':
    main()
