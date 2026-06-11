"""
shared/utils.py - 前后端共用的工具函数

【设计目标】
- 任何前后端都可能用到的工具放这里
- 业务专用的工具放 backend/utils/ 或 frontend/utils/
- 纯函数优先，避免引入状态
"""

import os
import re
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Union, Optional


# ============================================
# 时间相关
# ============================================

def to_yyyymmdd(d: Union[str, date, datetime]) -> str:
    """
    把日期统一转为 YYYYMMDD 字符串格式
    用于 API 接口的 trade_date 字段
    """
    if isinstance(d, str):
        # 已经是字符串，尝试解析
        d = parse_date(d)
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime('%Y%m%d')


def parse_date(s: str) -> date:
    """
    解析多种日期格式
    支持: 2026-06-05, 2026/06/05, 20260605
    """
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()

    s = s.strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y%m%d', '%Y.%m.%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {s}")


def trading_days_between(start: str, end: str) -> int:
    """
    估算两个日期之间的"交易日"数（粗略估算，未去除节假日）
    精确交易日历需要接入 jqdatasdk / baostock 的交易日历
    """
    s = parse_date(start)
    e = parse_date(end)
    days = (e - s).days
    # 粗略：每周 5 个交易日
    return max(0, days * 5 // 7)


def today_str() -> str:
    """返回今天的 YYYY-MM-DD"""
    return datetime.now().strftime('%Y-%m-%d')


def yesterday_str() -> str:
    """返回昨天的 YYYY-MM-DD"""
    return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


# ============================================
# 数字相关
# ============================================

def safe_decimal(v, default: Optional[Decimal] = None) -> Optional[Decimal]:
    """安全地把值转 Decimal（None / 非法值返回 default）"""
    if v is None or v == '' or (isinstance(v, str) and v.strip().lower() in ('nan', 'null', 'none')):
        return default
    try:
        return Decimal(str(v))
    except Exception:
        return default


def safe_float(v, default: Optional[float] = None) -> Optional[float]:
    """安全地把值转 float"""
    if v is None or v == '':
        return default
    try:
        f = float(v)
        return f if f == f else default  # 排除 NaN
    except (ValueError, TypeError):
        return default


def pct_change(new: float, old: float) -> Optional[float]:
    """计算涨跌幅（%），避免除零"""
    if old == 0 or old is None or new is None:
        return None
    return (new - old) / old * 100


# ============================================
# 字符串相关
# ============================================

def normalize_stock_code(code: str) -> str:
    """
    标准化股票代码
    - '000001' -> '000001.SZ'
    - 'sh600000' -> '600000.SH'
    - '600000.SH' -> '600000.SH' (不变)
    """
    if not code:
        return code
    code = code.strip().upper()
    if '.' in code:
        return code

    # 处理 sh/sz 前缀
    if code.startswith('SH'):
        return f'{code[2:]}.SH'
    if code.startswith('SZ'):
        return f'{code[2:]}.SZ'
    if code.startswith('BJ'):
        return f'{code[2:]}.BJ'

    # 处理纯数字
    if code.isdigit() and len(code) == 6:
        if code.startswith(('60', '68', '90')):  # 沪市主板/科创板/B股
            return f'{code}.SH'
        if code.startswith(('00', '30', '20')):  # 深市主板/创业板/B股
            return f'{code}.SZ'
        if code.startswith(('43', '83', '87', '88')):  # 北交所
            return f'{code}.BJ'

    return code


def is_valid_stock_code(code: str) -> bool:
    """校验股票代码是否合法"""
    return bool(re.match(r'^\d{6}\.(SH|SZ|BJ)$', code or ''))


# ============================================
# 文件路径相关
# ============================================

def project_root() -> str:
    """获取项目根目录（绝对路径）"""
    # shared/utils.py 在 <root>/shared/utils.py
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
