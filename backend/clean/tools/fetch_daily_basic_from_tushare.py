#!/usr/bin/env python3
"""
fetch_daily_basic_from_tushare.py - 从 Tushare 获取每日基本面数据

获取字段：
- pe_ttm: 滚动市盈率
- ps: 市销率
- ps_ttm: 滚动市销率
- dv_ratio: 股息率
- dv_ttm: 滚动股息率
- float_share: 流通股本
- volume_ratio: 量比
- buy_sm_amount/sell_sm_amount: 小单买卖金额
- buy_md_amount/sell_md_amount: 中单买卖金额
- buy_lg_amount/sell_lg_amount: 大单买卖金额
- buy_elg_amount/sell_elg_amount: 特大单买卖金额
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
from datetime import datetime, timedelta
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('fetch_daily_basic')


def get_db_conn():
    db_config = config.get('database', {})
    return psycopg2.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432),
        database=db_config.get('database', 'quant_trading'),
        user=db_config.get('username', db_config.get('user', 'quant_user')),
        password=db_config.get('password', ''),
    )


def get_daily_basic_from_tushare(trade_date):
    """从 Tushare 获取每日基本面数据"""
    logger.info(f"📥 从 Tushare 获取 {trade_date} 的每日基本面数据...")
    
    try:
        import tushare as ts
        
        token = os.environ.get('TUSHARE_TOKEN') or os.environ.get('TS_TOKEN')
        if not token:
            logger.error("❌ 未找到 Tushare Token")
            return pd.DataFrame()
        
        pro = ts.pro_api(token)
        
        # 获取每日基本面数据
        df = pro.daily_basic(
            ts_code='',
            trade_date=trade_date,
            fields='ts_code,pe_ttm,ps,ps_ttm,dv_ratio,dv_ttm,float_share,volume_ratio'
        )
        
        logger.info(f"✅ 获取到 {len(df)} 条每日基本面数据")
        return df
        
    except Exception as e:
        logger.error(f"❌ 获取每日基本面数据失败：{e}", exc_info=True)
        return pd.DataFrame()


def get_money_flow_from_tushare(trade_date):
    """从 Tushare 获取资金流向数据"""
    logger.info(f"📥 从 Tushare 获取 {trade_date} 的资金流向数据...")
    
    try:
        import tushare as ts
        
        token = os.environ.get('TUSHARE_TOKEN') or os.environ.get('TS_TOKEN')
        if not token:
            logger.error("❌ 未找到 Tushare Token")
            return pd.DataFrame()
        
        pro = ts.pro_api(token)
        
        # 获取资金流向数据（需要较高权限）
        df = pro.moneyflow(
            ts_code='',
            trade_date=trade_date
        )
        
        logger.info(f"✅ 获取到 {len(df)} 条资金流向数据")
        return df
        
    except Exception as e:
        logger.warning(f"⚠️ 获取资金流向数据失败（可能需要更高权限）：{e}")
        return pd.DataFrame()


def update_daily_snapshot(conn, daily_basic_df, money_flow_df, trade_date):
    """更新 stock_daily_snapshot 表"""
    cur = conn.cursor()
    
    # 更新每日基本面数据
    if not daily_basic_df.empty:
        logger.info("🔄 更新每日基本面数据...")
        updated = 0
        for _, row in daily_basic_df.iterrows():
            code = row.get('ts_code', '').replace('.SZ', '').replace('.SH', '')
            if not code or len(code) != 6:
                continue
            
            updates = []
            params = []
            
            for col in ['pe_ttm', 'ps', 'ps_ttm', 'dv_ratio', 'dv_ttm', 'float_share', 'volume_ratio']:
                val = row.get(col)
                if pd.notna(val) and val != '' and val != '-':
                    updates.append(f"{col} = %s")
                    params.append(val)
            
            if updates:
                params.append(code)
                params.append(trade_date)
                cur.execute(f"""
                    UPDATE stock_daily_snapshot 
                    SET {', '.join(updates)} 
                    WHERE code = %s AND trade_date = %s
                """, params)
                updated += cur.rowcount
        
        conn.commit()
        logger.info(f"✅ 更新了 {updated} 条基本面数据")
    
    # 更新资金流向数据
    if not money_flow_df.empty:
        logger.info("🔄 更新资金流向数据...")
        updated = 0
        for _, row in money_flow_df.iterrows():
            code = row.get('ts_code', '').replace('.SZ', '').replace('.SH', '')
            if not code or len(code) != 6:
                continue
            
            updates = []
            params = []
            
            for col in ['buy_sm_amount', 'sell_sm_amount', 'buy_md_amount', 'sell_md_amount',
                        'buy_lg_amount', 'sell_lg_amount', 'buy_elg_amount', 'sell_elg_amount',
                        'net_mf_amount']:
                val = row.get(col)
                if pd.notna(val) and val != '':
                    updates.append(f"{col} = %s")
                    params.append(val)
            
            if updates:
                params.append(code)
                params.append(trade_date)
                cur.execute(f"""
                    UPDATE stock_daily_snapshot 
                    SET {', '.join(updates)} 
                    WHERE code = %s AND trade_date = %s
                """, params)
                updated += cur.rowcount
        
        conn.commit()
        logger.info(f"✅ 更新了 {updated} 条资金流向数据")
    
    cur.close()


def main():
    logger.info("=" * 60)
    logger.info("🔧 从 Tushare 获取每日基本面数据")
    logger.info("=" * 60)
    
    try:
        # 获取最新交易日
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(trade_date) FROM stock_daily_snapshot")
        latest_date = cur.fetchone()[0]
        cur.close()
        
        if not latest_date:
            logger.error("❌ 未找到交易日期")
            conn.close()
            return
        
        trade_date_str = latest_date.strftime('%Y%m%d')
        logger.info(f"📅 最新交易日：{latest_date}")
        
        # 1. 获取每日基本面数据
        daily_basic_df = get_daily_basic_from_tushare(trade_date_str)
        
        # 2. 获取资金流向数据
        money_flow_df = get_money_flow_from_tushare(trade_date_str)
        
        # 3. 更新数据库
        if not daily_basic_df.empty or not money_flow_df.empty:
            update_daily_snapshot(conn, daily_basic_df, money_flow_df, latest_date)
        
        conn.close()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 每日基本面数据获取完成")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 执行失败：{e}", exc_info=True)


if __name__ == '__main__':
    main()
