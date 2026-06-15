#!/usr/bin/env python3
"""特征服务模块 - 提供统一的防前视偏差特征接口"""
import pandas as pd
from typing import List, Optional
from datetime import datetime
from utils.storage_factory import StorageFactory
from clean.processor.technical_indicator import TechnicalIndicator
from utils.logger import setup_logger
from utils.config import config

logger = setup_logger('feature_service')


class FeatureService:
    """特征服务 - 提供防前视偏差的特征获取接口"""
    
    def __init__(self):
        self.storage = StorageFactory.create_storage(config.storage)
    
    def connect(self) -> bool:
        """连接数据库"""
        return self.storage.connect()
    
    def disconnect(self):
        """断开连接"""
        self.storage.disconnect()
    
    def get_features(
        self,
        symbol: str,
        start: str,
        end: str,
        as_of_date: str = None,
        indicators: List[str] = None,
        adjust_type: str = 'qfq'
    ) -> pd.DataFrame:
        """
        按 as_of_date 返回点-in-time特征快照，严格防前视偏差
        
        Args:
            symbol: 股票代码
            start: 开始日期
            end: 结束日期
            as_of_date: 查询基准日期（用于防前视偏差），默认使用 end
            indicators: 需要的指标列表，默认 ["MA", "MACD", "RSI"]
            adjust_type: 复权类型: qfq(前复权), hfq(后复权), None(不复权)
        
        Returns:
            特征 DataFrame，包含日期、价格和指定指标
        """
        logger.info(f"获取特征: {symbol} [{start} - {end}], as_of_date: {as_of_date}")
        
        if indicators is None:
            indicators = ["MA", "MACD", "RSI"]
        
        if as_of_date is None:
            as_of_date = end
        
        # 获取行情数据
        quotes_df = self.storage.get_quotes(symbol, 'daily', start, end)
        
        if quotes_df.empty:
            logger.warning(f"股票 {symbol} 在 [{start} - {end}] 期间无行情数据")
            return pd.DataFrame()
        
        # 过滤有效日期（基于 as_of_date 防止前视偏差）
        quotes_df = quotes_df[quotes_df['effective_date'] <= as_of_date]
        
        # 应用复权
        if adjust_type and adjust_type != 'None':
            quotes_df = self._apply_adjustment(quotes_df, adjust_type)
        
        # 计算指标
        features_df = self._calculate_features(quotes_df, indicators)
        
        # 添加基本信息
        features_df['symbol'] = symbol
        features_df['as_of_date'] = as_of_date
        
        # 确保只返回 as_of_date 之前的数据
        features_df = features_df[features_df['trade_date'] <= as_of_date]
        
        logger.info(f"特征获取完成: {len(features_df)} 条记录")
        return features_df
    
    def get_features_batch(
        self,
        symbols: List[str],
        start: str,
        end: str,
        as_of_date: str = None,
        indicators: List[str] = None,
        adjust_type: str = 'qfq'
    ) -> pd.DataFrame:
        """
        批量获取多个股票的特征
        
        Args:
            symbols: 股票代码列表
            start: 开始日期
            end: 结束日期
            as_of_date: 查询基准日期
            indicators: 需要的指标列表
            adjust_type: 复权类型
        
        Returns:
            合并后的特征 DataFrame
        """
        all_features = []
        
        for symbol in symbols:
            features = self.get_features(symbol, start, end, as_of_date, indicators, adjust_type)
            if not features.empty:
                all_features.append(features)
        
        if all_features:
            return pd.concat(all_features).reset_index(drop=True)
        return pd.DataFrame()
    
    def get_universe(
        self,
        as_of_date: str,
        exclude_st: bool = True,
        exclude_delisted: bool = True
    ) -> List[str]:
        """
        获取指定日期的股票池（防前视偏差）
        
        Args:
            as_of_date: 查询日期
            exclude_st: 是否排除 ST 股票
            exclude_delisted: 是否排除已退市股票
        
        Returns:
            股票代码列表
        """
        stocks_df = self.storage.get_stock_list()
        
        if stocks_df.empty:
            return []
        
        # 过滤上市日期
        stocks_df = stocks_df[stocks_df['list_date'] <= as_of_date]
        
        # 过滤退市日期
        if exclude_delisted:
            stocks_df = stocks_df[(stocks_df['delist_date'].isna()) | 
                                (stocks_df['delist_date'] > as_of_date)]
        
        # 检查 ST 状态（需要查询 symbol_mapping）
        if exclude_st:
            st_events = self.storage.get_symbol_events(event_type='st', end_date=as_of_date)
            st_codes = set(st_events['new_code'].tolist()) | set(st_events['old_code'].tolist())
            stocks_df = stocks_df[~stocks_df['code'].isin(st_codes)]
        
        return stocks_df['code'].tolist()
    
    def _apply_adjustment(self, df: pd.DataFrame, adjust_type: str) -> pd.DataFrame:
        """
        应用复权
        
        Args:
            df: 原始行情数据
            adjust_type: 复权类型
        
        Returns:
            复权后的数据
        """
        result = df.copy()
        
        # 筛选指定复权类型的数据
        if adjust_type in ['qfq', 'hfq']:
            adjusted = df[df['adjust_type'] == adjust_type]
            if not adjusted.empty:
                result = adjusted
            else:
                # 如果没有预计算的复权数据，使用 adjust_factor 计算
                if 'adjust_factor' in df.columns:
                    factor = df['adjust_factor'].fillna(1)
                    result['open'] = df['open'] * factor
                    result['high'] = df['high'] * factor
                    result['low'] = df['low'] * factor
                    result['close'] = df['close'] * factor
        
        return result
    
    def _calculate_features(self, df: pd.DataFrame, indicators: List[str]) -> pd.DataFrame:
        """
        计算指定的技术指标
        
        Args:
            df: 行情数据
            indicators: 指标列表
        
        Returns:
            包含指标的 DataFrame
        """
        result = df.copy()
        
        # 根据请求的指标计算
        if 'MA' in indicators:
            result = TechnicalIndicator.calculate_ma(result)
        
        if 'MACD' in indicators:
            result = TechnicalIndicator.calculate_macd(result)
        
        if 'KDJ' in indicators:
            result = TechnicalIndicator.calculate_kdj(result)
        
        if 'BOLL' in indicators:
            result = TechnicalIndicator.calculate_boll(result)
        
        if 'RSI' in indicators:
            result = TechnicalIndicator.calculate_rsi(result)
        
        if 'ATR' in indicators:
            result = TechnicalIndicator.calculate_atr(result)
        
        if 'VOLUME' in indicators:
            result = TechnicalIndicator.calculate_volume_ma(result)
        
        return result
    
    def get_feature_names(self, indicators: List[str] = None) -> List[str]:
        """
        获取指定指标的特征名称列表
        
        Args:
            indicators: 指标类型列表
        
        Returns:
            特征名称列表
        """
        if indicators is None:
            indicators = ["MA", "MACD", "RSI"]
        
        feature_names = []
        
        if 'MA' in indicators:
            feature_names.extend(['MA5', 'MA10', 'MA20', 'MA60', 'MA120', 'MA250'])
        
        if 'MACD' in indicators:
            feature_names.extend(['MACD', 'MACD_SIGNAL', 'MACD_HIST'])
        
        if 'KDJ' in indicators:
            feature_names.extend(['KDJ_K', 'KDJ_D', 'KDJ_J'])
        
        if 'BOLL' in indicators:
            feature_names.extend(['BOLL_MID', 'BOLL_UPPER', 'BOLL_LOWER'])
        
        if 'RSI' in indicators:
            feature_names.extend(['RSI'])
        
        if 'ATR' in indicators:
            feature_names.extend(['ATR'])
        
        if 'VOLUME' in indicators:
            feature_names.extend(['VOL_MA5', 'VOL_MA10', 'VOL_MA20'])
        
        return feature_names


# 测试函数
if __name__ == '__main__':
    service = FeatureService()
    
    if service.connect():
        print("✅ 特征服务连接成功")
        
        # 测试获取单个股票特征
        print("\n🔍 测试获取单个股票特征...")
        features = service.get_features(
            symbol='sh.600000',
            start='2024-01-01',
            end='2024-01-31',
            as_of_date='2024-01-31',
            indicators=['MA', 'MACD', 'RSI']
        )
        print(f"获取到 {len(features)} 条特征数据")
        if not features.empty:
            print("特征列:", list(features.columns))
            print("\n前3行数据:")
            print(features[['trade_date', 'close', 'MA5', 'MA10', 'MACD', 'RSI']].head(3))
        
        # 测试获取股票池
        print("\n🔍 测试获取股票池...")
        universe = service.get_universe('2024-01-15')
        print(f"股票池大小: {len(universe)}")
        print(f"前10只股票: {universe[:10]}")
        
        service.disconnect()
        print("\n✅ 特征服务测试完成")
    else:
        print("❌ 连接失败")
