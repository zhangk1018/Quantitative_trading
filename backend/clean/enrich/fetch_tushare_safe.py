#!/usr/bin/env python3
"""从 Tushare 获取基本面数据（带频率控制）"""

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
    print("📥 从 Tushare 获取基本面数据（带频率控制）")
    print("=" * 60)

    # 1. 获取日线基本面数据（限制1分钟1次）
    print("\n📡 获取日线基本面数据...")
    trade_dates = ['20260529', '20260601']

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

            # 等待65秒以避免频率限制
            print(f"  ⏳ 等待65秒以避免频率限制...")
            time.sleep(65)

        except Exception as e:
            print(f"  ❌ 获取 {trade_date} 数据失败: {e}")
            print(f"  ⏳ 等待65秒后重试...")
            time.sleep(65)

    # 2. 验证数据
    print("\n📊 验证数据...")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM stock_fundamental_pit"))
        count = result.scalar_one()
        print(f"stock_fundamental_pit 表: {count} 条记录")

    print("\n" + "=" * 60)
    print("✅ 数据获取完成！")
    print("=" * 60)

if __name__ == '__main__':
    main()
