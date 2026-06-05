#!/usr/bin/env python3
"""
从日线数据合成周线/月线数据
并与 Tushare 接口数据对比验证
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Tuple

from collector.storage.postgresql_storage import PostgreSQLStorage
from collector.datasource.tushare import TushareDataSource
from utils.logger import setup_logger

logger = setup_logger('cycle_synthesis')


class CycleSynthesizer:
    """周线/月线合成器"""
    
    def __init__(self):
        self.storage = PostgreSQLStorage({})
        self.storage.connect()
        self.tushare = TushareDataSource()
        
    def get_daily_data(self, code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取日线数据"""
        return self.storage.get_quotes(code, cycle='daily', start_date=start_date, end_date=end_date)
    
    def synthesize_weekly(self, daily_df: pd.DataFrame) -> pd.DataFrame:
        """从日线数据合成周线"""
        if daily_df.empty:
            return pd.DataFrame()
        
        df = daily_df.copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        # 按周分组（周一到周五，确保周线结束于周五）
        df['week'] = df['trade_date'].dt.isocalendar().week
        df['year'] = df['trade_date'].dt.year
        
        # 周线合成
        weekly = df.groupby(['year', 'week']).agg(
            trade_date=('trade_date', 'last'),
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
            pre_close=('pre_close', 'first'),
            volume=('volume', 'sum'),
            amount=('amount', 'sum')
        ).reset_index(drop=True)
        
        # 检查是否为周末（周五）- 必须在日期格式转换之前进行
        weekly['is_weekend'] = weekly['trade_date'].dt.dayofweek == 4  # 4 = Friday
        
        # 格式化日期
        weekly['trade_date'] = weekly['trade_date'].dt.strftime('%Y-%m-%d')
        weekly['cycle'] = '1w'
        
        logger.debug(f"周线合成完成，共{len(weekly)}条，周末标记数: {weekly['is_weekend'].sum()}")
        return weekly
    
    def synthesize_monthly(self, daily_df: pd.DataFrame) -> pd.DataFrame:
        """从日线数据合成月线"""
        if daily_df.empty:
            return pd.DataFrame()
        
        df = daily_df.copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        # 按月分组
        df['month'] = df['trade_date'].dt.month
        df['year'] = df['trade_date'].dt.year
        
        # 月线合成
        monthly = df.groupby(['year', 'month']).agg(
            trade_date=('trade_date', 'last'),
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
            pre_close=('pre_close', 'first'),
            volume=('volume', 'sum'),
            amount=('amount', 'sum')
        ).reset_index(drop=True)
        
        # 检查是否为月末
        # 获取每月最后一个交易日是否等于该月自然月末
        monthly['is_month_end'] = monthly['trade_date'].dt.is_month_end
        
        # 格式化日期
        monthly['trade_date'] = monthly['trade_date'].dt.strftime('%Y-%m-%d')
        monthly['cycle'] = '1m'
        
        logger.debug(f"月线合成完成，共{len(monthly)}条，月末标记数: {monthly['is_month_end'].sum()}")
        return monthly
    
    def get_tushare_weekly(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """从Tushare获取周线数据"""
        if not self.tushare.connected:
            self.tushare.connect()
        return self.tushare.get_kline(code, cycle='weekly', start_date=start_date, end_date=end_date)
    
    def get_tushare_monthly(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """从Tushare获取月线数据"""
        if not self.tushare.connected:
            self.tushare.connect()
        return self.tushare.get_kline(code, cycle='monthly', start_date=start_date, end_date=end_date)
    
    def compare_data(self, syn_df: pd.DataFrame, ts_df: pd.DataFrame, cycle: str) -> Dict:
        """对比合成数据与Tushare数据"""
        if syn_df.empty or ts_df.empty:
            return {'match': False, 'reason': '数据为空'}
        
        # 对齐日期格式
        syn_df['trade_date'] = pd.to_datetime(syn_df['trade_date']).dt.date
        ts_df['trade_date'] = pd.to_datetime(ts_df['trade_date']).dt.date
        
        # 找到共同日期
        common_dates = set(syn_df['trade_date']) & set(ts_df['trade_date'])
        if not common_dates:
            return {'match': False, 'reason': '无共同日期'}
        
        # 筛选共同日期的数据
        syn_filtered = syn_df[syn_df['trade_date'].isin(common_dates)].sort_values('trade_date')
        ts_filtered = ts_df[ts_df['trade_date'].isin(common_dates)].sort_values('trade_date')
        
        # 对比关键字段（价格允许0.5%误差）
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            syn_vals = syn_filtered[col].values.astype(float)
            ts_vals = ts_filtered[col].values.astype(float)
            diff = np.abs(syn_vals - ts_vals) / np.maximum(ts_vals, 0.01)
            if np.any(diff > 0.005):  # 0.5%误差
                return {'match': False, 'reason': f'{col}字段差异超过0.5%'}
        
        return {
            'match': True,
            'common_dates': len(common_dates),
            'syn_rows': len(syn_df),
            'ts_rows': len(ts_df)
        }
    
    def save_synthesized(self, code: str, df: pd.DataFrame, cycle: str):
        """保存合成数据到数据库"""
        if df.empty:
            return 0
        
        df['code'] = code
        df['adjust_type'] = 'qfq'
        df = df[['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close', 
                 'pre_close', 'volume', 'amount', 'adjust_type']]
        
        return self.storage.save_quotes(df)


def main():
    parser = argparse.ArgumentParser(description='周线/月线数据合成与验证')
    parser.add_argument('--test', action='store_true', help='测试模式：对比Tushare数据')
    parser.add_argument('--codes', nargs='+', help='指定股票代码列表')
    args = parser.parse_args()
    
    synthesizer = CycleSynthesizer()
    
    # 选择测试股票
    if args.codes:
        test_codes = args.codes
    else:
        # 随机选10只股票
        test_codes = ['600000', '600519', '000001', '000002', '300750', 
                      '601318', '600036', '000858', '002594', '600030']
    
    logger.info(f"测试股票列表: {test_codes}")
    
    if args.test:
        # 测试模式：对比合成数据与Tushare数据
        logger.info("========== 周线对比测试 ==========")
        for code in test_codes[:3]:  # 只测试3只，避免频繁调用受限接口
            try:
                daily = synthesizer.get_daily_data(code, '2026-01-01', '2026-06-04')
                syn_weekly = synthesizer.synthesize_weekly(daily)
                
                ts_weekly = synthesizer.get_tushare_weekly(code, '2026-01-01', '2026-06-04')
                
                result = synthesizer.compare_data(syn_weekly, ts_weekly, 'weekly')
                status = "✅" if result['match'] else "❌"
                logger.info(f"{status} {code} - {result}")
                
                if not result['match']:
                    logger.debug(f"合成周线:\n{syn_weekly[['trade_date', 'open', 'high', 'low', 'close']]}")
                    logger.debug(f"Tushare周线:\n{ts_weekly[['trade_date', 'open', 'high', 'low', 'close']]}")
                
            except Exception as e:
                logger.error(f"{code} 周线测试失败: {e}")
        
        logger.info("\n========== 月线对比测试 ==========")
        for code in test_codes[:1]:  # 只测试1只月线
            try:
                daily = synthesizer.get_daily_data(code, '2026-01-01', '2026-06-04')
                syn_monthly = synthesizer.synthesize_monthly(daily)
                
                ts_monthly = synthesizer.get_tushare_monthly(code, '2026-01-01', '2026-06-04')
                
                result = synthesizer.compare_data(syn_monthly, ts_monthly, 'monthly')
                status = "✅" if result['match'] else "❌"
                logger.info(f"{status} {code} - {result}")
                
            except Exception as e:
                logger.error(f"{code} 月线测试失败: {e}")
        
        synthesizer.tushare.disconnect()
    
    else:
        # 生产模式：合成并保存所有股票的周线/月线
        logger.info("========== 开始合成周线数据 ==========")
        for code in test_codes:
            try:
                daily = synthesizer.get_daily_data(code)
                if daily.empty:
                    logger.warning(f"{code} 无日线数据")
                    continue
                
                weekly = synthesizer.synthesize_weekly(daily)
                cnt = synthesizer.save_synthesized(code, weekly, '1w')
                logger.info(f"{code} 周线合成完成: {len(weekly)} 条记录")
                
            except Exception as e:
                logger.error(f"{code} 周线合成失败: {e}")
        
        logger.info("\n========== 开始合成月线数据 ==========")
        for code in test_codes:
            try:
                daily = synthesizer.get_daily_data(code)
                if daily.empty:
                    continue
                
                monthly = synthesizer.synthesize_monthly(daily)
                cnt = synthesizer.save_synthesized(code, monthly, '1m')
                logger.info(f"{code} 月线合成完成: {len(monthly)} 条记录")
                
            except Exception as e:
                logger.error(f"{code} 月线合成失败: {e}")
    
    synthesizer.storage.disconnect()


if __name__ == '__main__':
    main()
