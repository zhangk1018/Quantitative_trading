#!/usr/bin/env python3
"""
calc_additional_indicators.py - 计算额外的技术指标

计算字段：
- break_high_20: 突破20日新高
- break_high_60: 突破60日新高
- consec_up_days: 连续上涨天数
- vol_ratio_5: 5日量比
"""

import sys
import os

_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(os.path.dirname(_script_dir))
_project_root = os.path.dirname(_backend_dir)
for p in [_project_root, _backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd
import psycopg2
import numpy as np
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('calc_additional_indicators')


def get_db_conn():
    db_config = config.get('database', {})
    return psycopg2.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432),
        database=db_config.get('database', 'quant_trading'),
        user=db_config.get('username', db_config.get('user', 'quant_user')),
        password=db_config.get('password', ''),
    )


def calc_indicators():
    """计算额外的技术指标"""
    logger.info("🔧 计算额外技术指标...")
    
    conn = get_db_conn()
    
    try:
        # 获取所有股票代码
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT code FROM stock_daily_snapshot ORDER BY code")
        codes = [row[0] for row in cur.fetchall()]
        cur.close()
        
        logger.info(f"📊 共有 {len(codes)} 只股票需要计算")
        
        total_updated = 0
        
        for idx, code in enumerate(codes):
            try:
                # 获取该股票的历史数据
                cur = conn.cursor()
                cur.execute("""
                    SELECT trade_date, high, volume 
                    FROM stock_quotes 
                    WHERE code = %s 
                    ORDER BY trade_date
                """, (code,))
                rows = cur.fetchall()
                cur.close()
                
                if len(rows) < 60:
                    continue
                
                df = pd.DataFrame(rows, columns=['trade_date', 'high', 'volume'])
                df['trade_date'] = pd.to_datetime(df['trade_date'])
                
                # 计算20日和60日最高价
                df['high_20'] = df['high'].rolling(window=20).max().shift(1)
                df['high_60'] = df['high'].rolling(window=60).max().shift(1)
                
                # 判断是否突破新高
                df['break_high_20'] = (df['high'] > df['high_20']).astype(int)
                df['break_high_60'] = (df['high'] > df['high_60']).astype(int)
                
                # 计算连续上涨天数（简单版本：当日high > 前日high）
                df['up_day'] = (df['high'] > df['high'].shift(1)).astype(int)
                df['consec_up_days'] = df['up_day'].groupby((df['up_day'] != df['up_day'].shift()).cumsum()).cumsum()
                
                # 计算5日量比
                df['vol_5_avg'] = df['volume'].rolling(window=5).mean().shift(1)
                df['vol_ratio_5'] = df['volume'] / df['vol_5_avg']
                
                # 更新到 stock_daily_snapshot
                cur = conn.cursor()
                for _, row in df.iterrows():
                    trade_date = row['trade_date'].date()
                    cur.execute("""
                        UPDATE stock_daily_snapshot 
                        SET break_high_20 = %s, break_high_60 = %s, 
                            consec_up_days = %s, vol_ratio_5 = %s
                        WHERE code = %s AND trade_date = %s
                    """, (row['break_high_20'], row['break_high_60'],
                          row['consec_up_days'], row['vol_ratio_5'],
                          code, trade_date))
                
                conn.commit()
                total_updated += cur.rowcount
                cur.close()
                
                if (idx + 1) % 100 == 0:
                    logger.info(f"  进度：{idx+1}/{len(codes)}")
                    
            except Exception as e:
                logger.debug(f"  计算 {code} 失败：{e}")
                conn.rollback()
        
        logger.info(f"✅ 共更新了 {total_updated} 条记录")
        
    finally:
        conn.close()


def main():
    logger.info("=" * 60)
    logger.info("🔧 计算额外技术指标")
    logger.info("=" * 60)
    
    try:
        calc_indicators()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 额外技术指标计算完成")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 执行失败：{e}", exc_info=True)


if __name__ == '__main__':
    main()
