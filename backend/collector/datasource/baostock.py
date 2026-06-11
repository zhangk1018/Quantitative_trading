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
import time
import threading
import queue
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from .base import BaseDataSource
from utils.logger import setup_logger
from utils.stock_code_utils import normalize_code

logger = setup_logger('baostock_datasource')

# Baostock 请求超时时间（秒）
BAOSTOCK_REQUEST_TIMEOUT = 30

# Baostock 频率限制配置
# 官方建议：每分钟请求 ≤ 10 次（实时数据），≤ 20 次（历史数据）
# 日K线建议：0.1 秒以上/次
BAOSTOCK_RATE_LIMIT = {
    'min_interval': 0.15,       # 最小请求间隔（秒），建议 0.1-0.2
    'max_requests_per_minute': 20,  # 每分钟最大请求数
    'burst_size': 3,            # 允许的突发请求数
}


class RateLimiter:
    """令牌桶算法实现的频率限制器"""
    
    def __init__(self, rate: float = 1.0, burst: int = 3):
        """
        Args:
            rate: 每秒产生的令牌数（即允许的平均请求速率）
            burst: 令牌桶容量（允许的突发请求数）
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self.lock = threading.Lock()
    
    def acquire(self, timeout: float = None) -> bool:
        """
        获取一个令牌，如果没有可用令牌则等待
        
        Args:
            timeout: 最大等待时间（秒），None 表示无限等待
            
        Returns:
            是否成功获取令牌
        """
        start_time = time.time()
        
        while True:
            with self.lock:
                now = time.time()
                # 计算新增的令牌
                elapsed = now - self.last_update
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                self.last_update = now
                
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                
                # 计算需要等待的时间
                wait_time = (1 - self.tokens) / self.rate
            
            # 检查是否超时
            if timeout is not None:
                elapsed_total = time.time() - start_time
                if elapsed_total + wait_time > timeout:
                    return False
            
            time.sleep(wait_time)
    
    def get_wait_time(self) -> float:
        """获取需要等待的时间（不实际等待）"""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= 1:
                return 0
            return (1 - self.tokens) / self.rate


def _run_baostock_with_timeout(func, args=(), kwargs={}, timeout=BAOSTOCK_REQUEST_TIMEOUT):
    """带超时的 Baostock 函数执行"""
    result_queue = queue.Queue()
    thread = None
    
    def worker():
        try:
            result = func(*args, **kwargs)
            result_queue.put(('success', result))
        except Exception as e:
            result_queue.put(('error', e))
    
    try:
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        
        result = result_queue.get(timeout=timeout)
        if result[0] == 'success':
            return result[1]
        else:
            raise result[1]
    except queue.Empty:
        raise TimeoutError(f"Baostock 请求超时（超过 {timeout} 秒）")
    finally:
        # 清理队列
        try:
            while not result_queue.empty():
                result_queue.get_nowait()
        except:
            pass


class BaostockDataSource(BaseDataSource):
    """Baostock 数据源实现（带频率限制）"""
    
    # Baostock周期映射
    _CYCLE_MAP = {
        'daily': 'd',
        'min5': '5',
        'min15': '15',
        'min30': '30',
        'min60': '60'
    }
    
    # Baostock复权类型
    _ADJUST_FLAG = '3'  # 前复权（推荐）
    
    def __init__(self, rate_limit_config: Dict = None):
        self.connected = False
        self._reconnect_count = 0
        self._max_reconnect = 3
        self._last_request_time = 0
        self._keep_alive_interval = 55  # 默认55秒，短于Baostock超时时间
        self._connection_timeout = 25   # 连接超时时间
        
        # 频率限制器
        config = rate_limit_config or BAOSTOCK_RATE_LIMIT
        # 计算令牌产生速率：每分钟 max_requests，即每秒 max_requests/60
        rate = config['max_requests_per_minute'] / 60.0
        self.rate_limiter = RateLimiter(rate=rate, burst=config['burst_size'])
        self._min_interval = config['min_interval']
        
        # 请求统计
        self._request_count = 0
        self._last_minute_requests = []
    
    def _wait_for_rate_limit(self):
        """等待频率限制"""
        # 使用令牌桶算法控制频率
        self.rate_limiter.acquire(timeout=60)
        
        # 额外确保最小间隔
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        
        self._last_request_time = time.time()
        self._request_count += 1
        
        # 记录每分钟的请求次数（用于监控）
        now = time.time()
        self._last_minute_requests.append(now)
        # 只保留最近60秒的记录
        self._last_minute_requests = [t for t in self._last_minute_requests if now - t < 60]
        
        if len(self._last_minute_requests) >= 15:
            logger.debug(f"最近60秒请求次数: {len(self._last_minute_requests)}")

    def _ensure_connected(self) -> bool:
        """确保已连接，如未连接则自动重连，并保持连接活跃"""
        current_time = time.time()
        
        if self.connected:
            time_since_last_request = current_time - self._last_request_time
            if time_since_last_request >= self._keep_alive_interval:
                logger.debug(f"执行连接保活（距上次请求 {int(time_since_last_request)} 秒）")
                self._keep_alive()
            return True

        for i in range(self._max_reconnect):
            try:
                lg = bs.login()
                if lg.error_code == '0':
                    self.connected = True
                    self._last_request_time = time.time()
                    logger.info(f"✅ Baostock 重连成功（第 {i+1} 次）")
                    return True
            except Exception as e:
                logger.warning(f"⚠️ Baostock 重连失败（第 {i+1}/{self._max_reconnect} 次）: {str(e)}")

        return False
    
    def _keep_alive(self):
        """保持连接活跃，防止超时断开"""
        try:
            rs = bs.query_history_k_data_plus(
                code='sh.600000',
                fields='date,close',
                start_date='2025-01-01',
                end_date='2025-01-02',
                frequency='d',
                adjustflag='3'
            )
            if rs.error_code == '0':
                logger.debug("✅ Baostock 连接保活成功")
                self.connected = True
            else:
                logger.warning(f"⚠️ Baostock 保活失败: {rs.error_msg}")
                self.connected = False
        except Exception as e:
            logger.warning(f"⚠️ Baostock 保活异常: {str(e)}")
            self.connected = False

    def _check_and_reconnect(self):
        """检查连接状态，如断开则自动重连"""
        try:
            # 尝试执行一个简单查询来检查连接状态
            rs = bs.query_history_k_data_plus(
                code='sh.600000',
                fields='date,close',
                start_date='2025-01-01',
                end_date='2025-01-02',
                frequency='d',
                adjustflag='3'
            )
            if rs.error_code == '1000' or '用户未登录' in str(rs.error_msg):
                logger.warning("⚠️ Baostock 连接已断开，尝试重连...")
                self.connected = False
                self._ensure_connected()
        except Exception:
            self._ensure_connected()

    def connect(self) -> bool:
        """建立连接"""
        try:
            lg = bs.login()
            if lg.error_code == '0':
                self.connected = True
                return True
            return False
        except Exception:
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            bs.logout()
            self.connected = False
            return True
        except Exception:
            return False
    
    def _get_latest_trade_date(self) -> str:
        """获取最近一个交易日的日期"""
        try:
            today = datetime.now()
            # 查询一年内的交易日
            start = (today - timedelta(days=365)).strftime('%Y-%m-%d')
            end = today.strftime('%Y-%m-%d')
            self._wait_for_rate_limit()
            rs = bs.query_trade_dates(start_date=start, end_date=end)
            if rs.error_code != '0':
                # 降级到默认值
                return '2026-06-05'
            df = rs.get_data()
            if df.empty:
                return '2026-06-05'
            # 取最近一个交易日
            open_days = df[df['isOpen'].isin(['1', 1])]['calendarDate']
            if open_days.empty:
                return '2026-06-05'
            return open_days.iloc[-1]
        except Exception:
            return '2026-06-05'

    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表"""
        if not self.connected:
            raise RuntimeError("未连接到Baostock")

        try:
            # 先获取最近交易日
            latest_date = self._get_latest_trade_date()
            rs = bs.query_all_stock(day=latest_date)
            
            if rs.error_code != '0':
                raise RuntimeError(f"获取股票列表失败: {rs.error_msg}")
            
            self._last_request_time = time.time()
            
            df = rs.get_data()
            
            if df.empty:
                raise RuntimeError("获取股票列表为空")
            
            # 处理数据（统一为纯数字格式）
            result = pd.DataFrame({
                'code': df['code'].apply(lambda x: normalize_code(x) or x),
                'name': df['code_name'],
                'exchange': df['code'].apply(lambda x: 'SH' if x.startswith('sh') else 'SZ'),
                'industry': '',
                'list_date': '',
                'delist_date': ''
            })
            
            # 过滤有效股票（纯6位数字代码）
            result = result[result['code'].str.match(r'^\d{6}$')]
            # 排除指数代码：sh.000xxx（上证指数）、sz.399xxx（深证系列指数）
            # 注意：sz.000xxx 是深市主板股票（如平安银行 000001），不是指数
            # 纯数字格式下：排除 000 开头且 exchange=SH 的（上证指数），排除 399 开头的（深证系列指数）
            result = result[~((result['code'].str.startswith('000')) & (result['exchange'] == 'SH'))]
            result = result[~result['code'].str.startswith('399')]
            
            return result
            
        except Exception as e:
            raise RuntimeError(f"获取股票列表异常: {str(e)}")

    def get_adj_factor(self, trade_date: str) -> pd.DataFrame:
        """
        获取指定日期所有股票的复权因子

        使用 Baostock query_history_k_data_plus 获取每日复权因子。
        query_adjust_factor 只返回除权除息事件日，不适合每日同步。

        Args:
            trade_date: 交易日期，格式 YYYYMMDD

        Returns:
            DataFrame: 包含 code, trade_date, adj_factor 三列
        """
        if not self._ensure_connected():
            raise RuntimeError("未连接到 Baostock")

        # 格式化 Baostock 日期格式 YYYY-MM-DD
        bs_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

        try:
            stocks = self.get_stock_list()
        except Exception:
            query_date = datetime.now().strftime('%Y-%m-%d')
            rs = bs.query_all_stock(day=query_date)
            if rs.error_code != '0':
                return pd.DataFrame()
            df_raw = rs.get_data()
            df_raw['code'] = df_raw['code'].apply(lambda x: normalize_code(x) or x)
            stocks = df_raw[df_raw['code'].str.match(r'^\d{6}$')].copy()

        if stocks.empty:
            return pd.DataFrame()

        results = []
        total = len(stocks)

        for idx, row in stocks.iterrows():
            code_raw = row.get('code', '')
            exchange = row.get('exchange', 'SH' if code_raw.startswith('6') else 'SZ')
            bs_code = f"{exchange.lower()}.{code_raw}"

            try:
                self._wait_for_rate_limit()

                # 使用 query_history_k_data_plus 获取每日复权因子
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,code,tradestatus,isST",
                    start_date=bs_date,
                    end_date=bs_date,
                    frequency="d",
                    adjustflag="3"
                )
                self._last_request_time = time.time()

                if rs.error_code != '0':
                    continue

                # 获取复权因子需要用 query_adjust_factor 的最新记录
                rs2 = bs.query_adjust_factor(code=bs_code, start_date=bs_date, end_date=bs_date)
                adj_val = None
                if rs2.error_code == '0':
                    while rs2.next():
                        row_data = rs2.get_row_data()
                        if len(row_data) >= 2 and row_data[1] and row_data[1] != '':
                            adj_val = float(row_data[1])
                            break

                # 如果当天没有除权事件，用最近的历史复权因子
                if adj_val is None:
                    # 向前查找最近的复权因子
                    rs3 = bs.query_adjust_factor(code=bs_code, start_date="2000-01-01", end_date=bs_date)
                    if rs3.error_code == '0':
                        last_adj = None
                        while rs3.next():
                            row_data = rs3.get_row_data()
                            if len(row_data) >= 2 and row_data[1] and row_data[1] != '':
                                last_adj = float(row_data[1])
                        adj_val = last_adj

                # 检查是否交易（非停牌）
                is_trading = False
                while rs.next():
                    r = rs.get_row_data()
                    if len(r) >= 3 and r[2] == '1':  # tradestatus == '1'
                        is_trading = True
                    break

                if adj_val is not None:
                    results.append({
                        'code': code_raw,
                        'trade_date': trade_date,
                        'adj_factor': adj_val
                    })

            except Exception as e:
                logger.debug(f"获取 {code_raw} 复权因子失败: {e}")
                continue

            if (idx + 1) % 200 == 0:
                logger.info(f"  📊 复权因子进度: {idx+1}/{total}，已获取 {len(results)} 条")

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        return df

    def get_stock_basic(self) -> pd.DataFrame:
        """
        获取股票基本资料（含行业分类）
        
        使用 Baostock query_stock_industry 获取全市场行业信息。
        
        Returns:
            DataFrame: 包含 code, name, industry 三列
        """
        if not self._ensure_connected():
            raise RuntimeError("未连接到 Baostock")

        try:
            self._wait_for_rate_limit()

            rs = bs.query_stock_industry()

            if rs.error_code != '0':
                raise RuntimeError(f"获取行业分类失败: {rs.error_msg}")

            self._last_request_time = time.time()

            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                return pd.DataFrame()

            df = pd.DataFrame(data_list, columns=rs.fields)
            # fields: code, code_name, industry
            df = df.rename(columns={
                'code_name': 'name',
            })
            # 统一 code 为纯数字格式
            df['code'] = df['code'].apply(lambda x: normalize_code(x) or x)
            df = df[['code', 'name', 'industry']]
            df = df.dropna(subset=['code'])
            return df

        except Exception as e:
            raise RuntimeError(f"获取股票基本资料异常: {str(e)}")

    def get_daily_basic(self, trade_date: str, **kwargs) -> pd.DataFrame:
        """
        获取指定日期全市场日频基本面数据（PE/PB/换手率/量比）

        使用 Baostock query_history_k_data_plus 批量获取。
        Baostock 不直接提供 daily_basic 接口，但 kline 数据包含
        peTTM, pbMRQ, turn 等字段。

        Args:
            trade_date: 交易日期，格式 YYYY-MM-DD 或 YYYYMMDD

        Returns:
            DataFrame: 包含 code, trade_date, pe, pe_ttm, pb, turnover_rate, volume_ratio
        """
        if not self._ensure_connected():
            raise RuntimeError("未连接到 Baostock")

        # 标准化日期格式
        if len(trade_date) == 8:
            bs_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
        else:
            bs_date = trade_date

        try:
            stocks = self.get_stock_list()
            if stocks is None or stocks.empty:
                return pd.DataFrame()
        except Exception:
            return pd.DataFrame()

        results = []
        total = len(stocks)
        failed = 0

        for idx, row in stocks.iterrows():
            plain_code = str(row.get('code', '')).strip()
            if not plain_code or not plain_code.isdigit():
                continue

            bs_code = self._normalize_code(plain_code)
            if not bs_code:
                continue

            try:
                self._wait_for_rate_limit()
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,code,peTTM,pbMRQ,turn,tradestatus,volume",
                    start_date=bs_date,
                    end_date=bs_date,
                    frequency="d",
                    adjustflag="3"
                )
                self._last_request_time = time.time()

                if rs.error_code != '0':
                    failed += 1
                    continue

                while rs.next():
                    r = rs.get_row_data()
                    if len(r) < 7:
                        continue
                    status = r[5]
                    if status != '1':  # 跳过停牌
                        continue
                    pe_ttm = float(r[2]) if r[2] and r[2] != '' else None
                    pb_val = float(r[3]) if r[3] and r[3] != '' else None
                    turn_val = float(r[4]) if r[4] and r[4] != '' else None
                    vol_val = float(r[6]) if r[6] and r[6] != '' else None

                    results.append({
                        'code': plain_code,
                        'trade_date': bs_date,
                        'pe': pe_ttm,  # Baostock 只有 peTTM
                        'pe_ttm': pe_ttm,
                        'pb': pb_val,
                        'turnover_rate': turn_val,
                        'volume_ratio': None,  # 需要后续计算
                        'total_mv': None,  # Baostock 不提供
                        'circ_mv': None,
                    })

            except Exception:
                failed += 1
                continue

            # 每 500 只打印进度
            if (idx + 1) % 500 == 0:
                logger.info(f"  daily_basic 进度: {idx+1}/{total} (获取:{len(results)} 失败:{failed})")

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        logger.info(f"✅ {bs_date} daily_basic 获取 {len(df)} 条 (失败:{failed})")
        return df
    
    def get_kline(
        self,
        code: str,
        cycle: str = 'daily',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """获取K线数据（支持自动重连、超时控制和频率限制）

        使用 baostock 推荐的游标迭代方式获取数据，避免重复索引问题。
        参考: https://www.baostock.com/mainContent?file=pythonAPI.md
        """
        if cycle not in self._CYCLE_MAP:
            raise ValueError(f"不支持的周期: {cycle}，支持的周期: {list(self._CYCLE_MAP.keys())}")

        start = start_date or '2000-01-01'
        end = end_date or self._get_today_str()
        bs_code = self._normalize_code(code)

        for attempt in range(3):
            try:
                if not self._ensure_connected():
                    raise RuntimeError("无法连接到Baostock")

                # 等待频率限制
                self._wait_for_rate_limit()

                fields = "date,code,open,high,low,close,preclose,volume,amount"
                if cycle in ['min5', 'min15', 'min30', 'min60']:
                    fields = "date,time," + fields.replace("date,", "")

                # 使用超时控制执行 Baostock 请求
                def do_request():
                    return bs.query_history_k_data_plus(
                        code=bs_code,
                        fields=fields,
                        start_date=start,
                        end_date=end,
                        frequency=self._CYCLE_MAP[cycle],
                        adjustflag=self._ADJUST_FLAG
                    )
                
                rs = _run_baostock_with_timeout(do_request)

                if rs.error_code != '0':
                    error_msg = rs.error_msg or ''
                    if '用户未登录' in error_msg or rs.error_code == '1000':
                        logger.warning(f"⚠️ Baostock 连接断开，尝试重连（第 {attempt+1}/3 次）...")
                        self.connected = False
                        continue
                    raise RuntimeError(f"获取K线数据失败: {error_msg}")

                self._last_request_time = time.time()
                
                data_list = []
                max_iterations = 100000  # 防止无限循环
                iteration_count = 0
                
                while (rs.error_code == '0') & rs.next():
                    iteration_count += 1
                    if iteration_count > max_iterations:
                        logger.warning(f"⚠️ 获取 {code} 数据时迭代次数超过限制({max_iterations})，强制退出")
                        break
                    data_list.append(rs.get_row_data())

                result = pd.DataFrame(data_list, columns=rs.fields)

                if result.empty:
                    return pd.DataFrame()

                result = result.reset_index(drop=True)

                if cycle in ['min5', 'min15', 'min30', 'min60']:
                    dates = list(result['date'])
                    times = list(result['time'])
                    trade_dates = []
                    for d, t in zip(dates, times):
                        time_str = t[8:10] + ':' + t[10:12] + ':' + t[12:14]
                        trade_dates.append(d + ' ' + time_str)
                else:
                    trade_dates = list(result['date'])

                result = pd.DataFrame({
                    'code': code,
                    'trade_date': trade_dates,
                    'open': list(pd.to_numeric(result['open'], errors='coerce')),
                    'high': list(pd.to_numeric(result['high'], errors='coerce')),
                    'low': list(pd.to_numeric(result['low'], errors='coerce')),
                    'close': list(pd.to_numeric(result['close'], errors='coerce')),
                    'pre_close': list(pd.to_numeric(result['preclose'], errors='coerce')),
                    'volume': list(pd.to_numeric(result['volume'], errors='coerce')),
                    'amount': list(pd.to_numeric(result['amount'], errors='coerce')),
                    'cycle': cycle
                })

                result = result.sort_values('trade_date').reset_index(drop=True)
                return result

            except TimeoutError as e:
                if attempt < 2:
                    logger.warning(f"⚠️ 获取 {code} 数据超时，尝试重连...（第 {attempt+1}/3 次）")
                    self.connected = False
                    continue
                raise RuntimeError(f"获取 {code} K线数据超时，已重试3次")
            except Exception as e:
                error_msg = str(e)
                if attempt < 2 and ('用户未登录' in error_msg or '连接' in error_msg.lower() or '超时' in error_msg):
                    logger.warning(f"⚠️ 获取 {code} 数据失败，尝试重连...（第 {attempt+1}/3 次）")
                    self.connected = False
                    continue
                raise RuntimeError(f"获取K线数据异常: {error_msg}")

        raise RuntimeError(f"获取 {code} K线数据失败，已重试3次")
    
    def get_trade_calendar(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exchange: str = 'SH'
    ) -> pd.DataFrame:
        """
        获取交易日历
        
        Args:
            start_date: 开始日期，格式 YYYY-MM-DD
            end_date: 结束日期，格式 YYYY-MM-DD
            exchange: 交易所，SH或SZ
        
        Returns:
            DataFrame: 包含 cal_date, is_open, exchange 字段
        """
        if not self.connected:
            raise RuntimeError("未连接到Baostock")
        
        start = start_date or '2000-01-01'
        end = end_date or self._get_today_str()
        
        try:
            rs = bs.query_trade_dates(start_date=start, end_date=end)
            
            if rs.error_code != '0':
                raise RuntimeError(f"获取交易日历失败: {rs.error_msg}")
            
            df = rs.get_data()
            
            if df.empty:
                return pd.DataFrame()
            
            # 处理数据 - 兼容不同的字段名
            if 'calendarDate' in df.columns:
                date_col = 'calendarDate'
            elif 'date' in df.columns:
                date_col = 'date'
            else:
                date_col = df.columns[0] if len(df.columns) > 0 else None
            
            if 'isTradeDay' in df.columns:
                trade_day_col = 'isTradeDay'
            elif 'is_open' in df.columns:
                trade_day_col = 'is_open'
            else:
                trade_day_col = df.columns[1] if len(df.columns) > 1 else None
            
            if date_col is None or trade_day_col is None:
                raise RuntimeError("无法识别交易日历字段")
            
            result = pd.DataFrame({
                'cal_date': df[date_col],
                'is_open': df[trade_day_col].apply(lambda x: 1 if str(x) == '1' else 0),
                'exchange': exchange
            })
            
            return result
            
        except Exception as e:
            # 如果Baostock获取失败，生成一个简单的交易日历作为备选
            return self._generate_simple_calendar(start, end, exchange)
    
    def get_next_trade_date(
        self,
        last_date: str,
        exchange: str = 'SH'
    ) -> Optional[str]:
        """
        获取下一个交易日
        
        Args:
            last_date: 最后日期，格式 YYYY-MM-DD
            exchange: 交易所
        
        Returns:
            下一个交易日日期，如果不存在则返回None
        """
        # 获取未来30天的日历
        end_date = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=30)).strftime('%Y-%m-%d')
        
        try:
            calendar = self.get_trade_calendar(start_date=last_date, end_date=end_date)
            
            if calendar.empty:
                return None
            
            # 过滤大于last_date且是交易日的数据
            mask = (calendar['cal_date'] > last_date) & (calendar['is_open'] == 1)
            next_dates = calendar[mask]['cal_date'].sort_values()
            
            if next_dates.empty:
                return None
            
            next_date = next_dates.iloc[0]
            
            # 检查是否超过今天
            today = self._get_today_str()
            if next_date > today:
                return None
            
            return next_date
            
        except Exception as e:
            # 如果日历查询失败，返回简单计算结果
            return self._simple_next_trade_date(last_date)
    
    def _simple_next_trade_date(self, last_date: str) -> Optional[str]:
        """
        简单计算下一个交易日（备用方案）
        
        Args:
            last_date: 最后日期，格式 YYYY-MM-DD
        
        Returns:
            下一个交易日日期，如果超过今天则返回None
        """
        try:
            last_dt = datetime.strptime(last_date, '%Y-%m-%d')
            today = datetime.now()
            
            # 最多检查14天
            for i in range(1, 15):
                next_dt = last_dt + timedelta(days=i)
                # 跳过周末
                if next_dt.weekday() >= 5:
                    continue
                # 检查是否超过今天
                if next_dt.date() > today.date():
                    return None
                return next_dt.strftime('%Y-%m-%d')
            
            return None
        except Exception:
            return None
    
    def _normalize_code(self, code: str) -> str:
        """标准化股票代码格式为Baostock格式"""
        code = str(code).strip()
        
        # 如果已经是Baostock格式，直接返回
        if code.startswith('sh.') or code.startswith('sz.'):
            return code
        
        # 6位数字代码
        if len(code) == 6:
            # 60开头 -> sh，00/30开头 -> sz
            if code.startswith('6'):
                return f'sh.{code}'
            else:
                return f'sz.{code}'
        
        return code
    
    def _get_today_str(self) -> str:
        """获取今天日期字符串"""
        return datetime.now().strftime('%Y-%m-%d')
    
    @property
    def name(self) -> str:
        return "Baostock"
    
    @property
    def requires_token(self) -> bool:
        return False
    
    def _generate_simple_calendar(self, start_date: str, end_date: str, exchange: str) -> pd.DataFrame:
        """
        生成简单的交易日历（备选方案）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            exchange: 交易所
        
        Returns:
            DataFrame: 交易日历数据
        """
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            dates = []
            current_dt = start_dt
            
            # 已知节假日（简化版）
            holidays = {
                '2025-01-01', '2025-01-29', '2025-01-30', '2025-01-31', '2025-02-01', '2025-02-02',
                '2025-04-04', '2025-04-05', '2025-05-01', '2025-05-02', '2025-05-03',
                '2025-06-08', '2025-06-09', '2025-06-10',
                '2025-09-28', '2025-09-29', '2025-09-30',
                '2025-10-01', '2025-10-02', '2025-10-03', '2025-10-04', '2025-10-05', '2025-10-06', '2025-10-07',
                '2026-01-01', '2026-01-28', '2026-01-29', '2026-01-30', '2026-01-31', '2026-02-01',
                '2026-04-04', '2026-04-05', '2026-05-01', '2026-05-02', '2026-05-03',
                '2026-06-07', '2026-06-08', '2026-06-09',
                '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04', '2026-10-05', '2026-10-06', '2026-10-07',
            }
            
            while current_dt <= end_dt:
                date_str = current_dt.strftime('%Y-%m-%d')
                # 判断是否为交易日（周一到周五，排除节假日）
                is_open = 1 if (current_dt.weekday() < 5 and date_str not in holidays) else 0
                dates.append({
                    'cal_date': date_str,
                    'is_open': is_open,
                    'exchange': exchange
                })
                current_dt += timedelta(days=1)
            
            return pd.DataFrame(dates)
        except Exception as e:
            logger.error(f"生成简单日历失败: {str(e)}")
            return pd.DataFrame()
    
    @property
    def supported_cycles(self) -> List[str]:
        return list(self._CYCLE_MAP.keys())


# 测试代码
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    
    ds = BaostockDataSource()
    
    if ds.connect():
        _logger.info("✅ 连接成功")
        
        # 测试股票列表
        _logger.info("📋 获取股票列表...")
        stocks = ds.get_stock_list()
        _logger.info(f"获取到 {len(stocks)} 只股票")
        _logger.info(f"\n{stocks.head()}")
        
        # 测试日线数据
        _logger.info("📊 获取日线数据...")
        df = ds.get_kline('600000', cycle='daily', start_date='2025-05-01', end_date='2025-05-28')
        _logger.info(f"获取到 {len(df)} 条日线数据")
        _logger.info(f"\n{df.head()}")
        
        # 测试分钟线数据
        _logger.info("⏱️ 获取60分钟线数据...")
        df = ds.get_kline('600000', cycle='min60', start_date='2025-05-20', end_date='2025-05-28')
        _logger.info(f"获取到 {len(df)} 条60分钟线数据")
        _logger.info(f"\n{df.head()}")
        
        # 测试交易日历
        _logger.info("📅 获取交易日历...")
        calendar = ds.get_trade_calendar(start_date='2025-05-01', end_date='2025-05-31')
        _logger.info(f"获取到 {len(calendar)} 天日历数据")
        _logger.info(f"\n{calendar.head()}")
        
        # 测试获取下一个交易日
        _logger.info("🔮 获取下一个交易日...")
        next_date = ds.get_next_trade_date('2025-05-28')
        _logger.info(f"2025-05-28 的下一个交易日: {next_date}")
        
        ds.disconnect()
        _logger.info("✅ 断开连接")
    else:
        _logger.error("❌ 连接失败")
