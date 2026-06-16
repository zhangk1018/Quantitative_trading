#!/usr/bin/env python3
"""
全市场日线技术指标计算脚本

从 stock_quotes 表读取价格数据，计算技术指标（MA/MACD/RSI/BOLL/KDJ）
并写入 stock_indicators 表。

用法：
    python backend/clean/etl/compute_indicators_daily.py              # 全市场计算
    python backend/clean/etl/compute_indicators_daily.py --code 000001  # 单只股票
"""
import sys
import os
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import argparse
import pandas as pd
from datetime import datetime
from collector.storage.postgresql_storage import PostgreSQLStorage
from clean.processor.technical_indicator import TechnicalIndicator
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('indicator_compute')


def compute_indicators_for_stock(storage: PostgreSQLStorage, code: str) -> int:
    """为指定股票计算技术指标（全量）"""
    db_code = code.split('.')[-1] if '.' in code else code
    # 2026-06-09: 扩展为 2025-01-01 以确保 MA60/RSI24 等长窗口指标有充足历史，
    # 提升信号预计算命中率（任务 5 验收：信号覆盖股票 ≥ 1000 只）
    start_date = '2025-01-01'
    end_date = datetime.now().strftime('%Y-%m-%d')

    quotes_df = storage.get_quotes(code=db_code, cycle='daily', start_date=start_date, end_date=end_date)
    if quotes_df.empty or len(quotes_df) < 60:
        logger.debug(f"{code} 数据不足（< 60天），跳过")
        return 0

    quotes_df['adjust_type'] = 'qfq'
    quotes_df['adjust_factor'] = 1.0
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        if col in quotes_df.columns:
            quotes_df[col] = quotes_df[col].astype(float)

    try:
        indicators_df = TechnicalIndicator.calculate_all(quotes_df, require_adjust=False)
    except Exception as e:
        logger.warning(f"{code} 计算失败: {e}")
        return 0

    # --- 准备入库数据 ---
    # 列顺序必须与 save_indicators 的 copy_from 一致：
    #   code, cycle, trade_date, ma5, ma10, ma20, ma60, macd, dif, dea, rsi6, rsi12, rsi24, trade_time, trade_datetime
    # TechnicalIndicator.calculate_all 返回列名为大写：MA5, MA10, MACD, MACD_SIGNAL, MACD_HIST, RSI 等
    # 2026-06-16 修复：MACD 字段映射错误 + RSI12/RSI24 未计算
    # 标准 MACD 定义：DIF = EMA12-EMA26, DEA = DIF 的 9 日 EMA, MACD 柱 = (DIF-DEA)*2
    # 代码计算：MACD = EMA12-EMA26 = DIF, MACD_SIGNAL = DEA, MACD_HIST = 柱状图
    indicator_mapping = {
        'MA5': 'ma5', 'MA10': 'ma10', 'MA20': 'ma20', 'MA60': 'ma60',
        'MACD_HIST': 'macd',  # 柱状图 → macd
        'MACD': 'dif',        # EMA12-EMA26 → dif
        'MACD_SIGNAL': 'dea'  # DIF 的 9 日 EMA → dea
    }

    # 从 indicators_df（=== result == df.copy()）取 code/trade_date 以保持索引一致，避免 NaN 对齐问题
    save_df = pd.DataFrame()
    save_df['code'] = indicators_df['code'] if 'code' in indicators_df.columns else db_code
    save_df['cycle'] = '1d'
    save_df['trade_date'] = indicators_df['trade_date']

    for src_col, dst_col in indicator_mapping.items():
        if src_col in indicators_df.columns:
            save_df[dst_col] = indicators_df[src_col].fillna(0)
        else:
            save_df[dst_col] = 0

    # 2026-06-16 修复：RSI 需要分别计算 6/12/24 三个窗口
    # calculate_all 默认 RSI window=14，不符合 RSI6 要求
    for window, col_name in [(6, 'rsi6'), (12, 'rsi12'), (24, 'rsi24')]:
        try:
            rsi_df = TechnicalIndicator.calculate_rsi(quotes_df.copy(), window=window, require_adjust=False)
            save_df[col_name] = rsi_df['RSI'].fillna(0) if 'RSI' in rsi_df.columns else 0
        except Exception:
            save_df[col_name] = 0

    # trade_time / trade_datetime 必须在数值列之后
    save_df['trade_time'] = save_df['trade_date'].apply(
        lambda x: f"{x.strftime('%Y-%m-%d')} 15:00:00" if hasattr(x, 'strftime') else f"{str(x)[:10]} 15:00:00"
    )
    save_df['trade_datetime'] = save_df['trade_time']

    count = storage.save_indicators(save_df)
    return count


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
        compute_indicators_for_stock(storage, args.code)
        storage.disconnect()
        return

    # 全市场计算
    stocks_df = storage.get_stock_list()
    if stocks_df.empty:
        logger.error("无股票列表")
        storage.disconnect()
        return

    codes = stocks_df['code'].tolist()
    total = len(codes)
    success = 0
    total_count = 0

    logger.info(f"开始全市场技术指标计算: {total} 只股票")

    for i, code in enumerate(codes):
        try:
            count = compute_indicators_for_stock(storage, code)
            if count > 0:
                success += 1
                total_count += count
        except Exception as e:
            logger.warning(f"{code} 处理失败: {e}")

        if (i + 1) % 200 == 0 or i == total:
            logger.info(f"进度: {i+1}/{total} ({(i+1)/total*100:.1f}%), 成功 {success}, 记录 {total_count}")

    logger.info(f"全市场技术指标计算完成: 成功 {success}/{total}, 总记录 {total_count}")
    storage.disconnect()


if __name__ == '__main__':
    main()