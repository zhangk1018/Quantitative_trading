"""
kline_service.py - K线数据服务

提供股票K线数据查询、处理和分析功能。
"""

import pandas as pd
import numpy as np
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import time
import random

from collector.db.loader import DataLoader
from collector.storage.postgresql_storage import PostgreSQLStorage
from core.api.models.schemas import (
    KLineResponse, KLineItem, StockResponse,
)

class KlineService:
    """K线数据服务"""
    
    # 缓存配置
    CACHE_SIZE = 100  # 缓存100只股票
    CACHE_TTL = 600   # 10分钟过期
    
    def __init__(self, loader: DataLoader, storage: PostgreSQLStorage = None):
        self.loader = loader
        self.df = loader.df
        self.trade_date = loader.trade_date
        self._storage = storage

        # 缓存存储
        self._cache = {}  # {stock_code_period: (expire_time, data)}
    
    def _generate_mock_kline(self, base_price: float, limit: int) -> pd.DataFrame:
        """生成模拟 K线数据（用于演示）"""
        dates = []
        base_date = datetime.strptime(self.trade_date, "%Y%m%d")
        
        for i in range(limit, 0, -1):
            trade_date = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
            # 生成随机波动
            change = (random.random() - 0.5) * 0.04  # ±2% 波动
            open_price = base_price * (1 + change)
            high_price = open_price * (1 + random.random() * 0.02)
            low_price = open_price * (1 - random.random() * 0.02)
            close_price = (high_price + low_price) / 2 + (random.random() - 0.5) * (high_price - low_price)
            volume = int(random.randint(1000000, 10000000))
            amount = float(close_price * volume / 100)
            
            dates.append({
                "trade_date": trade_date,
                "open": Decimal(str(round(open_price, 2))),
                "high": Decimal(str(round(high_price, 2))),
                "low": Decimal(str(round(low_price, 2))),
                "close": Decimal(str(round(close_price, 2))),
                "volume": volume,
                "amount": Decimal(str(round(amount, 2)))
            })
            
            base_price = float(close_price)
        
        return pd.DataFrame(dates)
    
    def get_kline_data(
        self, 
        stock_code: str, 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily",
        limit: int = 100
    ) -> Optional[KLineResponse]:
        """获取K线数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期 (YYYYMMDD格式)
            end_date: 结束日期 (YYYYMMDD格式)
            period: 周期类型 (daily, weekly, monthly, minute)
            limit: 最大返回条数
            
        Returns:
            KLineResponse对象，包含K线数据列表
        """
        # 生成缓存键
        cache_key = f"{stock_code}_{period}"
        
        # 检查缓存
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # 1. 优先从数据库读取真实数据
        kline_df = pd.DataFrame()
        if self._storage is not None:
            try:
                # 标准化代码格式（兼容 sh.600000 / sz.000001 / 600000 三种写法）
                db_code = stock_code
                for prefix in ('sh.', 'sz.', 'SH.', 'SZ.'):
                    if db_code.startswith(prefix):
                        db_code = db_code.replace(prefix, '').lower()

                # 转换日期格式（API 用 YYYYMMDD，storage 用 YYYY-MM-DD）
                s = start_date
                e = end_date
                if s and len(s) == 8:
                    s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
                if e and len(e) == 8:
                    e = f"{e[:4]}-{e[4:6]}-{e[6:]}"

                raw = self._storage.get_quotes(
                    code=db_code,
                    cycle=period,
                    start_date=s,
                    end_date=e
                )
                if not raw.empty:
                    kline_df = raw.copy()
                    # 确保日期格式统一为 YYYY-MM-DD
                    if 'trade_date' in kline_df.columns:
                        kline_df['trade_date'] = pd.to_datetime(kline_df['trade_date']).dt.strftime('%Y-%m-%d')
                    # 按日期倒序后取 limit 条（最近 N 天）
                    kline_df = kline_df.sort_values('trade_date', ascending=False).head(limit)
                    kline_df = kline_df.sort_values('trade_date', ascending=True)
            except Exception:
                kline_df = pd.DataFrame()

        # 2. 数据库无数据时降级使用 mock（仅用于演示/测试）
        if kline_df.empty:
            base_price = 10.0
            stock_info = self._get_stock_info(stock_code)
            if stock_info and stock_info.close:
                base_price = float(stock_info.close)
            kline_df = self._generate_mock_kline(base_price, limit)

        # 3. 应用日期范围过滤
        if start_date or end_date:
            kline_df = self._filter_by_date_range(kline_df, start_date, end_date)

        # 转换日期为字符串（YYYY-MM-DD）以匹配 KLineItem 期望格式
        if not kline_df.empty and "trade_date" in kline_df.columns:
            kline_df["trade_date"] = kline_df["trade_date"].apply(
                lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x)
            )

        # 转换为K线项列表
        kline_items = self._convert_to_kline_items(kline_df)

        # 构建响应
        response = KLineResponse(
            stock_code=stock_code,
            data=kline_items,
            count=len(kline_items)
        )
        
        # 存入缓存
        self._set_cache(cache_key, response)
        
        return response
    
    def _get_from_cache(self, cache_key: str):
        """从缓存获取数据"""
        if cache_key in self._cache:
            expire_time, data = self._cache[cache_key]
            if time.time() < expire_time:
                return data
            else:
                # 缓存过期，删除
                del self._cache[cache_key]
        return None
    
    def _set_cache(self, cache_key: str, data):
        """设置缓存"""
        # 如果缓存已满，删除最早的10%
        if len(self._cache) >= self.CACHE_SIZE:
            # 获取所有键并按过期时间排序，删除前10%
            sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][0])
            to_delete = sorted_keys[:int(self.CACHE_SIZE * 0.1)]
            for key in to_delete:
                del self._cache[key]
        
        # 设置新缓存（过期时间=当前时间+TTL）
        self._cache[cache_key] = (time.time() + self.CACHE_TTL, data)
    
    def _get_stock_info(self, stock_code: str) -> Optional[StockResponse]:
        """获取股票基本信息"""
        from core.service.screener_service import ScreenerService
        screener_service = ScreenerService(self.loader)
        return screener_service.get_stock_by_code(stock_code)

    def _filter_by_date_range(
        self,
        df: pd.DataFrame,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        按日期范围过滤 K 线数据

        Args:
            df: 原始 K 线 DataFrame
            start_date: 开始日期 (YYYYMMDD 或 YYYY-MM-DD)
            end_date: 结束日期 (YYYYMMDD 或 YYYY-MM-DD)
        """
        if df.empty:
            return df

        # 标准化 trade_date 为 YYYY-MM-DD 字符串用于比较
        dates = pd.to_datetime(df["trade_date"], errors="coerce")

        if start_date:
            start_norm = self._normalize_date(start_date)
            if start_norm:
                dates_mask = dates >= pd.Timestamp(start_norm)
                df = df[dates_mask].copy()

        if end_date:
            end_norm = self._normalize_date(end_date)
            if end_norm:
                # 包含 end_date 当天
                dates_mask = dates <= pd.Timestamp(end_norm)
                df = df[dates_mask].copy()

        return df.reset_index(drop=True)

    @staticmethod
    def _normalize_date(date_str: str) -> Optional[str]:
        """将 YYYYMMDD 或 YYYY-MM-DD 统一为 YYYY-MM-DD"""
        if not date_str:
            return None
        date_str = date_str.strip()
        if len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        # 假设已经是 YYYY-MM-DD
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except ValueError:
            return None
    
    def _calc_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标：MA、RSI、MACD、BOLL"""
        if df.empty or len(df) < 20:
            return df
        df = df.copy()
        df['close_f'] = df['close'].astype(float)
        # MA
        df['ma5'] = df['close_f'].rolling(window=5, min_periods=1).mean()
        df['ma10'] = df['close_f'].rolling(window=10, min_periods=1).mean()
        df['ma20'] = df['close_f'].rolling(window=20, min_periods=1).mean()
        # RSI(6)
        delta = df['close_f'].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=6, min_periods=1).mean()
        avg_loss = loss.rolling(window=6, min_periods=1).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        df['rsi_6'] = 100 - (100 / (1 + rs))
        # MACD
        ema12 = df['close_f'].ewm(span=12, adjust=False).mean()
        ema26 = df['close_f'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        # BOLL(20,2)
        ma20 = df['close_f'].rolling(window=20, min_periods=1).mean()
        std20 = df['close_f'].rolling(window=20, min_periods=1).std()
        df['boll_upper'] = ma20 + 2 * std20
        df['boll_mid'] = ma20
        df['boll_lower'] = ma20 - 2 * std20
        # 清理临时列
        df = df.drop(columns=['close_f'])
        return df

    def _convert_to_kline_items(self, df: pd.DataFrame) -> List[KLineItem]:
        """将DataFrame转换为K线项列表"""
        # 计算技术指标
        df = self._calc_indicators(df)
        kline_items = []
        
        for _, row in df.iterrows():
            # 构建K线项对象
            kline_item = KLineItem(
                trade_date=row.get("trade_date", ""),
                open=row.get("open", Decimal(0)),
                high=row.get("high", Decimal(0)),
                low=row.get("low", Decimal(0)),
                close=row.get("close", Decimal(0)),
                volume=row.get("volume", 0),
                amount=row.get("amount", Decimal(0)),
                ma5=Decimal(str(round(row.get("ma5"), 2))) if pd.notna(row.get("ma5")) else None,
                ma10=Decimal(str(round(row.get("ma10"), 2))) if pd.notna(row.get("ma10")) else None,
                ma20=Decimal(str(round(row.get("ma20"), 2))) if pd.notna(row.get("ma20")) else None,
                rsi_6=Decimal(str(round(row.get("rsi_6"), 2))) if pd.notna(row.get("rsi_6")) else None,
                macd=Decimal(str(round(row.get("macd"), 4))) if pd.notna(row.get("macd")) else None,
                boll_upper=Decimal(str(round(row.get("boll_upper"), 2))) if pd.notna(row.get("boll_upper")) else None,
                boll_mid=Decimal(str(round(row.get("boll_mid"), 2))) if pd.notna(row.get("boll_mid")) else None,
                boll_lower=Decimal(str(round(row.get("boll_lower"), 2))) if pd.notna(row.get("boll_lower")) else None,
            )
            
            kline_items.append(kline_item)
        
        return kline_items