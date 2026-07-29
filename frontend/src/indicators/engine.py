import pandas as pd
from src.indicators.technical import TechnicalIndicators
from src.storage.sqlite_storage import SQLiteStorage # 假设你已有的存储模块

class IndicatorEngine:
    def __init__(self, db_path: str = "data/stock_data.db"):
        self.storage = SQLiteStorage(db_path)

    def get_stock_indicators(self, code: str, start_date: str = None, end_date: str = None):
        """
        获取单只股票的技术指标数据
        """
        # 1. 从数据库获取基础行情
        df = self.storage.get_quotes(code, cycle='day', start_date=start_date, end_date=end_date)
        
        if df.empty:
            return pd.DataFrame()

        # 2. 计算指标
        df = TechnicalIndicators.calculate_all(df)
        
        # 3. 处理 NaN (指标计算初期会有空值)
        df = df.dropna(subset=['ma5', 'macd_dif']) 
        
        return df

    def batch_calculate_for_screener(self, codes: List[str], date: str):
        """
        为选股器批量计算最新一天的指标状态
        这是前端“选股试图”性能的关键
        """
        results = []
        for code in codes:
            # 优化点：实际生产中应使用 SQL 聚合或批量读取，避免循环查库
            df = self.get_stock_indicators(code, end_date=date)
            if not df.empty:
                last_row = df.iloc[-1]
                results.append({
                    'code': code,
                    'ma5': last_row['ma5'],
                    'ma20': last_row['ma20'],
                    'macd_dif': last_row['macd_dif'],
                    'rsi': last_row['rsi'],
                    'boll_upper': last_row['boll_upper'],
                    'volume_ratio': last_row['volume_ratio']
                })
        return pd.DataFrame(results)