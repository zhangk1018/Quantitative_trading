"""
基础存储接口
定义统一的存储操作接口，支持多种数据库实现
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict
import pandas as pd

class BaseStorage(ABC):
    """存储接口基类"""

    @abstractmethod
    def connect(self) -> bool:
        """连接数据库"""
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    def save_quotes(self, df: pd.DataFrame, adjust_type: str = 'qfq') -> int:
        """保存行情数据"""
        pass

    @abstractmethod
    def get_quotes(self, code: str, cycle: str = 'daily', 
                   start_date: Optional[str] = None, 
                   end_date: Optional[str] = None) -> pd.DataFrame:
        """获取行情数据"""
        pass

    @abstractmethod
    def save_stock_basic(self, df: pd.DataFrame) -> int:
        """保存股票基本信息"""
        pass

    @abstractmethod
    def get_stock_basic(self, code: Optional[str] = None) -> pd.DataFrame:
        """获取股票基本信息"""
        pass

    @abstractmethod
    def save_indicators(self, df: pd.DataFrame) -> int:
        """保存技术指标"""
        pass

    @abstractmethod
    def get_indicators(self, code: str, cycle: str = 'daily',
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None) -> pd.DataFrame:
        """获取技术指标"""
        pass

    @abstractmethod
    def save_trade_calendar(self, df: pd.DataFrame) -> int:
        """保存交易日历"""
        pass

    @abstractmethod
    def get_trade_calendar(self, start_date: Optional[str] = None,
                           end_date: Optional[str] = None,
                           is_open: Optional[int] = None) -> pd.DataFrame:
        """获取交易日历"""
        pass

    @abstractmethod
    def save_task_metrics(self, metrics: Dict):
        """保存任务指标"""
        pass

    @abstractmethod
    def get_latest_trade_date(self) -> Optional[str]:
        """获取最新交易日期"""
        pass

    @abstractmethod
    def get_stock_count(self, cycle: str = 'daily') -> int:
        """获取股票数量"""
        pass

    @abstractmethod
    def get_data_count(self, cycle: str = 'daily') -> int:
        """获取数据条数"""
        pass