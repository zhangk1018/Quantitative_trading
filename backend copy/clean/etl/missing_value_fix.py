#!/usr/bin/env python3
"""
缺失值处理脚本 - 对 stock_indicators 表中的空值进行填充处理

处理策略：
1. 均线指标（ma5, ma10, ma20, ma60）：使用前向填充（ffill）
2. 振荡指标（macd, dif, dea, rsi6, rsi12, rsi24）：使用线性插值（interpolate）
"""
import sys
import os
# 将 backend 目录加入 Python 路径
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import pandas as pd
from datetime import datetime
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('missing_value_fix')


def fix_missing_values():
    """处理缺失值"""
    logger.info("=" * 60)
    logger.info("开始处理缺失值...")
    logger.info("=" * 60)

    # 初始化数据库连接
    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'user': db_config.get('user', 'postgres'),
        'password': db_config.get('password', '')
    })

    # 连接数据库
    if not storage.connect():
        logger.error("❌ 数据库连接失败")
        return

    # 直接查询有缺失值的股票代码（优化：只处理有缺失值的股票）
    query = """
        SELECT DISTINCT code FROM stock_indicators 
        WHERE ma5 IS NULL OR ma10 IS NULL OR ma20 IS NULL OR ma60 IS NULL
           OR macd IS NULL OR dif IS NULL OR dea IS NULL
           OR rsi6 IS NULL OR rsi12 IS NULL OR rsi24 IS NULL
    """
    try:
        import psycopg2
        cursor = storage.conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        codes = [row[0] for row in results]
        cursor.close()
    except Exception as e:
        logger.error(f"❌ 查询有缺失值的股票失败: {e}")
        return

    total_stocks = len(codes)
    fixed_count = 0

    logger.info(f"📊 待处理股票（有缺失值）: {total_stocks} 只")

    for i, code in enumerate(codes):
        try:
            # 对每个股票，处理所有周期的数据
            for cycle in ['1d', '5m', '15m', '30m', '60m', '1w', '1m']:
                # 获取技术指标数据
                indicators_df = storage.get_indicators(code=code, cycle=cycle)
                if indicators_df.empty:
                    continue

                # 检查是否有缺失值
                missing_count = indicators_df.isnull().sum().sum()
                if missing_count == 0:
                    continue

                # 按日期排序
                indicators_df = indicators_df.sort_values('trade_date')

                # 1. 均线指标使用前向填充（pandas 新版本语法）
                ma_cols = ['ma5', 'ma10', 'ma20', 'ma60']
                for col in ma_cols:
                    if col in indicators_df.columns:
                        indicators_df[col] = indicators_df[col].ffill()

                # 2. 振荡指标使用线性插值
                osc_cols = ['macd', 'dif', 'dea', 'rsi6', 'rsi12', 'rsi24']
                for col in osc_cols:
                    if col in indicators_df.columns:
                        indicators_df[col] = indicators_df[col].interpolate(method='linear')

                # 3. 如果还有剩余空值，用0填充
                indicators_df = indicators_df.fillna(0)

                # 添加缺失的列（trade_time, trade_datetime）
                for col in ['trade_time', 'trade_datetime']:
                    if col not in indicators_df.columns:
                        indicators_df[col] = indicators_df['trade_date'].apply(
                            lambda x: f"{x.strftime('%Y-%m-%d')} 15:00:00" if hasattr(x, 'strftime') else f"{str(x)[:10]} 15:00:00"
                        )

                # 保存修复后的数据
                count = storage.save_indicators(indicators_df)
                if count > 0:
                    fixed_count += 1
                    logger.debug(f"  {code} ({cycle}): 修复 {missing_count} 个缺失值")

        except Exception as e:
            logger.warning(f"⚠️ {code} 缺失值处理失败: {e}")
            continue

    logger.info("=" * 60)
    logger.info(f"✅ 缺失值处理完成")
    logger.info(f"  修复股票: {fixed_count} 只")
    logger.info("=" * 60)


if __name__ == '__main__':
    fix_missing_values()
