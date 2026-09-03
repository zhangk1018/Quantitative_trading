#!/usr/bin/env python3
"""
Yahoo 金融数据源适配器（协作单 30.0 V2 / M2 基石）

通过 yfinance 拉取全球市场行情与基本面，供港股/美股 ETL 使用。

关键设计（对齐方案 v2 §3.1 / §1.2）：
- MarketConfig 市场特性抽象：避免 `if market=='hk'` 散落业务，扩展日/英只需加配置
- 代码规范化：港股去前导零保留≥1位（`09988.HK`→`9988.HK`、`00001.HK`→`1.HK`）
- 分片下载 + 随机休眠防 429（单批≤20 只 + 429 随机休眠 10-30s + 批间 1-3s）
- 复权口径：`auto_adjust=False` 取原始价 + `Adj Close`（后复权），由调用方存 `raw_*`+`adj_*`
- 代理配置：读 `yf.config.network.proxy`（网络由 K 打通）

本适配器【继承 BaseDataSource】以复用 DataSourceManager 的 failover 机制，
同时提供批量/市场级方法（download_history / get_market_list / get_fundamentals）。
"""
import sys
import os
import time
import random
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd

# 保证 `import utils.logger` 可解析（脚本独立运行时）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from utils.logger import setup_logger
    logger = setup_logger('yahoo_datasource')
except Exception:  # 库被导入但日志组件不可用时降级
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('yahoo_datasource')

try:
    import yfinance as yf
except ImportError as e:  # pragma: no cover
    yf = None
    logger.warning(f"yfinance 未安装: {e}（安装：./venv/bin/pip install yfinance）")

from collector.datasource.base import BaseDataSource  # noqa: E402


# =====================================================================
# 市场特性配置
# =====================================================================
@dataclass
class MarketConfig:
    """市场特性抽象：集中描述某市场的下载/清洗/存储特性。

    新增市场（如日本 .T / 英国 .L）只需在此加一条配置，业务代码零改动。
    """
    market: str                                    # 市场标识：cn / hk / us ...
    currency: str                                  # 本位币：CNY / HKD / USD
    timezone: str                                  # 默认时区（缺失时用）
    yahoo_suffix: str = ""                          # Yahoo 代码后缀（美股空，港股 .HK）
    has_limit_up_down: bool = False                 # 是否有涨跌停（仅 A 股）
    trading_hours: str = "09:30-16:00"             # 描述用
    default_period: str = "max"                     # --init 全量拉取周期
    incremental_lookback_days: int = 7              # 增量兜底回溯天数（通常从最后交易日+1）
    # 分片与限流参数
    batch_size: int = 20                            # 单批最大标的数
    batch_retry_min_sleep: float = 10.0            # 429 重试随机休眠下限（秒）
    batch_retry_max_sleep: float = 30.0            # 429 重试随机休眠上限（秒）
    batch_interval_min_sleep: float = 1.0         # 批间随机休眠下限（秒）
    batch_interval_max_sleep: float = 3.0        # 批间随机休眠上限（秒）
    max_retries: int = 3                            # 单批最大重试次数
    # 停牌处理
    suspended_log_threshold_days: int = 30         # 停牌超过该天数在 ETL 日志记录
    # 基本面字段映射（Yahoo info key -> 本项目字段名）
    fundamental_fields: Dict[str, str] = field(default_factory=lambda: {
        'marketCap': 'total_mv',
        'trailingPE': 'pe',
        'priceToBook': 'pb',
        'fiftyTwoWeekHigh': 'year_high',
        'fiftyTwoWeekLow': 'year_low',
        'currency': 'currency',
        'exchange': 'exchange',
        'timezoneName': 'timezone',
    })


# 预置市场配置（仅港/美，后续日/英可追加）
MARKET_CONFIGS: Dict[str, MarketConfig] = {
    'hk': MarketConfig(
        market='hk', currency='HKD', timezone='Asia/Hong_Kong',
        yahoo_suffix='.HK', has_limit_up_down=False, trading_hours='09:30-16:00',
    ),
    'us': MarketConfig(
        market='us', currency='USD', timezone='America/New_York',
        yahoo_suffix='', has_limit_up_down=False, trading_hours='09:30-16:00',
        default_period='max',
    ),
}


def get_market_config(market: str) -> MarketConfig:
    """获取市场配置，未知市场抛 ValueError。"""
    if market not in MARKET_CONFIGS:
        raise ValueError(f"不支持的 market: {market}（支持: {list(MARKET_CONFIGS)}）")
    return MARKET_CONFIGS[market]


# =====================================================================
# 代码规范化
# =====================================================================
def _normalize_hk_code(code: str) -> str:
    """港股代码规范化：规范化为 4 位宽（右对齐，不足补前导零），附带 .HK 后缀。

    实测关键（2026-09-03）：Yahoo 港股代码固定【4 位宽】，不足 4 位须补前导零，
    **不能**去前导零到短码——否则 404：
      '0700.HK' -> '0700.HK'（4 位，保留前导零）
      '700'     -> '0700.HK'（不足 4 位补零）
      '09988.HK' -> '9988.HK'（超 4 位去前导零到 4 位：09988→9988）
      '1299.HK' -> '1299.HK'（已是 4 位）
      '1.HK'     -> '0001.HK'（1→0001）
    """
    code = str(code).strip().upper()
    if code.endswith('.HK'):
        num = code[:-3]
    elif '.' in code:  # 其他后缀（.SS/.SZ 等）不属港股，原样返回调用方自行处理
        return code
    else:
        num = code
    # 仅保留数字部分；先取有效整数再去前导零，避免 '00001' 这类
    try:
        num_int = int(num)
    except ValueError:
        return f"{num}.HK"
    # 超 4 位则去前导零（09988→9988）；否则补零到 4 位（700→0700）
    if num_int >= 10000:
        digits = str(num_int)
    else:
        digits = str(num_int).zfill(4)
    return f"{digits}.HK"


def normalize_code(code: str, market: str) -> str:
    """按市场规范化代码（入库统一格式）。

    港股：去前导零 + .HK（`_normalize_hk_code`）
    美股：原样（大写）
    """
    if market == 'hk':
        return _normalize_hk_code(code)
    if market == 'us':
        return str(code).strip().upper()
    return str(code).strip()


# =====================================================================
# Yahoo 数据源适配器
# =====================================================================
class YahooDataSource(BaseDataSource):
    """基于 yfinance 的 Yahoo 数据源适配器。

    复用 BaseDataSource 抽象（get_stock_list / get_kline 等），以便 DataSourceManager
    统一 failover；额外提供批量/市场级方法供港股/美股 ETL 使用：
      - download_history(tickers, market, start, end)  # 批量日线，天然复权+停牌清洗
      - get_market_list(market)                         # 港股列表
      - get_fundamentals(code)                          # 单标的基本面（低频）
    """

    name = 'Yahoo'
    requires_token = False
    supported_cycles = ['daily', 'weekly', 'monthly']

    def __init__(self, market: str = 'hk'):
        """Args:
            market: 市场标识（hk/us），决定代码规范化、时区、限流配置。
        """
        self.market = market
        self.cfg = get_market_config(market)
        self.connected = False
        self._configure_network()

    # ---------- BaseDataSource 抽象实现 ----------
    def connect(self) -> bool:
        if yf is None:
            logger.error("yfinance 未安装，无法连接 Yahoo 数据源")
            return False
        self.connected = True
        return True

    def disconnect(self) -> bool:
        self.connected = False
        return True

    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表（港股用 get_market_list；此处于通用接口下默认返回港股列表）。"""
        return self.get_market_list(self.market)

    def get_kline(
        self,
        code: str,
        cycle: str = 'daily',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """按 BaseDataSource 契约返回单标的历史 K 线（原始价 + 后复权 adj_close）。"""
        ticker = normalize_code(code, self.market)
        df = self.download_single(ticker, market=self.market, start=start_date, end=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        # 统一列名（小写 + 复权字段），对齐 A 股 ETL 下游
        out = df.rename(columns={
            'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close',
            'Adj Close': 'adj_close', 'Volume': 'volume',
        }).reset_index()
        out = out.rename(columns={'Date': 'trade_date'})
        out['code'] = ticker
        out['cycle'] = cycle
        return out

    # ---------- 网络/限流配置 ----------
    @staticmethod
    def _configure_network() -> None:
        """配置 yf 全局网络参数（代理/重试）。仅在 yfinance 可用且为首次时设置。"""
        if yf is None:
            return
        try:
            proxy = os.environ.get('YAHOO_PROXY') or os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
            if proxy:
                yf.config.network.proxy = proxy
                logger.info(f"已配置 Yahoo 代理: {proxy}")
            yf.config.network.retries = 3
        except Exception as e:
            logger.warning(f"配置 Yahoo 网络参数失败: {e}")

    def _snooze_on_ratelimit(self) -> None:
        """429 限流后随机休眠，避免集中重试加剧风控。"""
        sleep_sec = random.uniform(self.cfg.batch_retry_min_sleep, self.cfg.batch_retry_max_sleep)
        logger.warning(f"⏳ 疑似 Yahoo 限流，随机休眠 {sleep_sec:.1f}s 后重试...")
        time.sleep(sleep_sec)

    def _interval_sleep(self) -> None:
        """批间随机休眠，保护代理 IP。"""
        sleep_sec = random.uniform(self.cfg.batch_interval_min_sleep, self.cfg.batch_interval_max_sleep)
        time.sleep(sleep_sec)

    # ---------- 单标的历史 ----------
    def download_single(
        self,
        ticker: str,
        market: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        period: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """拉取单标的日线，`auto_adjust=False` 保原始价 + Adj Close（后复权）。

        Args:
            ticker: Yahoo ticker（如 9988.HK / AAPL）
            market: 市场标识（用于代码规范化，缺省用 self.market）
            start/end: 日期区间（YYYY-MM-DD，含 start 不含 end）
            period: 或指定周期（max/1y/...），与 start/end 二者最多一项

        Returns:
            DataFrame（Yahoo 原生列），失败或为空返回 None；NaN 行已在调用侧清洗。
        """
        if yf is None:
            return None
        mkt = market or self.market
        try:
            kw: Dict[str, Any] = {'interval': '1d', 'auto_adjust': False, 'prepost': False}
            if start:
                kw['start'] = start
            if end:
                kw['end'] = end
            if period:
                kw['period'] = period
            df = yf.Ticker(ticker).history(**kw)
            if df is None or df.empty:
                return df
            # 补充 timezone（Yahoo 偶发缺失，按市场默认）
            if 'Timezone' not in df.columns:
                df['Timezone'] = get_market_config(mkt).timezone
            return df
        except Exception as e:
            msg = str(e)
            if 'Rate limit' in msg or '429' in msg or 'Too Many Requests' in msg:
                logger.warning(f"⏳ {ticker} 触发 Yahoo 限流: {msg}")
                self._snooze_on_ratelimit()
            else:
                logger.warning(f"⚠️ {ticker} 拉取失败: {msg}")
            return None

    # ---------- 批量下载（分片 + 限流） ----------
    def download_history(
        self,
        tickers: List[str],
        market: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        period: Optional[str] = None,
    ) -> Dict[str, pd.DataFrame]:
        """批量下载日线，分片（≤batch_size）+ 批间随机休眠 + 单批内逐只调用以精确 429 退避。

        Args:
            tickers: Yahoo ticker 列表（需已规范化为 Yahoo 格式）
            market: 市场标识（缺省 self.market）
            start/end/period: 同 download_single

        Returns:
            {ticker: DataFrame}，失败标的返回 None（保留键以区分"无数据"）。
        """
        mkt = market or self.market
        result: Dict[str, Optional[pd.DataFrame]] = {}
        # 规范化代码（保证港股去前导零）
        norm_tickers = [normalize_code(t, mkt) for t in tickers]
        # 分片
        chunks = [norm_tickers[i:i + self.cfg.batch_size] for i in range(0, len(norm_tickers), self.cfg.batch_size)]
        total = len(norm_tickers)
        done = 0
        for chunk in chunks:
            for attempt in range(self.cfg.max_retries + 1):
                for t in chunk:
                    df = self.download_single(t, market=mkt, start=start, end=end, period=period)
                    result[t] = df
                    done += 1
                # 若本批全部成功（或无 429），结束重试
                failed = [t for t in chunk if result.get(t) is None]
                if not failed or attempt >= self.cfg.max_retries:
                    logger.info(f"📦 批量下载进度 {done}/{total}")
                    break
                logger.warning(f"🔁 批次 {chunk} 中 {len(failed)} 只失败，第 {attempt+1} 次重试")
                self._snooze_on_ratelimit()
            self._interval_sleep()
        return result

    # ---------- 港股列表 ----------
    def get_market_list(self, market: str) -> pd.DataFrame:
        """获取市场标的列表（方案 M0 三路径配置化）。

        港股（主源 = 新浪全市场）：
          - `ak.stock_hk_spot()`（新浪港股全市场实时列表，~2800 只，含代码+中文名+英文名），
            实测 2026-09-03 可用，比 Yahoo 指数成分（^HSI/^HSCE 的 info.components 实测为空）
            更完整、稳定。
          - Yahoo 指数成分兜底（若新浪不可用）。
        美股（主源 = 指数成分）：
          - ^GSPC（标普 500）info.components；Yahoo 对美股指数 info.components 通常可用。

        Args:
            market: 市场标识（hk/us）

        Returns:
            DataFrame: code(Jahoo 规范化), name, exchange, market
        """
        mkt_cfg = get_market_config(market)
        if market == 'hk':
            df = self._fetch_hk_list_sina()
            if df is not None and not df.empty:
                return df
            logger.warning('⚠️ 新浪港股列表不可用，回退 Yahoo 指数成分兜底')
            return self._fetch_market_list_yahoo(market)
        # 美股：核心池配置（主，K 批示 ~600 只）
        df = self._fetch_market_list_universe()
        if df is not None and not df.empty:
            return df
        logger.warning('⚠️ 美股核心池清单不可用，回退 Yahoo 指数成分兜底')
        return self._fetch_market_list_yahoo(market)

    def _fetch_market_list_universe(self) -> Optional[pd.DataFrame]:
        """从 `backend/config/us_core_universe.json` 读美股核心池清单（市场=us）。

        与方案 §8「宽白名单 + Ticker 判异常」一致：此处仅组装代码，实际有效性由
        `sync_us_stock_list`（V3）在落库前用 Yahoo Ticker.info 逐个校验剔除无效码。
        """
        import json as _json
        mkt = 'us'
        path = Path(__file__).resolve().parents[3] / 'backend/config/us_core_universe.json'
        try:
            data = _json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            logger.warning(f"⚠️ 读取美股核心池清单失败: {e}")
            return None
        symbols = data.get('symbols', []) if isinstance(data, dict) else []
        rows = [{
            'code': normalize_code(s, mkt),
            'name': s,
            'exchange': 'NMS',
            'market': mkt,
        } for s in symbols if str(s).strip()]
        return pd.DataFrame(rows).drop_duplicates(subset=['code']).reset_index(drop=True)

    def _fetch_hk_list_sina(self) -> Optional[pd.DataFrame]:
        """从新浪获取港股全市场列表（ak.stock_hk_spot），规范化 code 为 Yahoo 4 位宽。"""
        try:
            import akshare as ak
            raw = ak.stock_hk_spot()
            if raw is None or raw.empty:
                return None
            rows: List[Dict[str, Any]] = []
            for _, r in raw.iterrows():
                code = str(r.get('代码', '')).strip()
                if not code:
                    continue
                rows.append({
                    'code': _normalize_hk_code(code),   # 00001 -> 0001.HK
                    'name': r.get('中文名称') or r.get('英文名称') or code,
                    'exchange': 'HKEX',
                    'market': self.market,
                })
            out = pd.DataFrame(rows)
            return out.drop_duplicates(subset=['code']).reset_index(drop=True)
        except Exception as e:
            logger.warning(f"⚠️ 新浪港股列表拉取失败: {e}")
            return None

    def _fetch_market_list_yahoo(self, market: str) -> pd.DataFrame:
        """从 Yahoo 指数成分获取列表（兜底；美股 ^GSPC / 港股 ^HSI+^HSCE）。"""
        mkt_cfg = get_market_config(market)
        idx_symbols = ('^HSI', '^HSCE') if market == 'hk' else ('^GSPC',)
        rows: List[Dict[str, Any]] = []
        for idx_symbol in idx_symbols:
            try:
                comps = yf.Ticker(idx_symbol).info.get('components', [])
                for c in comps:
                    rows.append({
                        'code': normalize_code(c, market),
                        'name': c,
                        'exchange': 'HKEX' if market == 'hk' else 'NMS',
                        'market': market,
                    })
            except Exception as e:
                logger.warning(f"⚠️ 拉取 {idx_symbol} 成分失败: {e}")
                self._snooze_on_ratelimit()
            self._interval_sleep()
        return pd.DataFrame(rows).drop_duplicates(subset=['code']).reset_index(drop=True)

    # ---------- 基本面 ----------
    def get_fundamentals(self, code: str, market: Optional[str] = None) -> Dict[str, Any]:
        """拉取单标的基本面（低频调用，勿每日全市场遍历）。

        `Ticker.info` 风控远比 history 严，仅在每周/除权/财报日等批量低频场景使用。

        Args:
            code: 股票代码（未规范化则按市场规范化）

        Returns:
            dict，键为项目字段（total_mv/pe/pb/year_high/low/currency/exchange/timezone）
        """
        mkt = market or self.market
        cfg = get_market_config(mkt)
        ticker = normalize_code(code, mkt)
        if yf is None:
            return {}
        try:
            info = yf.Ticker(ticker).info
            out: Dict[str, Any] = {}
            for yk, fk in cfg.fundamental_fields.items():
                if info.get(yk) is not None:
                    out[fk] = info.get(yk)
            out.setdefault('currency', cfg.currency)
            out.setdefault('timezone', cfg.timezone)
            out.setdefault('exchange', None)
            return out
        except Exception as e:
            msg = str(e)
            if 'Rate limit' in msg or '429' in msg:
                self._snooze_on_ratelimit()
            logger.warning(f"⚠️ {ticker} 基本面拉取失败: {msg}")
            return {}


# 便捷工厂
def create_yahoo_source(market: str = 'hk') -> YahooDataSource:
    """创建 Yahoo 数据源适配器（市场参数化）。"""
    return YahooDataSource(market=market)


if __name__ == '__main__':
    # 自测：拉取腾讯日线（需网络可用，当前出口若 429 会打印限流提示）
    import argparse
    p = argparse.ArgumentParser(description='Yahoo 适配器自测')
    p.add_argument('--ticker', default='9988.HK')
    p.add_argument('--period', default='1y')
    args = p.parse_args()
    src = create_yahoo_source('hk')
    ok = src.connect()
    print(f"连接: {ok}")
    df = src.download_single(args.ticker, start=(date.today() - timedelta(days=400)).isoformat())
    if df is None or df.empty:
        print("❌ 拉取失败或为空（可能限流）")
    else:
        print(f"✅ {args.ticker} 拉取 {len(df)} 行，列: {list(df.columns)}")
        print(df.tail(3))