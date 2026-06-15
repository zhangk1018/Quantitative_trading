import pandas as pd
import numpy as np
from typing import List, Dict, Optional

class TechnicalIndicators:
    """
    技术指标计算类
    输入: 包含 'open', 'high', 'low', 'close', 'volume' 的 DataFrame
    输出: 带有新指标列的 DataFrame
    """

    @staticmethod
    def calculate_ma(df: pd.DataFrame, windows: List[int] = [5, 10, 20, 60]) -> pd.DataFrame:
        """计算移动平均线"""
        for w in windows:
            col_name = f'ma{w}'
            df[col_name] = df['close'].rolling(window=w).mean()
        return df

    @staticmethod
    def calculate_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> pd.DataFrame:
        """计算 MACD"""
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        df['macd_dif'] = ema_fast - ema_slow
        df['macd_dea'] = df['macd_dif'].ewm(span=signal, adjust=False).mean()
        df['macd_hist'] = 2 * (df['macd_dif'] - df['macd_dea'])
        return df

    @staticmethod
    def calculate_rsi(df: pd.DataFrame, window=14) -> pd.DataFrame:
        """计算 RSI"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        return df

    @staticmethod
    def calculate_boll(df: pd.DataFrame, window=20, num_std=2) -> pd.DataFrame:
        """计算布林带"""
        df['boll_mid'] = df['close'].rolling(window=window).mean()
        std_dev = df['close'].rolling(window=window).std()
        df['boll_upper'] = df['boll_mid'] + (std_dev * num_std)
        df['boll_lower'] = df['boll_mid'] - (std_dev * num_std)
        return df

    @staticmethod
    def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
        """一键计算所有常用技术指标"""
        if df.empty:
            return df
        
        # 确保按时间排序
        df = df.sort_values('trade_date')
        
        df = TechnicalIndicators.calculate_ma(df)
        df = TechnicalIndicators.calculate_macd(df)
        df = TechnicalIndicators.calculate_rsi(df)
        df = TechnicalIndicators.calculate_boll(df)
        
        # 计算成交量相关指标 (量比简化版)
        df['vol_ma5'] = df['volume'].rolling(5).mean()
        df['volume_ratio'] = df['volume'] / df['vol_ma5'].replace(0, np.nan)
        
        return df