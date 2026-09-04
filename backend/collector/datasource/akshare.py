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
from datetime import datetime
from typing import Optional, Dict, List, Any

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

_PROXY_ENV_KEYS = ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
                   'all_proxy', 'ALL_PROXY')


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
        except Exception:
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
            return None

    def _fetch_hk(self, sym: str, ticker: str, start: Optional[str], end: Optional[str]) -> Optional[pd.DataFrame]:
        """港股：新浪不复权 + 后复权→组装原始 OHLC 与后复权 Adj Close。"""
        raw = ak.stock_hk_daily(symbol=sym, adjust='')
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
        else:
            # 后复权缺失时退化为原始价（记录到日志由调用方提示）
            close_hfq = raw['close']

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
        raw = ak.stock_us_daily(symbol=sym, adjust='')
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
        else:
            q = raw['close']

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