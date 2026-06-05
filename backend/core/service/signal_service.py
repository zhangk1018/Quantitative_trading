"""
signal_service.py - 买卖信号服务

提供股票买卖信号生成、分析和查询功能。
"""

import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime
from decimal import Decimal
import time

from collector.db.loader import DataLoader
from collector.storage.postgresql_storage import PostgreSQLStorage
from core.api.models.schemas import (
    SignalResponse, SignalItem, StockResponse,
)

class SignalService:
    """买卖信号服务"""
    
    # 缓存配置
    CACHE_SIZE = 100   # 缓存100只股票
    CACHE_TTL = 300    # 5分钟过期
    TIMEOUT = 30       # 超时时间（秒）
    
    def __init__(self, loader: DataLoader, storage: PostgreSQLStorage = None):
        self.loader = loader
        self.df = loader.df
        self.trade_date = loader.trade_date
        self._storage = storage
        
        # 缓存存储
        self._cache = {}  # {stock_code_signal_type: (expire_time, data)}
        
        # 信号类型配置
        self.signal_config = {
            "macd_cross": {
                "name": "MACD金叉/死叉",
                "description": "MACD指标的快线与慢线交叉产生的买卖信号",
                "buy_condition": "macd > signal and prev_macd <= prev_signal",
                "sell_condition": "macd < signal and prev_macd >= prev_signal",
            },
            "rsi_overbought": {
                "name": "RSI超买",
                "description": "RSI指标超过70，表示可能超买，产生卖出信号",
                "buy_condition": "rsi_6 < 30",
                "sell_condition": "rsi_6 > 70",
            },
            "bollinger_breakout": {
                "name": "布林带突破",
                "description": "价格突破布林带上轨或下轨产生的买卖信号",
                "buy_condition": "close < boll_lower",
                "sell_condition": "close > boll_upper",
            },
        }
    
    def get_signals(
        self, 
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        signal_type: Optional[str] = None,
        limit: int = 100
    ) -> Optional[SignalResponse]:
        """获取买卖信号
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期 (YYYYMMDD格式)
            end_date: 结束日期 (YYYYMMDD格式)
            signal_type: 信号类型
            limit: 最大返回条数
            
        Returns:
            SignalResponse对象，包含信号数据列表
        """
        # 生成缓存键
        cache_key = f"{stock_code}_{signal_type or 'all'}"
        
        # 检查缓存
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return self._filter_cached_signals(cached_data, start_date, end_date, limit)
        
        # 记录开始时间，用于超时检测
        start_time = time.time()
        
        # 验证股票代码（获取基本信息，允许找不到）
        stock_info = self._get_stock_info(stock_code)
        
        # 检查超时
        if time.time() - start_time > self.TIMEOUT:
            raise TimeoutError("信号查询超时")
        
        # 加载K线数据
        from core.service.kline_service import KlineService
        kline_service = KlineService(self.loader, self._storage)
        
        kline_response = kline_service.get_kline_data(
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            period="daily",
            limit=limit * 2,  # 加载更多数据用于信号计算
        )
        
        # 检查超时
        if time.time() - start_time > self.TIMEOUT:
            raise TimeoutError("信号查询超时")
        
        if not kline_response or kline_response.count == 0:
            return None
        
        # 生成信号
        signals = self._generate_signals(kline_response, signal_type)
        
        # 检查超时
        if time.time() - start_time > self.TIMEOUT:
            raise TimeoutError("信号查询超时")
        
        # 构建完整响应并缓存
        full_response = SignalResponse(
            stock_code=stock_code,
            stock_name=stock_info.stock_name if stock_info else None,
            listed_board=stock_info.listed_board if stock_info else None,
            signal_type=signal_type or "all",
            start_date=start_date,
            end_date=end_date,
            count=len(signals),
            signals=signals,
        )
        
        # 存入缓存
        self._set_cache(cache_key, full_response)
        
        # 应用日期筛选后返回
        return self._filter_cached_signals(full_response, start_date, end_date, limit)
    
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
    
    def _filter_cached_signals(self, response: SignalResponse, start_date: Optional[str], 
                               end_date: Optional[str], limit: int) -> SignalResponse:
        """从缓存的完整信号数据中筛选"""
        if start_date is None and end_date is None and limit >= response.count:
            return response
        
        # 转换日期格式用于比较（兼容 YYYY-MM-DD 和 YYYYMMDD）
        def str_to_date(date_str):
            if isinstance(date_str, str):
                for fmt in ("%Y-%m-%d", "%Y%m%d"):
                    try:
                        return datetime.strptime(date_str, fmt).date()
                    except ValueError:
                        continue
                raise ValueError(f"无法解析日期: {date_str}")
            return date_str
        
        # 筛选信号
        filtered_signals = response.signals
        
        if start_date:
            start_date_val = str_to_date(start_date)
            filtered_signals = [s for s in filtered_signals if s.signal_date >= start_date_val]
        
        if end_date:
            end_date_val = str_to_date(end_date)
            filtered_signals = [s for s in filtered_signals if s.signal_date <= end_date_val]
        
        # 应用限制
        filtered_signals = filtered_signals[:limit]
        
        # 返回筛选后的响应
        return SignalResponse(
            stock_code=response.stock_code,
            stock_name=response.stock_name,
            listed_board=response.listed_board,
            signal_type=response.signal_type,
            start_date=filtered_signals[0].signal_date if filtered_signals else None,
            end_date=filtered_signals[-1].signal_date if filtered_signals else None,
            count=len(filtered_signals),
            signals=filtered_signals,
        )
    
    def _get_stock_info(self, stock_code: str) -> Optional[StockResponse]:
        """获取股票基本信息"""
        from core.service.screener_service import ScreenerService
        screener_service = ScreenerService(self.loader)
        return screener_service.get_stock_by_code(stock_code)
    
    def _generate_signals(
        self, 
        kline_response: Any,
        signal_type: Optional[str] = None
    ) -> List[SignalItem]:
        """生成买卖信号"""
        signals = []
        
        # 将K线数据转换为DataFrame
        kline_items = kline_response.data
        if not kline_items:
            return signals
        
        # 创建DataFrame
        data = []
        for kline in kline_items:
            data.append({
                "date": kline.trade_date,
                "open": float(kline.open) if kline.open else 0,
                "high": float(kline.high) if kline.high else 0,
                "low": float(kline.low) if kline.low else 0,
                "close": float(kline.close) if kline.close else 0,
                "volume": kline.volume,
                "amount": kline.amount,
                "ma5": float(kline.ma5) if kline.ma5 else 0,
                "ma10": float(kline.ma10) if kline.ma10 else 0,
                "ma20": float(kline.ma20) if kline.ma20 else 0,
                "rsi_6": float(kline.rsi_6) if kline.rsi_6 else 0,
                "macd": float(kline.macd) if kline.macd else 0,
                "boll_upper": float(kline.boll_upper) if kline.boll_upper else 0,
                "boll_mid": float(kline.boll_mid) if kline.boll_mid else 0,
                "boll_lower": float(kline.boll_lower) if kline.boll_lower else 0,
            })
        
        df = pd.DataFrame(data)
        if df.empty:
            return signals
        
        # 按日期排序（从旧到新）
        df = df.sort_values("date", ascending=True)
        
        # 生成MACD信号
        if not signal_type or signal_type == "macd_cross":
            macd_signals = self._generate_macd_signals(df)
            signals.extend(macd_signals)
        
        # 生成RSI信号
        if not signal_type or signal_type == "rsi_overbought":
            rsi_signals = self._generate_rsi_signals(df)
            signals.extend(rsi_signals)
        
        # 生成布林带信号
        if not signal_type or signal_type == "bollinger_breakout":
            bollinger_signals = self._generate_bollinger_signals(df)
            signals.extend(bollinger_signals)
        
        # 按日期排序（从新到旧）
        signals.sort(key=lambda x: x.date, reverse=True)
        
        # 限制返回数量
        return signals[:100]
    
    def _generate_macd_signals(self, df: pd.DataFrame) -> List[SignalItem]:
        """生成MACD交叉信号"""
        signals = []
        
        # 需要至少2个数据点
        if len(df) < 2:
            return signals
        
        for i in range(1, len(df)):
            prev_row = df.iloc[i-1]
            curr_row = df.iloc[i]
            
            prev_macd = prev_row["macd"]
            curr_macd = curr_row["macd"]
            
            # 计算信号线（简单移动平均）
            signal_period = 9
            start_idx = max(0, i - signal_period + 1)
            prev_signal = df.iloc[start_idx:i]["macd"].mean()
            curr_signal = df.iloc[start_idx:i+1]["macd"].mean()
            
            # 金叉信号（买入）
            if curr_macd > curr_signal and prev_macd <= prev_signal:
                signals.append(SignalItem(
                    trade_date=curr_row["date"],
                    signal_type="macd_cross",
                    price=Decimal(str(curr_row["close"])),
                    reason=f"MACD金叉：{curr_macd:.2f} > {curr_signal:.2f}",
                ))

            # 死叉信号（卖出）
            elif curr_macd < curr_signal and prev_macd >= prev_signal:
                signals.append(SignalItem(
                    trade_date=curr_row["date"],
                    signal_type="macd_cross",
                    price=Decimal(str(curr_row["close"])),
                    reason=f"MACD死叉：{curr_macd:.2f} < {curr_signal:.2f}",
                ))

        return signals

    def _generate_rsi_signals(self, df: pd.DataFrame) -> List[SignalItem]:
        """生成RSI超买超卖信号"""
        signals = []

        for _, row in df.iterrows():
            rsi = row["rsi_6"]

            # RSI超卖信号（买入）
            if rsi < 30:
                signals.append(SignalItem(
                    trade_date=row["date"],
                    signal_type="rsi_oversold",
                    price=Decimal(str(row["close"])),
                    reason=f"RSI超卖：{rsi:.2f} < 30",
                ))

            # RSI超买信号（卖出）
            elif rsi > 70:
                signals.append(SignalItem(
                    trade_date=row["date"],
                    signal_type="rsi_overbought",
                    price=Decimal(str(row["close"])),
                    reason=f"RSI超买：{rsi:.2f} > 70",
                ))

        return signals

    def _generate_bollinger_signals(self, df: pd.DataFrame) -> List[SignalItem]:
        """生成布林带突破信号"""
        signals = []

        for _, row in df.iterrows():
            close = row["close"]
            boll_upper = row["boll_upper"]
            boll_lower = row["boll_lower"]

            # 突破上轨（卖出信号）
            if close > boll_upper:
                signals.append(SignalItem(
                    trade_date=row["date"],
                    signal_type="bollinger_breakout",
                    price=Decimal(str(close)),
                    reason=f"突破布林上轨：{close:.2f} > {boll_upper:.2f}",
                ))

            # 突破下轨（买入信号）
            elif close < boll_lower:
                signals.append(SignalItem(
                    trade_date=row["date"],
                    signal_type="bollinger_breakout",
                    price=Decimal(str(close)),
                    reason=f"突破布林下轨：{close:.2f} < {boll_lower:.2f}",
                ))

        return signals
    
    def get_signal_types(self) -> List[Dict[str, Any]]:
        """获取信号类型列表"""
        result = []
        
        for signal_type, config in self.signal_config.items():
            result.append({
                "type": signal_type,
                "name": config["name"],
                "description": config["description"],
            })
        
        return result
    
    def analyze_signal_performance(
        self,
        stock_code: str,
        signal_type: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """分析信号表现
        
        返回指定信号类型的回测表现
        """
        # 暂时返回占位数据
        return {
            "stock_code": stock_code,
            "signal_type": signal_type,
            "days": days,
            "total_signals": 0,
            "buy_signals": 0,
            "sell_signals": 0,
            "win_rate": 0,
            "avg_profit": 0,
            "max_drawdown": 0,
            "sharpe_ratio": 0,
            "message": "信号回测功能正在开发中",
        }