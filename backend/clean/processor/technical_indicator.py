#!/usr/bin/env python3
"""技术指标计算模块 - 支持 MA/EMA/MACD/KDJ/BOLL/RSI/ATR/量比/换手率等常用指标
注意：技术指标必须基于复权后价格计算，本模块强制验证复权数据"""
from typing import Optional
import numpy as np
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger('technical_indicator')


class TechnicalIndicator:
    """技术指标计算器 - 强制使用复权数据"""
    
    # 支持的复权类型
    VALID_ADJUST_TYPES = ['qfq', 'hfq']
    
    @staticmethod
    def _validate_adjust_data(df: pd.DataFrame, require_adjust: bool = True) -> bool:
        """
        验证数据是否为复权数据
        
        Args:
            df: 待验证的 DataFrame
            require_adjust: 是否强制要求复权数据
        
        Returns:
            是否通过验证
        """
        # 检查必要列是否存在
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(f"缺少必要列: {missing_cols}")
            return False
        
        # 检查是否为复权数据
        if require_adjust:
            if 'adjust_type' not in df.columns or 'adjust_factor' not in df.columns:
                logger.error("缺少复权标识列 (adjust_type, adjust_factor)，技术指标必须基于复权后价格计算")
                return False
            
            # 检查复权类型是否有效
            if not df['adjust_type'].isin(TechnicalIndicator.VALID_ADJUST_TYPES).all():
                invalid_types = df[~df['adjust_type'].isin(TechnicalIndicator.VALID_ADJUST_TYPES)]['adjust_type'].unique()
                logger.error(f"无效的复权类型: {invalid_types}，仅支持 {TechnicalIndicator.VALID_ADJUST_TYPES}")
                return False
            
            # 检查复权因子是否合理
            if (df['adjust_factor'] <= 0).any():
                logger.error("复权因子必须大于0")
                return False
        
        return True
    
    @staticmethod
    def calculate_ma(df: pd.DataFrame, windows: list = None, require_adjust: bool = True) -> pd.DataFrame:
        """
        计算移动平均线 (MA)
        
        Args:
            df: 包含 'close' 列的 DataFrame，必须包含复权标识
            windows: 窗口大小列表，默认 [5, 10, 20, 60, 120, 250]
            require_adjust: 是否强制要求复权数据
        
        Returns:
            添加了 MA 列的 DataFrame
        """
        # 验证数据
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust):
            raise ValueError("数据验证失败：技术指标必须基于复权后价格计算")
        
        if windows is None:
            windows = [5, 10, 20, 60, 120, 250]
        
        result = df.copy()
        
        for window in windows:
            result[f'MA{window}'] = result['close'].rolling(window=window).mean()
        
        return result
    
    @staticmethod
    def calculate_macd(df: pd.DataFrame, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9, 
                      require_adjust: bool = True) -> pd.DataFrame:
        """
        计算 MACD 指标
        
        Args:
            df: 包含 'close' 列的 DataFrame，必须包含复权标识
            fast_period: 快线周期，默认 12
            slow_period: 慢线周期，默认 26
            signal_period: 信号线周期，默认 9
            require_adjust: 是否强制要求复权数据
        
        Returns:
            添加了 MACD、MACD_SIGNAL、MACD_HIST 列的 DataFrame
        """
        # 验证数据
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust):
            raise ValueError("数据验证失败：技术指标必须基于复权后价格计算")
        
        result = df.copy()
        
        # 计算短期和长期指数移动平均
        ema_fast = result['close'].ewm(span=fast_period, adjust=False).mean()
        ema_slow = result['close'].ewm(span=slow_period, adjust=False).mean()
        
        # MACD = 快线 - 慢线
        result['MACD'] = ema_fast - ema_slow
        
        # 信号线 = MACD 的 9 日 EMA
        result['MACD_SIGNAL'] = result['MACD'].ewm(span=signal_period, adjust=False).mean()
        
        # 柱状图 = MACD - 信号线
        result['MACD_HIST'] = result['MACD'] - result['MACD_SIGNAL']
        
        return result
    
    @staticmethod
    def calculate_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3, 
                     require_adjust: bool = True) -> pd.DataFrame:
        """
        计算 KDJ 指标
        
        Args:
            df: 包含 'high', 'low', 'close' 列的 DataFrame，必须包含复权标识
            n: 周期，默认 9
            m1: K 值平滑周期，默认 3
            m2: D 值平滑周期，默认 3
            require_adjust: 是否强制要求复权数据
        
        Returns:
            添加了 KDJ_K、KDJ_D、KDJ_J 列的 DataFrame
        """
        # 验证数据
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust):
            raise ValueError("数据验证失败：技术指标必须基于复权后价格计算")
        
        result = df.copy()
        
        # 计算 RSV (未成熟随机值)
        low_min = result['low'].rolling(window=n).min()
        high_max = result['high'].rolling(window=n).max()
        
        # 处理除零情况：当 high_max == low_min 时（价格无波动），RSV 设为 50
        price_range = high_max - low_min
        price_range = price_range.replace(0, 1)  # 避免除零，设为1表示轻微波动
        rsv = (result['close'] - low_min) / price_range * 100
        rsv = rsv.where(price_range != 0, 50)  # 价格无波动时设为中性值50
        
        # 计算 K 值（RSV 的 m1 日平滑）
        result['KDJ_K'] = rsv.ewm(alpha=1/m1, adjust=False).mean()
        
        # 计算 D 值（K 值的 m2 日平滑）
        result['KDJ_D'] = result['KDJ_K'].ewm(alpha=1/m2, adjust=False).mean()
        
        # 计算 J 值 = 3*K - 2*D
        result['KDJ_J'] = 3 * result['KDJ_K'] - 2 * result['KDJ_D']
        
        return result
    
    @staticmethod
    def calculate_boll(df: pd.DataFrame, window: int = 20, std_dev: int = 2, 
                      require_adjust: bool = True) -> pd.DataFrame:
        """
        计算布林带 (BOLL) 指标
        
        Args:
            df: 包含 'close' 列的 DataFrame，必须包含复权标识
            window: 窗口大小，默认 20
            std_dev: 标准差倍数，默认 2
            require_adjust: 是否强制要求复权数据
        
        Returns:
            添加了 BOLL_MID、BOLL_UPPER、BOLL_LOWER 列的 DataFrame
        """
        # 验证数据
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust):
            raise ValueError("数据验证失败：技术指标必须基于复权后价格计算")
        
        result = df.copy()
        
        # 布林带中轨 = 20日移动平均线
        result['BOLL_MID'] = result['close'].rolling(window=window).mean()
        
        # 标准差
        std = result['close'].rolling(window=window).std()
        
        # 布林带上轨 = 中轨 + 2*标准差
        result['BOLL_UPPER'] = result['BOLL_MID'] + std_dev * std
        
        # 布林带下轨 = 中轨 - 2*标准差
        result['BOLL_LOWER'] = result['BOLL_MID'] - std_dev * std
        
        return result
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, window: int = 14, require_adjust: bool = True) -> pd.DataFrame:
        """
        计算相对强弱指标 (RSI)
        
        Args:
            df: 包含 'close' 列的 DataFrame，必须包含复权标识
            window: 窗口大小，默认 14
            require_adjust: 是否强制要求复权数据
        
        Returns:
            添加了 RSI 列的 DataFrame
        """
        # 验证数据
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust):
            raise ValueError("数据验证失败：技术指标必须基于复权后价格计算")
        
        result = df.copy()
        
        # 计算价格变化
        delta = result['close'].diff(1)
        
        # 分离上涨和下跌
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # 计算平均上涨和平均下跌
        avg_gain = gain.rolling(window=window).mean()
        avg_loss = loss.rolling(window=window).mean()
        
        # 计算 RSI，处理 avg_loss == 0 的情况（全涨或全跌）
        rs = avg_gain / avg_loss.replace(0, 0.0001)  # 避免除零，用极小值替代
        result['RSI'] = 100 - (100 / (1 + rs))
        # 当 avg_loss 为 0 时（连续上涨），RSI 设为 100
        result['RSI'] = result['RSI'].where(avg_loss != 0, 100)
        
        return result
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, window: int = 14, require_adjust: bool = True) -> pd.DataFrame:
        """
        计算平均真实波动幅度 (ATR)
        
        Args:
            df: 包含 'high', 'low', 'close' 列的 DataFrame，必须包含复权标识
            window: 窗口大小，默认 14
            require_adjust: 是否强制要求复权数据
        
        Returns:
            添加了 ATR 列的 DataFrame
        """
        # 验证数据
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust):
            raise ValueError("数据验证失败：技术指标必须基于复权后价格计算")
        
        result = df.copy()
        
        # 计算真实波动幅度
        high_low = result['high'] - result['low']
        high_close = (result['high'] - result['close'].shift(1)).abs()
        low_close = (result['low'] - result['close'].shift(1)).abs()
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # 计算 ATR
        result['ATR'] = tr.rolling(window=window).mean()
        
        return result
    
    @staticmethod
    def calculate_volume_ma(df: pd.DataFrame, windows: list = None, require_adjust: bool = True) -> pd.DataFrame:
        """
        计算成交量移动平均线
        
        Args:
            df: 包含 'volume' 列的 DataFrame，必须包含复权标识
            windows: 窗口大小列表，默认 [5, 10, 20]
            require_adjust: 是否强制要求复权数据
        
        Returns:
            添加了 VOL_MA 列的 DataFrame
        """
        # 验证数据（成交量指标不需要强制复权，但仍检查必要列）
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust=False):
            raise ValueError("数据验证失败")
        
        if windows is None:
            windows = [5, 10, 20]
        
        result = df.copy()
        
        for window in windows:
            result[f'VOL_MA{window}'] = result['volume'].rolling(window=window).mean()
        
        return result
    
    @staticmethod
    def calculate_ema(df: pd.DataFrame, periods: list = None, require_adjust: bool = True) -> pd.DataFrame:
        """
        计算指数移动平均线 (EMA)。

        优化：单次遍历 close，对每个周期调用 ewm()。
        使用 adjust=False 递推公式，避免重复计算中间状态。

        Args:
            df: 包含 'close' 列的 DataFrame，必须包含复权标识
            periods: 周期列表，默认 [5, 10, 20, 60]
            require_adjust: 是否强制要求复权数据

        Returns:
            添加了 EMA5/EMA10/EMA20/EMA60 列的 DataFrame
        """
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust):
            raise ValueError("数据验证失败：技术指标必须基于复权后价格计算")

        if periods is None:
            periods = [5, 10, 20, 60]

        result = df.copy()
        close = result["close"].astype(float)

        for p in periods:
            result[f"EMA{p}"] = close.ewm(span=p, adjust=False).mean().values

        return result

    @staticmethod
    def calculate_volume_ratio(df: pd.DataFrame, n: int = 5, require_adjust: bool = True) -> pd.DataFrame:
        """
        计算量比 = 当日成交量 / 前n日平均成交量。

        前置条件：df 必须为交易日序列完备且按日期升序排列。
        使用 shift(1) 确保前 n 日平均不含当日成交量。

        Args:
            df: 包含 'volume' 列的 DataFrame
            n: 平均窗口，默认 5
            require_adjust: 是否强制要求复权数据

        Returns:
            添加了 VOL_RATIO 列的 DataFrame
        """
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust=False):
            raise ValueError("数据验证失败")

        result = df.copy()
        vol = result["volume"].astype(float)

        # 前 n 日平均成交量（不含当日，shift(1) 按物理行号偏移）
        avg_vol = vol.shift(1).rolling(window=n, min_periods=1).mean()

        # 避免除零
        result["VOL_RATIO"] = (vol / avg_vol.where(avg_vol > 0, float("nan"))).values

        return result

    @staticmethod
    def calculate_turnover_rate(
        df: pd.DataFrame,
        float_shares: Optional[float] = None,
        require_adjust: bool = True,
    ) -> pd.DataFrame:
        """
        计算换手率 = 成交量(股) / 流通股本(股) × 100%。

        若流通股本缺失，该列填充 -1（显式标识数据缺失，而非 NaN）。

        Args:
            df: 包含 'volume' 列的 DataFrame
            float_shares: 流通股本（股），若为 None 则填充 -1
            require_adjust: 是否强制要求复权数据

        Returns:
            添加了 TURNOVER_RATE 列的 DataFrame
        """
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust=False):
            raise ValueError("数据验证失败")

        result = df.copy()
        vol = result["volume"].astype(float)

        if float_shares is None or float_shares <= 0:
            result["TURNOVER_RATE"] = -1.0
        else:
            result["TURNOVER_RATE"] = (vol / float_shares * 100).values

        return result

    @staticmethod
    def calculate_all(df: pd.DataFrame, require_adjust: bool = True) -> pd.DataFrame:
        """
        计算所有技术指标
        
        Args:
            df: 包含 'open', 'high', 'low', 'close', 'volume' 列的 DataFrame，必须包含复权标识
            require_adjust: 是否强制要求复权数据
        
        Returns:
            添加了所有技术指标的 DataFrame
        """
        # 统一验证数据
        if not TechnicalIndicator._validate_adjust_data(df, require_adjust):
            raise ValueError("数据验证失败：技术指标必须基于复权后价格计算")
        
        logger.debug("计算技术指标...")
        
        result = df.copy()
        
        # 计算各类指标（复用已验证的数据，不再重复验证）
        result = TechnicalIndicator.calculate_ma(result, require_adjust=False)
        result = TechnicalIndicator.calculate_ema(result, require_adjust=False)
        result = TechnicalIndicator.calculate_macd(result, require_adjust=False)
        result = TechnicalIndicator.calculate_kdj(result, require_adjust=False)
        result = TechnicalIndicator.calculate_boll(result, require_adjust=False)
        result = TechnicalIndicator.calculate_rsi(result, require_adjust=False)
        result = TechnicalIndicator.calculate_atr(result, require_adjust=False)
        result = TechnicalIndicator.calculate_volume_ma(result, require_adjust=False)
        result = TechnicalIndicator.calculate_volume_ratio(result, require_adjust=False)
        
        logger.debug(f"技术指标计算完成，新增 {len(result.columns) - len(df.columns)} 列")
        
        return result
    
    @staticmethod
    def is_adjusted_data(df: pd.DataFrame) -> bool:
        """
        判断数据是否为复权数据
        
        Args:
            df: 待判断的 DataFrame
        
        Returns:
            是否为复权数据
        """
        return 'adjust_type' in df.columns and 'adjust_factor' in df.columns


# 测试函数
if __name__ == '__main__':
    # 创建测试数据
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(100) * 2)
    high = close + np.random.rand(100) * 3
    low = close - np.random.rand(100) * 3
    open_price = close.shift(1).fillna(close.iloc[0])
    volume = np.random.randint(1000000, 5000000, size=100)
    
    test_df = pd.DataFrame({
        'trade_date': dates.strftime('%Y-%m-%d'),
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    # 计算所有指标
    result = TechnicalIndicator.calculate_all(test_df)
    
    print(f"原始列数: {len(test_df.columns)}")
    print(f"计算后列数: {len(result.columns)}")
    print(f"新增指标列: {[col for col in result.columns if col not in test_df.columns]}")
    print("\n前5行数据:")
    print(result[['trade_date', 'close', 'MA5', 'MA10', 'MACD', 'KDJ_K', 'BOLL_MID', 'RSI']].head())
