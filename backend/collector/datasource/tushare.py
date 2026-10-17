#!/usr/bin/env python3
"""
Tushare Pro 数据源实现 — 仅支持日线数据下载

⚠️ 限用说明：该数据源仅保留日线（daily）数据下载功能。
其他功能（daily_basic / adj_factor / trade_cal / 非日线K线等）受 Tushare
用户等级限制无法使用，调用会直接抛出 NotImplementedError。

如需获取基本面、复权因子等数据，请使用 Baostock / AkShare 等其他数据源。
"""
import os
import time
import threading
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict
from .base import BaseDataSource
from utils.logger import setup_logger
from utils.rate_limiter import RateLimiter

logger = setup_logger('tushare_datasource')

# Tushare daily API 频率限制配置（免费版 daily 接口限 50次/分钟，留余量设 45）
TUSHARE_RATE_LIMIT = {
    'min_interval': 1.4,
    'max_requests_per_minute': 45,
    'burst_size': 3,
}

# ===================== 下载层硬超时（协作单 57.0） =====================
# 背景：2026-10-15 阶段 2（daily_import）静默死亡 —— Tushare 批量接口长时间无响应
# （socket 空闲、CPU≈0），进程被杀、台账卡 running、stdout 缓冲丢失。tushare 库内虽
# 已有 requests timeout=30，但仅为主 30s 且非我方显式声明；半死连接实测可永久阻塞在
# SSL_read。故采用「守护线程 + join(timeout)」拿回控制权：卡死线程置 daemon，不阻止
# 进程退出；泄漏线程（仍 alive）累计超过上限即 fast-fail，避免线程无限堆积。
TUSHARE_QUERY_TIMEOUT = int(os.getenv('TUSHARE_QUERY_TIMEOUT', '60'))      # 单只 get_kline
TUSHARE_BATCH_TIMEOUT = int(os.getenv('TUSHARE_BATCH_TIMEOUT', '120'))    # batch_get_daily
TUSHARE_HTTP_TIMEOUT = int(os.getenv('TUSHARE_HTTP_TIMEOUT', '30'))       # requests 层
_MAX_HUNG_THREADS = int(os.getenv('TUSHARE_MAX_HUNG_THREADS', '3'))


class TushareTimeoutError(TimeoutError):
    """Tushare 网络调用超时（半死连接 / 接口无响应兜底）。"""


# 仍卡死（join 超时后 thread 仍 alive）的下载线程列表；入口先剔除已自愈的线程，
# 若在存线程数达到上限则不再新增线程、直接快速失败。
_hung_threads: list = []
_hung_lock = threading.Lock()


def _call_with_hard_timeout(func, args=(), kwargs=None, timeout=TUSHARE_QUERY_TIMEOUT, name='tushare'):
    """在守护线程中执行 func 并设硬超时，超时抛 TushareTimeoutError。

    线程置 daemon：即便底层阻塞在 SSL_read 无法被信号打断，也不会拖住进程退出；
    入口先清理已结束的泄漏线程（requests timeout=30 通常 ≤30s 自愈），
    在存卡死线程数达 _MAX_HUNG_THREADS 时直接 fast-fail。

    Args:
        func: 待执行的网络调用（如 self._pro.daily）
        args/kwargs: 传给 func 的参数
        timeout: 硬超时秒数；<=0 表示不设限（同步执行）
        name: 日志/异常标识（如 'tushare.daily'）
    """
    kwargs = kwargs or {}
    if timeout and timeout > 0:
        with _hung_lock:
            _hung_threads[:] = [t for t in _hung_threads if t.is_alive()]
            if len(_hung_threads) >= _MAX_HUNG_THREADS:
                raise TushareTimeoutError(
                    f"{name} 已有 {len(_hung_threads)} 个下载线程疑似卡死，快速失败（不再新增线程）")

    result = {}
    error = {}

    def _runner():
        try:
            result['value'] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - 需把任意异常透传给调用方
            error['value'] = exc

    if not timeout or timeout <= 0:
        _runner()
        if 'value' in error:
            raise error['value']
        return result.get('value')

    thread = threading.Thread(target=_runner, name=f'{name}_dl', daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        # 超时：线程仍在后台运行 → 记入泄漏列表（后续入口会清理自愈线程）
        with _hung_lock:
            _hung_threads.append(thread)
        logger.warning(f"⚠️ {name} 下载超过 {timeout}s 未返回（疑似连接半死），已放弃等待")
        raise TushareTimeoutError(f"{name} 网络请求超过 {timeout}s 未返回（疑似连接半死）")
    if 'value' in error:
        raise error['value']
    return result.get('value')


class TushareDataSource(BaseDataSource):
    """
    Tushare Pro 数据源 — 支持日线数据下载 + daily_basic（Pro token）

    功能支持说明：
    - pro.daily()：日线行情（OHLCV），免费版可用，限速 180次/分钟
    - pro.daily_basic()：每日基本面指标（PE/PB/换手率/市值/dv/ps等），
      需 Tushare Pro Token（2000+ 积分），限速 1次/小时全市场
    - pro.adj_factor() / pro.trade_cal() 等：受等级限制不可用
    """

    # 日线限流：免费版 daily 接口限 50次/分钟 → 约 0.83次/秒，留余量取 45次/分钟
    _DAILY_RATE = 45 / 60.0  # 0.75 次/秒

    def __init__(self, rate_limit_config: Dict = None):
        self._pro = None
        self.connected = False
        self._last_request_time = 0
        self._limiter = RateLimiter(rate=self._DAILY_RATE, burst=1)
        self._request_count = 0
        self._last_minute_requests = []

    def _get_token(self) -> str:
        """从环境变量获取 Tushare Token"""
        token = os.environ.get('TUSHARE_TOKEN') or os.environ.get('TS_TOKEN')
        if not token:
            try:
                from dotenv import load_dotenv
                load_dotenv()
                token = os.environ.get('TUSHARE_TOKEN') or os.environ.get('TS_TOKEN')
            except ImportError:
                pass
        if not token:
            raise RuntimeError("未找到 Tushare Token，请在 .env 中设置 TUSHARE_TOKEN")
        return token

    def _wait_for_rate_limit(self):
        """等待频率限制"""
        self._limiter.acquire(timeout=120)
        self._last_request_time = time.time()
        self._request_count += 1
        now = time.time()
        self._last_minute_requests.append(now)
        self._last_minute_requests = [t for t in self._last_minute_requests if now - t < 60]

    def connect(self) -> bool:
        """建立连接（初始化 Tushare Pro API）"""
        try:
            import tushare as ts
            token = self._get_token()
            # 显式固化 requests 层超时（tushare 库默认 30s，防止版本漂移失效）
            self._pro = ts.pro_api(token=token, timeout=TUSHARE_HTTP_TIMEOUT)
            self.connected = True
            logger.info("✅ Tushare Pro 连接成功（仅日线模式）")
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
        """将内部代码格式转换为 Tushare 格式"""
        code = str(code).strip()
        if '.' in code and code.split('.')[1].upper() in ('SH', 'SZ'):
            parts = code.split('.')
            return f"{parts[0]}.{parts[1].upper()}"
        if code.startswith('sh.'):
            return f"{code[3:]}.SH"
        if code.startswith('sz.'):
            return f"{code[3:]}.SZ"
        if code.startswith('SH.') or code.startswith('SZ.'):
            parts = code.split('.')
            return f"{parts[1]}.{parts[0].upper()}"
        if code.isdigit() and len(code) == 6:
            if code.startswith('6') or code.startswith('9'):
                return f"{code}.SH"
            else:
                return f"{code}.SZ"
        return code

    def get_kline(
        self,
        code: str,
        cycle: str = 'daily',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取日线 K 线数据

        仅支持 daily 周期。weekly / monthly / 分钟线 等受用户等级限制，
        调用会抛出 ValueError。

        Args:
            code: 股票代码（支持 sh.600000、sz.000001、600000 等格式）
            cycle: 仅支持 'daily'
            start_date: 起始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
        """
        if not self.connected or self._pro is None:
            raise RuntimeError("未连接到 Tushare Pro")

        if cycle != 'daily':
            raise ValueError(
                f"Tushare 免费版不支持 {cycle} 周期。"
                "如需获取周线/月线/分钟线，请使用 BaostockDataSource 或 AkShareDataSource。"
            )

        ts_code = self._code_to_ts(code)
        start = start_date.replace('-', '') if start_date else '20000101'
        end = end_date.replace('-', '') if end_date else datetime.now().strftime('%Y%m%d')

        try:
            self._wait_for_rate_limit()

            df = _call_with_hard_timeout(
                self._pro.daily,
                kwargs={
                    'ts_code': ts_code,
                    'start_date': start,
                    'end_date': end,
                    'fields': 'ts_code,trade_date,open,high,low,close,pre_close,vol,amount',
                },
                timeout=TUSHARE_QUERY_TIMEOUT,
                name=f'tushare.daily[{ts_code}]',
            )

            if df is None or df.empty:
                return pd.DataFrame()

            # Tushare 单位: vol=手(1手=100股), amount=千元(1千元=1000元)
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

            return result.sort_values('trade_date').reset_index(drop=True)

        except TushareTimeoutError:
            # 硬超时语义需透传，不能被下面的 RuntimeError 吞掉（否则上游重试判定失效）
            raise
        except Exception as e:
            raise RuntimeError(f"获取日线数据异常: {e}")

    def batch_get_daily(self, trade_date: str) -> pd.DataFrame:
        """
        批量获取全市场所有股票在指定日期的日线数据（内置限流保护）

        注意：返回数据已统一单位 — vol=股、amount=元（与 get_kline 一致）

        Args:
            trade_date: 交易日期，格式 YYYY-MM-DD
        """
        if not self.connected or self._pro is None:
            raise RuntimeError("未连接到 Tushare Pro")

        try:
            self._wait_for_rate_limit()
            ts_date = trade_date.replace('-', '')
            df = _call_with_hard_timeout(
                self._pro.daily,
                kwargs={
                    'trade_date': ts_date,
                    'fields': 'ts_code,trade_date,open,high,low,close,pre_close,vol,amount,ah_vol,ah_amount',
                },
                timeout=TUSHARE_BATCH_TIMEOUT,
                name=f'tushare.daily_batch[{trade_date}]',
            )
            if df is not None and not df.empty:
                # 统一单位：vol(手→股), amount(千元→元)
                df['vol'] = df['vol'] * 100
                df['amount'] = df['amount'] * 1000
                if 'ah_vol' in df.columns:
                    df['ah_vol'] = df['ah_vol'] * 100
                if 'ah_amount' in df.columns:
                    df['ah_amount'] = df['ah_amount'] * 1000
            return df
        except TushareTimeoutError:
            raise
        except Exception as e:
            raise RuntimeError(f"批量获取日线数据失败: {e}")

    # ── 以下方法受用户等级限制，不可使用 ──────────────────────────────

    def get_stock_list(self) -> pd.DataFrame:
        """Tushare 免费版不支持 stock_basic 接口，返回空 DataFrame（不抛异常，由调用方降级）"""
        logger.warning("Tushare 免费版不支持 stock_basic 接口，返回空列表。请使用 BaostockDataSource 获取股票列表。")
        return pd.DataFrame()

    def get_stock_basic(self) -> pd.DataFrame:
        """Tushare 免费版不支持 stock_basic 接口，返回空 DataFrame"""
        logger.warning("Tushare 免费版不支持 stock_basic 接口。请使用 BaostockDataSource 获取股票基本信息。")
        return pd.DataFrame()

    def get_trade_calendar(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exchange: str = 'SH'
    ) -> pd.DataFrame:
        """Tushare 免费版不支持 trade_cal 接口，返回空 DataFrame"""
        logger.warning("Tushare 免费版不支持 trade_cal 接口。请使用 BaostockDataSource 获取交易日历。")
        return pd.DataFrame()

    def get_daily_basic(
        self,
        trade_date: Optional[str] = None,
        ts_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取每日基本面指标（PE/PB/换手率/市值/dv/ps等）

        使用 Tushare Pro daily_basic 接口（需 2000+ 积分，限速 5次/天）
        返回字段: dv_ratio, dv_ttm, ps, ps_ttm, float_share, turnover_rate, volume_ratio, pe, pe_ttm, pb

        Args:
            trade_date: 交易日期 YYYY-MM-DD（全市场指定日）
            ts_code: 股票代码如 600000.SH（单只股票历史）
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
        Returns:
            DataFrame，含字段: ts_code,trade_date,close,turnover_rate,volume_ratio,
                               pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,
                               total_share,float_share,total_mv,circ_mv
        """
        if not self.connected or self._pro is None:
            raise RuntimeError("未连接 Tushare，请先调用 connect()")

        # 等待限速（1次/小时 → 用锁保护时间窗口）
        self._wait_for_rate_limit_hourly()

        try:
            if trade_date:
                # 全市场单日（trade_date 格式 YYYYMMDD）
                tushare_date = trade_date.replace('-', '')
                df = _call_with_hard_timeout(
                    self._pro.daily_basic,
                    kwargs={
                        'trade_date': tushare_date,
                        'fields': 'ts_code,trade_date,close,turnover_rate,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,total_mv,circ_mv',
                    },
                    timeout=TUSHARE_BATCH_TIMEOUT,
                    name='tushare.daily_basic',
                )
            elif ts_code:
                # 单只股票历史
                code = ts_code if '.' in ts_code else self._code_to_ts(ts_code)
                start = start_date.replace('-', '') if start_date else '20000101'
                end = end_date.replace('-', '') if end_date else datetime.now().strftime('%Y%m%d')
                df = _call_with_hard_timeout(
                    self._pro.daily_basic,
                    kwargs={
                        'ts_code': code,
                        'start_date': start,
                        'end_date': end,
                        'fields': 'ts_code,trade_date,close,turnover_rate,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,total_mv,circ_mv',
                    },
                    timeout=TUSHARE_QUERY_TIMEOUT,
                    name=f'tushare.daily_basic[{code}]',
                )
            else:
                raise ValueError("trade_date 和 ts_code 至少需要提供一个")

            if df is None or df.empty:
                return pd.DataFrame()

            # 转换 ts_code -> code (去掉 .SH/.SZ)
            df['code'] = df['ts_code'].str.replace(r'\.(SH|SZ|BJ)', '', regex=True)

            # 统一 trade_date 为 YYYY-MM-DD
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')

            # 字段名对齐（与 PyWenCai/Baostock 保持一致）
            rename = {
                'total_share': 'total_share',
                'float_share': 'float_share',
                'total_mv': 'total_mv',
                'circ_mv': 'circ_mv',
            }
            df = df.rename(columns=rename)

            logger.debug(f"✅ daily_basic 获取 {len(df)} 条")
            return df

        except (ConnectionError, TimeoutError, ValueError, KeyError) as e:
            logger.error(f"daily_basic 调用失败: {e}")
            return pd.DataFrame()

    def _wait_for_rate_limit_hourly(self):
        """daily_basic 限速 1次/小时，使用文件锁保护"""
        now = time.time()
        last_file = '/tmp/tushare_daily_basic_last.txt'
        if os.path.exists(last_file):
            try:
                last = float(open(last_file).read().strip())
                elapsed = now - last
                if elapsed < 3600:
                    wait = 3600 - elapsed
                    logger.info(f"⏳ daily_basic 限速，需等待 {wait:.0f}s...")
                    time.sleep(wait)
            except (ValueError, OSError):
                pass
        with open(last_file, 'w') as f:
            f.write(str(time.time()))

    def get_adj_factor(
        self,
        code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        trade_date: Optional[str] = None
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "Tushare 免费版不支持 adj_factor 接口（复权因子）。"
            "请升级 Tushare 账号等级或使用其他数据源计算复权。"
        )

    def get_next_trade_date(self, last_date: str, exchange: str = 'SH') -> Optional[str]:
        raise NotImplementedError(
            "Tushare 免费版不支持交易日历接口。请使用 BaostockDataSource 获取下一交易日。"
        )

    @property
    def requires_token(self) -> bool:
        return True

    @property
    def supported_cycles(self) -> list:
        return ['daily']

    @property
    def name(self) -> str:
        return 'tushare'


if __name__ == '__main__':
    # 测试连接
    ts = TushareDataSource()
    if ts.connect():
        print(f"✅ {ts.name} 连接成功")
        ts.disconnect()
    else:
        print("❌ 连接失败")