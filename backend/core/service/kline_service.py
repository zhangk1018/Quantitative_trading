"""
kline_service.py - K线数据服务

提供股票K线数据查询、处理和分析功能。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import os
from functools import lru_cache
import time
import random

from collector.db.loader import DataLoader
from core.api.models.schemas import (
    KLineResponse, KLineItem, StockResponse, ListedBoard
)

class KlineService:
    """K线数据服务"""
    
    # 缓存配置
    CACHE_SIZE = 100  # 缓存100只股票
    CACHE_TTL = 600   # 10分钟过期
    
    def __init__(self, loader: DataLoader):
        self.loader = loader
        self.df = loader.df
        self.trade_date = loader.trade_date
        
        # 缓存存储
        self._cache = {}  # {stock_code_period: (expire_time, data)}
    
    def _generate_mock_kline(self, stock_code: str, base_price: float, limit: int) -> pd.DataFrame:
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
        
        # 验证股票代码
        stock_info = self._get_stock_info(stock_code)
        if not stock_info:
            return None
        
        # 获取基准价格
        base_price = 10.0
        if stock_info.close:
            base_price = float(stock_info.close)
        
        # 生成模拟 K线数据
        kline_df = self._generate_mock_kline(stock_code, base_price, limit)
        
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
    
    def _convert_to_kline_items(self, df: pd.DataFrame) -> List[KLineItem]:
        """将DataFrame转换为K线项列表"""
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
                amount=row.get("amount", Decimal(0))
            )
            
            kline_items.append(kline_item)
        
        return kline_items