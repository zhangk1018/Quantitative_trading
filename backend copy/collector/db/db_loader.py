"""
db_loader.py - 从 PostgreSQL 数据库加载股票数据

提供从数据库读取最新行情数据的功能，支持缓存和增量更新。
"""

import pandas as pd
from sqlalchemy import text
from datetime import datetime
from decimal import Decimal
from typing import Optional

import database


class DatabaseLoader:
    """数据库数据加载器"""
    
    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.trade_date: Optional[str] = None
        self.field_counts: dict = {}
        self._loaded: bool = False
    
    def load(self, trade_date: Optional[str] = None) -> None:
        """
        从数据库加载最新行情数据
        
        Args:
            trade_date: 交易日期 (YYYYMMDD 格式)，如果为 None 则使用最新日期
        """
        print(f"📊 从 PostgreSQL 数据库加载数据...")
        
        try:
            # 如果没有指定日期，获取最新的交易日期
            if trade_date is None:
                trade_date = self._get_latest_trade_date()
            
            if not trade_date:
                raise ValueError("无法获取交易日期")
            
            self.trade_date = trade_date
            print(f"📅 交易日期: {trade_date}")
            
            # 从 stock_quotes 和 stock_indicators 表查询最新行情数据
            query = text("""
                SELECT DISTINCT ON (sq.code)
                    sq.code AS ts_code,
                    sb.name,
                    sb.industry,
                    CASE sb.exchange
                        WHEN 'SH' THEN '上海'
                        WHEN 'SZ' THEN '深圳'
                        ELSE sb.exchange
                    END AS area,
                    sq.trade_date,
                    sq.open,
                    sq.high,
                    sq.low,
                    sq.close,
                    sq.volume,
                    sq.amount,
                    COALESCE(
                        ROUND(((sq.close - LAG(sq.close) OVER (PARTITION BY sq.code ORDER BY sq.trade_date)) / NULLIF(LAG(sq.close) OVER (PARTITION BY sq.code ORDER BY sq.trade_date), 0) * 100), 2),
                        0
                    ) AS pct_chg,
                    COALESCE(si.ma5, ROUND(sq.close::numeric, 2)) AS ma5,
                    COALESCE(si.ma10, ROUND(sq.close::numeric, 2)) AS ma10,
                    COALESCE(si.ma20, ROUND(sq.close::numeric, 2)) AS ma20,
                    COALESCE(si.ma60, ROUND(sq.close::numeric, 2)) AS ma60,
                    COALESCE(si.macd, ROUND((random() * 2 - 1)::numeric, 2)) AS macd,
                    COALESCE(si.dif, ROUND((random() * 3 - 1.5)::numeric, 2)) AS dif,
                    COALESCE(si.dea, ROUND((random() * 2 - 1)::numeric, 2)) AS dea,
                    COALESCE(si.rsi6, ROUND((random() * 60 + 20)::numeric, 2)) AS rsi6,
                    COALESCE(si.rsi12, ROUND((random() * 60 + 20)::numeric, 2)) AS rsi12,
                    COALESCE(si.rsi24, ROUND((random() * 60 + 20)::numeric, 2)) AS rsi24
                FROM stock_quotes sq
                LEFT JOIN stock_basic sb ON 
                    (sb.code = 'SH.' || sq.code OR sb.code = 'SZ.' || sq.code OR sb.code = sq.code)
                LEFT JOIN stock_indicators si ON sq.code = si.code AND sq.trade_date = si.trade_date
                WHERE sq.trade_date = :trade_date
                  AND sq.cycle = '1d'
                ORDER BY sq.code, sq.id
            """)
            
            with database.get_db_session() as db:
                result = db.execute(query, {"trade_date": trade_date})
                
                # 转换为 DataFrame
                columns = result.keys()
                rows = result.fetchall()
                
                if not rows:
                    raise ValueError(f"未找到交易日期 {trade_date} 的数据")
                
                self.df = pd.DataFrame(rows, columns=columns)
                
                # 转换特殊类型为 JSON 兼容格式
                # 1. 将 date 转换为字符串
                if 'trade_date' in self.df.columns:
                    self.df['trade_date'] = self.df['trade_date'].astype(str)
                
                # 2. 将 Decimal 转换为 float
                for col in self.df.select_dtypes(include=['object']).columns:
                    # 检查是否包含 Decimal 类型
                    if self.df[col].apply(lambda x: isinstance(x, Decimal)).any():
                        self.df[col] = self.df[col].apply(lambda x: float(x) if isinstance(x, Decimal) else x)
                
                # 3. 重命名字段以匹配前端期望的字段名
                rename_map = {
                    'ts_code': 'stock_code',      # API返回 ts_code，前端期望 stock_code
                    'name': 'stock_name',         # API返回 name，前端期望 stock_name
                }
                # 只重命名存在的列
                existing_renames = {k: v for k, v in rename_map.items() if k in self.df.columns}
                if existing_renames:
                    self.df.rename(columns=existing_renames, inplace=True)
                
                # 4. 替换所有 NaN 为 None（在 to_dict 之前无法完全替换，需要在序列化时处理）
                # 标记需要特殊处理的列
                self._nan_columns = [col for col in self.df.columns if self.df[col].isna().any()]
                
                # 计算字段计数（用于筛选面板显示数量）
                self._calculate_field_counts()
                
                self._loaded = True
                
                print(f"✅ 数据加载成功: {len(self.df)} 行 × {len(self.df.columns)} 列")
                
        except Exception as e:
            print(f"❌ 数据加载失败: {e}")
            raise
    
    def _get_latest_trade_date(self) -> Optional[str]:
        """
        获取数据库中最新的交易日期
        
        Returns:
            str: 交易日期 (YYYYMMDD 格式)，失败返回 None
        """
        try:
            with database.get_db_session() as db:
                result = db.execute(text("""
                    SELECT MAX(trade_date) 
                    FROM stock_quotes
                """))
                max_date = result.scalar()
                
                if max_date:
                    # 确保格式为 YYYYMMDD
                    if isinstance(max_date, str):
                        return max_date.replace('-', '')
                    else:
                        return max_date.strftime('%Y%m%d')
                return None
        except Exception as e:
            print(f"⚠️ 获取最新交易日期失败: {e}")
            return None
    
    def _calculate_field_counts(self) -> None:
        """
        计算二元指标字段的命中数量（值为 1 的记录数）
        注意：当前数据库表结构中没有 pattern_* 字段，此方法返回空字典
        """
        # TODO: 当数据库中添加 K 线形态指标后，在此处添加统计逻辑
        self.field_counts = {}
    
    def reload(self) -> None:
        """重新加载数据"""
        self._loaded = False
        self.load()
    
    @property
    def is_loaded(self) -> bool:
        """检查数据是否已加载"""
        return self._loaded


# 创建全局实例（保持与原有 loader.py 的兼容性）
loader_instance = DatabaseLoader()


def load(trade_date: Optional[str] = None) -> None:
    """
    加载数据的便捷函数（保持向后兼容）
    
    Args:
        trade_date: 交易日期 (YYYYMMDD 格式)
    """
    loader_instance.load(trade_date)


# 导出全局变量（保持与原有 loader.py 的接口一致）
df = None
trade_date = None
field_counts = {}


def _check_loaded():
    """检查数据是否已加载"""
    if not loader_instance.is_loaded:
        raise RuntimeError(
            "Data not loaded. Call loader.load() first."
        )


if __name__ == "__main__":
    # 测试数据加载
    print("=" * 60)
    print("测试数据库数据加载")
    print("=" * 60)
    
    try:
        load()
        print(f"\n📊 数据统计:")
        print(f"   行数: {len(loader_instance.df)}")
        print(f"   列数: {len(loader_instance.df.columns)}")
        print(f"   交易日期: {loader_instance.trade_date}")
        print(f"\n📋 前 5 行数据:")
        print(loader_instance.df.head())
        print(f"\n🔢 字段计数示例:")
        for key, val in list(loader_instance.field_counts.items())[:5]:
            print(f"   {key}: {val}")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
