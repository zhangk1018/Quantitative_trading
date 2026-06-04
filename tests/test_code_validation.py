#!/usr/bin/env python3
"""股票代码校验单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from base_importer import BaseDataImporter


class TestStockCodeValidation:
    """股票代码格式验证测试类"""
    
    def test_valid_a_stock_codes(self):
        """测试合法的A股股票代码"""
        valid_codes = [
            '600000',  # 沪市主板
            '600001',
            '000001',  # 深市主板
            '000002',
            '300001',  # 创业板
            '300002',
        ]
        
        for code in valid_codes:
            assert BaseDataImporter.validate_stock_code(code), f"合法代码 {code} 未通过校验"
    
    def test_invalid_stock_codes(self):
        """测试非法的股票代码"""
        invalid_codes = [
            '60000',   # 长度不足6位
            '6000000', # 长度超过6位
            '60000A',  # 包含非数字字符
            'ABCDEF',  # 全字母
            '123456',  # 前缀不在{60, 00, 30}中
            '900001',  # B股（不在项目支持范围内）
            '688001',  # 科创板（不在项目支持范围内）
            '830001',  # 北交所（不在项目支持范围内）
            '',        # 空字符串
            None,      # None
        ]
        
        for code in invalid_codes:
            assert not BaseDataImporter.validate_stock_code(code), f"非法代码 {code} 错误通过校验"
    
    def test_format_code_with_prefix(self):
        """测试带市场前缀的代码格式化"""
        test_cases = [
            ('sh600000', '600000'),
            ('sz000001', '000001'),
            ('SZ300001', '300001'),
            ('SH600001', '600001'),
            ('600000.SH', '600000'),
            ('000001.SZ', '000001'),
            ('sh.600000', '600000'),
            ('sz.000001', '000001'),
            ('600000', '600000'),  # 纯数字
        ]
        
        for input_code, expected in test_cases:
            result = BaseDataImporter._format_code(input_code)
            assert result == expected, f"格式化失败: {input_code} -> {result} (期望: {expected})"
    
    def test_format_code_invalid(self):
        """测试非法代码格式化返回None"""
        invalid_codes = [
            '123456',   # 前缀不合法
            '900000',   # B股
            '688001',   # 科创板
            'ABCDEF',   # 字母
            '60000',    # 5位
            '6000000',  # 7位
        ]
        
        for code in invalid_codes:
            result = BaseDataImporter._format_code(code)
            assert result is None, f"非法代码 {code} 格式化结果不为None: {result}"


class TestDateValidation:
    """日期格式验证测试类"""
    
    def test_valid_dates(self):
        """测试合法的日期格式"""
        valid_dates = [
            '2026-01-01',
            '2026-12-31',
            '2026-02-28',
            '2024-02-29',  # 闰年
        ]
        
        for date_str in valid_dates:
            result = BaseDataImporter.validate_date(date_str)
            assert result == date_str, f"合法日期 {date_str} 未通过校验"
    
    def test_invalid_dates(self):
        """测试非法的日期格式"""
        invalid_dates = [
            '2026/01/01',    # 斜杠分隔
            '2026-13-01',    # 月份超过12
            '2026-01-32',    # 日期超过31
            '2026-02-30',    # 2月30日
            '2025-02-29',    # 非闰年2月29日
            '2026-00-01',    # 月份为0
            '2026-01-00',    # 日期为0
            '20260101',      # 无分隔符
            '2026年1月1日',  # 中文格式
        ]
        
        for date_str in invalid_dates:
            with pytest.raises(ValueError):
                BaseDataImporter.validate_date(date_str)
    
    def test_date_range_validation(self):
        """测试日期范围校验"""
        # 合法范围
        BaseDataImporter.validate_date_range('2026-01-01', '2026-01-31')
        BaseDataImporter.validate_date_range('2026-01-15', '2026-01-15')  # 同一天
        
        # 非法范围
        with pytest.raises(ValueError):
            BaseDataImporter.validate_date_range('2026-02-01', '2026-01-01')


class TestCycleValidation:
    """周期参数验证测试类"""
    
    def test_valid_cycles(self):
        """测试合法的周期参数"""
        valid_cycles = ['1m', '5m', '15m', '30m', '60m', '1d', '1w', '1M']
        
        for cycle in valid_cycles:
            result = BaseDataImporter.validate_cycles([cycle])
            assert cycle in result, f"合法周期 {cycle} 未通过校验"
    
    def test_invalid_cycles(self):
        """测试非法的周期参数"""
        invalid_cycles = [
            ['2m'],      # 不支持的分钟周期
            ['1h'],      # 不支持的小时周期
            ['daily'],   # 错误格式
            ['week'],    # 错误格式
            ['month'],   # 错误格式
        ]
        
        for cycles in invalid_cycles:
            with pytest.raises(ValueError):
                BaseDataImporter.validate_cycles(cycles)
    
    def test_mixed_cycles(self):
        """测试混合合法和非法周期"""
        # 全部合法
        result = BaseDataImporter.validate_cycles(['5m', '15m', '1d'])
        assert len(result) == 3
        
        # 空列表
        result = BaseDataImporter.validate_cycles([])
        assert len(result) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])