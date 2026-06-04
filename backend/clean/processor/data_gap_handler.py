"""
数据补全模块 - 检测和修复缺失数据
支持 Akshare 和 Tushare 两种数据源
"""
import os
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Tuple, Dict

logger = logging.getLogger(__name__)

# 尝试导入 Akshare
HAS_AKSHARE = False
try:
    from akshare_fetcher import AkshareFetcher
    HAS_AKSHARE = True
except ImportError:
    pass


class DataGapDetector:
    """
    数据缺口检测器
    检测本地数据与实际交易日之间的差异
    """
    
    @staticmethod
    def get_trading_dates(start_date: str, end_date: str) -> List[str]:
        """
        生成交易日历（排除周末）
        注意：实际交易日需要结合交易所日历，这里简化处理
        
        Args:
            start_date: 开始日期 'YYYYMMDD'
            end_date: 结束日期 'YYYYMMDD'
            
        Returns:
            交易日列表
        """
        start = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')
        
        trading_dates = []
        current = start
        
        while current <= end:
            # 排除周末（周一=0，周六=5，周日=6）
            if current.weekday() < 5:
                trading_dates.append(current.strftime('%Y%m%d'))
            current += timedelta(days=1)
        
        return trading_dates
    
    @staticmethod
    def detect_gaps(local_df: pd.DataFrame, expected_dates: List[str]) -> List[str]:
        """
        检测本地数据中缺失的日期
        
        Args:
            local_df: 本地已有数据
            expected_dates: 期望的所有交易日
            
        Returns:
            缺失的日期列表
        """
        if local_df is None or local_df.empty:
            return expected_dates
        
        # 转换trade_date为字符串格式
        if 'trade_date' in local_df.columns:
            local_dates = set(local_df['trade_date'].dt.strftime('%Y%m%d').tolist())
            missing = [d for d in expected_dates if d not in local_dates]
            return missing
        
        return expected_dates
    
    @staticmethod
    def is_data_outdated(local_df: pd.DataFrame, reference_date: str = None) -> Tuple[bool, str]:
        """
        检查数据是否为最新
        
        Args:
            local_df: 本地数据
            reference_date: 参考日期（YYYYMMDD），默认今天
            
        Returns:
            (是否过期, 最新日期)
        """
        if local_df is None or local_df.empty:
            return True, None
        
        if 'trade_date' not in local_df.columns:
            return True, None
        
        # 获取本地最新日期
        latest_local = local_df['trade_date'].max()
        
        # 确保 latest_local 是 datetime 类型
        if isinstance(latest_local, str):
            latest_local = datetime.strptime(latest_local, '%Y%m%d')
        
        latest_str = latest_local.strftime('%Y%m%d')
        
        # 如果没有指定参考日期，使用今天
        if reference_date is None:
            reference_date = datetime.now().strftime('%Y%m%d')
        
        # 判断是否需要更新（本地最新日期 < 参考日期）
        is_outdated = latest_str < reference_date
        
        return is_outdated, latest_str


class DataGapFiller:
    """
    数据缺口填充器
    增量补全缺失的数据
    自动适配 Akshare 和 Tushare 数据源
    """
    
    def __init__(self, fetcher=None, storage=None):
        self.storage = storage
        self._akshare_fetcher = None
        self._tushare_fetcher = None
        
        # 初始化数据获取器
        if HAS_AKSHARE:
            try:
                self._akshare_fetcher = AkshareFetcher()
                logger.info('✅ DataGapFiller 已启用 Akshare 数据源')
            except Exception as e:
                logger.warning(f'⚠️ Akshare 初始化失败: {e}')
        
        # 如果传入了 Tushare fetcher，保存它
        if fetcher is not None:
            self._tushare_fetcher = fetcher
    
    def _get_fetcher(self):
        """获取当前可用的数据获取器"""
        if self._akshare_fetcher is not None:
            return self._akshare_fetcher
        elif self._tushare_fetcher is not None:
            return self._tushare_fetcher
        else:
            raise RuntimeError('没有可用的数据获取器')
    
    def fetch_daily_data(self, stock_code: str, start_date: str, end_date: str):
        """
        获取日线数据，自动适配不同的数据源
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            DataFrame 或 None
        """
        fetcher = self._get_fetcher()
        
        # 适配 Akshare 的接口
        if isinstance(fetcher, AkshareFetcher):
            return fetcher.fetch_daily_data(stock_code, start_date, end_date)
        
        # 适配 Tushare 的接口
        return fetcher.fetch_daily_data(stock_code, start_date, end_date)
    
    def fill_gaps(self, stock_code: str, freq: str = 'daily', force_fetch: bool = False) -> Dict:
        """
        填充单个股票的数据缺口
        
        Args:
            stock_code: 股票代码
            freq: 数据频率
            force_fetch: 是否强制获取（修复模式），True时忽略交易时段限制
            
        Returns:
            补全结果统计
        """
        result = {
            'stock_code': stock_code,
            'status': 'success',
            'gaps_found': 0,
            'gaps_filled': 0,
            'latest_date': None,
            'errors': []
        }
        
        try:
            # 1. 加载本地数据
            local_df = self.storage.load_price_data(stock_code, freq)
            
            # 2. 确定需要补全的时间范围
            today = datetime.now()
            start_date = '20200101'  # 默认起始
            need_fetch = True  # 是否需要调用API
            
            if local_df is not None and not local_df.empty:
                # 如果有本地数据，从最新日期的下一天开始
                latest_date = local_df['trade_date'].max()
                
                # 确保 latest_date 是 datetime 类型
                if isinstance(latest_date, str):
                    latest_date = datetime.strptime(latest_date, '%Y%m%d')
                
                # 检查本地数据是否已是今天
                today_str = today.strftime('%Y%m%d')
                yesterday_str = (today - timedelta(days=1)).strftime('%Y%m%d')
                latest_str = latest_date.strftime('%Y%m%d')
                
                # 检查是否是交易时段
                weekday = today.weekday()
                current_time = today.time()
                morning_start = timedelta(hours=9, minutes=30)
                afternoon_end = timedelta(hours=15, minutes=0)
                current_timedelta = timedelta(hours=current_time.hour, minutes=current_time.minute)
                is_trading_time = weekday < 5 and (morning_start <= current_timedelta <= afternoon_end)
                
                # 判断是否需要调用API
                if latest_str >= today_str:
                    # 本地数据已是今天，不需要调用API
                    need_fetch = False
                    logger.info(f'{stock_code} 本地数据已是最新 ({latest_str})，跳过API调用')
                    result['status'] = 'success'
                    result['gaps_filled'] = 0
                    return result
                
                if latest_str == yesterday_str and not is_trading_time and not force_fetch:
                    # 本地数据最新到昨天，且当前不在交易时段，跳过API调用
                    # 这种情况说明：昨天是最后一个交易日，今天还没开盘
                    need_fetch = False
                    logger.info(f'{stock_code} 本地数据最新到昨天 ({latest_str})，当前非交易时段，跳过API调用')
                    result['status'] = 'success'
                    result['gaps_filled'] = 0
                    return result
                
                if not is_trading_time and not force_fetch:
                    # 当前不在交易时段，跳过所有API调用（修复模式除外）
                    need_fetch = False
                    logger.info(f'{stock_code} 本地数据最新到 {latest_str}，当前非交易时段，跳过API调用')
                    result['status'] = 'success'
                    result['gaps_filled'] = 0
                    return result
                
                start_date = (latest_date + timedelta(days=1)).strftime('%Y%m%d')
                result['latest_date'] = latest_str
                
                if force_fetch:
                    logger.info(f'{stock_code} 本地数据最新到 {latest_str}，修复模式：强制更新到 {today_str}')
                else:
                    logger.info(f'{stock_code} 本地数据最新到 {latest_str}，需要补全到 {today_str}')
            
            # 3. 如果起始日期在今天之前，则需要补全
            if need_fetch and start_date <= today.strftime('%Y%m%d'):
                # 再次检查：不在交易时段时跳过API调用（修复模式除外）
                weekday = today.weekday()
                current_time = today.time()
                morning_start = timedelta(hours=9, minutes=30)
                afternoon_end = timedelta(hours=15, minutes=0)
                current_timedelta = timedelta(hours=current_time.hour, minutes=current_time.minute)
                is_trading_time = weekday < 5 and (morning_start <= current_timedelta <= afternoon_end)
                
                if not is_trading_time and not force_fetch:
                    logger.info(f'{stock_code} 当前非交易时段，跳过API调用')
                    result['status'] = 'success'
                    result['gaps_filled'] = 0
                    return result
                
                # 获取需要补全的日期范围
                expected_dates = DataGapDetector.get_trading_dates(start_date, today.strftime('%Y%m%d'))
                result['gaps_found'] = len(expected_dates)
                
                if expected_dates:
                    logger.info(f'{stock_code} 需要补全 {len(expected_dates)} 个交易日数据')
                    
                    # 4. 分批获取数据（每次最多365天）
                    for batch_start, batch_end in self._batch_dates(expected_dates, batch_size=365):
                        try:
                            # 使用统一的 fetch_daily_data 方法
                            batch_df = self.fetch_daily_data(
                                stock_code,
                                batch_start,
                                batch_end
                            )
                            
                            if batch_df is not None and not batch_df.empty:
                                # 5. 合并数据
                                merged_df = self._merge_data(local_df, batch_df)
                                local_df = merged_df
                                result['gaps_filled'] += len(batch_df)
                                
                        except Exception as e:
                            logger.error(f'补全失败 {stock_code}: {str(e)}')
                            result['errors'].append(str(e))
                    
                    # 6. 保存更新后的数据
                    if result['gaps_filled'] > 0:
                        self.storage.save_price_data(local_df, stock_code, freq)
                        logger.info(f'{stock_code} 补全完成，新增 {result["gaps_filled"]} 条数据')
                else:
                    logger.info(f'{stock_code} 数据已是最新，无需补全')
            else:
                logger.info(f'{stock_code} 数据已是最新')
                
        except Exception as e:
            result['status'] = 'error'
            result['errors'].append(str(e))
            logger.error(f'补全处理失败 {stock_code}: {str(e)}')
        
        return result
    
    def _batch_dates(self, dates: List[str], batch_size: int = 365) -> List[Tuple[str, str]]:
        """将日期列表分批"""
        batches = []
        for i in range(0, len(dates), batch_size):
            batch = dates[i:i+batch_size]
            if batch:
                batches.append((batch[0], batch[-1]))
        return batches
    
    def _merge_data(self, existing_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
        """
        合并新旧数据，去重
        
        Args:
            existing_df: 已有数据
            new_df: 新数据
            
        Returns:
            合并后的数据
        """
        if existing_df is None or existing_df.empty:
            return new_df
        
        if new_df is None or new_df.empty:
            return existing_df
        
        # 转换日期格式
        if 'trade_date' in existing_df.columns and 'trade_date' in new_df.columns:
            existing_df['trade_date'] = pd.to_datetime(existing_df['trade_date'])
            new_df['trade_date'] = pd.to_datetime(new_df['trade_date'])
        
        # 合并并去重
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        
        # 按日期去重，保留新数据
        combined = combined.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
        
        # 排序
        combined = combined.sort_values('trade_date')
        
        return combined
    
    def check_all_stocks(self, stock_codes: List[str], freq: str = 'daily') -> List[Dict]:
        """
        检查所有股票的数据状态
        
        Args:
            stock_codes: 股票代码列表
            freq: 数据频率
            
        Returns:
            各股票的数据状态列表
        """
        results = []
        
        for code in stock_codes:
            try:
                local_df = self.storage.load_price_data(code, freq)
                is_outdated, latest_date = DataGapDetector.is_data_outdated(local_df)
                
                # 检测缺失日期
                missing_dates = []
                if is_outdated and local_df is not None:
                    today = datetime.now().strftime('%Y%m%d')
                    expected = DataGapDetector.get_trading_dates('20200101', today)
                    missing_dates = DataGapDetector.detect_gaps(local_df, expected)
                
                results.append({
                    'stock_code': code,
                    'has_local_data': local_df is not None and not local_df.empty,
                    'latest_date': latest_date,
                    'is_outdated': is_outdated,
                    'missing_count': len(missing_dates)
                })
                
            except Exception as e:
                logger.error(f'检查 {code} 失败: {str(e)}')
                results.append({
                    'stock_code': code,
                    'has_local_data': False,
                    'latest_date': None,
                    'is_outdated': True,
                    'missing_count': 0,
                    'error': str(e)
                })
        
        return results
