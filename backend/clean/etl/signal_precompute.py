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

    def detect_all_signals_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        统一向量化检测所有信号类型（一次遍历，提升缓存命中率）

        包含：MACD金叉死叉、RSI超买超卖、布林带突破

        Returns:
            包含所有信号的 DataFrame
        """
        if df.empty:
            return pd.DataFrame()

        df = df.sort_values('trade_date').copy()
        all_signals = []

        # MACD 信号
        if 'dif' in df.columns and 'dea' in df.columns:
            diff = df['dif'] - df['dea']
            prev_diff = diff.shift(1)

            # 金叉
            golden_mask = (prev_diff <= 0) & (diff > 0)
            if golden_mask.any():
                df_golden = df[golden_mask]
                all_signals.append(pd.DataFrame({
                    'code': df_golden['code'],
                    'cycle': '1d',
                    'trade_date': df_golden['trade_date'],
                    'signal_type': 'macd_cross',
                    'signal_direction': 'buy',
                    'signal_value': df_golden['dif'].astype(float),
                    'signal_strength': (diff[golden_mask].abs() * 100).astype(int),
                    'description': 'MACD金叉'
                }))

            # 死叉
            death_mask = (prev_diff >= 0) & (diff < 0)
            if death_mask.any():
                df_death = df[death_mask]
                all_signals.append(pd.DataFrame({
                    'code': df_death['code'],
                    'cycle': '1d',
                    'trade_date': df_death['trade_date'],
                    'signal_type': 'macd_cross',
                    'signal_direction': 'sell',
                    'signal_value': df_death['dif'].astype(float),
                    'signal_strength': (diff[death_mask].abs() * 100).astype(int),
                    'description': 'MACD死叉'
                }))

        # RSI 信号
        if 'rsi6' in df.columns:
            # 超卖
            oversold_mask = df['rsi6'] < 30
            if oversold_mask.any():
                df_oversold = df[oversold_mask]
                all_signals.append(pd.DataFrame({
                    'code': df_oversold['code'],
                    'cycle': '1d',
                    'trade_date': df_oversold['trade_date'],
                    'signal_type': 'rsi_oversold',
                    'signal_direction': 'buy',
                    'signal_value': df_oversold['rsi6'].astype(float),
                    'signal_strength': ((30 - df_oversold['rsi6']) / 30 * 100).astype(int),
                    'description': 'RSI超卖'
                }))

            # 超买
            overbought_mask = df['rsi6'] > 70
            if overbought_mask.any():
                df_overbought = df[overbought_mask]
                all_signals.append(pd.DataFrame({
                    'code': df_overbought['code'],
                    'cycle': '1d',
                    'trade_date': df_overbought['trade_date'],
                    'signal_type': 'rsi_overbought',
                    'signal_direction': 'sell',
                    'signal_value': df_overbought['rsi6'].astype(float),
                    'signal_strength': ((df_overbought['rsi6'] - 70) / 30 * 100).astype(int),
                    'description': 'RSI超买'
                }))

        # 布林带信号
        if 'close' in df.columns:
            # 计算布林带（如不存在）
            if 'boll_upper' not in df.columns or 'boll_lower' not in df.columns:
                window = 20
                df['boll_mid'] = df['close'].rolling(window=window).mean()
                std = df['close'].rolling(window=window).std()
                df['boll_upper'] = df['boll_mid'] + 2 * std
                df['boll_lower'] = df['boll_mid'] - 2 * std

            # 上轨突破（卖出）
            upper_break_mask = df['close'] > df['boll_upper']
            if upper_break_mask.any():
                df_upper = df[upper_break_mask]
                all_signals.append(pd.DataFrame({
                    'code': df_upper['code'],
                    'cycle': '1d',
                    'trade_date': df_upper['trade_date'],
                    'signal_type': 'bollinger_breakout',
                    'signal_direction': 'sell',
                    'signal_value': (df_upper['close'] - df_upper['boll_upper']).round(2),
                    'signal_strength': ((df_upper['close'] - df_upper['boll_upper']) / df_upper['boll_upper'] * 100).astype(int),
                    'description': '突破BOLL上轨'
                }))

            # 下轨突破（买入）
            lower_break_mask = df['close'] < df['boll_lower']
            if lower_break_mask.any():
                df_lower = df[lower_break_mask]
                all_signals.append(pd.DataFrame({
                    'code': df_lower['code'],
                    'cycle': '1d',
                    'trade_date': df_lower['trade_date'],
                    'signal_type': 'bollinger_breakout',
                    'signal_direction': 'buy',
                    'signal_value': (df_lower['boll_lower'] - df_lower['close']).round(2),
                    'signal_strength': ((df_lower['boll_lower'] - df_lower['close']) / df_lower['boll_lower'] * 100).astype(int),
                    'description': '突破BOLL下轨'
                }))

        return pd.concat(all_signals, ignore_index=True) if all_signals else pd.DataFrame()

    def precompute_signals_for_stock(self, code: str, start_date: str = None, end_date: str = None) -> int:
        """
        为指定股票预计算所有信号（使用向量化检测）

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
        combined_df = combined_df.reset_index(drop=True)

        # 3. 使用向量化函数检测所有信号（一次遍历）
        try:
            signals_df = self.detect_all_signals_vectorized(combined_df)
        except Exception as e:
            logger.error(f"  ⚠️ {code} 信号检测异常: {e}")
            return 0

        # 4. 保存到数据库
        if signals_df.empty:
            logger.debug(f"  {code}: 无信号")
            return 0

        count = self.storage.save_signals(signals_df)
        logger.debug(f"  {code}: 保存 {count} 条信号")
        return count

    def precompute_all_signals_batch(self, start_date: str = None, end_date: str = None, incremental: bool = True) -> Dict[str, int]:
        """
        批量预计算所有股票信号（使用批量查询和向量化处理，支持增量计算）

        Args:
            start_date: 开始日期（如果 incremental=True 则忽略）
            end_date: 结束日期
            incremental: 是否增量计算（只计算最新缺失日期的数据）

        Returns:
            统计信息 {'total_stocks': int, 'success_stocks': int, 'total_signals': int}
        """
        logger.info("=" * 60)
        logger.info("开始批量预计算全市场交易信号...")
        logger.info(f"  增量模式: {'开启' if incremental else '关闭'}")
        logger.info("=" * 60)

        # 获取所有股票代码
        stocks_df = self.storage.get_stock_list()
        if stocks_df.empty:
            logger.error("❌ 无股票列表")
            return {'total_stocks': 0, 'success_stocks': 0, 'total_signals': 0}

        codes = stocks_df['code'].tolist()
        total_stocks = len(codes)
        total_signals = 0
        processed_codes = set()  # 使用集合统计成功处理的股票

        logger.info(f"📊 待处理股票: {total_stocks} 只")

        # 分块处理，每批 200 只股票
        chunk_size = 200
        total_chunks = (len(codes) + chunk_size - 1) // chunk_size

        # 如果增量模式，批量获取每只股票的最后信号日期
        last_signal_dates = {}
        if incremental:
            db_codes = [c.split('.')[-1] if '.' in c else c for c in codes]
            last_signal_dates = self.storage.get_last_signal_dates_batch(db_codes, '1d')

            # 计算需要处理的日期范围
            if end_date is None:
                from datetime import datetime, timedelta
                end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        for chunk_idx in range(total_chunks):
            # 获取当前批次的股票代码
            start_idx = chunk_idx * chunk_size
            end_idx = min((chunk_idx + 1) * chunk_size, len(codes))
            chunk_codes = codes[start_idx:end_idx]
            db_chunk_codes = [c.split('.')[-1] if '.' in c else c for c in chunk_codes]

            logger.info(f"  处理批次 {chunk_idx + 1}/{total_chunks} ({len(db_chunk_codes)} 只股票)")

            # 确定该批次的日期范围（增量模式下取最早的最后信号日期）
            batch_start_date = start_date
            if incremental:
                # 回退 5 天确保交叉检测完整
                min_last_date = None
                for code in db_chunk_codes:
                    ld = last_signal_dates.get(code)
                    if ld is not None:
                        if min_last_date is None or ld < min_last_date:
                            min_last_date = ld

                if min_last_date is not None:
                    from datetime import timedelta
                    batch_start_date = (min_last_date - timedelta(days=5)).strftime('%Y-%m-%d')
                else:
                    batch_start_date = '2010-01-01'  # 无信号则全量

            # 批量查询技术指标和行情数据（一次 JOIN 查询，减少网络往返）
            merged_df = self.storage.get_indicators_with_quotes_batch(
                db_chunk_codes, cycle='1d',
                start_date=batch_start_date, end_date=end_date
            )

            if merged_df.empty:
                logger.warning(f"    该批次无数据")
                continue

            # 按股票代码分组处理
            all_signals = []
            for code, group in merged_df.groupby('code'):
                group = group.reset_index(drop=True)
                try:
                    signals = self.detect_all_signals_vectorized(group)
                    if not signals.empty:
                        # 增量模式下，只保留新日期的信号
                        if incremental:
                            last_date = last_signal_dates.get(code)
                            if last_date is not None:
                                # 统一为 pd.Timestamp 进行比较，避免类型不一致
                                last_ts = pd.Timestamp(last_date)
                                # signals['trade_date'] 可能是 date 或 Timestamp，统一转换
                                signals = signals.copy()
                                signals['trade_date'] = pd.to_datetime(signals['trade_date'])
                                signals = signals[signals['trade_date'] > last_ts]
                        all_signals.append(signals)
                except Exception as e:
                    logger.error(f"    ⚠️ {code} 信号检测异常: {e}")
                    continue

            # 批量写入
            if all_signals:
                final_df = pd.concat(all_signals, ignore_index=True)
                count = self.storage.save_signals_batch(final_df)
                processed_codes.update(final_df['code'].tolist())
                total_signals += count
                logger.info(f"    批次完成: 保存 {count} 条信号")
            else:
                logger.debug(f"    批次完成: 无新信号")

        logger.info("=" * 60)
        logger.info(f"✅ 批量信号预计算完成")
        logger.info(f"  生成新信号股票: {len(processed_codes)}/{total_stocks}")
        logger.info(f"  生成信号: {total_signals} 条")
        logger.info("=" * 60)

        return {
            'total_stocks': total_stocks,
            'success_stocks': len(processed_codes),
            'total_signals': total_signals
        }

    def precompute_all_signals(self, start_date: str = None, end_date: str = None, force_full: bool = False) -> Dict[str, int]:
        """
        为所有股票预计算信号

        Args:
            start_date: 开始日期（仅在 force_full=True 时生效）
            end_date: 结束日期
            force_full: 是否强制全量重算（默认 False，即增量计算）

        Returns:
            统计信息 {'total_stocks': int, 'success_stocks': int, 'total_signals': int}
        """
        return self.precompute_all_signals_batch(
            start_date=start_date,
            end_date=end_date,
            incremental=not force_full
        )


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
    print(f"  生成新信号股票: {stats['success_stocks']}/{stats['total_stocks']}")
    print(f"  生成信号: {stats['total_signals']} 条")