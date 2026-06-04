#!/usr/bin/env python3
"""
股票代码工具模块单元测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.stock_code_utils import (
    normalize_code,
    validate_stock_code,
    get_exchange,
    to_ts_code,
    to_market_prefix,
    to_short_code,
    classify_market,
    convert_code_format,
    batch_convert_codes,
    is_a_stock,
)


def run_tests():
    """运行所有测试"""
    passed = 0
    failed = 0

    # 测试 normalize_code
    assert normalize_code('600000') == '600000', "normalize_code 测试失败"
    assert normalize_code('000001') == '000001', "normalize_code 测试失败"
    assert normalize_code('300001') == '300001', "normalize_code 测试失败"
    assert normalize_code('600000.SH') == '600000', "normalize_code 测试失败"
    assert normalize_code('000001.SZ') == '000001', "normalize_code 测试失败"
    assert normalize_code('sh.600000') == '600000', "normalize_code 测试失败"
    assert normalize_code('sz.000001') == '000001', "normalize_code 测试失败"
    assert normalize_code('') is None, "normalize_code 空值测试失败"
    passed += 1
    print("✓ normalize_code 测试通过")

    # 测试 validate_stock_code
    assert validate_stock_code('600000') is True, "validate_stock_code 测试失败"
    assert validate_stock_code('000001') is True, "validate_stock_code 测试失败"
    assert validate_stock_code('900000') is False, "validate_stock_code B股测试失败"
    passed += 1
    print("✓ validate_stock_code 测试通过")

    # 测试 get_exchange
    assert get_exchange('600000') == 'SH', "get_exchange 测试失败"
    assert get_exchange('000001') == 'SZ', "get_exchange 测试失败"
    passed += 1
    print("✓ get_exchange 测试通过")

    # 测试 to_ts_code
    assert to_ts_code('600000') == '600000.SH', "to_ts_code 测试失败"
    assert to_ts_code('000001') == '000001.SZ', "to_ts_code 测试失败"
    passed += 1
    print("✓ to_ts_code 测试通过")

    # 测试 to_market_prefix
    assert to_market_prefix('600000') == 'sh.600000', "to_market_prefix 测试失败"
    assert to_market_prefix('000001') == 'sz.000001', "to_market_prefix 测试失败"
    passed += 1
    print("✓ to_market_prefix 测试通过")

    # 测试 classify_market
    assert classify_market('600000') == ('sh_main', '上海主板'), "classify_market 测试失败"
    assert classify_market('300001') == ('sz_cyb', '创业板'), "classify_market 测试失败"
    passed += 1
    print("✓ classify_market 测试通过")

    # 测试 convert_code_format
    assert convert_code_format('600000', 'normalized') == '600000', "convert_code_format 测试失败"
    assert convert_code_format('600000', 'ts') == '600000.SH', "convert_code_format 测试失败"
    assert convert_code_format('600000', 'invalid') is None, "convert_code_format 无效格式测试失败"
    passed += 1
    print("✓ convert_code_format 测试通过")

    # 测试 batch_convert_codes
    codes = ['600000', '000001', 'invalid']
    result = batch_convert_codes(codes, 'ts')
    assert result == ['600000.SH', '000001.SZ', None], "batch_convert_codes 测试失败"
    passed += 1
    print("✓ batch_convert_codes 测试通过")

    # 测试 is_a_stock
    assert is_a_stock('600000') is True, "is_a_stock 测试失败"
    assert is_a_stock('900000') is False, "is_a_stock B股测试失败"
    passed += 1
    print("✓ is_a_stock 测试通过")

    print(f"\n🎉 所有测试通过！({passed} 个测试)")


if __name__ == '__main__':
    run_tests()