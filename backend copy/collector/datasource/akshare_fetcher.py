#!/usr/bin/env python3
"""
Akshare 数据源模块 v2.0
免费获取全量股票列表、行情数据、实时数据
支持超时设置和重试机制

功能：
1. 获取全量股票列表
2. 获取日线数据（前复权）
3. 获取实时行情
4. 获取市场快照
5. 交易日期日历
"""
import os
import sys
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict

# 添加项目路径
sys.path.append(os.path.dirname(__file__))
from utils.logger import setup_logger


class AkshareFetcher:
    """Akshare 数据获取器 v2.0"""
    
    def __init__(self, timeout=60, max_retries=3):
        """
        初始化 Akshare 数据获取器
        
        Args:
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.logger = setup_logger()
        self._akshare = None
        self._timeout = timeout
        self._max_retries = max_retries
        self._init_akshare()
    
    def _init_akshare(self):
        """初始化 akshare"""
        try:
            import akshare as ak
            self._akshare = ak
            
            # 设置请求头，模拟浏览器（兼容不同 akshare 版本）
            try:
                if hasattr(self._akshare, 'session'):
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    }
                    self._akshare.session.headers.update(headers)
            except Exception:
                pass
            
            self.logger.info('✅ Akshare 初始化成功')
        except ImportError:
            self.logger.error('❌ Akshare 未安装，请运行: pip install akshare')
            raise
        except Exception as e:
            self.logger.warning(f'⚠️ Akshare 设置警告: {str(e)}')
    
    def _retry_request(self, func, max_retries=None, delay=3):
        """
        带重试机制的请求
        
        Args:
            func: 要执行的函数
            max_retries: 最大重试次数
            delay: 重试间隔（秒）
            
        Returns:
            函数执行结果，或 None 如果失败
        """
        if max_retries is None:
            max_retries = self._max_retries
        
        last_error = None
        for attempt in range(max_retries):
            try:
                result = func()
                if result is not None:
                    return result
                last_error = "返回 None"
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f'⚠️ 请求失败 (尝试 {attempt+1}/{max_retries}): {last_error}')
            
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 30)  # 指数退避，最大30秒
        
        self.logger.error(f'❌ 请求最终失败: {last_error}')
        return None
    
    def _is_valid_result(self, df):
        """检查结果是否有效"""
        return df is not None and not df.empty
    
    def fetch_stock_list(self):
        """
        获取全量 A 股股票列表
        
        Returns:
            DataFrame: 包含 ts_code, name, market, market_name 列
        """
        self.logger.info('🔍 正在从 Akshare 获取股票列表...')
        
        # 尝试多个 akshare 接口作为备选（兼容新版本）
        methods = [
            ('stock_info_a_code_name', lambda: self._akshare.stock_info_a_code_name()),
            ('stock_sh_a_spot_em', lambda: self._akshare.stock_sh_a_spot_em()),
            ('stock_sz_a_spot_em', lambda: self._akshare.stock_sz_a_spot_em()),
            ('stock_bj_a_spot_em', lambda: self._akshare.stock_bj_a_spot_em()),
        ]
        
        df = None
        last_error = None
        
        for method_name, method_func in methods:
            try:
                self.logger.info(f'   尝试接口: {method_name}')
                df = self._retry_request(method_func, max_retries=3, delay=3)
                
                if df is not None and not df.empty:
                    self.logger.info(f'✅ 接口 {method_name} 成功')
                    break
                else:
                    last_error = f'接口 {method_name} 返回为空'
            except Exception as e:
                last_error = f'接口 {method_name} 失败: {str(e)}'
                self.logger.warning(f'⚠️ {last_error}')
        
        if df is None or df.empty:
            self.logger.error(f'❌ 所有接口都失败: {last_error}')
            return None
        
        self.logger.info(f'✅ 原始数据: {len(df)} 只股票')
        
        # 处理数据，转换为与现有格式兼容的结构
        result_df = self._process_stock_list(df)
        
        self.logger.info(f'✅ 筛选后: {len(result_df)} 只股票')
        return result_df
    
    def _process_stock_list(self, df):
        """
        处理股票列表，转换为与现有格式兼容的结构
        
        Args:
            df: akshare 返回的原始数据
            
        Returns:
            DataFrame: 标准化后的股票列表
        """
        result = []
        
        # 支持多种列名格式（不同接口返回不同的列名）
        code_columns = ['code', '代码', '股票代码', 'ts_code', 'symbol']
        name_columns = ['name', '名称', '股票名称', 'stock_name', 'name_abbr']
        
        def get_value(row, columns):
            for col in columns:
                if col in df.columns:
                    return row.get(col, '')
            return ''
        
        for _, row in df.iterrows():
            code = get_value(row, code_columns)
            name = get_value(row, name_columns)
            
            # 如果代码已经带后缀（如 000001.SZ），直接使用
            if isinstance(code, str) and '.' in code:
                ts_code = code
                code_only = code.split('.')[0]
                _, market, market_name = self._classify_stock(code_only, name)
            else:
                # 根据股票代码前缀判断市场
                ts_code, market, market_name = self._classify_stock(str(code), name)
            
            if ts_code:
                result.append({
                    'ts_code': ts_code,
                    'name': name,
                    'market': market,
                    'market_name': market_name
                })
        
        result_df = pd.DataFrame(result)
        
        # 去重（按 ts_code）
        if not result_df.empty:
            result_df = result_df.drop_duplicates(subset=['ts_code'])
        
        return result_df
    
    def _classify_stock(self, code, name):
        """
        分类股票市场
        
        Args:
            code: 股票代码
            name: 股票名称
            
        Returns:
            tuple: (ts_code, market, market_name)
        """
        # 去掉可能存在的后缀
        code = str(code).replace('.SH', '').replace('.SZ', '')
        
        # 判断市场
        prefix = code[:3]
        
        # 上海主板: 600/601/602/603/604/605 开头
        if prefix in ['600', '601', '602', '603', '604', '605']:
            ts_code = f'{code}.SH'
            market = 'sh_main'
            market_name = '上海主板'
        # 上海科创板: 688/689 开头
        elif prefix in ['688', '689']:
            ts_code = f'{code}.SH'
            market = 'sh_star'
            market_name = '科创板'
        # 深圳主板: 000/001/002/003 开头
        elif prefix in ['000', '001', '002', '003']:
            ts_code = f'{code}.SZ'
            market = 'sz_main'
            market_name = '深圳主板'
        # 深圳创业板: 300/301 开头
        elif prefix in ['300', '301']:
            ts_code = f'{code}.SZ'
            market = 'sz_cyb'
            market_name = '创业板'
        # 北交所/精选层: 400/800/830/880 开头
        elif prefix in ['400', '800', '830', '880']:
            ts_code = f'{code}.BJ'
            market = 'bj'
            market_name = '北交所'
        else:
            # 其他默认归为深圳主板
            ts_code = f'{code}.SZ'
            market = 'sz_main'
            market_name = '深圳主板'
        
        return ts_code, market, market_name
    
    def fetch_daily_data(self, ts_code, start_date=None, end_date=None):
        """
        获取单只股票的日线数据
        
        Args:
            ts_code: 股票代码，如 '000001.SZ'
            start_date: 开始日期，格式 'YYYYMMDD'
            end_date: 结束日期，格式 'YYYYMMDD'
            
        Returns:
            DataFrame: 日线数据
        """
        try:
            # 处理 ts_code，提取纯数字代码
            code = ts_code.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
            
            # 转换日期格式（YYYYMMDD -> YYYY-MM-DD）
            def format_date(d):
                if d and len(d) == 8:
                    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
                return d
            
            formatted_start = format_date(start_date)
            formatted_end = format_date(end_date)
            
            self.logger.info(f"📊 获取 {ts_code} 数据 ({formatted_start or '最早'} 到 {formatted_end or '最新'})")
            
            # 尝试多个 akshare 接口
            methods = [
                # 方法1: stock_zh_a_daily（推荐）
                lambda: self._akshare.stock_zh_a_daily(
                    symbol=code,
                    start_date=formatted_start,
                    end_date=formatted_end,
                    adjust="qfq"
                ),
                # 方法2: stock_zh_a_hist
                lambda: self._akshare.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq"
                ),
            ]
            
            df = None
            last_error = None
            
            for i, method_func in enumerate(methods):
                try:
                    self.logger.info(f"   尝试接口 {i+1}...")
                    result = self._retry_request(method_func, max_retries=2, delay=2)
                    if result is not None and not result.empty:
                        df = result
                        self.logger.info(f"✅ 接口 {i+1} 成功获取 {len(df)} 条数据")
                        break
                except Exception as e:
                    last_error = str(e)
                    self.logger.warning(f"⚠️ 接口 {i+1} 失败: {last_error}")
            
            if df is None or df.empty:
                self.logger.error(f"❌ 所有接口都失败: {last_error}")
                return None
            
            # 处理数据格式，与现有格式兼容
            df = self._process_daily_data(df, ts_code)
            
            return df
            
        except Exception as e:
            self.logger.error(f"❌ 获取 {ts_code} 日线数据失败: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    def _process_daily_data(self, df, ts_code):
        """
        处理日线数据，转换为与现有格式兼容的结构
        
        Args:
            df: akshare 返回的原始数据
            ts_code: 股票代码
            
        Returns:
            DataFrame: 标准化后的日线数据
        """
        # 支持多种列名格式
        column_mapping = {
            # 日期相关
            '日期': 'trade_date',
            'date': 'trade_date',
            'trade_date': 'trade_date',
            '时间': 'trade_date',
            # 开盘价
            '开盘': 'open',
            'open': 'open',
            '开盘价': 'open',
            # 收盘价
            '收盘': 'close',
            'close': 'close',
            '收盘价': 'close',
            '最新价': 'close',
            # 最高价
            '最高': 'high',
            'high': 'high',
            '最高价': 'high',
            # 最低价
            '最低': 'low',
            'low': 'low',
            '最低价': 'low',
            # 成交量
            '成交量': 'vol',
            'volume': 'vol',
            'vol': 'vol',
            '成交': 'vol',
            # 成交额
            '成交额': 'amount',
            'amount': 'amount',
            '金额': 'amount',
            # 其他
            '换手率': 'turnover_rate',
            '涨跌幅': 'pct_chg',
            'change': 'change',
            '涨跌额': 'change',
            '昨日收盘': 'pre_close',
            'pre_close': 'pre_close',
            '市盈率': 'pe',
            'pe': 'pe',
        }
        
        # 首先确保索引唯一（避免后续操作失败）
        if not df.index.is_unique:
            self.logger.warning("检测到重复索引，重新设置索引")
            df = df.reset_index(drop=True)
        
        # 处理索引中的日期（stock_zh_a_daily 接口会把日期放在索引中）
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index(drop=True)
            df['trade_date'] = df.index
        elif 'trade_date' not in df.columns and '日期' not in df.columns and 'date' not in df.columns:
            # 如果没有日期列，尝试重置索引
            df = df.reset_index(drop=True)
        
        # 重命名列
        df = df.rename(columns=column_mapping)
        
        # 再次确保索引唯一
        if not df.index.is_unique:
            df = df.reset_index(drop=True)
        
        # 转换日期格式
        if 'trade_date' in df.columns:
            try:
                # 处理 trade_date 列（确保是 Series）
                if isinstance(df['trade_date'], pd.Series):
                    # 先检查是否已经是字符串格式
                    if len(df) > 0:
                        sample_val = df['trade_date'].iloc[0]
                        if isinstance(sample_val, str) and len(str(sample_val)) == 10 and '-' in str(sample_val):
                            # 已经是 YYYY-MM-DD 格式
                            df['trade_date'] = df['trade_date'].str.replace('-', '')
                        else:
                            df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce').dt.strftime('%Y%m%d')
                    else:
                        df['trade_date'] = ''
                else:
                    # 处理非 Series 情况（可能是多重索引展开）
                    self.logger.warning("trade_date 不是 Series，尝试转换")
                    df['trade_date'] = pd.Series(df['trade_date'].values.flatten()[:len(df)])
                    df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce').dt.strftime('%Y%m%d')
            except Exception as e:
                self.logger.warning(f"日期转换失败，尝试直接转换为字符串: {e}")
                try:
                    df['trade_date'] = df['trade_date'].apply(lambda x: str(x).replace('-', '')[:8] if pd.notna(x) else '')
                except Exception as e2:
                    self.logger.error(f"日期转换最终失败: {e2}")
        
        # 添加股票代码列
        df['ts_code'] = ts_code
        
        # 确保必要的列存在
        required_columns = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount']
        for col in required_columns:
            if col not in df.columns:
                df[col] = None
        
        # 计算涨跌额和涨跌幅
        if 'pre_close' in df.columns and 'close' in df.columns:
            df['change'] = df['close'] - df['pre_close']
            df['pct_chg'] = (df['change'] / df['pre_close']) * 100
        
        # 只保留需要的列
        result_columns = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 
                         'vol', 'amount', 'change', 'pct_chg', 'pre_close', 
                         'turnover_rate', 'pe']
        
        # 过滤出存在的列
        existing_columns = [col for col in result_columns if col in df.columns]
        
        # 确保索引唯一后再进行列选择
        if not df.index.is_unique:
            df = df.reset_index(drop=True)
        
        df = df[existing_columns].copy()
        
        # 过滤空日期（使用索引方式避免重复索引问题）
        if 'trade_date' in df.columns:
            valid_mask = df['trade_date'].notna() & (df['trade_date'] != '')
            df = df.loc[valid_mask.values]
        
        return df


    def fetch_realtime_data(self, ts_code: str) -> Optional[pd.DataFrame]:
        """
        获取单只股票实时行情数据
        
        Args:
            ts_code: 股票代码，如 '000001.SZ'
            
        Returns:
            实时行情数据
        """
        try:
            code = ts_code.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
            
            self.logger.info(f'📊 获取实时行情: {ts_code}')
            
            # 方法1: stock_zh_a_spot_em（东方财富实时行情）
            result = self._retry_request(
                lambda: self._akshare.stock_zh_a_spot_em()
            )
            
            if result is not None and not result.empty:
                # 筛选这只股票
                if '代码' in result.columns:
                    stock_data = result[result['代码'] == code]
                    if not stock_data.empty:
                        self.logger.info(f'✅ 获取实时数据成功')
                        return stock_data
            
            self.logger.warning(f'⚠️ 未找到 {ts_code} 的实时数据')
            return None
            
        except Exception as e:
            self.logger.error(f'❌ 获取实时数据失败: {str(e)}')
            return None
    
    def fetch_market_snapshot(self) -> Optional[pd.DataFrame]:
        """
        获取A股市场快照（所有股票实时行情）
        
        Returns:
            市场快照数据
        """
        try:
            self.logger.info('📊 获取A股市场快照...')
            
            result = self._retry_request(
                lambda: self._akshare.stock_zh_a_spot_em()
            )
            
            if self._is_valid_result(result):
                self.logger.info(f'✅ 获取市场快照成功，共 {len(result)} 只股票')
                return result
            
            return None
            
        except Exception as e:
            self.logger.error(f'❌ 获取市场快照失败: {str(e)}')
            return None
    
    def fetch_trade_calendar(self, start_date: str, end_date: str) -> Optional[List[str]]:
        """
        获取交易日历
        
        Args:
            start_date: 开始日期，格式 'YYYYMMDD'
            end_date: 结束日期，格式 'YYYYMMDD'
            
        Returns:
            交易日列表
        """
        try:
            self.logger.info(f'📅 获取交易日历: {start_date} 到 {end_date}')
            
            # 使用新接口 tool_trade_date_hist_sina（替代已移除的 trade_cal）
            result = self._retry_request(
                lambda: self._akshare.tool_trade_date_hist_sina()
            )
            
            if self._is_valid_result(result):
                # 转换日期格式并过滤范围
                result['trade_date'] = pd.to_datetime(result['trade_date'], errors='coerce')
                
                # 转换输入日期
                start_dt = pd.to_datetime(start_date, format='%Y%m%d')
                end_dt = pd.to_datetime(end_date, format='%Y%m%d')
                
                # 过滤日期范围
                filtered = result[(result['trade_date'] >= start_dt) & (result['trade_date'] <= end_dt)]
                
                # 转换为 YYYYMMDD 格式
                trade_days = filtered['trade_date'].dt.strftime('%Y%m%d').tolist()
                
                self.logger.info(f'✅ 获取交易日历成功，共 {len(trade_days)} 个交易日')
                return trade_days
            
            return None
            
        except Exception as e:
            self.logger.error(f'❌ 获取交易日历失败: {str(e)}')
            return None
    
    def fetch_bulk_daily_data(self, ts_codes: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """
        批量获取多只股票的日线数据
        
        Args:
            ts_codes: 股票代码列表
            start_date: 开始日期，格式 'YYYYMMDD'
            end_date: 结束日期，格式 'YYYYMMDD'
            
        Returns:
            股票代码到数据的字典
        """
        results = {}
        
        self.logger.info(f'📦 批量获取 {len(ts_codes)} 只股票数据...')
        
        for i, code in enumerate(ts_codes):
            if (i + 1) % 100 == 0:
                self.logger.info(f'   进度: {i+1}/{len(ts_codes)}')
            
            df = self.fetch_daily_data(code, start_date, end_date)
            if df is not None and not df.empty:
                results[code] = df
        
        self.logger.info(f'✅ 批量获取完成，成功 {len(results)}/{len(ts_codes)} 只')
        return results


def update_stock_list():
    """
    更新股票列表并保存
    """
    logger = setup_logger()
    logger.info('=' * 70)
    logger.info('使用 Akshare 更新股票列表')
    logger.info('=' * 70)
    
    try:
        # 创建 fetcher 实例
        fetcher = AkshareFetcher()
        
        # 获取股票列表
        stock_list = fetcher.fetch_stock_list()
        
        if stock_list is None or stock_list.empty:
            logger.error('❌ 获取股票列表失败')
            return False
        
        # 保存文件 - 使用绝对路径
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'metadata')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, 'stock_list.parquet')
        
        stock_list.to_parquet(output_path, index=False)
        
        logger.info(f'✅ 股票列表已保存: {output_path}')
        logger.info(f'   共 {len(stock_list)} 只股票')
        
        # 显示统计信息
        logger.info('\n📊 市场分布:')
        market_counts = stock_list['market_name'].value_counts()
        for market, count in market_counts.items():
            logger.info(f'   {market}: {count} 只')
        
        return True
        
    except Exception as e:
        logger.error(f'❌ 更新股票列表失败: {str(e)}')
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == '__main__':
    update_stock_list()
