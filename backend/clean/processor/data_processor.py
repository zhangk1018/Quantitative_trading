"""
数据处理模块 - 数据清洗和转换
"""
import logging
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

logger = logging.getLogger(__name__)

class DataProcessor:
    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        处理原始数据
        
        Args:
            df: 原始DataFrame
            
        Returns:
            处理后的DataFrame
        """
        if df is None or df.empty:
            return df
            
        df = df.copy()
        
        # 1. 日期格式转换
        df = self._convert_date(df)
        
        # 2. 排序
        df = self._sort_by_date(df)
        
        # 3. 处理缺失值
        df = self._handle_missing_values(df)
        
        # 4. 数据类型转换
        df = self._convert_data_types(df)
        
        logger.debug(f'数据处理完成，当前数据量: {len(df)}')
        return df
    
    def _convert_date(self, df: pd.DataFrame) -> pd.DataFrame:
        """转换日期格式"""
        try:
            df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
            logger.debug('日期格式转换完成')
        except Exception as e:
            logger.warning(f'日期格式转换失败: {str(e)}')
        return df
    
    def _sort_by_date(self, df: pd.DataFrame) -> pd.DataFrame:
        """按日期排序"""
        if 'trade_date' in df.columns:
            df = df.sort_values('trade_date')
            logger.debug('按日期排序完成')
        return df
    
    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理缺失值"""
        missing_count = df.isnull().sum().sum()
        if missing_count > 0:
            logger.warning(f'发现 {missing_count} 个缺失值，使用前向填充')
            df = df.ffill().bfill()
        return df
    
    def _convert_data_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """转换数据类型"""
        numeric_cols = ['open', 'high', 'low', 'close', 'pre_close', 
                       'change', 'pct_chg', 'volume', 'amount']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    
    def visualize(self, df: pd.DataFrame, stock_code: str):
        """
        可视化收盘价走势
        
        Args:
            df: 数据DataFrame
            stock_code: 股票代码
        """
        try:
            plt.figure(figsize=(12, 6))
            plt.plot(df['trade_date'], df['close'], label='收盘价', color='#1f77b4')
            
            # 添加5日均线
            df['ma5'] = df['close'].rolling(5).mean()
            plt.plot(df['trade_date'], df['ma5'], label='5日均线', color='#ff7f0e', linestyle='--')
            
            # 添加20日均线
            df['ma20'] = df['close'].rolling(20).mean()
            plt.plot(df['trade_date'], df['ma20'], label='20日均线', color='#2ca02c', linestyle='--')
            
            plt.title(f'{stock_code} 股价走势', fontsize=14)
            plt.xlabel('日期')
            plt.ylabel('价格')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.show()
            logger.debug('可视化图表生成成功')
        except Exception as e:
            logger.error(f'可视化失败: {str(e)}')
