#!/usr/bin/env python3
"""
AkShare 金融数据源适配器（替代 Yahoo，作为港股/美股日线唯一数据源）

后端延用 yahoo.py 的 MarketConfig 市场配置与代码规范化，仅将“拉取日线”这一层
从 yfinance 换成 AkShare（新浪财经本源），彻底规避 Yahoo 429 限流问题。

复权口径（对齐 yahoo.py / adj_adjust.py：stock_quotes 存 `raw_*` + `adj_*`，成交价列=后复权）：
- 港股：ak.stock_hk_daily(symbol, adjust='hfq') 直接返回【后复权】收盘价，与 Yahoo 后复权口径一致
  → 原始 Close 用 adjust='' 的不复权；Adj Close 用 adjust='hfq' 的 close
- 美股：新浪接口不支持 hfq（仅 '' / qfq / qfq-factor）。采用“锚点重建法”：
    1. 拉 adjust='' 得原始 Close；adjust='qfq' 得前复权 close（最新日=原始价）
    2. 由调用方读取该股最近一笔已入库 adj_close/raw_close 得锚点 C
    3. Adj Close = 前复权 close × C（还原为与存量一致的【后复权】水平）
  锚点需访问数据库，故适配器 download_single 返回“占位前复权 Adj Close”，
  美股后复权精确重建在 import_one（持有连库）中完成（见 anchor_us_adj_close）。

网络策略：AkShare 走新浪（国内源），connect() 时临时清空代理环境变量，强制国内直连。

接口约定（download_single 返回值与 yfinance 同构，供下游 clean_and_split 零改动复用）：
    index=Date；列 Open/High/Low/Close(原始) / Adj Close(后复权) / Volume / Timezone
"""
import sys
import os
import signal
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import akshare as ak
except ImportError as e:  # pragma: no cover
    ak = None

from collector.datasource.base import BaseDataSource  # noqa: E402
from collector.datasource.yahoo import (  # noqa: E402
    get_market_config,
    MarketConfig,
    normalize_code,
)
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger('akshare_datasource')

_PROXY_ENV_KEYS = ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
                   'all_proxy', 'ALL_PROXY')

# 网络调用硬超时（秒）。AkShare 各接口不暴露 timeout 参数（requests 默认无限等待），
# 系统休眠后 TCP 连接半死时会永久阻塞在 SSL_read，拖死整个 ETL 进程
# （2026-10-01 美股日线清洗僵死 3.5 小时即此因）。单标的日线为两次小请求，
# 全市场快照（stock_hk_spot 一次返回全市场）为大响应，故分别设限。
_NETWORK_TIMEOUT_SECONDS = int(os.getenv('AKSHARE_NETWORK_TIMEOUT', '60'))
_BULK_NETWORK_TIMEOUT_SECONDS = int(os.getenv('AKSHARE_BULK_NETWORK_TIMEOUT', '180'))


class NetworkTimeoutError(TimeoutError):
    """AkShare 网络调用超时（半死连接兜底）。"""


@contextmanager
def network_deadline(seconds: int):
    """给 AkShare 网络调用设硬超时，避免半死 socket 上永久阻塞。

    仅主线程生效（ETL 各脚本均为串行单线程调用 AkShare）；非主线程退化为不设限，
    以免在 SIGALRM 不可用的线程上下文中误报。超时抛出的异常由调用方原有的
    try/except 兜底（跳过该标的或降级到下一个数据源），不再拖死进程。

    Args:
        seconds: 超时秒数；<=0 表示不设限。

    Yields:
        None

    Raises:
        NetworkTimeoutError: 超过 seconds 仍未返回。
    """
    if seconds <= 0 or threading.current_thread() is not threading.main_thread():
        yield
        return

    def _on_timeout(signum, frame):
        raise NetworkTimeoutError(f"网络请求超过 {seconds}s 未返回（疑似连接半死）")

    previous = signal.signal(signal.SIGALRM, _on_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _sanitize_proxy_env() -> None:
    """清空代理环境变量，迫使 AkShare（新浪/东财）走国内直连。

    与 Yahoo 相反（Yahoo 需代理才通、新浪需直连），AkShare 适配器强制直连。
    仅移除代理 key，不改变其他环境变量。
    """
    for key in _PROXY_ENV_KEYS:
        os.environ.pop(key, None)


def _to_ak_symbol(code: str, market: str) -> str:
    """把库存规范化代码转换为 AkShare 使用的 symbol。

    - 港股：库存 '0700.HK'（4 位补零）→ 新浪港股 symbol 需 5 位数字 '00700'
    - 美股：库存 'AAPL'（大写）→ 新浪美股 symbol 原样大写 'AAPL'
    """
    if market == 'hk':
        digits = str(code).split('.')[0].strip()
        try:
            num = int(digits)
        except ValueError:
            return digits
        # 新浪港股 symbol 统一 5 位宽带前导零（0700 -> 00700）
        if num < 100000:
            return str(num).zfill(5)
        return str(num)
    if market == 'us':
        return str(code).strip().upper()
    return str(code).strip()


def _fill_lagging_adj(
    raw_close: pd.Series,
    adj_close: Optional[pd.Series],
) -> Tuple[pd.Series, int]:
    """复权序列缺失日，用最近可得复权倍率填补（防止整行被丢弃）。

    新浪 `adjust='hfq'`/`'qfq'` 与 `adjust=''` 是两次独立请求，两者覆盖的交易日**并非完全一致**：
    1. **尾部滞后**：不复权序列已含最新交易日 T，而复权序列止于 T-1（源尚未更新）；
    2. **历史间断**：复权序列在个别交易日有单日空洞（实测 0026.HK 6639 天中缺 1384 天、
       0700.HK 5482 天中缺 3 天，多为孤立单日）。

    原实现直接 `adj.reindex(raw.index)` 会在这两类日期产出 NaN，随后 `clean_and_split` 的
    `dropna(subset=[... 'adj_close'])` 把**整行丢弃**，表现为「源有数据、库里缺该交易日」的
    静默缺口（实测 0026.HK 缺 9/28 整行）。

    这里改为按复权倍率填补：`ratio = adj_close / raw_close`，对缺失日取最近可得 ratio
    （先 ffill 后 bfill，全缺则退化为 1.0），再以 `raw_close × ratio` 还原该日复权价。
    复权倍率仅在除权除息日跳变，孤立缺口取相邻倍率的误差极小；填补值在数据源补齐后会被
    下一次导入覆盖（write_quotes 为 upsert），故可自愈。

    注意：若缺口恰好跨过除权除息日，本次填入的是缺口前的倍率，会使该缺口段少标一次
    `factor_date`；权衡后仍优于「直接丢行」。

    Args:
        raw_close: 不复权收盘价（index 为交易日）
        adj_close: 复权收盘价（可能缺尾/缺中/缺头/为空）；None 表示数据源无复权序列

    Returns:
        (填补后的复权收盘价, 填补行数)；填补行数 0 表示无缺失或无需填补
    """
    raw = pd.to_numeric(raw_close, errors='coerce').astype(float)
    if adj_close is None:
        return raw.copy(), 0
    adj = pd.to_numeric(adj_close, errors='coerce').astype(float)
    miss = adj.isna() & raw.notna() & (raw > 0)
    n_miss = int(miss.sum())
    if n_miss == 0:
        return adj, 0
    ratio = adj.div(raw.where(raw > 0))
    # 过滤非正/异常倍率（除零、脏数据），其余缺失位置由前后最近倍率补齐
    ratio = ratio.where((ratio > 0) & (ratio < 1e6))
    ratio = ratio.ffill().bfill().fillna(1.0)
    filled = adj.where(~miss, raw * ratio)
    return filled, n_miss


class AkShareDataSource(BaseDataSource):
    """基于 AkShare（新浪财经）的港股/美股日线数据源适配器。

    复用 BaseDataSource 抽象与 yahoo.MarketConfig 市场配置；核心方法 `download_single`
    返回与 yfinance 同构的 DataFrame，使下游 clean_and_split / write_quotes 完全复用。
    """

    name = 'AkShare'
    requires_token = False
    supported_cycles = ['daily', 'weekly', 'monthly']

    def __init__(self, market: str = 'hk'):
        """Args:
            market: 市场标识（hk/us），决定代码规范化、时区。
        """
        self.market = market
        self.cfg = get_market_config(market)
        self.connected = False
        _sanitize_proxy_env()

    # ---------- BaseDataSource 抽象实现 ----------
    def connect(self) -> bool:
        if ak is None:
            return False
        _sanitize_proxy_env()
        self.connected = True
        return True

    def disconnect(self) -> bool:
        self.connected = False
        return True

    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表（港股用新浪全市场；美股读核心池配置文件）。"""
        if self.market == 'hk':
            df = self._fetch_hk_list()
            if df is not None and not df.empty:
                return df
            return pd.DataFrame()
        return self._fetch_us_list()

    def get_kline(
        self,
        code: str,
        cycle: str = 'daily',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        ticker = normalize_code(code, self.market)
        df = self.download_single(ticker, market=self.market, start=start_date, end=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.rename(columns={
            'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close',
            'Adj Close': 'adj_close', 'Volume': 'volume',
        }).reset_index().rename(columns={'Date': 'trade_date'})
        out['code'] = ticker
        out['cycle'] = cycle
        return out

    # ---------- 列表 ----------
    def _fetch_hk_list(self) -> Optional[pd.DataFrame]:
        """从新浪获取港股全市场列表（ak.stock_hk_spot），规范化为 '_normalize_hk_code' 4 位。"""
        if ak is None:
            return None
        try:
            with network_deadline(_BULK_NETWORK_TIMEOUT_SECONDS):
                raw = ak.stock_hk_spot()
            if raw is None or raw.empty:
                return None
            rows: List[Dict[str, Any]] = []
            for _, r in raw.iterrows():
                code = str(r.get('代码', '')).strip()
                if not code:
                    continue
                rows.append({
                    'code': normalize_code(code, 'hk'),
                    'name': r.get('中文名称') or r.get('英文名称') or code,
                    'exchange': 'HKEX',
                    'market': self.market,
                })
            return pd.DataFrame(rows).drop_duplicates(subset=['code']).reset_index(drop=True)
        except Exception as e:
            logger.warning(f"⚠️ 港股列表（stock_hk_spot）拉取失败：{type(e).__name__}: {e}")
            return None

    def _fetch_us_list(self) -> pd.DataFrame:
        """从 `backend/config/us_core_universe.json` 读美股核心池清单。"""
        from pathlib import Path
        path = Path(__file__).resolve().parents[3] / 'backend/config/us_core_universe.json'
        try:
            import json
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return pd.DataFrame()
        symbols = data.get('symbols', []) if isinstance(data, dict) else []
        rows = [{
            'code': normalize_code(s, 'us'),
            'name': str(s),
            'exchange': 'NMS',
            'market': 'us',
        } for s in symbols if str(s).strip()]
        return pd.DataFrame(rows).drop_duplicates(subset=['code']).reset_index(drop=True)

    # ---------- 单标日线（核心） ----------
    def download_single(
        self,
        ticker: str,
        market: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        period: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """拉取单只港股/美股日线，返回与 yfinance 同构的 DataFrame。

        Args:
            ticker: 库存规范化代码（如 0700.HK / AAPL）
            market: 市场标识（缺省 self.market）
            start/end: 日期区间（YYYY-MM-DD，含 start 不含 end）；新浪接口全量返回，按此切片
            period: 忽略（新浪无周期参数，始终取全量历史后切片）

        Returns:
            DataFrame（index=Date；Open/High/Low/Close 原始 + Adj Close 复权 + Volume + Timezone），
            失败或为空返回 None。美股 Adj Close 为占位前复权（需 anchor_us_adj_close 重建后复权）。
        """
        if ak is None:
            return None
        mkt = market or self.market
        sym = _to_ak_symbol(ticker, mkt)
        _sanitize_proxy_env()
        try:
            if mkt == 'hk':
                return self._fetch_hk(sym, ticker, start, end)
            return self._fetch_us(sym, ticker, start, end)
        except Exception as e:
            logger.warning(f"⚠️ {ticker} 下载失败：{type(e).__name__}: {e}")
            return None

    def download_hk_snapshot_all(self) -> Optional[pd.DataFrame]:
        """一次拉取港股全市场**当日实时快照**（ak.stock_hk_spot，单次请求返回全市场）。

        用于「当日增量快速对齐」：仅覆盖最新交易日单日，且**不含复权因子**——
        调用方必须锚定库中既有后复权序列换算（见 import_hk_daily.import_hk_snapshot_daily）。

        Returns:
            DataFrame（index=交易日期；列 Open/High/Low/Close/Volume/Amount/Timezone，
            附加 prev_close=昨收、raw_code=新浪原始代码、has_adj=False 标记无复权），
            失败或为空返回 None。
        """
        if ak is None:
            return None
        _sanitize_proxy_env()
        try:
            with network_deadline(_BULK_NETWORK_TIMEOUT_SECONDS):
                raw = ak.stock_hk_spot()
        except Exception as e:
            logger.warning(f"⚠️ 港股快照（stock_hk_spot）拉取失败：{type(e).__name__}: {e}")
            return None
        if raw is None or raw.empty:
            return None
        # 新浪快照列名（需容错列名漂移，仅取必要列）
        col = {c: str(c) for c in raw.columns}
        def _col(*names: str) -> Optional[str]:
            """按候选列名返回实际列名（首个命中）或 None。"""
            al = xl = None
            for n in names:
                if n in col:
                    al = col[n]
                    break
            for n in names:
                if n in col.values():
                    xl = n
            return al if al else xl
        c_code = _col('代码')
        c_time = _col('日期时间', '时间')
        c_open = _col('今开')
        c_high = _col('最高')
        c_low = _col('最低')
        c_close = _col('最新价', '最新')
        c_prev = _col('昨收')
        c_vol = _col('成交量')
        c_amt = _col('成交额')
        if not c_code or not c_close:
            return None
        rows: List[Dict[str, Any]] = []
        for _, r in raw.iterrows():
            code = str(r.get(c_code, '')).strip()
            if not code:
                continue
            open_v = self._num(r.get(c_open)) if c_open else None
            high_v = self._num(r.get(c_high)) if c_high else None
            low_v = self._num(r.get(c_low)) if c_low else None
            close_v = self._num(r.get(c_close))
            prev_v = self._num(r.get(c_prev)) if c_prev else None
            vol_v = self._num(r.get(c_vol)) if c_vol else None
            amt_v = self._num(r.get(c_amt)) if c_amt else None
            dt = None
            if c_time:
                try:
                    dt = pd.to_datetime(str(r.get(c_time)))
                except Exception:
                    dt = None
            rows.append({
                'Date': pd.Timestamp(dt) if dt is not None else pd.Timestamp.now().normalize(),
                'code': normalize_code(code, 'hk'),
                'raw_code': code,
                'Open': open_v, 'High': high_v, 'Low': low_v, 'Close': close_v,
                'prev_close': prev_v, 'Volume': vol_v, 'Amount': amt_v,
                'Timezone': self.cfg.timezone,
            })
        if not rows:
            return None
        df = pd.DataFrame(rows).set_index('Date')
        df['has_adj'] = False
        return df

    def download_hk_trade_dates(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Optional[set]:
        """拉取港股**真实交易日**集合（数据源驱动，替代工作日/本地日历粗判）。

        港股除周末外还有本地独有假日（佛诞、重阳、7·1、圣诞等），且与 A 股日历**不一致**
        （例：中秋节 A 股休市、港股照常开市），故港股交易日一律以港股数据源为准，不得用
        `weekday()` 或 A 股 `trade_calendar` 推断。

        数据源（按序降级，均为单请求）：
        1. 恒生指数日线 `ak.stock_hk_index_daily_sina(symbol='HSI')`——指数覆盖全部港股交易日；
        2. 腾讯 00700 日线 `ak.stock_hk_daily(symbol='00700', adjust='')`——回退锚定标的。

        Args:
            start: 起始日期（YYYY-MM-DD，含）；None 表示不设下界
            end: 结束日期（YYYY-MM-DD，含）；None 表示不设上界

        Returns:
            set[datetime.date] 交易日集合；两条数据源均失败返回 None（调用方须保守退回逐只路径）
        """
        if ak is None:
            return None
        _sanitize_proxy_env()
        return self._trade_dates_from((
            lambda: ak.stock_hk_index_daily_sina(symbol='HSI'),
            lambda: ak.stock_hk_daily(symbol='00700', adjust=''),
        ), start, end)

    def download_us_trade_dates(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Optional[set]:
        """拉取美股**真实交易日**集合（数据源驱动，替代工作日粗判）。

        美股假日（感恩节、独立日、圣诞、马丁·路德·金日等）与 A 股/港股均不同，故交易日
        一律以美股数据源为准。数据源（按序降级，均为单请求）：
        1. 纳斯达克指数日线 `ak.index_us_stock_sina(symbol='.IXIC')`；
        2. 苹果日线 `ak.stock_us_daily(symbol='AAPL', adjust='')`——回退锚定标的。

        Args:
            start: 起始日期（YYYY-MM-DD，含）；None 表示不设下界
            end: 结束日期（YYYY-MM-DD，含）；None 表示不设上界

        Returns:
            set[datetime.date] 交易日集合；两条数据源均失败返回 None
        """
        if ak is None:
            return None
        _sanitize_proxy_env()
        return self._trade_dates_from((
            lambda: ak.index_us_stock_sina(symbol='.IXIC'),
            lambda: ak.stock_us_daily(symbol='AAPL', adjust=''),
        ), start, end)

    @staticmethod
    def _trade_dates_from(
        getters: tuple, start: Optional[str], end: Optional[str]
    ) -> Optional[set]:
        """按序尝试各数据源 getter，返回首个可用数据源的交易日集合（按区间过滤）。

        Args:
            getters: 无参 callable 元组，每个返回含 `date` 列的日线 DataFrame
            start/end: 区间边界（YYYY-MM-DD，含）；None 表示不设界

        Returns:
            交易日集合（已按区间裁剪）；全部数据源失败返回 None
        """
        lo = datetime.strptime(start, '%Y-%m-%d').date() if start else None
        hi = datetime.strptime(end, '%Y-%m-%d').date() if end else None
        for getter in getters:
            try:
                with network_deadline(_NETWORK_TIMEOUT_SECONDS):
                    df = getter()
            except Exception:
                df = None
            if df is None or getattr(df, 'empty', True) or 'date' not in df.columns:
                continue
            days = set(pd.to_datetime(df['date']).dt.date)
            if lo:
                days = {d for d in days if d >= lo}
            if hi:
                days = {d for d in days if d <= hi}
            if days:
                return days
        return None

    @staticmethod
    def _num(v: Any) -> Optional[float]:
        """把新浪快照单元格安全转 float（失败/空返回 None）。"""
        try:
            f = float(v)
            return f
        except (TypeError, ValueError):
            return None

    def _fetch_hk(self, sym: str, ticker: str, start: Optional[str], end: Optional[str]) -> Optional[pd.DataFrame]:
        """港股：新浪不复权 + 后复权→组装原始 OHLC 与后复权 Adj Close。"""
        with network_deadline(_NETWORK_TIMEOUT_SECONDS):
            raw = ak.stock_hk_daily(symbol=sym, adjust='')
        with network_deadline(_NETWORK_TIMEOUT_SECONDS):
            hfq = ak.stock_hk_daily(symbol=sym, adjust='hfq')
        if raw is None or raw.empty:
            return None
        raw = raw.set_index(pd.to_datetime(raw['date']))
        raw = raw[~raw.index.duplicated(keep='last')]
        close_hfq = None
        if hfq is not None and not hfq.empty:
            hfq = hfq.set_index(pd.to_datetime(hfq['date']))
            hfq = hfq[~hfq.index.duplicated(keep='last')]
            close_hfq = hfq['close'].reindex(raw.index)
        # 复权序列缺失日按最近倍率填补，避免整行被下游 dropna 丢弃
        close_hfq, n_filled = _fill_lagging_adj(raw['close'], close_hfq)
        if n_filled > 0:
            logger.warning(
                f"⚠️ {ticker} 后复权序列缺失 {n_filled} 个交易日（滞后/间断），"
                f"已按最近可得复权倍率填补（否则这些行会被丢弃）"
            )

        out = pd.DataFrame({
            'Open': raw['open'],
            'High': raw['high'],
            'Low': raw['low'],
            'Close': raw['close'],
            'Adj Close': close_hfq,
            'Volume': raw['volume'],
            'Timezone': self.cfg.timezone,
        })
        return self._slice(out, start, end)

    def _fetch_us(self, sym: str, ticker: str, start: Optional[str], end: Optional[str]) -> Optional[pd.DataFrame]:
        """美股：新浪不复权 + 前复权（占位 Adj Close）。"""
        with network_deadline(_NETWORK_TIMEOUT_SECONDS):
            raw = ak.stock_us_daily(symbol=sym, adjust='')
        with network_deadline(_NETWORK_TIMEOUT_SECONDS):
            qfq = ak.stock_us_daily(symbol=sym, adjust='qfq')
        if raw is None or raw.empty:
            return None
        raw = raw.set_index(pd.to_datetime(raw['date']))
        raw = raw[~raw.index.duplicated(keep='last')]
        q = None
        if qfq is not None and not qfq.empty:
            qfq = qfq.set_index(pd.to_datetime(qfq['date']))
            qfq = qfq[~qfq.index.duplicated(keep='last')]
            q = qfq['close'].reindex(raw.index)
        # 与港股同构：qfq 序列缺失日按最近倍率填补，避免整行被下游 dropna 丢弃
        q, n_filled = _fill_lagging_adj(raw['close'], q)
        if n_filled > 0:
            logger.warning(
                f"⚠️ {ticker} 前复权序列缺失 {n_filled} 个交易日（滞后/间断），"
                f"已按最近可得复权倍率填补（否则这些行会被丢弃）"
            )

        out = pd.DataFrame({
            'Open': raw['open'],
            'High': raw['high'],
            'Low': raw['low'],
            'Close': raw['close'],
            'Adj Close': q,          # 占位前复权，调用方需锚定重建后复权
            'Volume': raw['volume'],
            'Timezone': self.cfg.timezone,
        })
        return self._slice(out, start, end)

    @staticmethod
    def _slice(df: pd.DataFrame, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
        """按日期区间切片（含 start、不含 end）。"""
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index < pd.Timestamp(end)]
        return df

    def _snooze_on_ratelimit(self) -> None:
        """新浪国内源通常不触发 429；保留占位以兼容 BaseDataSource 约定。"""
        import time
        time.sleep(1.0)


def anchor_us_adj_close(conn: Any, code: str) -> float:
    """读取美股该股最近一笔已入库后复权锚点 C = adj_close / raw_close。

    用于把 download_single 的占位【前复权】Adj Close 重建为与存量一致的【后复权】：
        后复权 Adj Close = 前复权 close × C
    若库中无该股记录（新上市）或 raw_close 无有效值，返回 1.0（退化为前复权）。

    Args:
        conn: psycopg2 连接
        code: 美股规范化代码（如 AAPL）

    Returns:
        锚点系数 C（float）
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT adj_close, raw_close FROM stock_quotes "
                "WHERE market='us' AND code=%s AND cycle='1d' "
                "AND adj_close IS NOT NULL AND raw_close IS NOT NULL AND raw_close > 0 "
                "ORDER BY trade_date DESC LIMIT 1",
                (code,),
            )
            row = cur.fetchone()
        if row and row[0] and row[1]:
            return float(row[0]) / float(row[1])
    except Exception:
        pass
    return 1.0


# 便捷工厂
def create_akshare_source(market: str = 'hk') -> AkShareDataSource:
    """创建 AkShare 数据源适配器（市场参数化）。"""
    return AkShareDataSource(market=market)


if __name__ == '__main__':
    # 自测：拉取腾讯港股日线（需国内直连，关闭系统代理）
    import argparse
    p = argparse.ArgumentParser(description='AkShare 适配器自测')
    p.add_argument('--ticker', default='0700.HK')
    p.add_argument('--market', default='hk')
    args = p.parse_args()
    src = create_akshare_source(args.market)
    ok = src.connect()
    print(f"连接: {ok}")
    df = src.download_single(normalize_code(args.ticker, args.market), market=args.market)
    if df is None or df.empty:
        print("❌ 拉取失败或为空")
    else:
        print(f"✅ {args.ticker} 拉取 {len(df)} 行，列: {list(df.columns)}")
        print(df.tail(3))