#!/usr/bin/env python3
"""
股票代码处理工具模块

提供统一的股票代码格式转换和校验功能，解决以下问题：
- stock_basic 表使用带市场前缀的代码（如 SZ.000001）
- stock_quotes 表使用纯数字代码（如 000001）
- 不同数据源使用不同格式（如 ts_code: 000001.SZ）

支持的格式转换：
1. 纯数字代码 ↔ 带市场前缀代码
2. 带下划线格式 ↔ 带点格式
3. 统一校验和标准化
"""
import re
from typing import Optional, Tuple, List


def normalize_code(code: str) -> Optional[str]:
    """
    标准化股票代码为纯6位数字格式
    
    Args:
        code: 股票代码（支持多种格式）
    
    Returns:
        标准化后的6位数字代码，格式不合法返回None
    
    支持的输入格式：
        - 纯数字：600000
        - 带市场前缀：sh600000, sz000001
        - 带点分隔：600000.SH, 000001.SZ, sh.600000, sz.000001
    """
    if not code:
        return None
    
    code = str(code).strip()
    
    # 移除市场标识后缀/前缀
    code = code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
    code = code.replace('.sh', '').replace('.sz', '').replace('.bj', '')
    code = code.replace('SH', '').replace('SZ', '').replace('BJ', '')
    code = code.replace('sh', '').replace('sz', '').replace('bj', '')
    code = code.replace('.', '')
    
    # 校验是否为6位数字
    if len(code) == 6 and code.isdigit():
        return code
    
    return None


def validate_stock_code(code: str) -> bool:
    """
    校验股票代码格式（6位数字，且符合A股代码规则）
    
    A股代码规则：
        - 60开头：上海证券交易所主板
        - 00开头：深圳证券交易所主板
        - 002开头：深圳证券交易所中小板
        - 30开头：深圳证券交易所创业板
    
    Returns:
        True表示格式合法，False表示格式不合法
    """
    normalized = normalize_code(code)
    if not normalized:
        return False
    
    prefix = normalized[:2]
    valid_prefixes = {'60', '00', '30'}
    if prefix in valid_prefixes:
        return True
    
    prefix3 = normalized[:3]
    return prefix3 in {'002', '688', '920'}


def get_exchange(code: str) -> Optional[str]:
    """
    根据股票代码判断交易所
    
    Args:
        code: 股票代码（支持纯数字或带前缀格式）
    
    Returns:
        'SH' 表示上交所，'SZ' 表示深交所，无法识别返回None
    """
    normalized = normalize_code(code)
    if not normalized:
        return None
    
    prefix = normalized[:3]
    
    # 上交所：600/601/602/603/605/688/689 开头
    if prefix in ['600', '601', '602', '603', '604', '605', '688', '689']:
        return 'SH'
    
    # 北交所：920/8 开头
    if prefix in ['920'] or prefix.startswith('8'):
        return 'BJ'
    
    # 深交所：其他前缀
    return 'SZ'


def to_ts_code(code: str) -> Optional[str]:
    """
    转换为TS格式代码（如 000001.SZ, 600000.SH）
    
    Args:
        code: 股票代码（支持多种格式）
    
    Returns:
        TS格式代码，格式不合法返回None
    """
    normalized = normalize_code(code)
    exchange = get_exchange(code)
    
    if normalized and exchange:
        return f'{normalized}.{exchange}'
    
    return None


def to_market_prefix(code: str) -> Optional[str]:
    """
    转换为带市场前缀格式（如 sz.000001, sh.600000）
    
    Args:
        code: 股票代码（支持多种格式）
    
    Returns:
        带市场前缀格式代码，格式不合法返回None
    """
    normalized = normalize_code(code)
    exchange = get_exchange(code)
    
    if normalized and exchange:
        return f'{exchange.lower()}.{normalized}'
    
    return None


def to_short_code(code: str) -> Optional[str]:
    """
    转换为短格式代码（如 sz000001, sh600000）
    
    Args:
        code: 股票代码（支持多种格式）
    
    Returns:
        短格式代码，格式不合法返回None
    """
    normalized = normalize_code(code)
    exchange = get_exchange(code)
    
    if normalized and exchange:
        return f'{exchange.lower()}{normalized}'
    
    return None


def classify_market(code: str) -> Tuple[str, str]:
    """
    分类股票市场
    
    Args:
        code: 股票代码
    
    Returns:
        tuple: (market_code, market_name)
            market_code: 市场代码（如 sh_main, sz_main, sz_cyb, sh_star）
            market_name: 市场名称（如 上海主板, 深圳主板, 创业板, 科创板）
    """
    normalized = normalize_code(code)
    if not normalized:
        return ('unknown', '未知')
    
    prefix = normalized[:3]
    
    # 上海主板: 600/601/602/603/604/605 开头
    if prefix in ['600', '601', '602', '603', '604', '605']:
        return ('sh_main', '上海主板')
    
    # 上海科创板: 688/689 开头
    elif prefix in ['688', '689']:
        return ('sh_star', '科创板')
    
    # 深圳主板(含原中小板): 000/001/002/003 开头
    elif prefix in ['000', '001', '002', '003']:
        return ('sz_main', '深圳主板')
    
    # 深圳创业板: 300/301/302 开头
    elif prefix in ['300', '301', '302']:
        return ('sz_cyb', '创业板')
    
    # 北交所: 920/8 开头
    elif prefix in ['920'] or prefix.startswith('8'):
        return ('bj', '北交所')
    
    return ('unknown', '未知')


def convert_code_format(code: str, target_format: str) -> Optional[str]:
    """
    统一转换函数，根据目标格式进行转换
    
    Args:
        code: 原始股票代码
        target_format: 目标格式
            - 'normalized': 纯6位数字（如 000001）
            - 'ts': TS格式（如 000001.SZ）
            - 'prefix': 带点前缀（如 sz.000001）
            - 'short': 短格式（如 sz000001）
    
    Returns:
        转换后的代码，格式不合法或目标格式不支持返回None
    """
    format_map = {
        'normalized': normalize_code,
        'ts': to_ts_code,
        'prefix': to_market_prefix,
        'short': to_short_code,
    }
    
    converter = format_map.get(target_format)
    if converter:
        return converter(code)
    
    return None


def batch_convert_codes(codes: List[str], target_format: str) -> List[Optional[str]]:
    """
    批量转换股票代码格式
    
    Args:
        codes: 股票代码列表
        target_format: 目标格式（同 convert_code_format）
    
    Returns:
        转换后的代码列表，格式不合法的位置为None
    """
    return [convert_code_format(code, target_format) for code in codes]


def is_a_stock(code: str) -> bool:
    """
    判断是否为A股代码（排除B股、基金等）
    
    A股代码范围：
        - 沪市主板：600xxx, 601xxx, 603xxx, 605xxx
        - 深市主板：000xxx, 001xxx
        - 中小板：002xxx
        - 创业板：300xxx, 301xxx
        - 科创板：688xxx, 689xxx
    
    B股代码（排除）：
        - 沪市B股：900xxx
        - 深市B股：200xxx
    
    Returns:
        True表示是A股，False表示不是
    """
    normalized = normalize_code(code)
    if not normalized:
        return False
    
    prefix = normalized[:3]
    
    # A股代码前缀
    a_stock_prefixes = [
        '600', '601', '602', '603', '604', '605',  # 沪市主板
        '688', '689',                               # 科创板
        '000', '001', '002', '003',                   # 深市主板
        '300', '301', '302',                           # 创业板
        '920',                                      # 北交所
    ]
    
    return prefix in a_stock_prefixes


# 北交所股票代码前缀正则（6位格式）
# - 920xxx: 北交所（9开头，3位前缀920）
# - 8xxxxx: 北交所（8开头，6位）
BSE_CODE_PATTERN = r'^(8[0-9]{5}|920[0-9]{3})$'


def is_bse_code(code: str) -> bool:
    """
    判断是否为北交所股票代码

    Args:
        code: 股票代码（支持纯数字或带市场前缀格式）

    Returns:
        True 表示是北交所代码，False 表示不是
    """
    normalized = normalize_code(code)
    if not normalized:
        return False
    return bool(__import__('re').match(BSE_CODE_PATTERN, normalized))


def filter_out_bse(df, code_column: str = 'code') -> tuple:
    """
    从 DataFrame 中过滤掉北交所股票（统一入口）

    Args:
        df: 包含股票代码列的 DataFrame
        code_column: 代码列的列名，默认 'code'

    Returns:
        (filtered_df, removed_count): 过滤后的 DataFrame 和被移除的记录数

    注意:
        - 项目数据范围不包含北交所，所有 ETL 入库程序必须调用此函数
        - 代码必须先 normalize_code 标准化后再过滤
    """
    import logging
    logger = logging.getLogger(__name__)

    if df is None or df.empty:
        return df, 0

    import re
    codes = df[code_column].astype(str)
    bse_mask = codes.str.match(BSE_CODE_PATTERN)
    bse_count = int(bse_mask.sum())

    if bse_count > 0:
        logger.warning(f"过滤 {bse_count} 条北交所数据（{list(codes[bse_mask].unique()[:5])}{'...' if bse_count > 5 else ''}）")
        return df[~bse_mask], bse_count

    return df, 0
