#!/usr/bin/env python3
"""
全市场日线技术指标计算脚本 (多进程优化版)
从 stock_quotes 表读取价格数据，计算技术指标（MA/MACD/RSI/BOLL）
并写入 stock_indicators 表。
"""
import sys
import os
import json
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)
import argparse
import pandas as pd
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from collector.storage.postgresql_storage import PostgreSQLStorage
from clean.processor.technical_indicator import TechnicalIndicator
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('indicator_compute')


def compute_indicators_for_stock(storage: PostgreSQLStorage, code: str) -> int:
    """为指定股票计算技术指标（全量）"""
    db_code = code.split('.')[-1] if '.' in code else code
    logger.info(f"▶️ 开始处理 {code} (DB Code: {db_code})...")
    
    # 动态计算起始日期：往前推 300 个自然日，确保长窗口指标有充足历史
    start_date = (datetime.now() - pd.Timedelta(days=300)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    quotes_df = storage.get_quotes(code=db_code, cycle='daily', start_date=start_date, end_date=end_date)
    
    if quotes_df.empty or len(quotes_df) < 60:
        logger.warning(f"⚠️ {code} 行情数据不足 (仅获取到 {len(quotes_df)} 条，需至少60条)，跳过计算")
        return 0
        
    logger.info(f"✅ {code} 获取到 {len(quotes_df)} 条行情数据，开始计算指标...")
    
    quotes_df['adjust_type'] = 'qfq'
    quotes_df['adjust_factor'] = 1.0
    
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        if col in quotes_df.columns:
            quotes_df[col] = quotes_df[col].astype(float)
            
    try:
        indicators_df = TechnicalIndicator.calculate_all(quotes_df, require_adjust=False)
    except Exception as e:
        logger.warning(f"❌ {code} 基础指标计算失败: {e}")
        return 0

    # --- 准备入库数据 ---
    indicator_mapping = {
        'MA5': 'ma5', 'MA10': 'ma10', 'MA20': 'ma20', 'MA60': 'ma60',
        'MACD_HIST': 'macd', 'MACD': 'dif', 'MACD_SIGNAL': 'dea'
    }
    
    save_df = pd.DataFrame()
    save_df['code'] = indicators_df['code'] if 'code' in indicators_df.columns else db_code
    save_df['cycle'] = '1d'
    save_df['trade_date'] = indicators_df['trade_date']
    
    # 构建 trade_datetime（带时区）
    save_date_index = pd.to_datetime(save_df['trade_date']).dt.date
    
    if 'trade_datetime' in indicators_df.columns:
        save_df['trade_datetime'] = indicators_df['trade_datetime']
    elif 'trade_datetime' in quotes_df.columns:
        dt_series = quotes_df.set_index(pd.to_datetime(quotes_df['trade_date']).dt.date)['trade_datetime']
        save_df['trade_datetime'] = save_date_index.map(dt_series)
    else:
        # 兜底：使用 trade_date 加上 15:00:00 (A股日线通常代表收盘时间)
        save_df['trade_datetime'] = pd.to_datetime(save_df['trade_date']) + pd.Timedelta(hours=15)

    # 【核心修复】确保 trade_time 列存在（save_indicators 内部需要该列）
    # 此处将 trade_time 设置为与 trade_datetime 相同（或可设为 None）
    save_df['trade_time'] = save_df['trade_datetime']

    for src_col, dst_col in indicator_mapping.items():
        save_df[dst_col] = indicators_df[src_col] if src_col in indicators_df.columns else None

    # RSI 计算 (6/12/24)
    for window, col_name in [(6, 'rsi6'), (12, 'rsi12'), (24, 'rsi24')]:
        try:
            rsi_df = TechnicalIndicator.calculate_rsi(quotes_df.copy(), window=window, require_adjust=False)
            if 'RSI' in rsi_df.columns:
                rsi_series = rsi_df.set_index(pd.to_datetime(rsi_df['trade_date']).dt.date)['RSI']
                save_df[col_name] = save_date_index.map(rsi_series)
            else:
                save_df[col_name] = None
        except Exception:
            save_df[col_name] = None

    # BOLL 计算 (20日)
    try:
        boll_df = TechnicalIndicator.calculate_boll(quotes_df.copy(), window=20, std_dev=2, require_adjust=False)
        for src_col, dst_col in [('BOLL_MID', 'boll_mid'), ('BOLL_UPPER', 'boll_upper'), ('BOLL_LOWER', 'boll_lower')]:
            if src_col in boll_df.columns:
                boll_series = boll_df.set_index(pd.to_datetime(boll_df['trade_date']).dt.date)[src_col]
                save_df[dst_col] = save_date_index.map(boll_series)
            else:
                save_df[dst_col] = None
    except Exception:
        save_df[['boll_mid', 'boll_upper', 'boll_lower']] = None

    if save_df.empty:
        return 0
        
    count = storage.save_indicators(save_df)
    logger.info(f"💾 {code} 指标保存完成，共写入 {count} 条记录")
    return count


def worker_compute(code: str) -> int:
    """子进程 Worker：每个子进程独立维护数据库连接"""
    db_config = config.get('database', {})
    local_storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', ''),
    })
    local_storage.connect()
    try:
        return compute_indicators_for_stock(local_storage, code)
    finally:
        local_storage.disconnect()


def main():
    parser = argparse.ArgumentParser(description='全市场日线技术指标计算')
    parser.add_argument('--code', type=str, help='单只股票代码')
    args = parser.parse_args()

    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', ''),
    })
    storage.connect()
    storage.init_tables()

    if args.code:
        # 单只股票计算（主进程直接执行）
        count = compute_indicators_for_stock(storage, args.code)
        print(f"\n🎉 单只股票 {args.code} 处理完成，共写入/更新 {count} 条指标记录。")
        storage.disconnect()
        return

    # 全市场多进程计算
    stocks_df = storage.get_stock_list()
    storage.disconnect()  # 主进程断开，避免连接池冲突
    
    if stocks_df.empty:
        logger.error("❌ 无股票列表")
        return
        
    codes = stocks_df['code'].tolist()
    total = len(codes)
    
    # 留 1-2 个核心给系统，其余全开
    max_workers = max(1, mp.cpu_count() - 1)
    logger.info(f"🚀 启动 {max_workers} 个进程并行计算 {total} 只股票...")
    
    success = 0
    total_count = 0
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker_compute, code) for code in codes]
        for i, future in enumerate(futures):
            try:
                count = future.result()
                if count > 0:
                    success += 1
                    total_count += count
            except Exception as e:
                logger.warning(f"❌ 股票 {codes[i]} 处理异常: {e}")
            
            if (i + 1) % 500 == 0 or i == total - 1:
                logger.info(f"📊 进度: {i+1}/{total} ({(i+1)/total*100:.1f}%), 成功 {success}, 记录 {total_count}")

    logger.info(f"🏁 全市场计算完成: 成功 {success}/{total}, 总记录 {total_count}")
    print(f'TASK_RESULT:{json.dumps({"rows_affected": total_count, "extra_metrics": {"success_stocks": success, "total_stocks": total}})}')


if __name__ == '__main__':
    main()