#!/usr/bin/env python3
"""指标计算窗口校验单元测试 - 验证滚动窗口严格限定在 trade_date 及之前"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import pandas as pd
import numpy as np
from processor.technical_indicator import TechnicalIndicator


class TestIndicatorWindowValidation:
    """指标计算窗口验证测试类"""
    
    def setup_method(self):
        """创建测试数据"""
        # 创建100天的测试数据
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        np.random.seed(42)
        close = pd.Series(100 + np.cumsum(np.random.randn(100) * 2))
        high = close + np.random.rand(100) * 3
        low = close - np.random.rand(100) * 3
        open_price = close.shift(1).fillna(close.iloc[0])
        volume = np.random.randint(1000000, 5000000, size=100)
        
        self.test_df = pd.DataFrame({
            'trade_date': dates.strftime('%Y-%m-%d'),
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
            'adjust_type': 'qfq',
            'adjust_factor': 1.0
        })
    
    def test_ma_window_boundary(self):
        """测试移动平均线窗口边界 - 前N天应为NaN"""
        result = TechnicalIndicator.calculate_ma(self.test_df, windows=[5, 10, 20])
        
        # MA5: 前4天应为NaN
        assert pd.isna(result['MA5'].iloc[0]), "MA5第1天应为NaN"
        assert pd.isna(result['MA5'].iloc[1]), "MA5第2天应为NaN"
        assert pd.isna(result['MA5'].iloc[2]), "MA5第3天应为NaN"
        assert pd.isna(result['MA5'].iloc[3]), "MA5第4天应为NaN"
        assert not pd.isna(result['MA5'].iloc[4]), "MA5第5天不应为NaN"
        
        # MA10: 前9天应为NaN
        for i in range(9):
            assert pd.isna(result['MA10'].iloc[i]), f"MA10第{i+1}天应为NaN"
        assert not pd.isna(result['MA10'].iloc[9]), "MA10第10天不应为NaN"
        
        # MA20: 前19天应为NaN
        for i in range(19):
            assert pd.isna(result['MA20'].iloc[i]), f"MA20第{i+1}天应为NaN"
        assert not pd.isna(result['MA20'].iloc[19]), "MA20第20天不应为NaN"
    
    def test_rsi_window_boundary(self):
        """测试RSI窗口边界 - 前N-1天应为NaN"""
        result = TechnicalIndicator.calculate_rsi(self.test_df, window=14)
        
        # RSI14: 前13天应为NaN
        for i in range(13):
            assert pd.isna(result['RSI'].iloc[i]), f"RSI第{i+1}天应为NaN"
        assert not pd.isna(result['RSI'].iloc[13]), "RSI第14天不应为NaN"
    
    def test_macd_no_leading_nan(self):
        """测试MACD没有前置NaN（使用EMA）"""
        result = TechnicalIndicator.calculate_macd(self.test_df)
        
        # MACD使用EMA，没有前置NaN（除了开头几个）
        # EMA会从第一个有效值开始计算
        assert not pd.isna(result['MACD'].iloc[0]), "MACD第1天不应为NaN"
        assert not pd.isna(result['MACD_SIGNAL'].iloc[0]), "MACD_SIGNAL第1天不应为NaN"
    
    def test_kdj_window_boundary(self):
        """测试KDJ窗口边界 - 前N-1天应为NaN"""
        result = TechnicalIndicator.calculate_kdj(self.test_df, n=9)
        
        # KDJ9: 前8天应为NaN
        for i in range(8):
            assert pd.isna(result['KDJ_K'].iloc[i]), f"KDJ_K第{i+1}天应为NaN"
            assert pd.isna(result['KDJ_D'].iloc[i]), f"KDJ_D第{i+1}天应为NaN"
            assert pd.isna(result['KDJ_J'].iloc[i]), f"KDJ_J第{i+1}天应为NaN"
        assert not pd.isna(result['KDJ_K'].iloc[8]), "KDJ_K第9天不应为NaN"
    
    def test_boll_window_boundary(self):
        """测试布林带窗口边界 - 前N-1天应为NaN"""
        result = TechnicalIndicator.calculate_boll(self.test_df, window=20)
        
        # BOLL20: 前19天应为NaN
        for i in range(19):
            assert pd.isna(result['BOLL_MID'].iloc[i]), f"BOLL_MID第{i+1}天应为NaN"
            assert pd.isna(result['BOLL_UPPER'].iloc[i]), f"BOLL_UPPER第{i+1}天应为NaN"
            assert pd.isna(result['BOLL_LOWER'].iloc[i]), f"BOLL_LOWER第{i+1}天应为NaN"
        assert not pd.isna(result['BOLL_MID'].iloc[19]), "BOLL_MID第20天不应为NaN"
    
    def test_atr_window_boundary(self):
        """测试ATR窗口边界 - 前N-1天应为NaN"""
        result = TechnicalIndicator.calculate_atr(self.test_df, window=14)
        
        # ATR14: 前13天应为NaN
        for i in range(13):
            assert pd.isna(result['ATR'].iloc[i]), f"ATR第{i+1}天应为NaN"
        assert not pd.isna(result['ATR'].iloc[13]), "ATR第14天不应为NaN"
    
    def test_no_lookahead_in_ma(self):
        """验证MA计算没有前视偏差"""
        # 取前20天数据计算MA20
        df_20days = self.test_df.iloc[:20].copy()
        result_20days = TechnicalIndicator.calculate_ma(df_20days, windows=[20])
        
        # 取全部100天数据计算MA20
        result_full = TechnicalIndicator.calculate_ma(self.test_df, windows=[20])
        
        # 第20天的MA20应该相同（没有使用未来数据）
        ma_20_from_20days = result_20days['MA20'].iloc[19]
        ma_20_from_full = result_full['MA20'].iloc[19]
        
        assert abs(ma_20_from_20days - ma_20_from_full) < 1e-10, \
            f"MA20计算存在前视偏差: {ma_20_from_20days} != {ma_20_from_full}"
    
    def test_no_lookahead_in_rsi(self):
        """验证RSI计算没有前视偏差"""
        # 取前14天数据计算RSI14
        df_14days = self.test_df.iloc[:14].copy()
        result_14days = TechnicalIndicator.calculate_rsi(df_14days, window=14)
        
        # 取全部100天数据计算RSI14
        result_full = TechnicalIndicator.calculate_rsi(self.test_df, window=14)
        
        # 第14天的RSI应该相同
        rsi_14_from_14days = result_14days['RSI'].iloc[13]
        rsi_14_from_full = result_full['RSI'].iloc[13]
        
        assert abs(rsi_14_from_14days - rsi_14_from_full) < 1e-10, \
            f"RSI计算存在前视偏差: {rsi_14_from_14days} != {rsi_14_from_full}"
    
    def test_missing_data_handling(self):
        """测试缺失数据处理"""
        # 创建包含NaN的测试数据（在索引5-10设置NaN）
        df_with_nan = self.test_df.copy()
        df_with_nan.loc[5:10, 'close'] = np.nan
        
        result = TechnicalIndicator.calculate_ma(df_with_nan, windows=[5])
        
        # MA5的计算：
        # - 索引4（第5天）: 依赖索引0-4，全部有效，不应为NaN
        # - 索引5（第6天）: 依赖索引1-5，索引5是NaN，应为NaN
        # - 索引6（第7天）: 依赖索引2-6，索引5-6是NaN，应为NaN
        # - ...以此类推
        
        assert not pd.isna(result['MA5'].iloc[4]), "第5天MA不应为NaN（依赖索引0-4，全部有效）"
        assert pd.isna(result['MA5'].iloc[5]), "第6天MA应为NaN（依赖索引1-5，索引5是NaN）"
        assert pd.isna(result['MA5'].iloc[6]), "第7天MA应为NaN（依赖索引2-6，索引5-6是NaN）"
        
        # 恢复后应该正常计算（索引15依赖索引11-15，全部有效）
        assert not pd.isna(result['MA5'].iloc[15]), "第16天MA不应为NaN"
    
    def test_all_indicators_calculation(self):
        """测试所有指标计算"""
        result = TechnicalIndicator.calculate_all(self.test_df)
        
        # 检查所有指标列是否存在
        expected_columns = [
            'MA5', 'MA10', 'MA20', 'MA60', 'MA120', 'MA250',
            'MACD', 'MACD_SIGNAL', 'MACD_HIST',
            'KDJ_K', 'KDJ_D', 'KDJ_J',
            'BOLL_MID', 'BOLL_UPPER', 'BOLL_LOWER',
            'RSI', 'ATR',
            'VOL_MA5', 'VOL_MA10', 'VOL_MA20'
        ]
        
        for col in expected_columns:
            assert col in result.columns, f"缺少指标列: {col}"


if __name__ == '__main__':
    # 运行测试
    pytest.main([__file__, '-v'])
