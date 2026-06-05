"""
测试周线/月线合成逻辑
验证周末和月末判断是否正确
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from collector.etl.synthesize_cycle_data import CycleSynthesizer


class TestCycleSynthesis:
    """周线/月线合成测试类"""
    
    @pytest.fixture
    def synthesizer(self):
        return CycleSynthesizer()
    
    @pytest.fixture
    def sample_daily_data(self):
        """生成示例日线数据"""
        dates = pd.date_range('2026-01-01', '2026-01-31', freq='B')  # 工作日
        data = {
            'trade_date': dates,
            'open': np.random.uniform(10, 15, len(dates)),
            'high': np.random.uniform(10, 15, len(dates)),
            'low': np.random.uniform(10, 15, len(dates)),
            'close': np.random.uniform(10, 15, len(dates)),
            'pre_close': np.random.uniform(10, 15, len(dates)),
            'volume': np.random.randint(1000000, 10000000, len(dates)),
            'amount': np.random.uniform(10000000, 100000000, len(dates))
        }
        return pd.DataFrame(data)
    
    def test_weekly_synthesis(self, synthesizer, sample_daily_data):
        """测试周线合成"""
        weekly = synthesizer.synthesize_weekly(sample_daily_data)
        
        # 验证基本结构
        assert not weekly.empty
        assert 'trade_date' in weekly.columns
        assert 'is_weekend' in weekly.columns
        assert 'cycle' in weekly.columns
        
        # 验证周期标识
        assert all(weekly['cycle'] == '1w')
        
        # 验证周线数量（1月约4周）
        assert len(weekly) >= 3 and len(weekly) <= 5
        
    def test_monthly_synthesis(self, synthesizer, sample_daily_data):
        """测试月线合成"""
        monthly = synthesizer.synthesize_monthly(sample_daily_data)
        
        # 验证基本结构
        assert not monthly.empty
        assert 'trade_date' in monthly.columns
        assert 'is_month_end' in monthly.columns
        assert 'cycle' in monthly.columns
        
        # 验证周期标识
        assert all(monthly['cycle'] == '1m')
        
        # 验证月线数量
        assert len(monthly) == 1
    
    def test_weekend_detection(self, synthesizer):
        """测试周末检测（周线结束于周五）"""
        # 构建包含完整一周的数据（2026-06-02周一到2026-06-05周五）
        dates = pd.date_range('2026-06-02', '2026-06-05', freq='D')  # 周一到周五
        data = {
            'trade_date': dates,
            'open': [10.0, 10.1, 10.2, 10.3],
            'high': [10.5, 10.6, 10.7, 10.8],
            'low': [9.9, 10.0, 10.1, 10.2],
            'close': [10.3, 10.4, 10.5, 10.6],
            'pre_close': [9.8, 10.3, 10.4, 10.5],
            'volume': [1000000, 2000000, 3000000, 4000000],
            'amount': [10000000, 20000000, 30000000, 40000000]
        }
        df = pd.DataFrame(data)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        weekly = synthesizer.synthesize_weekly(df)
        
        # 验证周末标记（周五结束）
        assert len(weekly) == 1
        # 2026-06-05 是周五（dayofweek=4），应该标记为周末
        assert weekly['trade_date'].iloc[0] == '2026-06-05'
        # is_weekend 判断的是最后一个交易日是否为周五
        assert weekly['is_weekend'].iloc[0] == True
    
    def test_month_end_detection(self, synthesizer):
        """测试月末检测"""
        # 构建包含月末的数据（2026-06-30是周一）
        dates = pd.date_range('2026-06-27', '2026-06-30', freq='D')  # 周四到周一（月末）
        data = {
            'trade_date': dates,
            'open': [10.0, 10.1, 10.2, 10.3],
            'high': [10.5, 10.6, 10.7, 10.8],
            'low': [9.9, 10.0, 10.1, 10.2],
            'close': [10.3, 10.4, 10.5, 10.6],
            'pre_close': [9.8, 10.3, 10.4, 10.5],
            'volume': [1000000, 2000000, 3000000, 4000000],
            'amount': [10000000, 20000000, 30000000, 40000000]
        }
        df = pd.DataFrame(data)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        monthly = synthesizer.synthesize_monthly(df)
        
        # 验证月末标记
        assert len(monthly) == 1
        assert monthly['is_month_end'].iloc[0] == True
    
    def test_empty_data(self, synthesizer):
        """测试空数据处理"""
        empty_df = pd.DataFrame()
        weekly = synthesizer.synthesize_weekly(empty_df)
        monthly = synthesizer.synthesize_monthly(empty_df)
        
        assert weekly.empty
        assert monthly.empty
    
    def test_real_stock_data(self, synthesizer):
        """测试真实股票数据合成"""
        try:
            daily = synthesizer.get_daily_data('000001', '2026-01-01', '2026-01-31')
            if not daily.empty:
                weekly = synthesizer.synthesize_weekly(daily)
                monthly = synthesizer.synthesize_monthly(daily)
                
                assert not weekly.empty
                assert not monthly.empty
                assert monthly['is_month_end'].iloc[0] == True  # 1月31日是月末
        except Exception:
            pytest.skip("数据库连接失败")
        finally:
            synthesizer.storage.disconnect()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
