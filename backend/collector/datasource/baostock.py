#!/usr/bin/env python3
"""
Baostock 数据源实现
特点：
- 免费、稳定、无需Token
- 支持日线和分钟线数据
- 支持复权处理（前复权、后复权）
- 数据质量高、字段完整
- 支持交易日历查询
"""
import baostock as bs
import pandas as pd
import numpy as np
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from .base import BaseDataSource
from utils.logger import setup_logger
from utils.stock_code_utils import normalize_code

logger = setup_logger('baostock_datasource')

# Baostock 请求超时时间（秒）
BAOSTOCK_REQUEST_TIMEOUT = 30

# 全局线程池：限制最大工作线程数，防止超时后孤儿线程堆积导致资源泄漏
_baostock_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="baostock_worker")

def _run_baostock_with_timeout(func, args=(), kwargs={}, timeout=BAOSTOCK_REQUEST_TIMEOUT):
    """带超时的 Baostock 函数执行（使用线程池替代原生 Thread，避免孤儿线程泄漏）"""
    future = _baostock_executor.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        raise TimeoutError(f"Baostock 请求超时（超过 {timeout} 秒）")

# Baostock 频率限制配置
BAOSTOCK_RATE_LIMIT = {
    'min_interval': 0.15,
    'max_requests_per_minute': 20,
    'burst_size': 3,
}

class RateLimiter:
    """令牌桶算法实现的频率限制器"""
    def __init__(self, rate: float = 1.0, burst: int = 3):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self.lock = threading.Lock()

    def acquire(self, timeout: float = None) -> bool:
        start_time = time.time()
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                self.last_update = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                wait_time = (1 - self.tokens) / self.rate
                if timeout is not None:
                    elapsed_total = time.time() - start_time
                    if elapsed_total + wait_time > timeout:
                        return False
            time.sleep(wait_time)

class BaostockDataSource(BaseDataSource):
    """Baostock 数据源实现（带频率限制与全链路超时保护）"""
    
    _CYCLE_MAP = {
        'daily': 'd', 'min5': '5', 'min15': '15', 'min30': '30', 'min60': '60'
    }
    _ADJUST_FLAG = '2'  # 前复权（Baostock: 1=后复权, 2=前复权, 3=不复权）

    def __init__(self, rate_limit_config: Dict = None):
        self.connected = False
        self._reconnect_count = 0
        self._max_reconnect = 3
        self._last_request_time = 0
        self._keep_alive_interval = 55
        
        config = rate_limit_config or BAOSTOCK_RATE_LIMIT
        rate = config['max_requests_per_minute'] / 60.0
        self.rate_limiter = RateLimiter(rate=rate, burst=config['burst_size'])
        self._min_interval = config['min_interval']
        self._request_count = 0
        self._last_minute_requests = []
        
        # 🟢 新增：复权因子内存缓存，避免重复全量查询
        self._adj_cache = {}  # 格式: {(code, date): adj_factor}

    def _wait_for_rate_limit(self):
        self.rate_limiter.acquire(timeout=60)
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()
        self._request_count += 1
        
        now = time.time()
        self._last_minute_requests.append(now)
        self._last_minute_requests = [t for t in self._last_minute_requests if now - t < 60]

    def _fetch_all_rows(self, rs, max_iterations=100000) -> list:
        """辅助方法：安全地获取结果集所有行，消除重复的 while 循环"""
        # 🟢 增强防御：防止传入 None
        if rs is None:
            return []
            
        data_list = []
        iteration_count = 0
        while (rs.error_code == '0') and rs.next():
            iteration_count += 1
            if iteration_count > max_iterations:
                logger.warning(f"⚠️ 获取数据时迭代次数超过限制({max_iterations})，强制退出")
                break
            data_list.append(rs.get_row_data())
        return data_list

    def _keep_alive(self) -> bool:
        """保持连接活跃，防止超时断开。🟢 修复：返回是否保活成功"""
        try:
            def do_keep_alive():
                return bs.query_history_k_data_plus(
                    code='sh.600000', fields='date,close',
                    start_date='2025-01-01', end_date='2025-01-02',
                    frequency='d', adjustflag='3'
                )
            rs = _run_baostock_with_timeout(do_keep_alive, timeout=10)
            if rs is None or rs.error_code != '0':
                logger.warning("⚠️ Baostock 保活失败")
                return False
            return True
        except Exception as e:
            logger.warning(f"⚠️ Baostock 保活异常: {str(e)}")
            return False

    def _ensure_connected(self) -> bool:
        """确保已连接，如未连接则自动重连，并保持连接活跃"""
        current_time = time.time()
        if self.connected:
            time_since_last_request = current_time - self._last_request_time
            if time_since_last_request >= self._keep_alive_interval:
                logger.debug(f"执行连接保活（距上次请求 {int(time_since_last_request)} 秒）")
                # 🟢 修复：根据保活结果更新状态，杜绝假性恢复
                if not self._keep_alive():
                    self.connected = False  
            return self.connected  # 返回真实的连接状态
            
        for i in range(self._max_reconnect):
            try:
                # 🟢 修复：重试之间加入延迟，给 Baostock 服务器恢复时间
                if i > 0:
                    delay = min(5 * i, 15)  # 第1次重试等5s，第2次等10s，第3次等15s
                    logger.debug(f"⏸ 等待 {delay}s 后重试连接...")
                    time.sleep(delay)
                    
                def do_login(): return bs.login()
                lg = _run_baostock_with_timeout(do_login, timeout=15)
                if lg is None:
                    logger.warning(f"⚠️ Baostock login 返回 None（第 {i+1}/{self._max_reconnect} 次）")
                    continue
                if lg.error_code == '0':
                    self.connected = True
                    self._last_request_time = time.time()
                    logger.info(f"✅ Baostock 重连成功（第 {i+1} 次）")
                    return True
            except Exception as e:
                logger.warning(f"⚠️ Baostock 重连失败（第 {i+1}/{self._max_reconnect} 次）: {str(e)}")
        return False

    def connect(self, retry: bool = True) -> bool:
        """连接 Baostock，支持重试

        Args:
            retry: 是否在首次失败后自动重试（默认 True，最多 _max_reconnect 次）
        """
        try:
            def do_login(): return bs.login()
            lg = _run_baostock_with_timeout(do_login, timeout=15)
            if lg is not None and lg.error_code == '0':
                self.connected = True
                self._last_request_time = time.time()
                return True
            if not retry:
                return False
            # 首次失败后调用 _ensure_connected 的重试逻辑
            return self._ensure_connected()
        except Exception:
            if not retry:
                return False
            return self._ensure_connected()

    def disconnect(self) -> bool:
        try:
            bs.logout()
            self.connected = False
            return True
        except Exception:
            return False

    def _get_latest_trade_date(self) -> str:
        """获取最近一个交易日的日期（降级返回今日）"""
        today_str = datetime.now().strftime('%Y-%m-%d')
        try:
            today = datetime.now()
            start = (today - timedelta(days=365)).strftime('%Y-%m-%d')
            end = today_str
            self._wait_for_rate_limit()
            
            def do_query(): return bs.query_trade_dates(start_date=start, end_date=end)
            rs = _run_baostock_with_timeout(do_query, timeout=15)
            
            if rs is None or rs.error_code != '0':
                return today_str
            df = rs.get_data()
            if df.empty:
                return today_str
            open_days = df[df['isOpen'].isin(['1', 1])]['calendarDate']
            if open_days.empty:
                return today_str
            return open_days.iloc[-1]
        except Exception:
            return today_str

    def get_stock_list(self) -> pd.DataFrame:
        if not self.connected:
            raise RuntimeError("未连接到Baostock")
        try:
            latest_date = self._get_latest_trade_date()
            self._wait_for_rate_limit()
            
            def do_query(): return bs.query_all_stock(day=latest_date)
            rs = _run_baostock_with_timeout(do_query, timeout=15)
            
            if rs is None:
                raise RuntimeError("获取股票列表返回 None")
            if rs.error_code != '0':
                raise RuntimeError(f"获取股票列表失败: {rs.error_msg}")
                
            self._last_request_time = time.time()
            df = rs.get_data()
            if df.empty:
                raise RuntimeError("获取股票列表为空")
                
            result = pd.DataFrame({
                'code': df['code'].apply(lambda x: normalize_code(x) or x),
                'name': df['code_name'],
                'exchange': df['code'].apply(lambda x: 'SH' if x.startswith('sh') else 'SZ'),
                'industry': '', 'list_date': '', 'delist_date': ''
            })
            result = result[result['code'].str.match(r'^\d{6}$')]
            result = result[~((result['code'].str.startswith('000')) & (result['exchange'] == 'SH'))]
            result = result[~result['code'].str.startswith('399')]
            return result
        except Exception as e:
            raise RuntimeError(f"获取股票列表异常: {str(e)}")

    def get_adj_factor(self, trade_date: str) -> pd.DataFrame:
        """获取指定日期所有股票的复权因子（🟢 优化：增加内存缓存，大幅减少重复查询）"""
        if not self._ensure_connected():
            raise RuntimeError("未连接到 Baostock")
        bs_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
        try:
            stocks = self.get_stock_list()
        except Exception:
            return pd.DataFrame()
            
        if stocks.empty:
            return pd.DataFrame()
            
        results = []
        total = len(stocks)
        for idx, row in stocks.iterrows():
            code_raw = row.get('code', '')
            bs_code = self._normalize_code(code_raw)
            if not bs_code:
                continue
                
            try:
                self._wait_for_rate_limit()
                
                # 1. 必须查询当天的交易状态（停牌状态无法缓存）
                def do_query_kline():
                    return bs.query_history_k_data_plus(
                        bs_code, "date,code,tradestatus,isST",
                        start_date=bs_date, end_date=bs_date, frequency="d", adjustflag="3"
                    )
                rs = _run_baostock_with_timeout(do_query_kline, timeout=15)
                self._last_request_time = time.time()
                
                if rs is None or rs.error_code != '0':
                    continue
                    
                is_trading = False
                rows = self._fetch_all_rows(rs)
                for r in rows:
                    if len(r) >= 3 and r[2] == '1':
                        is_trading = True
                        break
                        
                if not is_trading:
                    continue

                # 2. 获取复权因子（优先使用缓存）
                cache_key = (code_raw, bs_date)
                adj_val = self._adj_cache.get(cache_key)
                
                if adj_val is None:
                    def do_query_adj1():
                        return bs.query_adjust_factor(code=bs_code, start_date=bs_date, end_date=bs_date)
                    rs2 = _run_baostock_with_timeout(do_query_adj1, timeout=15)
                    
                    if rs2 is not None and rs2.error_code == '0':
                        rows2 = self._fetch_all_rows(rs2)
                        for row_data in rows2:
                            # row_data = [code, dividOperateDate, foreAdjustFactor, backAdjustFactor, parValue]
                            if len(row_data) >= 3 and row_data[2] and row_data[2] != '':
                                adj_val = float(row_data[2])
                                break
                                
                    if adj_val is None:
                        def do_query_adj2():
                            return bs.query_adjust_factor(code=bs_code, start_date="2000-01-01", end_date=bs_date)
                        rs3 = _run_baostock_with_timeout(do_query_adj2, timeout=15)
                        if rs3 is not None and rs3.error_code == '0':
                            rows3 = self._fetch_all_rows(rs3)
                            # 倒序查找最新的一条
                            for row_data in reversed(rows3):
                                if len(row_data) >= 3 and row_data[2] and row_data[2] != '':
                                    adj_val = float(row_data[2])
                                    break
                                    
                    if adj_val is not None:
                        self._adj_cache[cache_key] = adj_val  # 写入缓存

                if adj_val is not None:
                    results.append({'code': code_raw, 'trade_date': trade_date, 'adj_factor': adj_val})
            except Exception as e:
                logger.debug(f"获取 {code_raw} 复权因子失败: {e}")
                continue
                
            if (idx + 1) % 200 == 0:
                logger.info(f"  📊 复权因子进度: {idx+1}/{total}，已获取 {len(results)} 条 (缓存命中:{len(self._adj_cache)})")
                
        return pd.DataFrame(results) if results else pd.DataFrame()

    def get_adj_factor_history(
        self,
        code: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """获取单只股票历史复权因子（变更日数据）

        基于 Baostock query_adjust_factor，返回 foreAdjustFactor（前复权因子）。
        数据仅包含复权因子发生变更的日期，调用方需自行前向填充到每日。

        Args:
            code: 股票代码（如 600000 或 sh.600000）
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            DataFrame: columns = [code, trade_date, adj_factor]
        """
        if not self._ensure_connected():
            raise RuntimeError("未连接到 Baostock")

        bs_code = self._normalize_code(code)
        if not bs_code:
            raise ValueError(f"无效的股票代码: {code}")

        self._wait_for_rate_limit()

        def do_query():
            return bs.query_adjust_factor(code=bs_code, start_date=start_date, end_date=end_date)

        try:
            rs = _run_baostock_with_timeout(do_query, timeout=15)
            if rs is None or rs.error_code != '0':
                return pd.DataFrame()

            rows = self._fetch_all_rows(rs)
            results = []
            for row_data in rows:
                # row_data = [code, dividOperateDate, foreAdjustFactor, backAdjustFactor, parValue]
                if len(row_data) >= 3 and row_data[1] and row_data[2]:
                    results.append({
                        'code': normalize_code(row_data[0]) or code,
                        'trade_date': str(row_data[1])[:10],
                        'adj_factor': float(row_data[2])
                    })

            df = pd.DataFrame(results)
            if not df.empty:
                df = df.sort_values('trade_date').reset_index(drop=True)
            return df

        except Exception as e:
            logger.warning(f"  {code}: Baostock 复权因子历史查询失败: {e}")
            return pd.DataFrame()

    def get_stock_basic(self) -> pd.DataFrame:
        if not self._ensure_connected():
            raise RuntimeError("未连接到 Baostock")
        try:
            self._wait_for_rate_limit()
            def do_query(): return bs.query_stock_industry()
            rs = _run_baostock_with_timeout(do_query, timeout=15)
            
            if rs is None:
                raise RuntimeError("获取行业分类返回 None")
            if rs.error_code != '0':
                raise RuntimeError(f"获取行业分类失败: {rs.error_msg}")
                
            self._last_request_time = time.time()
            data_list = self._fetch_all_rows(rs)
            if not data_list:
                return pd.DataFrame()
                
            df = pd.DataFrame(data_list, columns=rs.fields)
            df = df.rename(columns={'code_name': 'name'})
            df['code'] = df['code'].apply(lambda x: normalize_code(x) or x)
            return df[['code', 'name', 'industry']].dropna(subset=['code'])
        except Exception as e:
            raise RuntimeError(f"获取股票基本资料异常: {str(e)}")

    def get_daily_basic(self, trade_date: str, **kwargs) -> pd.DataFrame:
        if not self._ensure_connected():
            raise RuntimeError("未连接到 Baostock")
        bs_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}" if len(trade_date) == 8 else trade_date
        
        try:
            stocks = self.get_stock_list()
            if stocks.empty: return pd.DataFrame()
        except Exception:
            return pd.DataFrame()
            
        results = []
        total = len(stocks)
        failed = 0
        for idx, row in stocks.iterrows():
            plain_code = str(row.get('code', '')).strip()
            bs_code = self._normalize_code(plain_code)
            if not bs_code:
                continue
                
            try:
                self._wait_for_rate_limit()
                def do_query():
                    return bs.query_history_k_data_plus(
                        bs_code, "date,code,peTTM,pbMRQ,turn,tradestatus,volume",
                        start_date=bs_date, end_date=bs_date, frequency="d", adjustflag="3"
                    )
                rs = _run_baostock_with_timeout(do_query, timeout=15)
                self._last_request_time = time.time()
                
                if rs is None or rs.error_code != '0':
                    failed += 1
                    continue
                    
                rows = self._fetch_all_rows(rs)
                for r in rows:
                    if len(r) < 7: continue
                    if r[5] != '1': continue
                    results.append({
                        'code': plain_code, 'trade_date': bs_date,
                        'pe': float(r[2]) if r[2] else None, 'pe_ttm': float(r[2]) if r[2] else None,
                        'pb': float(r[3]) if r[3] else None, 'turnover_rate': float(r[4]) if r[4] else None,
                        'volume_ratio': None, 'total_mv': None, 'circ_mv': None,
                    })
            except Exception:
                failed += 1
                continue
                
            if (idx + 1) % 500 == 0:
                logger.info(f"  daily_basic 进度: {idx+1}/{total} (获取:{len(results)} 失败:{failed})")
                
        return pd.DataFrame(results) if results else pd.DataFrame()

    def get_daily_basic_for_code(self, code: str, trade_date: str) -> pd.DataFrame:
        """查询单只股票在指定日期的 pe_ttm（用于 pe_ttm 缺口补全）"""
        bs_code = self._normalize_code(code)
        if not bs_code:
            return pd.DataFrame()

        try:
            self._wait_for_rate_limit()
            def do_query():
                return bs.query_history_k_data_plus(
                    bs_code, "date,code,peTTM",
                    start_date=trade_date, end_date=trade_date,
                    frequency="d", adjustflag="3"
                )
            rs = _run_baostock_with_timeout(do_query, timeout=15)
            self._last_request_time = time.time()

            if rs is None or rs.error_code != '0':
                return pd.DataFrame()

            rows = self._fetch_all_rows(rs)
            if rows and len(rows[0]) >= 3 and rows[0][2]:
                return pd.DataFrame([{
                    'code': code,
                    'trade_date': trade_date,
                    'pe_ttm': float(rows[0][2]),
                }])
            return pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    def get_kline(self, code: str, cycle: str = 'daily', start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        if cycle not in self._CYCLE_MAP:
            raise ValueError(f"不支持的周期: {cycle}")
        start = start_date or '2000-01-01'
        end = end_date or self._get_today_str()
        bs_code = self._normalize_code(code)
        if not bs_code:
            raise ValueError(f"不支持的股票代码: {code} (可能为北交所代码)")
            
        for attempt in range(3):
            try:
                if not self._ensure_connected():
                    raise RuntimeError("无法连接到Baostock")
                self._wait_for_rate_limit()
                
                # 日线/周线/月线支持 preclose；分钟线字段不含 preclose
                if cycle in ['min5', 'min15', 'min30', 'min60']:
                    fields = "date,time,code,open,high,low,close,volume,amount"
                else:
                    fields = "date,code,open,high,low,close,preclose,volume,amount"
                    
                def do_request():
                    return bs.query_history_k_data_plus(
                        code=bs_code, fields=fields, start_date=start, end_date=end,
                        frequency=self._CYCLE_MAP[cycle], adjustflag=self._ADJUST_FLAG
                    )
                rs = _run_baostock_with_timeout(do_request)
                
                if rs is None:
                    self.connected = False
                    raise RuntimeError("Baostock 查询返回 None")
                if rs.error_code != '0':
                    error_msg = rs.error_msg or ''
                    if '用户未登录' in error_msg or rs.error_code == '1000':
                        self.connected = False
                        continue
                    raise RuntimeError(f"获取K线数据失败: {error_msg}")
                    
                self._last_request_time = time.time()
                data_list = self._fetch_all_rows(rs)
                result = pd.DataFrame(data_list, columns=rs.fields)
                if result.empty:
                    return pd.DataFrame()
                    
                result = result.reset_index(drop=True)
                if cycle in ['min5', 'min15', 'min30', 'min60']:
                    trade_dates = [f"{d} {t[8:10]}:{t[10:12]}:{t[12:14]}" for d, t in zip(result['date'], result['time'])]
                else:
                    trade_dates = list(result['date'])
                    
                # 分钟线无 preclose 字段，统一填充 NaN
                pre_close = pd.to_numeric(result.get('preclose'), errors='coerce') if 'preclose' in result.columns else pd.Series([np.nan] * len(result))
                result = pd.DataFrame({
                    'code': code, 'trade_date': trade_dates,
                    'open': pd.to_numeric(result['open'], errors='coerce'),
                    'high': pd.to_numeric(result['high'], errors='coerce'),
                    'low': pd.to_numeric(result['low'], errors='coerce'),
                    'close': pd.to_numeric(result['close'], errors='coerce'),
                    'pre_close': pre_close,
                    'volume': pd.to_numeric(result['volume'], errors='coerce'),
                    'amount': pd.to_numeric(result['amount'], errors='coerce'),
                    'cycle': cycle
                })
                return result.sort_values('trade_date').reset_index(drop=True)
                
            except TimeoutError as e:
                if attempt < 2:
                    self.connected = False
                    continue
                raise RuntimeError(f"获取 {code} K线数据超时，已重试3次")
            except Exception as e:
                error_msg = str(e)
                if attempt < 2 and ('用户未登录' in error_msg or '连接' in error_msg.lower() or '超时' in error_msg or 'None' in error_msg):
                    self.connected = False
                    continue
                raise RuntimeError(f"获取K线数据异常: {error_msg}")
        raise RuntimeError(f"获取 {code} K线数据失败，已重试3次")

    def get_trade_calendar(self, start_date: Optional[str] = None, end_date: Optional[str] = None, exchange: str = 'SH') -> pd.DataFrame:
        if not self.connected:
            raise RuntimeError("未连接到Baostock")
        start = start_date or '2000-01-01'
        end = end_date or self._get_today_str()
        try:
            self._wait_for_rate_limit()
            def do_query(): return bs.query_trade_dates(start_date=start, end_date=end)
            rs = _run_baostock_with_timeout(do_query, timeout=15)
            
            if rs is None:
                raise RuntimeError("获取交易日历返回 None")
            if rs.error_code != '0':
                raise RuntimeError(f"获取交易日历失败: {rs.error_msg}")
                
            df = rs.get_data()
            if df.empty: return pd.DataFrame()
            
            date_col = 'calendarDate' if 'calendarDate' in df.columns else ('date' if 'date' in df.columns else df.columns[0])
            trade_day_col = 'isTradeDay' if 'isTradeDay' in df.columns else ('is_open' if 'is_open' in df.columns else df.columns[1])
            
            return pd.DataFrame({
                'cal_date': df[date_col],
                'is_open': df[trade_day_col].apply(lambda x: 1 if str(x) == '1' else 0),
                'exchange': exchange
            })
        except Exception as e:
            return self._generate_simple_calendar(start, end, exchange)

    def get_next_trade_date(self, last_date: str, exchange: str = 'SH') -> Optional[str]:
        end_date = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=30)).strftime('%Y-%m-%d')
        try:
            calendar = self.get_trade_calendar(start_date=last_date, end_date=end_date)
            if calendar.empty: return None
            mask = (calendar['cal_date'] > last_date) & (calendar['is_open'] == 1)
            next_dates = calendar[mask]['cal_date'].sort_values()
            if next_dates.empty: return None
            next_date = next_dates.iloc[0]
            return next_date if next_date <= self._get_today_str() else None
        except Exception:
            return self._simple_next_trade_date(last_date)

    def _simple_next_trade_date(self, last_date: str) -> Optional[str]:
        try:
            last_dt = datetime.strptime(last_date, '%Y-%m-%d')
            today = datetime.now()
            for i in range(1, 15):
                next_dt = last_dt + timedelta(days=i)
                if next_dt.weekday() < 5 and next_dt.date() <= today.date():
                    return next_dt.strftime('%Y-%m-%d')
            return None
        except Exception:
            return None

    def _normalize_code(self, code: str) -> Optional[str]:
        """🟢 优化：统一转小写，兼容 SZ.000001 等大写格式，拦截北交所"""
        code = str(code).strip().lower()
        if code.startswith('sh.') or code.startswith('sz.'):
            return code
        if len(code) == 6:
            if code.startswith('6'):
                return f'sh.{code}'
            elif code.startswith('8') or code.startswith('920'):
                return None  # Baostock 不支持北交所
            else:
                return f'sz.{code}'
        return code

    def _get_today_str(self) -> str:
        return datetime.now().strftime('%Y-%m-%d')

    @property
    def name(self) -> str: return "Baostock"

    @property
    def requires_token(self) -> bool: return False

    def _generate_simple_calendar(self, start_date: str, end_date: str, exchange: str) -> pd.DataFrame:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            dates = []
            current_dt = start_dt
            while current_dt <= end_dt:
                date_str = current_dt.strftime('%Y-%m-%d')
                is_open = 1 if current_dt.weekday() < 5 else 0 
                dates.append({'cal_date': date_str, 'is_open': is_open, 'exchange': exchange})
                current_dt += timedelta(days=1)
            return pd.DataFrame(dates)
        except Exception:
            return pd.DataFrame()

    @property
    def supported_cycles(self) -> List[str]:
        return list(self._CYCLE_MAP.keys())