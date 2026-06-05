#!/usr/bin/env python3
"""
Tushare Pro 数据源实现

特点：
- 数据质量高、响应快
- 限频 200 次/分钟（免费版）
- 支持复权处理
- 需 Token（配置在 .env 中）
"""
import os
import time
import pandas as pd
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from .base import BaseDataSource
from utils.logger import setup_logger

logger = setup_logger('tushare_datasource')

# Tushare 频率限制配置
TUSHARE_RATE_LIMIT = {
    'min_interval': 0.35,            # 最小请求间隔（秒），保守设置为 180次/分钟
    'max_requests_per_minute': 180,  # 每分钟最大请求数（免费版 200次/分钟，留余量）
    'burst_size': 5,                 # 允许的突发请求数
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


class TushareDataSource(BaseDataSource):
    """Tushare Pro 数据源实现"""

    _CYCLE_MAP = {
        'daily': 'D',
        'weekly': 'W',
        'monthly': 'M',
        'min5': '5min',
        'min15': '15min',
        'min30': '30min',
        'min60': '60min',
    }
    
    # 各接口频率限制（次/分钟）
    _API_RATE_LIMITS = {
        'daily': 200,    # 日线：200次/分钟
        'weekly': 1,     # 周线：1次/分钟
        'monthly': 1/60, # 月线：1次/小时
        'min5': 30,      # 5分钟线：30次/分钟
        'min15': 30,     # 15分钟线：30次/分钟
        'min30': 30,     # 30分钟线：30次/分钟
        'min60': 30,     # 60分钟线：30次/分钟
    }

    def __init__(self, rate_limit_config: Dict = None):
        self._pro = None
        self.connected = False
        self._last_request_time = 0
        self._last_request_times = {}  # 记录每个接口的最后请求时间
        
        # 为每个接口创建独立的限流控制器
        self._rate_limiters = {}
        for cycle, limit in self._API_RATE_LIMITS.items():
            rate = limit / 60.0
            self._rate_limiters[cycle] = RateLimiter(rate=rate, burst=1)

        self._request_count = 0
        self._last_minute_requests = []

    def _get_token(self) -> str:
        """从环境变量获取 Tushare Token"""
        # 尝试从多个来源获取
        token = os.environ.get('TUSHARE_TOKEN') or os.environ.get('TS_TOKEN')
        if not token:
            # 尝试从 .env 文件读取
            try:
                from dotenv import load_dotenv
                load_dotenv()
                token = os.environ.get('TUSHARE_TOKEN') or os.environ.get('TS_TOKEN')
            except ImportError:
                pass
        if not token:
            raise RuntimeError("未找到 Tushare Token，请在 .env 中设置 TUSHARE_TOKEN")
        return token

    def _wait_for_rate_limit(self, cycle: str = 'daily'):
        """等待频率限制（按接口类型）"""
        # 获取该接口的限流控制器
        limiter = self._rate_limiters.get(cycle)
        if limiter:
            limiter.acquire(timeout=120)
        
        self._last_request_time = time.time()
        self._request_count += 1
        now = time.time()
        self._last_minute_requests.append(now)
        self._last_minute_requests = [t for t in self._last_minute_requests if now - t < 60]
        
        # 周线/月线接口特殊处理：确保至少间隔60秒
        if cycle in ['weekly', 'monthly']:
            last_time = self._last_request_times.get(cycle, 0)
            elapsed = now - last_time
            if elapsed < 60:
                sleep_time = 60 - elapsed
                logger.debug(f"⏳ {cycle}接口限流等待: {sleep_time:.1f}秒")
                time.sleep(sleep_time)
            self._last_request_times[cycle] = time.time()

    def connect(self) -> bool:
        """建立连接（初始化 Tushare Pro API，不额外调用接口以免触发限流）"""
        try:
            import tushare as ts
            token = self._get_token()
            self._pro = ts.pro_api(token=token)
            self.connected = True
            logger.info("✅ Tushare Pro 连接成功")
            return True
        except Exception as e:
            logger.error(f"❌ Tushare 连接失败: {e}")
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        self._pro = None
        self.connected = False
        return True

    def _code_to_ts(self, code: str) -> str:
        """将内部代码格式转换为 Tushare 格式
        
        Args:
            code: 内部代码格式，如 sh.600000, sz.000001, 000001
        
        Returns:
            Tushare 代码格式，如 600000.SH, 000001.SZ
        """
        code = str(code).strip()
        # 已是最新版
        if '.' in code and code.split('.')[1].upper() in ('SH', 'SZ'):
            parts = code.split('.')
            return f"{parts[0]}.{parts[1].upper()}"
        # 带 sh./sz. 前缀
        if code.startswith('sh.'):
            return f"{code[3:]}.SH"
        if code.startswith('sz.'):
            return f"{code[3:]}.SZ"
        if code.startswith('SH.') or code.startswith('SZ.'):
            parts = code.split('.')
            return f"{parts[1]}.{parts[0].upper()}"
        # 纯数字
        if code.isdigit() and len(code) == 6:
            if code.startswith('6') or code.startswith('9'):
                return f"{code}.SH"
            else:
                return f"{code}.SZ"
        return code

    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表"""
        if not self.connected or self._pro is None:
            raise RuntimeError("未连接到 Tushare Pro")

        try:
            self._wait_for_rate_limit()
            df = self._pro.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,symbol,name,area,industry,list_date'
            )

            if df is None or df.empty:
                logger.warning("⚠️ Tushare 返回空股票列表")
                return pd.DataFrame()

            # 过滤 B 股、北交所、ETF 等非 A 股品种
            # Tushare ts_code 格式: 600000.SH, 000001.SZ, 900901.SH(B股)
            mask = df['ts_code'].str.match(r'^\d{6}\.(SH|SZ)$')
            df = df[mask].copy()

            # 过滤 B 股（900xxx, 200xxx）、科创板（688xxx）
            df = df[~df['symbol'].str.match(r'^9\d{5}')]  # 900xxx B股
            df = df[~df['symbol'].str.match(r'^2\d{5}')]  # 200xxx B股
            df = df[~df['symbol'].str.match(r'^688')]     # 科创板

            # 转换为内部统一格式: sh.600000 / sz.000001
            result = pd.DataFrame({
                'code': df['ts_code'].apply(lambda x: f"{'sh' if x.endswith('.SH') else 'sz'}.{x[:6]}"),
                'name': df['name'],
                'exchange': df['ts_code'].apply(lambda x: 'SH' if x.endswith('.SH') else 'SZ'),
                'industry': df['industry'].fillna(''),
                'list_date': df['list_date'].fillna(''),
                'delist_date': ''
            })

            logger.info(f"Tushare 获取股票列表: {len(result)} 只")
            return result

        except Exception as e:
            raise RuntimeError(f"获取股票列表异常: {e}")

    def get_kline(
        self,
        code: str,
        cycle: str = 'daily',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """获取K线数据"""
        if not self.connected or self._pro is None:
            raise RuntimeError("未连接到 Tushare Pro")

        if cycle not in self._CYCLE_MAP:
            raise ValueError(f"不支持的周期: {cycle}，支持的周期: {list(self._CYCLE_MAP.keys())}")

        ts_code = self._code_to_ts(code)
        start = start_date.replace('-', '') if start_date else '20000101'
        end = end_date.replace('-', '') if end_date else datetime.now().strftime('%Y%m%d')

        try:
            self._wait_for_rate_limit(cycle)

            if cycle == 'daily':
                df = self._pro.daily(
                    ts_code=ts_code,
                    start_date=start,
                    end_date=end,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,vol,amount'
                )
            elif cycle == 'weekly':
                df = self._pro.weekly(
                    ts_code=ts_code,
                    start_date=start,
                    end_date=end,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,vol,amount'
                )
            elif cycle == 'monthly':
                df = self._pro.monthly(
                    ts_code=ts_code,
                    start_date=start,
                    end_date=end,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,vol,amount'
                )
            else:
                df = self._pro.stk_mins(
                    ts_code=ts_code,
                    start_date=start,
                    end_date=end,
                    freq=self._CYCLE_MAP[cycle],
                    fields='ts_code,trade_time,open,high,low,close,vol,amount'
                )

            if df is None or df.empty:
                return pd.DataFrame()

            if cycle == 'daily' or cycle == 'weekly' or cycle == 'monthly':
                # Tushare 单位: vol=手(1手=100股), amount=千元(1千元=1000元)
                # 转换为标准格式: volume=股数, amount=元
                result = pd.DataFrame({
                    'code': code,
                    'trade_date': df['trade_date'],
                    'open': pd.to_numeric(df['open'], errors='coerce'),
                    'high': pd.to_numeric(df['high'], errors='coerce'),
                    'low': pd.to_numeric(df['low'], errors='coerce'),
                    'close': pd.to_numeric(df['close'], errors='coerce'),
                    'pre_close': pd.to_numeric(df['pre_close'], errors='coerce'),
                    'volume': pd.to_numeric(df['vol'], errors='coerce') * 100,
                    'amount': pd.to_numeric(df['amount'], errors='coerce') * 1000,
                    'cycle': cycle,
                })
            else:
                # 分钟线
                result = pd.DataFrame({
                    'code': code,
                    'trade_date': df['trade_time'],
                    'open': pd.to_numeric(df['open'], errors='coerce'),
                    'high': pd.to_numeric(df['high'], errors='coerce'),
                    'low': pd.to_numeric(df['low'], errors='coerce'),
                    'close': pd.to_numeric(df['close'], errors='coerce'),
                    'pre_close': 0.0,
                    'volume': pd.to_numeric(df['vol'], errors='coerce') * 100,
                    'amount': pd.to_numeric(df['amount'], errors='coerce') * 1000,
                    'cycle': cycle,
                })

            result = result.sort_values('trade_date').reset_index(drop=True)
            return result

        except Exception as e:
            raise RuntimeError(f"获取K线数据异常: {e}")

    def get_trade_calendar(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exchange: str = 'SH'
    ) -> pd.DataFrame:
        """获取交易日历"""
        if not self.connected or self._pro is None:
            raise RuntimeError("未连接到 Tushare Pro")

        start = start_date.replace('-', '') if start_date else '20000101'
        end = end_date.replace('-', '') if end_date else datetime.now().strftime('%Y%m%d')
        exch_map = {'SH': 'SSE', 'SZ': 'SZSE'}

        try:
            self._wait_for_rate_limit()
            df = self._pro.trade_cal(exchange=exch_map.get(exchange, 'SSE'),
                                     start_date=start, end_date=end)

            if df is None or df.empty:
                return pd.DataFrame()

            result = pd.DataFrame({
                'cal_date': df['cal_date'],
                'is_open': df['is_open'].astype(int),
                'exchange': exchange,
            })
            return result

        except Exception as e:
            logger.warning(f"获取交易日历失败: {e}")
            return pd.DataFrame()

    def get_next_trade_date(self, last_date: str, exchange: str = 'SH') -> Optional[str]:
        """获取下一个交易日"""
        end = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=30)).strftime('%Y-%m-%d')
        calendar = self.get_trade_calendar(start_date=last_date, end_date=end, exchange=exchange)
        if calendar.empty:
            return None
        mask = (calendar['cal_date'] > last_date.replace('-', '')) & (calendar['is_open'] == 1)
        next_dates = calendar[mask]['cal_date'].sort_values()
        if next_dates.empty:
            return None
        next_date = next_dates.iloc[0]
        today = datetime.now().strftime('%Y%m%d')
        if next_date > today:
            return None
        return f"{next_date[:4]}-{next_date[4:6]}-{next_date[6:]}"

    @property
    def name(self) -> str:
        return 'tushare'

    @property
    def requires_token(self) -> bool:
        return True

    @property
    def supported_cycles(self) -> List[str]:
        return list(self._CYCLE_MAP.keys())

    def health_check(self) -> bool:
        """健康检查（仅检查连接状态，不发送 API 请求）"""
        return self.connected and self._pro is not None