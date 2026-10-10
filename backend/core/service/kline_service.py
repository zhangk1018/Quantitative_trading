"""
kline_service.py - K线数据服务
提供股票K线数据查询、处理和分析功能。
"""
import pandas as pd
import numpy as np
from typing import List, Optional, Dict
from datetime import datetime, timedelta, date
from decimal import Decimal
import time
import random
import os
import logging
logger = logging.getLogger(__name__)
from collector.db.loader import DataLoader
from collector.storage.postgresql_storage import PostgreSQLStorage
from core.api.models.schemas import (
    KLineResponse, KLineItem, StockResponse,
)
from shared.schemas import PatternMarker


class _AdjustNotSupported(Exception):
    """请求的复权口径无法由库内序列换算（协作单 45.0）。

    由 `get_kline_data` 捕获 → 把响应 `adj_method` 置为**实际返回数据的口径**
    （`eff_method`，缺省 none）并写入可见 `warning`，避免「声称已复权、实为其他口径」
    的静默错误契约。
    """

    def __init__(self, message: str, eff_method: str = 'none'):
        super().__init__(message)
        self.eff_method = eff_method


class KlineService:
    """K线数据服务"""
    # 缓存配置
    CACHE_SIZE = 100  # 缓存100只股票
    CACHE_TTL = 600   # 10分钟过期

    def __init__(self, loader: DataLoader, storage: PostgreSQLStorage = None):
        self.loader = loader
        self.df = loader.df
        self.trade_date = loader.trade_date
        self._storage = storage

        # 缓存存储
        self._cache = {}  # {stock_code_period: (expire_time, data)}

    def _generate_mock_kline(self, base_price: float, limit: int) -> pd.DataFrame:
        """生成模拟 K线数据（仅 debug 模式可用）"""
        if not os.environ.get("DEBUG", "").lower() in ("true", "1"):
            return pd.DataFrame(columns=[
                "trade_date", "open", "high", "low", "close", "volume", "amount"
            ])
        dates = []
        base_date = datetime.strptime(self.trade_date.replace('-', ''), "%Y%m%d")
        
        for i in range(limit, 0, -1):
            trade_date = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
            # 生成随机波动
            change = (random.random() - 0.5) * 0.04  # ±2% 波动
            open_price = base_price * (1 + change)
            high_price = open_price * (1 + random.random() * 0.02)
            low_price = open_price * (1 - random.random() * 0.02)
            close_price = (high_price + low_price) / 2 + (random.random() - 0.5) * (high_price - low_price)
            volume = int(random.randint(1000000, 10000000))
            amount = float(close_price * volume / 100)
            
            dates.append({
                "trade_date": trade_date,
                "open": Decimal(str(round(open_price, 2))),
                "high": Decimal(str(round(high_price, 2))),
                "low": Decimal(str(round(low_price, 2))),
                "close": Decimal(str(round(close_price, 2))),
                "volume": volume,
                "amount": Decimal(str(round(amount, 2)))
            })
            
            base_price = float(close_price)
        
        return pd.DataFrame(dates)

    def get_kline_data(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily",
        limit: int = 100,
        adj_method: str = "none",
    ) -> Optional[KLineResponse]:
        """获取K线数据

        Args:
            stock_code: 股票代码
            start_date: 开始日期 (YYYYMMDD格式)
            end_date: 结束日期 (YYYYMMDD格式)
            period: 周期类型 (daily, weekly, monthly, minute)
            limit: 最大返回条数
            adj_method: 复权方式 (none/forward/backward)

        Returns:
            KLineResponse对象，包含K线数据列表
        """
        # 生成缓存键（包含日期范围，避免不同日期返回相同缓存数据）
        date_part = f"{start_date or ''}_{end_date or ''}"
        cache_key = f"kline_v2_{stock_code}_{period}_{limit}_{adj_method}_{date_part}"
        
        # 检查缓存
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # 1. 优先从数据库读取真实数据
        kline_df = pd.DataFrame()
        if self._storage is not None:
            try:
                # 标准化代码格式（兼容 sh.600000 / sz.000001 / 600000 三种写法）
                db_code = stock_code
                for prefix in ('sh.', 'sz.', 'SH.', 'SZ.'):
                    if db_code.startswith(prefix):
                        db_code = db_code.replace(prefix, '').lower()

                # 转换日期格式（API 用 YYYYMMDD，storage 用 YYYY-MM-DD）
                s = start_date
                e = end_date
                if s and len(s) == 8:
                    s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
                if e and len(e) == 8:
                    e = f"{e[:4]}-{e[4:6]}-{e[6:]}"

                # 【核心修改】尝试使用联合查询获取带指标的数据
                kline_df = self._storage.get_kline_with_indicators(
                    code=db_code,
                    cycle=period,
                    start_date=s,
                    end_date=e,
                    limit=limit
                )

                # 如果联合查询没拿到数据（比如表还没建好），降级使用基础查询
                if kline_df.empty:
                    raw = self._storage.get_quotes(code=db_code, cycle=period, start_date=s, end_date=e)
                    if not raw.empty:
                        kline_df = raw.copy()
                        if 'trade_date' in kline_df.columns:
                            kline_df = kline_df.drop_duplicates(subset=['trade_date'], keep='last')
                            kline_df['trade_date'] = pd.to_datetime(kline_df['trade_date']).dt.strftime('%Y-%m-%d')
                        kline_df = kline_df.sort_values('trade_date', ascending=False).head(limit)
                        kline_df = kline_df.sort_values('trade_date', ascending=True)

            except Exception as e:
                logger.error(f"数据库查询异常: {e}")
                kline_df = pd.DataFrame()

        # 2. 数据库无数据时降级使用 mock（仅 debug 模式）
        # 退市股/无效代码：stock_info 为 None 时返回空
        if kline_df.empty:
            stock_info = self._get_stock_info(stock_code)
            if stock_info is None:
                # 退市/无效代码：返回空数组
                kline_df = pd.DataFrame(columns=[
                    "trade_date", "open", "high", "low", "close", "volume", "amount"
                ])
            else:
                base_price = 10.0
                if stock_info.close:
                    base_price = float(stock_info.close)
                kline_df = self._generate_mock_kline(base_price, limit)

        # 3. 应用日期范围过滤
        if start_date or end_date:
            kline_df = self._filter_by_date_range(kline_df, start_date, end_date)

        # 转换日期为字符串（YYYY-MM-DD）以匹配 KLineItem 期望格式
        if not kline_df.empty and "trade_date" in kline_df.columns:
            kline_df["trade_date"] = kline_df["trade_date"].apply(
                lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x)
            )

        # 转换为K线项列表
        kline_items = self._convert_to_kline_items(kline_df)

        # 复权（协作单 45.0 订正）
        # 库内主价格列口径已统一为**前复权**：cn=qfq(Baostock adjustflag=2)、
        # hk=由 raw_*/adj_*(hfq)/adj_share 精确重建的 qfq、us=新浪 qfq。
        # 历史坑：原实现 `from backend.imputer import Adjuster` 引用的模块已于 1978bcf 删除
        # → ImportError 被下方 except 吞掉 → **数据未换算却回显 adj_method=forward**（静默错误契约）；
        # 45.0 首版又对港股用「乘性重标定」把仿射序列压平。现统一按库内前复权原样返回，
        # none/backward 分别改用 raw_*/adj_*；无法换算时按**实际口径**回填并给出可见 warning。
        warning_msg = None
        latest_factor = None
        eff_method = 'none'
        if kline_df is not None and not kline_df.empty:
            try:
                kline_df, eff_method, latest_factor = self._apply_adjust(
                    kline_df, stock_code, adj_method, period,
                )
                kline_items = self._convert_to_kline_items(kline_df)
            except _AdjustNotSupported as e:
                eff_method = getattr(e, 'eff_method', 'none')
                warning_msg = str(e)
                logger.warning(f'⚠️ {stock_code} 复权口径不可得（实际返回 {eff_method}）：{warning_msg}')
            except Exception as e:
                eff_method = 'forward'
                warning_msg = f'复权处理失败，已按库内前复权序列返回（{type(e).__name__}: {e}）'
                logger.warning(f'⚠️ {stock_code} {warning_msg}')

        # 查询 pattern_markers（K 2026-07-06 需求：前端直接渲染 TA-Lib 结果）
        pattern_dicts = self._query_pattern_markers(stock_code, kline_df)
        pattern_markers = [
            PatternMarker(trade_date=datetime.strptime(m['date'], '%Y-%m-%d').date(), patterns=m['patterns'])
            for m in pattern_dicts
        ]

        # 查询除权除息日（协作单 31.0：前端 K 线标注 factor_date）
        ex_dates = self._query_ex_dates(stock_code, kline_df)

        # 构建响应
        response = KLineResponse(
            stock_code=stock_code,
            data=kline_items,
            count=len(kline_items),
            adj_method=eff_method,
            latest_factor=latest_factor,
            warning=warning_msg,
            pattern_markers=pattern_markers,
            ex_dates=ex_dates,
        )
        
        # 存入缓存
        self._set_cache(cache_key, response)
        
        return response

    def _get_from_cache(self, cache_key: str):
        """从缓存获取数据"""
        if cache_key in self._cache:
            expire_time, data = self._cache[cache_key]
            if time.time() < expire_time:
                return data
            else:
                # 缓存过期，删除
                del self._cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, data):
        """设置缓存"""
        # 如果缓存已满，删除最早的10%
        if len(self._cache) >= self.CACHE_SIZE:
            # 按插入顺序删除最早的 10%（Python 3.7+ dict 保序），避免 O(n log n) 排序
            to_delete_count = int(self.CACHE_SIZE * 0.1)
            for _ in range(to_delete_count):
                if self._cache:
                    self._cache.pop(next(iter(self._cache)))
        
        # 设置新缓存（过期时间=当前时间+TTL）
        self._cache[cache_key] = (time.time() + self.CACHE_TTL, data)

    def _get_stock_info(self, stock_code: str) -> Optional[StockResponse]:
        """获取股票基本信息"""
        from core.service.screener_service import ScreenerService
        screener_service = ScreenerService(self.loader)
        return screener_service.get_stock_by_code(stock_code)

    def _filter_by_date_range(
        self,
        df: pd.DataFrame,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        按日期范围过滤 K 线数据

        Args:
            df: 原始 K 线 DataFrame
            start_date: 开始日期 (YYYYMMDD 或 YYYY-MM-DD)
            end_date: 结束日期 (YYYYMMDD 或 YYYY-MM-DD)
        """
        if df.empty:
            return df

        # 标准化 trade_date 为 YYYY-MM-DD 字符串用于比较
        dates = pd.to_datetime(df["trade_date"], errors="coerce")

        if start_date:
            start_norm = self._normalize_date(start_date)
            if start_norm:
                dates_mask = dates >= pd.Timestamp(start_norm)
                df = df[dates_mask].copy()

        if end_date:
            end_norm = self._normalize_date(end_date)
            if end_norm:
                # 包含 end_date 当天
                dates_mask = dates <= pd.Timestamp(end_norm)
                df = df[dates_mask].copy()

        return df.reset_index(drop=True)

    @staticmethod
    def _normalize_date(date_str: str) -> Optional[str]:
        """将 YYYYMMDD 或 YYYY-MM-DD 统一为 YYYY-MM-DD"""
        if not date_str:
            return None
        date_str = date_str.strip()
        if len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        # 假设已经是 YYYY-MM-DD
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except ValueError:
            return None

    def _query_pattern_markers(self, stock_code: str, kline_df: pd.DataFrame) -> List[Dict]:
        """查询 stock_indicators 表，返回时间范围内的 K线形态标记

        Args:
            stock_code: 股票代码
            kline_df: K线数据 DataFrame（用于获取时间范围）

        Returns:
            形态标记列表，格式 [{"date": "YYYY-MM-DD", "patterns": ["hammer"]}, ...]
            失败时返回空数组，不影响 K线主数据返回
        """
        if self._storage is None or kline_df.empty or 'trade_date' not in kline_df.columns:
            return []

        # 获取时间范围（与 K线请求一致）
        dates = pd.to_datetime(kline_df['trade_date'], errors='coerce')
        valid_dates = dates.dropna()
        if valid_dates.empty:
            return []
        start_date = valid_dates.min().strftime('%Y-%m-%d')
        end_date = valid_dates.max().strftime('%Y-%m-%d')

        # 标准化股票代码（去掉 sh./sz. 前缀）
        db_code = stock_code
        for prefix in ('sh.', 'sz.', 'SH.', 'SZ.'):
            if db_code.startswith(prefix):
                db_code = db_code.replace(prefix, '').lower()

        try:
            return self._storage.get_pattern_markers(db_code, start_date, end_date)
        except (ValueError, KeyError) as e:
            logger.warning(f"pattern_markers 查询失败 ({stock_code}): {e}")
            return []

    # ================================================================
    # 复权换算（协作单 45.0 / 订正）
    # ================================================================
    PRICE_COLS = ('open', 'high', 'low', 'close')

    def _apply_adjust(self, df: pd.DataFrame, stock_code: str, method: str, cycle: str):
        """把库内主价格序列换算到请求的复权口径（协作单 45.0 订正）。

        库内主价格列（open/high/low/close）口径 —— 订正后**统一为前复权**：
        - **cn**：前复权(qfq) —— `baostock.py::_ADJUST_FLAG = '2'`；
        - **hk**：前复权(qfq) —— 由 `raw_*`/`adj_*(后复权)`/`adj_share` 精确重建
          （见 `collector.utils.adj_adjust.compute_qfq_prices`）；
        - **us**：前复权(qfq) —— 新浪 `adjust='qfq'`。

        请求口径换算（hk/us 另存 `raw_close` 原始价、hk 另存 `adj_close` 后复权价）：
        - `forward`：库内已满足 → 原样返回（三市场一致，**不再做任何重标定**）；
        - `none`：hk/us 改用 `raw_close`（原始成交价 = 不复权）；cn 库内无原始价 → 抛错降级；
        - `backward`：hk 改用 `adj_close`（后复权 hfq）；cn/us 库内无后复权序列 → 抛错降级。

        订正背景：港股主价格列原存**后复权**，`forward` 用「乘性重标定
        `k = raw_now/hfq_now`」换算，对**仿射**口径（`hfq = a·raw + b`）会把历史压平
        （碧桂园 2025-12 真实 0.415 显示成 0.19）。现改为库内落库即前复权。

        Args:
            df: 库内 K 线（含 open/high/low/close，可选 raw_*/adj_*）
            stock_code: 股票代码（各市场写法）
            method: none / forward / backward
            cycle: 周期（1d/1w/1m）

        Returns:
            (换算后的 df, 实际生效口径, latest_factor)

        Raises:
            _AdjustNotSupported: 该口径无法由库内序列换算（携带实际返回口径 eff_method）
        """
        from utils.stock_code_utils import infer_market

        # 与主查询一致地归一化代码（前端可能传 sh.600000 / sz.000001）
        norm = stock_code
        for prefix in ('sh.', 'sz.', 'SH.', 'SZ.'):
            if norm.startswith(prefix):
                norm = norm.replace(prefix, '').lower()
        market = infer_market(norm)

        if method == 'forward':
            # 库内主价格列已是前复权（cn/hk/us 统一）→ 原样返回
            return df, 'forward', None

        if method == 'none':
            if market in ('hk', 'us') and self._has_price_col(df, 'raw_'):
                return self._price_from(df, 'raw_'), 'none', None
            raise _AdjustNotSupported(
                '库内该市场未存原始成交价（raw_close），无法返回不复权，'
                '已按库内前复权序列返回',
                eff_method='forward',
            )

        if method == 'backward':
            if market == 'hk' and self._has_price_col(df, 'adj_'):
                return self._price_from(df, 'adj_'), 'backward', None
            raise _AdjustNotSupported(
                '库内该市场无后复权序列，无法返回后复权，已按库内前复权序列返回',
                eff_method='forward',
            )

        raise _AdjustNotSupported(
            f'未知复权方式 {method}，已按库内前复权序列返回', eff_method='forward',
        )

    @classmethod
    def _has_price_col(cls, df: pd.DataFrame, prefix: str) -> bool:
        """df 是否含可用的 <prefix>close（原始价/后复权价）列。"""
        col = f'{prefix}close'
        return col in df.columns and bool(pd.to_numeric(df[col], errors='coerce').notna().any())

    @classmethod
    def _price_from(cls, df: pd.DataFrame, prefix: str) -> pd.DataFrame:
        """用 <prefix>open/high/low/close 覆盖主价格列（缺失单元格回退库内主价格列）。"""
        out = df.copy()
        for c in cls.PRICE_COLS:
            src = f'{prefix}{c}'
            if src in df.columns:
                out[c] = pd.to_numeric(df[src], errors='coerce').fillna(
                    pd.to_numeric(df[c], errors='coerce')
                )
        return out

    def _query_ex_dates(self, stock_code: str, kline_df: pd.DataFrame) -> List[date]:
        """查询 stock_adj_factor 表，返回时间范围内的除权除息日（factor_date）。

        与 _query_pattern_markers 相同的时间范围与代码标准化逻辑，失败时返回空列表，
        不影响 K 线主数据返回。

        Args:
            stock_code: 股票代码
            kline_df: K线数据 DataFrame（用于获取时间范围）

        Returns:
            除权除息日列表（升序，YYYY-MM-DD 的 date 对象）
        """
        if self._storage is None or kline_df.empty or 'trade_date' not in kline_df.columns:
            return []

        # 获取时间范围（与 K线请求一致）
        dates = pd.to_datetime(kline_df['trade_date'], errors='coerce')
        valid_dates = dates.dropna()
        if valid_dates.empty:
            return []
        start_date = valid_dates.min().strftime('%Y-%m-%d')
        end_date = valid_dates.max().strftime('%Y-%m-%d')

        # 标准化股票代码（去掉 sh./sz. 前缀；港股 9988.HK / 美股 AAPL 原样保留）
        db_code = stock_code
        for prefix in ('sh.', 'sz.', 'SH.', 'SZ.'):
            if db_code.startswith(prefix):
                db_code = db_code.replace(prefix, '').lower()

        try:
            return self._storage.get_ex_dates(db_code, start_date, end_date)
        except (ValueError, KeyError) as e:
            logger.warning(f"ex_dates 查询失败 ({stock_code}): {e}")
            return []

    def _calc_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """兜底计算：如果数据库没存指标，则在内存中计算"""
        if df.empty: return df
        df = df.copy()
        df['close_f'] = df['close'].astype(float)
        if len(df) >= 5: df['ma5'] = df['close_f'].rolling(window=5, min_periods=1).mean()
        if len(df) >= 10: df['ma10'] = df['close_f'].rolling(window=10, min_periods=1).mean()
        if len(df) >= 20: df['ma20'] = df['close_f'].rolling(window=20, min_periods=1).mean()
        
        # MACD
        ema12 = df['close_f'].ewm(span=12, adjust=False).mean()
        ema26 = df['close_f'].ewm(span=26, adjust=False).mean()
        df['dif'] = ema12 - ema26
        df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
        
        # RSI
        delta = df['close_f'].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=6, min_periods=1).mean()
        avg_loss = loss.rolling(window=6, min_periods=1).mean()
        rs = avg_gain / (avg_loss + 1e-10) 
        df['rsi6'] = 100 - (100 / (1 + rs))
        
        df = df.drop(columns=['close_f'])
        return df

    def _convert_to_kline_items(self, df: pd.DataFrame) -> List[KLineItem]:
        """将DataFrame转换为K线项列表，兼容数据库字段"""
        # 如果数据库没返回指标列，则现场计算
        if 'ma5' not in df.columns and len(df) >= 5:
            df = self._calc_indicators(df)

        kline_items = []
        for _, row in df.iterrows():
            def safe_dec(val, digits=2):
                if pd.isna(val): return None
                try: return Decimal(str(round(float(val), digits)))
                except (TypeError, ValueError) as e:
                    logger.warning(f"Decimal转换失败: val={val}, digits={digits}, {e}")
                    return None

            kline_item = KLineItem(
                trade_date=row.get("trade_date", ""),
                # 价格列保留 4 位小数（协作单 45.0）：库内 hk/us 成交量级可达 1e-4
                # （如碧桂园前复权 0.183），按 2 位会退化为 0.18 而丢失全部日内信息
                open=safe_dec(row.get("open"), 4),
                high=safe_dec(row.get("high"), 4),
                low=safe_dec(row.get("low"), 4),
                close=safe_dec(row.get("close"), 4),
                volume=int(row.get("volume", 0)),
                amount=safe_dec(row.get("amount")),
                
                # 均线（价格量纲，同 4 位）
                ma5=safe_dec(row.get("ma5"), 4),
                ma10=safe_dec(row.get("ma10"), 4),
                ma20=safe_dec(row.get("ma20"), 4),
                
                # MACD
                macd=safe_dec(row.get("macd"), 4),
                diff=safe_dec(row.get("dif"), 4),
                dea=safe_dec(row.get("dea"), 4),
                
                # RSI
                rsi_6=safe_dec(row.get("rsi6") or row.get("rsi_6")),
                rsi_12=safe_dec(row.get("rsi12") or row.get("rsi_12")),
                rsi_24=safe_dec(row.get("rsi24") or row.get("rsi_24")),
                
                # 布林带（如果数据库有则取，没有则为 None）
                boll_upper=safe_dec(row.get("boll_upper")),
                boll_mid=safe_dec(row.get("boll_mid")),
                boll_lower=safe_dec(row.get("boll_lower")),

                # 基本面
                pe_ttm=safe_dec(row.get("pe_ttm")),
                turnover_rate=safe_dec(row.get("turnover_rate")),
            )
            kline_items.append(kline_item)
        
        return kline_items