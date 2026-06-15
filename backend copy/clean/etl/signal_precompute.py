#!/usr/bin/env python3
"""
信号预计算脚本 - 从 stock_indicators 表读取技术指标，计算交易信号并写入 trade_signals 表

信号类型：
1. macd_cross: MACD 金叉死叉信号（MACD 上穿/下穿 MACD_SIGNAL）
2. rsi_oversold: RSI 超卖信号（RSI < 30）
3. rsi_overbought: RSI 超买信号（RSI > 70）
4. bollinger_breakout: BOLL 突破信号（价格突破上轨/下轨）
"""
import sys
import os
# 将 backend 目录加入 Python 路径
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('signal_precompute')


class SignalPrecompute:
    """信号预计算器"""

    def __init__(self, storage: PostgreSQLStorage):
        self.storage = storage

    def detect_macd_cross(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        检测 MACD 金叉死叉信号

        金叉：MACD 上穿 MACD_SIGNAL（从负变正）
        死叉：MACD 下穿 MACD_SIGNAL（从正变负）

        Returns:
            包含 macd_cross 信号的 DataFrame
        """
        if df.empty or 'macd' not in df.columns or 'dif' not in df.columns or 'dea' not in df.columns:
            logger.warning("⚠️ MACD 数据不完整，跳过信号检测")
            return pd.DataFrame()

        signals = []
        df = df.sort_values('trade_date')

        # MACD 金叉死叉检测（dif 上穿/下穿 dea）
        for i in range(1, len(df)):
            prev_macd_diff = df.iloc[i-1]['dif'] - df.iloc[i-1]['dea']
            curr_macd_diff = df.iloc[i]['dif'] - df.iloc[i]['dea']

            # 金叉：MACD 从负变正
            if prev_macd_diff <= 0 and curr_macd_diff > 0:
                signals.append({
                    'code': df.iloc[i]['code'],
                    'cycle': '1d',
                    'trade_date': df.iloc[i]['trade_date'],
                    'signal_type': 'macd_cross',
                    'signal_direction': 'buy',
                    'signal_value': float(df.iloc[i]['dif']),
                    'signal_strength': abs(float(curr_macd_diff)) * 100,
                    'description': f'MACD金叉: DIF={df.iloc[i]["dif"]:.2f}, DEA={df.iloc[i]["dea"]:.2f}'
                })

            # 死叉：MACD 从正变负
            elif prev_macd_diff >= 0 and curr_macd_diff < 0:
                signals.append({
                    'code': df.iloc[i]['code'],
                    'cycle': '1d',
                    'trade_date': df.iloc[i]['trade_date'],
                    'signal_type': 'macd_cross',
                    'signal_direction': 'sell',
                    'signal_value': float(df.iloc[i]['dif']),
                    'signal_strength': abs(float(curr_macd_diff)) * 100,
                    'description': f'MACD死叉: DIF={df.iloc[i]["dif"]:.2f}, DEA={df.iloc[i]["dea"]:.2f}'
                })

        return pd.DataFrame(signals)

    def detect_rsi_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        检测 RSI 超买超卖信号

        超卖：RSI < 30（买入信号）
        超买：RSI > 70（卖出信号）

        Returns:
            包含 rsi_oversold/rsi_overbought 信号的 DataFrame
        """
        if df.empty or 'rsi6' not in df.columns:
            logger.warning("⚠️ RSI 数据不完整，跳过信号检测")
            return pd.DataFrame()

        signals = []
        df = df.sort_values('trade_date')

        for i in range(len(df)):
            rsi_value = df.iloc[i]['rsi6']

            # 超卖信号：RSI < 30
            if rsi_value < 30:
                signals.append({
                    'code': df.iloc[i]['code'],
                    'cycle': '1d',
                    'trade_date': df.iloc[i]['trade_date'],
                    'signal_type': 'rsi_oversold',
                    'signal_direction': 'buy',
                    'signal_value': float(rsi_value),
                    'signal_strength': int((30 - float(rsi_value)) / 30 * 100),
                    'description': f'RSI超卖: RSI={float(rsi_value):.2f}, Close={float(df.iloc[i]["close"]):.2f}'
                })

            # 超买信号：RSI > 70
            elif rsi_value > 70:
                signals.append({
                    'code': df.iloc[i]['code'],
                    'cycle': '1d',
                    'trade_date': df.iloc[i]['trade_date'],
                    'signal_type': 'rsi_overbought',
                    'signal_direction': 'sell',
                    'signal_value': float(rsi_value),
                    'signal_strength': int((float(rsi_value) - 70) / 30 * 100),
                    'description': f'RSI超买: RSI={float(rsi_value):.2f}, Close={float(df.iloc[i]["close"]):.2f}'
                })

        return pd.DataFrame(signals)

    def detect_bollinger_breakout(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        检测布林带突破信号

        上轨突破：价格突破上轨（买入信号）
        下轨突破：价格突破下轨（卖出信号）

        注意：需要从 stock_quotes 表获取 close 价格，因为 stock_indicators 表可能不包含价格数据

        Returns:
            包含 bollinger_breakout 信号的 DataFrame
        """
        if df.empty or 'close' not in df.columns:
            logger.warning("⚠️ 价格数据不完整，跳过 BOLL 突破检测")
            return pd.DataFrame()

        signals = []
        df = df.sort_values('trade_date')

        # 布林带突破检测（需要先计算布林带）
        # 这里假设 df 已经包含 BOLL_MID, BOLL_UPPER, BOLL_LOWER 列
        # 如果没有，需要先计算
        if 'BOLL_UPPER' not in df.columns or 'BOLL_LOWER' not in df.columns:
            # 简化版：使用 20 日移动平均线 + 2 倍标准差
            window = 20
            df['BOLL_MID'] = df['close'].rolling(window=window).mean()
            std = df['close'].rolling(window=window).std()
            df['BOLL_UPPER'] = df['BOLL_MID'] + 2 * std
            df['BOLL_LOWER'] = df['BOLL_MID'] - 2 * std

        for i in range(window, len(df)):
            close_price = float(df.iloc[i]['close'])
            upper = float(df.iloc[i]['BOLL_UPPER'])
            lower = float(df.iloc[i]['BOLL_LOWER'])

            # 上轨突破：价格突破上轨
            if close_price > upper:
                signals.append({
                    'code': df.iloc[i]['code'],
                    'cycle': '1d',
                    'trade_date': df.iloc[i]['trade_date'],
                    'signal_type': 'bollinger_breakout',
                    'signal_direction': 'sell',
                    'signal_value': round(close_price - upper, 2),
                    'signal_strength': int((close_price - upper) / upper * 100),
                    'description': f'突破BOLL上轨: Price={close_price:.2f}, Upper={upper:.2f}'
                })

            # 下轨突破：价格突破下轨
            elif close_price < lower:
                signals.append({
                    'code': df.iloc[i]['code'],
                    'cycle': '1d',
                    'trade_date': df.iloc[i]['trade_date'],
                    'signal_type': 'bollinger_breakout',
                    'signal_direction': 'buy',
                    'signal_value': round(lower - close_price, 2),
                    'signal_strength': int((lower - close_price) / lower * 100),
                    'description': f'跌破BOLL下轨: Price={close_price:.2f}, Lower={lower:.2f}'
                })

        return pd.DataFrame(signals)

    def precompute_signals_for_stock(self, code: str, start_date: str = None, end_date: str = None) -> int:
        """
        为指定股票预计算所有信号

        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            成功保存的信号数量
        """
        logger.debug(f"预计算 {code} 的交易信号...")

        # 1. 获取技术指标数据（从 stock_indicators 表）
        indicators_df = self.storage.get_indicators(code=code, cycle='1d', start_date=start_date, end_date=end_date)
        if indicators_df.empty:
            logger.warning(f"⚠️ {code} 无技术指标数据，跳过")
            return 0

        # 2. 获取价格数据（从 stock_quotes 表，用于 BOLL 突破检测）
        quotes_df = self.storage.get_quotes(code=code, cycle='daily', start_date=start_date, end_date=end_date)
        if quotes_df.empty:
            logger.warning(f"⚠️ {code} 无价格数据，跳过")
            return 0

        # 合并数据
        combined_df = pd.merge(indicators_df, quotes_df[['trade_date', 'close', 'volume']], on='trade_date', how='left')
        combined_df['code'] = code

        # 3. 检测各类信号
        all_signals = []

        # MACD 金叉死叉
        macd_signals = self.detect_macd_cross(combined_df)
        if not macd_signals.empty:
            all_signals.append(macd_signals)

        # RSI 超买超卖
        rsi_signals = self.detect_rsi_signals(combined_df)
        if not rsi_signals.empty:
            all_signals.append(rsi_signals)

        # BOLL 突破
        boll_signals = self.detect_bollinger_breakout(combined_df)
        if not boll_signals.empty:
            all_signals.append(boll_signals)

        # 4. 合并所有信号
        if not all_signals:
            logger.debug(f"  {code}: 无信号")
            return 0

        signals_df = pd.concat(all_signals, ignore_index=True)

        # 5. 保存到数据库
        count = self.storage.save_signals(signals_df)
        logger.debug(f"  {code}: 保存 {count} 条信号")
        return count

    def precompute_all_signals(self, start_date: str = None, end_date: str = None) -> Dict[str, int]:
        """
        为所有股票预计算信号

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            统计信息 {'total_stocks': int, 'success_stocks': int, 'total_signals': int}
        """
        logger.info("=" * 60)
        logger.info("开始预计算全市场交易信号...")
        logger.info("=" * 60)

        # 获取所有股票代码
        stocks_df = self.storage.get_stock_list()
        if stocks_df.empty:
            logger.error("❌ 无股票列表")
            return {'total_stocks': 0, 'success_stocks': 0, 'total_signals': 0}

        codes = stocks_df['code'].tolist()
        total_stocks = len(codes)
        success_stocks = 0
        total_signals = 0

        logger.info(f"📊 待处理股票: {total_stocks} 只")

        for i, code in enumerate(codes):
            try:
                # 转换代码格式：SZ.000001 -> 000001
                db_code = code.split('.')[-1] if '.' in code else code
                count = self.precompute_signals_for_stock(db_code, start_date, end_date)
                if count > 0:
                    success_stocks += 1
                    total_signals += count

                if (i + 1) % 100 == 0:
                    logger.info(f"  进度: {i+1}/{total_stocks} ({(i+1)/total_stocks*100:.1f}%)")

            except Exception as e:
                logger.warning(f"⚠️ {code} 信号预计算失败: {e}")
                continue

        logger.info("=" * 60)
        logger.info(f"✅ 信号预计算完成")
        logger.info(f"  处理股票: {success_stocks}/{total_stocks}")
        logger.info(f"  生成信号: {total_signals} 条")
        logger.info("=" * 60)

        return {
            'total_stocks': total_stocks,
            'success_stocks': success_stocks,
            'total_signals': total_signals
        }


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

    # 初始化表结构
    storage.init_tables()

    # 创建信号预计算器
    precompute = SignalPrecompute(storage)

    # 预计算全市场信号
    stats = precompute.precompute_all_signals()

    # 关闭连接
    storage.disconnect()

    return stats


if __name__ == '__main__':
    stats = main()
    print(f"\n📊 统计信息:")
    print(f"  处理股票: {stats['success_stocks']}/{stats['total_stocks']}")
    print(f"  生成信号: {stats['total_signals']} 条")