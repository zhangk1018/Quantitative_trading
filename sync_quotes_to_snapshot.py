#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 stock_quotes 计算技术指标并同步到 stock_daily_snapshot 宽表"""

import os
import sys
import pandas as pd
import psycopg2
from datetime import datetime, timedelta

# 配置
PG_HOST = 'localhost'
PG_PORT = '5432'
PG_DATABASE = 'quant_trading'
PG_USER = 'quant_user'
PG_PASSWORD = '990518'

def calc_ma(series, window):
    """计算移动平均线"""
    return series.rolling(window=window, min_periods=1).mean()

def calc_macd(series, fast=12, slow=26, signal=9):
    """计算 MACD 指标"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def calc_rsi(series, window=6):
    """计算 RSI 指标"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=window, min_periods=1).mean()
    avg_loss = loss.rolling(window=window, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, 0.0001)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss != 0, 100)
    return rsi

def calc_boll(series, window=20, std_dev=2):
    """计算布林带"""
    mid = series.rolling(window=window, min_periods=1).mean()
    std = series.rolling(window=window, min_periods=1).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower

def get_listed_board(code):
    """根据股票代码判断上市板"""
    if code.startswith('60'):
        return '主板'
    elif code.startswith('000'):
        return '主板'
    elif code.startswith('002'):
        return '中小板'
    elif code.startswith('300'):
        return '创业板'
    elif code.startswith('688'):
        return '科创板'
    else:
        return '其他'

def sync_date_to_snapshot(target_date: str):
    """同步指定日期的数据到宽表"""
    conn = psycopg2.connect(
        host=PG_HOST,
        port=int(PG_PORT),
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD
    )
    
    print(f"\n🔄 开始同步 {target_date} 的数据...")
    
    # 1. 从 stock_quotes 获取目标日期的数据
    with conn.cursor() as cur:
        cur.execute("""
            SELECT code, trade_date, open, high, low, close, pre_close, volume, amount, adjust_type
            FROM stock_quotes
            WHERE cycle = '1d' AND trade_date = %s
            ORDER BY code
        """, (target_date,))
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
        df_today = pd.DataFrame(rows, columns=columns)
    
    print(f"   📊 获取到 {len(df_today)} 条当日数据")
    
    if len(df_today) == 0:
        print(f"   ❌ {target_date} 没有数据")
        conn.close()
        return
    
    # 2. 从 stock_quotes 获取每只股票最近 60 个交易日的数据（用于计算指标）
    target_dt = datetime.strptime(target_date, '%Y-%m-%d')
    start_dt = target_dt - timedelta(days=120)  # 多取一些以确保有足够数据
    start_date = start_dt.strftime('%Y-%m-%d')
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT code, trade_date, open, high, low, close, volume
            FROM stock_quotes
            WHERE cycle = '1d' AND trade_date >= %s AND trade_date <= %s
            ORDER BY code, trade_date
        """, (start_date, target_date))
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
        df_history = pd.DataFrame(rows, columns=columns)
    
    print(f"   📊 获取到 {len(df_history)} 条历史数据（{start_date} ~ {target_date}）")
    
    # 3. 从 stock_basic 获取股票基本信息
    with conn.cursor() as cur:
        cur.execute("""
            SELECT code, name, industry, area
            FROM stock_basic
            WHERE delist_date IS NULL
        """)
        rows = cur.fetchall()
        df_basic = pd.DataFrame(rows, columns=['code', 'stock_name', 'industry', 'area'])
    
    print(f"   📊 获取到 {len(df_basic)} 条股票基本信息")
    
    # 4. 计算每只股票的技术指标
    print(f"   🔢 计算技术指标...")
    results = []
    
    # 按股票分组计算
    grouped = df_history.groupby('code')
    total_stocks = len(df_today)
    
    for idx, row in df_today.iterrows():
        code = row['code']
        
        # 获取该股票的历史数据
        if code not in grouped.groups:
            continue
        
        df_stock = grouped.get_group(code).sort_values('trade_date').reset_index(drop=True)
        
        if len(df_stock) < 5:
            continue
        
        # 计算技术指标
        close = df_stock['close']
        volume = df_stock['volume']
        
        ma5 = calc_ma(close, 5).dropna().iloc[-1] if len(close) >= 5 else None
        ma10 = calc_ma(close, 10).dropna().iloc[-1] if len(close) >= 10 else None
        ma20 = calc_ma(close, 20).dropna().iloc[-1] if len(close) >= 20 else None
        v_ma5 = int(calc_ma(volume, 5).dropna().iloc[-1]) if len(volume) >= 5 else None
        
        macd_line, signal_line, hist = calc_macd(close)
        macd_val = macd_line.dropna().iloc[-1] if len(macd_line.dropna()) > 0 else None
        _ = signal_line  # 未使用，仅计算
        _ = hist  # 未使用，仅计算
        
        rsi_6 = calc_rsi(close, 6).dropna().iloc[-1] if len(calc_rsi(close, 6).dropna()) > 0 else None
        
        boll_upper, boll_mid, boll_lower = calc_boll(close)
        boll_upper_val = boll_upper.dropna().iloc[-1] if len(boll_upper.dropna()) > 0 else None
        boll_mid_val = boll_mid.dropna().iloc[-1] if len(boll_mid.dropna()) > 0 else None
        boll_lower_val = boll_lower.dropna().iloc[-1] if len(boll_lower.dropna()) > 0 else None
        
        # 计算涨跌
        change = row['close'] - row['pre_close'] if row['pre_close'] else None
        change_pct = (change / row['pre_close'] * 100) if row['pre_close'] else None
        
        # 获取股票基本信息
        basic_info = df_basic[df_basic['code'] == code]
        if len(basic_info) > 0:
            stock_name = basic_info.iloc[0]['stock_name']
            industry = basic_info.iloc[0]['industry']
            area = basic_info.iloc[0]['area']
        else:
            stock_name = None
            industry = None
            area = None
        
        # 上市板
        listed_board = get_listed_board(code)
        
        results.append({
            'code': code,
            'stock_name': stock_name,
            'listed_board': listed_board,
            'industry': industry,
            'sub_industry': industry,
            'area': area,
            'trade_date': target_date,
            'open': float(row['open']) if pd.notna(row['open']) and row['open'] else None,
            'high': float(row['high']) if pd.notna(row['high']) and row['high'] else None,
            'low': float(row['low']) if pd.notna(row['low']) and row['low'] else None,
            'close': float(row['close']) if pd.notna(row['close']) and row['close'] else None,
            'pre_close': float(row['pre_close']) if pd.notna(row['pre_close']) and row['pre_close'] else None,
            'volume': int(row['volume']) if pd.notna(row['volume']) and row['volume'] else None,
            'amount': float(row['amount']) if pd.notna(row['amount']) and row['amount'] else None,
            'adjust_type': row['adjust_type'] or 'qfq',
            'change': round(change, 2) if change else None,
            'change_pct': round(change_pct, 2) if change_pct else None,
            'ma5': round(float(ma5), 2) if ma5 and not pd.isna(ma5) else None,
            'ma10': round(float(ma10), 2) if ma10 and not pd.isna(ma10) else None,
            'ma20': round(float(ma20), 2) if ma20 and not pd.isna(ma20) else None,
            'v_ma5': v_ma5,
            'rsi_6': round(float(rsi_6), 2) if rsi_6 and not pd.isna(rsi_6) else None,
            'macd': round(float(macd_val), 4) if macd_val and not pd.isna(macd_val) else None,
            'boll_upper': round(float(boll_upper_val), 2) if boll_upper_val and not pd.isna(boll_upper_val) else None,
            'boll_mid': round(float(boll_mid_val), 2) if boll_mid_val and not pd.isna(boll_mid_val) else None,
            'boll_lower': round(float(boll_lower_val), 2) if boll_lower_val and not pd.isna(boll_lower_val) else None,
        })
        
        if (idx + 1) % 500 == 0:
            print(f"   进度: {idx + 1}/{total_stocks}")
    
    df_result = pd.DataFrame(results)
    print(f"   ✅ 计算完成，共 {len(df_result)} 条记录")
    
    # 5. 同步到数据库
    print(f"   💾 同步到 stock_daily_snapshot...")
    
    with conn.cursor() as cur:
        # 先删除该日期的旧数据
        cur.execute("DELETE FROM stock_daily_snapshot WHERE trade_date = %s", (target_date,))
        deleted = cur.rowcount
        print(f"   🗑️  已清除 {deleted} 条旧数据")
        
        # 批量插入新数据
        insert_count = 0
        batch_size = 500
        
        for i in range(0, len(df_result), batch_size):
            batch = df_result.iloc[i:i+batch_size]
            
            for _, row in batch.iterrows():
                cols = []
                vals = []
                params = []
                
                for col in df_result.columns:
                    val = row[col]
                    if pd.isna(val) or val is None:
                        continue
                    cols.append(col)
                    vals.append('%s')
                    params.append(val)
                
                if cols:
                    sql = f"""
                        INSERT INTO stock_daily_snapshot ({', '.join(cols)})
                        VALUES ({', '.join(vals)})
                    """
                    cur.execute(sql, params)
                    insert_count += 1
            
            conn.commit()
            print(f"   进度: {min(i + batch_size, len(df_result))}/{len(df_result)}")
        
        print(f"   ✅ 插入 {insert_count} 条新数据")

    # 5b. 从 stock_daily_basic 补全 PE/vol_ratio（取最近可用日期）
    print(f"   📊 补全 PE/vol_ratio 字段...")
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE stock_daily_snapshot s
            SET
                pe = db.pe,
                pe_ttm = db.pe_ttm,
                pb = db.pb,
                turnover_rate = db.turnover_rate,
                volume_ratio = db.volume_ratio,
                market_cap = db.total_mv,
                circ_mv = db.circ_mv
            FROM (
                SELECT code, trade_date, pe, pe_ttm, pb, turnover_rate, volume_ratio, total_mv, circ_mv,
                       ROW_NUMBER() OVER (PARTITION BY SPLIT_PART(code, '.', 2) ORDER BY trade_date DESC) as rn
                FROM stock_daily_basic
                WHERE trade_date <= %s
            ) db
            WHERE SPLIT_PART(db.code, '.', 2) = s.code
              AND db.rn = 1
              AND s.trade_date = %s
              AND (s.pe IS NULL OR s.pe_ttm IS NULL)
        """, (target_date, target_date))
        conn.commit()
        updated = cur.rowcount
        print(f"   ✅ 更新了 {updated} 条的 PE/vol_ratio 字段")

    # 6. 验证结果
    print(f"\n📊 验证 {target_date} 数据...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN pe IS NOT NULL THEN 1 ELSE 0 END) as pe_count,
                SUM(CASE WHEN ma5 IS NOT NULL THEN 1 ELSE 0 END) as ma5_count,
                SUM(CASE WHEN ma10 IS NOT NULL THEN 1 ELSE 0 END) as ma10_count,
                SUM(CASE WHEN ma20 IS NOT NULL THEN 1 ELSE 0 END) as ma20_count,
                SUM(CASE WHEN macd IS NOT NULL THEN 1 ELSE 0 END) as macd_count,
                SUM(CASE WHEN rsi_6 IS NOT NULL THEN 1 ELSE 0 END) as rsi6_count,
                SUM(CASE WHEN boll_mid IS NOT NULL THEN 1 ELSE 0 END) as boll_count,
                SUM(CASE WHEN volume_ratio IS NOT NULL THEN 1 ELSE 0 END) as vr_count
            FROM stock_daily_snapshot 
            WHERE trade_date = %s
        """, (target_date,))
        row = cur.fetchone()
        
        if row:
            print(f"  总记录数: {row[0]}")
            print(f"  PE非空: {row[1]}")
            print(f"  MA5非空: {row[2]} ({row[2]/row[0]*100:.1f}%)")
            print(f"  MA10非空: {row[3]} ({row[3]/row[0]*100:.1f}%)")
            print(f"  MA20非空: {row[4]} ({row[4]/row[0]*100:.1f}%)")
            print(f"  MACD非空: {row[5]} ({row[5]/row[0]*100:.1f}%)")
            print(f"  RSI6非空: {row[6]} ({row[6]/row[0]*100:.1f}%)")
            print(f"  BOLL非空: {row[7]} ({row[7]/row[0]*100:.1f}%)")
            print(f"  vol_ratio非空: {row[8]} ({row[8]/row[0]*100:.1f}%)")
    
    conn.close()
    print(f"\n🎉 {target_date} 同步完成！")

if __name__ == '__main__':
    import subprocess
    
    if len(sys.argv) > 1 and sys.argv[1] != '--skip-health-check':
        target_date = sys.argv[1]
    else:
        # 自动获取 stock_quotes 最新日期
        conn = psycopg2.connect(
            host=PG_HOST,
            port=int(PG_PORT),
            database=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD
        )
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
            result = cur.fetchone()[0]
            target_date = result.strftime('%Y-%m-%d') if result else None
        conn.close()
        if not target_date:
            print('❌ 无法获取最新交易日期')
            sys.exit(1)
        print(f'📅 自动获取最新日期: {target_date}')
    skip_health = '--skip-health-check' in sys.argv

    # 前置条件检查
    if not skip_health:
        print('🔍 执行前置条件检查...')
        health_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       'backend', 'collector', 'etl', 'pipeline_health_check.py')
        if os.path.exists(health_script):
            ret = subprocess.run(
                [sys.executable, health_script, '--pre-sync'],
                capture_output=False
            )
            if ret.returncode != 0:
                print('❌ 前置条件检查未通过！')
                print('   使用 --skip-health-check 强制跳过（不推荐）')
                sys.exit(1)
        else:
            print(f'⚠️  前置检查脚本不存在: {health_script}（跳过检查）')

    sync_date_to_snapshot(target_date)
