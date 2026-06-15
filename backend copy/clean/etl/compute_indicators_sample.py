#!/usr/bin/env python3
"""
技术指标计算脚本 - 从 stock_quotes 表读取价格数据，计算技术指标并写入 stock_indicators 表

简化版：只计算部分股票（100只），用于验证信号预计算功能
"""
import sys
import os
# 将 backend 目录加入 Python 路径
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import pandas as pd
import numpy as np
from datetime import datetime
from collector.storage.postgresql_storage import PostgreSQLStorage
from clean.processor.technical_indicator import TechnicalIndicator
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('indicator_compute')


def compute_indicators_for_stock(storage: PostgreSQLStorage, code: str) -> int:
    """为指定股票计算技术指标"""
    logger.debug(f"计算 {code} 的技术指标...")

    # 转换代码格式：SZ.000001 -> 000001
    db_code = code.split('.')[-1] if '.' in code else code

    # 1. 获取价格数据（只获取 2026 年数据，因为只有 2026 年分区）
    start_date = '2026-01-01'
    end_date = datetime.now().strftime('%Y-%m-%d')

    quotes_df = storage.get_quotes(code=db_code, cycle='daily', start_date=start_date, end_date=end_date)
    if quotes_df.empty or len(quotes_df) < 60:
        logger.warning(f"⚠️ {code} 价格数据不足（< 60天），跳过")
        return 0

    # 2. 添加复权标识（技术指标计算器要求）
    quotes_df['adjust_type'] = 'qfq'
    quotes_df['adjust_factor'] = 1.0  # 简化版：假设已复权

    # 转换 Decimal 类型为 float（技术指标计算器要求）
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        if col in quotes_df.columns:
            quotes_df[col] = quotes_df[col].astype(float)

    # 3. 计算所有技术指标
    try:
        indicators_df = TechnicalIndicator.calculate_all(quotes_df, require_adjust=False)
    except Exception as e:
        logger.warning(f"⚠️ {code} 技术指标计算失败: {e}")
        return 0

    # 4. 准备入库数据（列顺序必须与 save_indicators 期望一致）
    save_df = pd.DataFrame()
    save_df['code'] = indicators_df['code'] if 'code' in indicators_df.columns else db_code
    save_df['cycle'] = '1d'
    save_df['trade_date'] = indicators_df['trade_date']

    # 添加技术指标列
    indicator_cols = {
        'MA5': 'ma5', 'MA10': 'ma10', 'MA20': 'ma20', 'MA60': 'ma60',
        'MACD': 'macd', 'MACD_SIGNAL': 'dif', 'MACD_HIST': 'dea',  # 注意：MACD_SIGNAL 对应 dif，MACD_HIST 对应 dea
        'RSI': 'rsi6'
    }

    for src_col, dst_col in indicator_cols.items():
        if src_col in indicators_df.columns:
            save_df[dst_col] = indicators_df[src_col]

    # 添加缺失的列（rsi12, rsi24, trade_time, trade_datetime）
    for col in ['rsi12', 'rsi24']:
        if col not in save_df.columns:
            save_df[col] = 0
    for col in ['trade_time', 'trade_datetime']:
        if col not in save_df.columns:
            # 使用 trade_date 转换为 datetime（处理 datetime.date 和 string 两种类型）
            save_df[col] = save_df['trade_date'].apply(
                lambda x: f"{x.strftime('%Y-%m-%d')} 15:00:00" if hasattr(x, 'strftime') else f"{str(x)[:10]} 15:00:00"
            )

    # 填充数值列的 NaN 值
    numeric_cols = ['ma5', 'ma10', 'ma20', 'ma60', 'macd', 'dif', 'dea', 'rsi6', 'rsi12', 'rsi24']
    for col in numeric_cols:
        if col in save_df.columns:
            save_df[col] = save_df[col].fillna(0)

    # 5. 保存到数据库
    count = storage.save_indicators(save_df)
    logger.debug(f"  {code}: 保存 {count} 条指标")
    return count


def main():
    """主函数"""
    # 初始化数据库连接
    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', ''),
    })
    storage.connect()

    logger.info("=" * 60)
    logger.info("开始计算技术指标（简化版：100只股票）...")
    logger.info("=" * 60)

    # 获取股票列表（只取前 100 只）
    stocks_df = storage.get_stock_list()
    if stocks_df.empty:
        logger.error("❌ 无股票列表")
        storage.disconnect()
        return

    # 只处理前 100 只股票（简化版）
    codes = stocks_df['code'].tolist()[:100]
    total = len(codes)
    success = 0
    total_count = 0

    logger.info(f"📊 待处理股票: {total} 只")

    for i, code in enumerate(codes):
        try:
            count = compute_indicators_for_stock(storage, code)
            if count > 0:
                success += 1
                total_count += count

            if (i + 1) % 10 == 0:
                logger.info(f"  进度: {i+1}/{total} ({(i+1)/total*100:.1f}%)")

        except Exception as e:
            logger.warning(f"⚠️ {code} 处理失败: {e}")
            continue

    logger.info("=" * 60)
    logger.info(f"✅ 技术指标计算完成")
    logger.info(f"  处理股票: {success}/{total}")
    logger.info(f"  生成指标: {total_count} 条")
    logger.info("=" * 60)

    storage.disconnect()

    return {'total': total, 'success': success, 'count': total_count}


if __name__ == '__main__':
    stats = main()
    print(f"\n📊 统计信息:")
    print(f"  处理股票: {stats['success']}/{stats['total']}")
    print(f"  生成指标: {stats['count']} 条")