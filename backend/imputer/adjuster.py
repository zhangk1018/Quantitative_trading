"""
adjuster.py - 复权处理（前复权 / 后复权 / 不复权）

【复权概念】
上市公司会进行分红、送股、拆股等操作，导致股价"跳空"。
例如：10 送 10 后，股价从 20 元"跳"到 10 元，但实际投资者持有的市值不变。

前复权（Forward Adjustment）
- 以最新价格为基准，向历史回溯调整
- 公式: adj_price_t = raw_price_t * (adj_factor_t / adj_factor_latest)
- 用途: 策略回测（避免价格跳空触发误止损）
- ✅ 推荐

后复权（Backward Adjustment）
- 以历史价格（上市首日）为基准，向未来推算调整
- 公式: adj_price_t = raw_price_t * (adj_factor_t / adj_factor_first)
- 用途: 观察长期走势

不复权（None）
- 直接使用原始价格
- 用途: 当日交易决策（与行情软件一致）

【数据源】
- Tushare: pro.adj_factor 接口（需 2000 积分以上）
- 字段: ts_code, trade_date, adj_factor

【避坑指南】
1. 复权仅影响 OHLC，不影响 volume/amount
2. 复权因子必须连续，如果某天缺失会导致后续全部错位
3. 复权计算是确定性的，同一股票同一日期结果唯一
"""

import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List

import pandas as pd
import psycopg2
from dotenv import load_dotenv

from shared.constants import AdjMethod, TABLE_STOCK_QUOTES
from utils.stock_code_utils import normalize_code

logger = logging.getLogger(__name__)

load_dotenv()


class Adjuster:
    """
    复权处理器

    使用方法：
        adj = Adjuster()
        df = adj.adjust(df, stock_code='000001.SZ', method=AdjMethod.FORWARD)
    """

    # 复权后需要重新计算的列（仅 OHLC，复权不影响成交量/额）
    ADJUSTABLE_COLUMNS = ['open', 'high', 'low', 'close']

    def __init__(self, conn=None):
        """
        Args:
            conn: 数据库连接（None 则自动创建）
        """
        self._conn = conn
        self._adj_factor_cache: Dict[str, pd.DataFrame] = {}

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=os.getenv('PG_HOST', 'localhost'),
                port=os.getenv('PG_PORT', '5432'),
                database=os.getenv('PG_DATABASE', 'quant_trading'),
                user=os.getenv('PG_USER', 'quant_user'),
                password=os.getenv('PG_PASSWORD', ''),
            )
        return self._conn

    def load_adj_factors(self, stock_code: str) -> pd.DataFrame:
        """
        从数据库加载复权因子

        Args:
            stock_code: 股票代码 (e.g. '000001.SZ')

        Returns:
            DataFrame with columns [trade_date, adj_factor]
        """
        # 标准化股票代码为纯6位数字格式（数据库中使用纯数字格式）
        normalized_code = normalize_code(stock_code)
        if not normalized_code:
            logger.warning(f'  ⚠️  股票代码格式无效: {stock_code}')
            return pd.DataFrame(columns=['trade_date', 'adj_factor'])

        # 使用标准化后的代码作为缓存键
        cache_key = normalized_code
        if cache_key in self._adj_factor_cache:
            return self._adj_factor_cache[cache_key]

        # 优先从数据库读
        try:
            sql = """
                SELECT trade_date, adj_factor
                FROM stock_adj_factor
                WHERE code = %s
                ORDER BY trade_date ASC
            """
            df = pd.read_sql(sql, self.conn, params=(normalized_code,))
            if not df.empty:
                df['trade_date'] = pd.to_datetime(df['trade_date'])
                self._adj_factor_cache[cache_key] = df
                logger.info(f'  ✅ {stock_code}({normalized_code}): 加载 {len(df)} 条复权因子')
                return df
        except Exception as e:
            logger.warning(f'  ⚠️  从数据库读 adj_factor 失败: {e}')

        # ⚠️  Tushare 免费版不支持 adj_factor 接口，退化方案已移除。
        # 如需复权因子数据，请升级 Tushare 账号等级，或使用其他数据源。

        # 无可用于回填复权因子的数据源：返回空 DataFrame
        logger.warning(f'  ⚠️  {stock_code}({normalized_code}) 无复权因子数据，将返回原始价格')
        return pd.DataFrame(columns=['trade_date', 'adj_factor'])

    def adjust(
        self,
        df: pd.DataFrame,
        stock_code: str,
        method: AdjMethod = AdjMethod.FORWARD,
    ) -> tuple:
        """
        对 K 线 DataFrame 应用复权

        Args:
            df: 原始 K 线（必须包含 trade_date, open/high/low/close）
            stock_code: 股票代码
            method: 复权方式

        Returns:
            tuple: (复权后的 DataFrame, 复权因子值)
                   对于前复权返回最新因子，后复权返回最早因子，不复权或失败返回 None
        """
        if method == AdjMethod.NONE:
            logger.info(f'  ℹ️  {stock_code}: 不复权')
            return df, None

        if df.empty:
            return df, None

        adj_factors = self.load_adj_factors(stock_code)
        if adj_factors.empty:
            logger.warning(f'  ⚠️  {stock_code}: 无复权因子，跳过复权')
            return df, None

        df = df.copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)

        # 合并复权因子
        df = df.merge(adj_factors, on='trade_date', how='left')

        adj_factor_value = None
        if method == AdjMethod.FORWARD:
            # 前复权：以最新因子为基准
            adj_factor_value = df['adj_factor'].dropna().iloc[-1] if df['adj_factor'].notna().any() else 1.0
            ratio = df['adj_factor'].fillna(adj_factor_value) / adj_factor_value
        elif method == AdjMethod.BACKWARD:
            # 后复权：以最早因子为基准
            adj_factor_value = df['adj_factor'].dropna().iloc[0] if df['adj_factor'].notna().any() else 1.0
            ratio = df['adj_factor'].fillna(adj_factor_value) / adj_factor_value
        else:
            return df, None

        # 对 OHLC 应用复权因子
        for col in self.ADJUSTABLE_COLUMNS:
            if col in df.columns:
                df[col] = df[col].astype(float)
                df[f'adj_{col}'] = (df[col] * ratio).round(2)
                df[col] = df[f'adj_{col}']

        logger.info(
            f'  ✅ {stock_code} 复权完成: method={method.value}, '
            f'factor={adj_factor_value}, rows={len(df)}'
        )
        return df, adj_factor_value


# ============================================
# 便捷函数
# ============================================

def adjust_prices(
    df: pd.DataFrame,
    stock_code: str,
    method: str = 'forward',
) -> pd.DataFrame:
    """
    便捷函数：对价格 DataFrame 应用复权

    Args:
        df: K线 DataFrame
        stock_code: 股票代码
        method: 复权方式 'forward' | 'backward' | 'none'
    
    Returns:
        复权后的 DataFrame（仅返回 DataFrame，不返回复权因子）
    """
    df, _ = Adjuster().adjust(df, stock_code, AdjMethod(method))
    return df


def load_adj_factors(stock_code: str) -> pd.DataFrame:
    """便捷函数：加载复权因子"""
    return Adjuster().load_adj_factors(stock_code)
