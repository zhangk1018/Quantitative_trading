"""
screener_service.py - 股票筛选服务

提供股票多条件筛选、排序、分页等核心业务逻辑。
所有方法均为同步，由 FastAPI 在后台线程池中执行。
"""

import pandas as pd
import datetime
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal

from collector.db.loader import DataLoader
from core.api.models.schemas import (
    StockResponse, ScreenerRequest, ScreenerResponse,
    FilterGroup, FilterField, ListedBoard
)

# ------------------------------------------------------------
# 列名映射：API 字段名 → Parquet 列名
# parquet 中大量列名与前端 types.ts / API 约定不同，
# 在此集中管理映射，避免散落各处。
# ------------------------------------------------------------
COLUMN_MAP: Dict[str, str] = {
    "stock_code": "code",
    "stock_name": "stock_name",
    "change_pct": "change_pct",
    "volume": "volume",
    "market_cap": "market_cap",
    # 形态：parquet 使用全称 "pattern_inverted_hammer"
    "pattern_inv_hammer": "pattern_inverted_hammer",
}

# ------------------------------------------------------------
# 默认排序字段（parquet 实际列名）
# ------------------------------------------------------------
DEFAULT_SORT_COLUMN = "change_pct"


class ScreenerService:
    """股票筛选服务"""

    def __init__(self, loader: DataLoader):
        self.loader = loader

        # 初始化筛选字段配置
        self._init_filter_config()

    # ------------------------------------------------------------------
    # 数据访问属性（通过 loader 动态获取，支持 parquet 热更新）
    # ------------------------------------------------------------------
    @property
    def df(self):
        return self.loader.df

    @property
    def trade_date(self):
        return self.loader.trade_date

    @property
    def field_counts(self):
        return self.loader.field_counts

    # ------------------------------------------------------------------
    # 列名解析
    # ------------------------------------------------------------------
    @staticmethod
    def to_parquet_col(field_name: str) -> str:
        """API 字段名 → Parquet 列名"""
        return COLUMN_MAP.get(field_name, field_name)

    # ------------------------------------------------------------------
    # 板块推导（parquet 无 listed_board 列）
    # ------------------------------------------------------------------
    @staticmethod
    def derive_listed_board(ts_code: str) -> ListedBoard:
        """从股票代码推导上市板块"""
        if ts_code.endswith(".SH"):
            code_num = ts_code.split(".")[0]
            if code_num.startswith("688"):
                return ListedBoard.STAR
            return ListedBoard.MAIN
        elif ts_code.endswith(".SZ"):
            code_num = ts_code.split(".")[0]
            if code_num.startswith("30"):
                return ListedBoard.CHINEXT
            return ListedBoard.MAIN
        elif ts_code.endswith(".BJ"):
            return ListedBoard.BSE
        return ListedBoard.MAIN

    # ------------------------------------------------------------------
    # 筛选配置
    # ------------------------------------------------------------------
    def _init_filter_config(self):
        """初始化筛选字段配置（keys 尽量与 API 约定一致）"""
        self.filter_config = {
            "price": {
                "close": {"label": "收盘价", "type": "range", "unit": "元"},
                "change": {"label": "涨跌额", "type": "range", "unit": "元"},
                "change_pct": {"label": "涨跌幅", "type": "range", "unit": "%"},
                "high": {"label": "最高价", "type": "range", "unit": "元"},
                "low": {"label": "最低价", "type": "range", "unit": "元"},
                "open": {"label": "开盘价", "type": "range", "unit": "元"},
                "pre_close": {"label": "前收盘价", "type": "range", "unit": "元"},
            },
            "volume": {
                "volume": {"label": "成交量", "type": "range", "unit": "手"},
                "amount": {"label": "成交额", "type": "range", "unit": "万元"},
                "turnover_rate": {"label": "换手率", "type": "range", "unit": "%"},
                "volume_ratio": {"label": "量比", "type": "range", "unit": ""},
                "vol_ratio_5": {"label": "5日量比", "type": "range", "unit": ""},
            },
            "technical": {
                "rsi_6": {"label": "RSI(6)", "type": "range", "unit": ""},
                "rsi_12": {"label": "RSI(12)", "type": "range", "unit": ""},
                "rsi_24": {"label": "RSI(24)", "type": "range", "unit": ""},
                "macd": {"label": "MACD", "type": "range", "unit": ""},
                "boll_upper": {"label": "布林上轨", "type": "range", "unit": "元"},
                "boll_mid": {"label": "布林中轨", "type": "range", "unit": "元"},
                "boll_lower": {"label": "布林下轨", "type": "range", "unit": "元"},
                "kdj_k": {"label": "KDJ-K", "type": "range", "unit": ""},
                "kdj_d": {"label": "KDJ-D", "type": "range", "unit": ""},
                "kdj_j": {"label": "KDJ-J", "type": "range", "unit": ""},
                "cci": {"label": "CCI", "type": "range", "unit": ""},
            },
            "fundamental": {
                "pe": {"label": "市盈率(静)", "type": "range", "unit": ""},
                "pe_ttm": {"label": "市盈率(TTM)", "type": "range", "unit": ""},
                "pb": {"label": "市净率", "type": "range", "unit": ""},
                "ps": {"label": "市销率(静)", "type": "range", "unit": ""},
                "ps_ttm": {"label": "市销率(TTM)", "type": "range", "unit": ""},
                "dv_ratio": {"label": "股息率(静)", "type": "range", "unit": "%"},
                "dv_ttm": {"label": "股息率(TTM)", "type": "range", "unit": "%"},
                "market_cap": {"label": "总市值", "type": "range", "unit": "万元"},
                "circ_mv": {"label": "流通市值", "type": "range", "unit": "万元"},
                "float_share": {"label": "流通股", "type": "range", "unit": "万股"},
                "total_share": {"label": "总股本", "type": "range", "unit": "万股"},
            },
            "fund_flow": {
                "net_mf_amount": {"label": "净流入额", "type": "range", "unit": "万元"},
                "net_mf_vol": {"label": "净流入量", "type": "range", "unit": "手"},
            },
            "pattern": {
                "pattern_hammer": {"label": "锤子线", "type": "binary"},
                "pattern_inv_hammer": {"label": "倒锤子线", "type": "binary"},
                "pattern_doji": {"label": "十字星", "type": "binary"},
                "pattern_bullish_engulfing": {"label": "看涨吞没", "type": "binary"},
                "pattern_bearish_engulfing": {"label": "看跌吞没", "type": "binary"},
                "pattern_morning_star": {"label": "早晨之星", "type": "binary"},
                "pattern_evening_star": {"label": "黄昏之星", "type": "binary"},
                "pattern_shooting_star": {"label": "射击之星", "type": "binary"},
                "pattern_hanging_man": {"label": "上吊线", "type": "binary"},
                "pattern_spinning_top": {"label": "纺锤线", "type": "binary"},
            },
            "breakout": {
                "break_high_20": {"label": "突破20日高点", "type": "binary"},
                "break_high_60": {"label": "突破60日高点", "type": "binary"},
                "break_high_120": {"label": "突破120日高点", "type": "binary"},
                "break_high_250": {"label": "突破250日高点", "type": "binary"},
            },
            "consecutive": {
                "consec_up_3": {"label": "连涨3天", "type": "binary"},
                "consec_up_5": {"label": "连涨5天", "type": "binary"},
                "consec_up_days": {"label": "连涨天数", "type": "range", "unit": "天"},
            },
        }

    def get_filter_meta(self) -> List[FilterGroup]:
        """获取筛选器元数据"""
        groups = []

        for group_key, fields in self.filter_config.items():
            filter_fields = []
            for field_key, config in fields.items():
                parquet_col = self.to_parquet_col(field_key)
                count = self.field_counts.get(parquet_col, 0) if config["type"] == "binary" else 0
                filter_fields.append(FilterField(key=field_key, label=config["label"], count=count))

            if filter_fields:
                groups.append(FilterGroup(
                    id=group_key,
                    label=self._get_group_label(group_key),
                    fields=filter_fields,
                ))

        return groups

    def _get_group_label(self, group_key: str) -> str:
        labels = {
            "price": "价格",
            "volume": "成交量",
            "technical": "技术指标",
            "fundamental": "基本面",
            "fund_flow": "资金流向",
            "pattern": "形态识别",
            "breakout": "突破信号",
            "consecutive": "连续走势",
        }
        return labels.get(group_key, group_key)

    # ------------------------------------------------------------------
    # 核心筛选逻辑
    # ------------------------------------------------------------------
    def screen_stocks(self, request: ScreenerRequest) -> ScreenerResponse:
        """执行股票筛选"""
        filtered_df = self._apply_filters(self.df, request.filters)
        sorted_df = self._apply_sorting(filtered_df, request.sort_by, request.sort_order)
        paginated_df, total_count = self._apply_pagination(sorted_df, request.page, request.page_size)
        stocks = self._convert_to_stock_responses(paginated_df)

        return ScreenerResponse(
            total=total_count,
            page=request.page,
            page_size=request.page_size,
            data=stocks,
        )

    def _apply_filters(self, df: pd.DataFrame, filters: Dict[str, Any]) -> pd.DataFrame:
        if not filters:
            return df

        mask = pd.Series(True, index=df.index)

        for field, condition in filters.items():
            col = self.to_parquet_col(field)
            if col not in df.columns:
                continue

            # 检查筛选字段类型（在所有分组中查找）
            field_type = self._get_filter_field_type(field)

            if isinstance(condition, dict):
                min_val = condition.get("min")
                max_val = condition.get("max")
                if min_val is not None:
                    mask &= (df[col] >= min_val)
                if max_val is not None:
                    mask &= (df[col] <= max_val)
            elif isinstance(condition, bool):
                if field_type == "range":
                    # 范围型字段的 bool 筛选：True → >0, False → <0
                    if condition:
                        mask &= (df[col] > 0)
                    else:
                        mask &= (df[col] < 0)
                else:
                    # 二进制/其他字段：精确匹配 0/1
                    mask &= (df[col] == (1 if condition else 0))
            elif isinstance(condition, (list, tuple)):
                # 处理列表类型的筛选条件，如多个行业
                mask &= df[col].isin(condition)
            else:
                mask &= (df[col] == condition)

        return df[mask].copy()

    def _get_filter_field_type(self, field: str) -> str:
        """获取字段的筛选类型（range/binary），用于 _apply_filters 处理逻辑"""
        for group in self.filter_config.values():
            if field in group:
                return group[field].get("type", "binary")
        return "binary"

    def _apply_sorting(self, df: pd.DataFrame, sort_by: str, sort_order: str) -> pd.DataFrame:
        col = self.to_parquet_col(sort_by)
        if col not in df.columns:
            col = DEFAULT_SORT_COLUMN
        ascending = sort_order == "asc"
        return df.sort_values(by=col, ascending=ascending)

    def _apply_pagination(self, df: pd.DataFrame, page: int, page_size: int) -> Tuple[pd.DataFrame, int]:
        total_count = len(df)
        if total_count == 0:
            return pd.DataFrame(), 0
        offset = (page - 1) * page_size
        if offset >= total_count:
            offset = 0
            page = 1
        end = min(offset + page_size, total_count)
        return df.iloc[offset:end].copy(), total_count

    # ------------------------------------------------------------------
    # 行 → StockResponse 转换
    # ------------------------------------------------------------------
    def _convert_to_stock_responses(self, df: pd.DataFrame) -> List[StockResponse]:
        stocks = []
        for _, row in df.iterrows():
            raw_date = str(row.get("trade_date", self.trade_date))
            try:
                parsed_date = datetime.datetime.strptime(raw_date, "%Y%m%d").date()
            except ValueError:
                parsed_date = datetime.date.today()
            stocks.append(StockResponse(
                stock_code=str(row.get("code", "")),
                stock_name=str(row.get("stock_name", "")),
                listed_board=self._to_listed_board(row.get("listed_board")),
                trade_date=parsed_date,
                industry=self._str_or_none(row.get("industry")),
                sub_industry=self._str_or_none(row.get("sub_industry")),
                close=self._to_decimal(row.get("close")),
                open=self._to_decimal(row.get("open")),
                high=self._to_decimal(row.get("high")),
                low=self._to_decimal(row.get("low")),
                pre_close=self._to_decimal(row.get("pre_close")),
                change=self._to_decimal(row.get("change")),
                change_pct=self._to_decimal(row.get("change_pct")),
                volume=self._to_int(row.get("volume")),
                amount=self._to_decimal(row.get("amount")),
                turnover_rate=self._to_decimal(row.get("turnover_rate")),
                pe=self._to_decimal(row.get("pe")),
                pe_ttm=self._to_decimal(row.get("pe_ttm")),
                pb=self._to_decimal(row.get("pb")),
                ps=self._to_decimal(row.get("ps")),
                ps_ttm=self._to_decimal(row.get("ps_ttm")),
                dv_ratio=self._to_decimal(row.get("dv_ratio")),
                dv_ttm=self._to_decimal(row.get("dv_ttm")),
                market_cap=self._to_decimal(row.get("market_cap")),
                circ_mv=self._to_decimal(row.get("circ_mv")),
                float_share=self._to_decimal(row.get("float_share")),
                volume_ratio=self._to_decimal(row.get("volume_ratio")),
                vol_ratio_5=self._to_decimal(row.get("vol_ratio_5")),
                net_mf_amount=self._to_decimal(row.get("net_mf_amount")),
                net_mf_vol=self._to_decimal(row.get("net_mf_vol")),
                # 详细资金流向
                buy_sm_amount=self._to_decimal(row.get("buy_sm_amount")),
                sell_sm_amount=self._to_decimal(row.get("sell_sm_amount")),
                buy_md_amount=self._to_decimal(row.get("buy_md_amount")),
                sell_md_amount=self._to_decimal(row.get("sell_md_amount")),
                buy_lg_amount=self._to_decimal(row.get("buy_lg_amount")),
                sell_lg_amount=self._to_decimal(row.get("sell_lg_amount")),
                buy_elg_amount=self._to_decimal(row.get("buy_elg_amount")),
                sell_elg_amount=self._to_decimal(row.get("sell_elg_amount")),
                # 技术指标
                ma5=self._to_decimal(row.get("ma5")),
                ma10=self._to_decimal(row.get("ma10")),
                ma20=self._to_decimal(row.get("ma20")),
                v_ma5=self._to_int(row.get("v_ma5")),
                rsi_6=self._to_decimal(row.get("rsi_6")),
                rsi_12=self._to_decimal(row.get("rsi_12")),
                rsi_24=self._to_decimal(row.get("rsi_24")),
                macd=self._to_decimal(row.get("macd")),
                boll_upper=self._to_decimal(row.get("boll_upper")),
                boll_mid=self._to_decimal(row.get("boll_mid")),
                boll_lower=self._to_decimal(row.get("boll_lower")),
                kdj_k=self._to_decimal(row.get("kdj_k")),
                kdj_d=self._to_decimal(row.get("kdj_d")),
                kdj_j=self._to_decimal(row.get("kdj_j")),
                cci=self._to_decimal(row.get("cci")),
                # 形态（映射列名）
                pattern_hammer=self._to_bool(row.get("pattern_hammer")),
                pattern_inv_hammer=self._to_bool(row.get("pattern_inverted_hammer")),
                pattern_doji=self._to_bool(row.get("pattern_doji")),
                pattern_bullish_engulfing=self._to_bool(row.get("pattern_bullish_engulfing")),
                pattern_bearish_engulfing=self._to_bool(row.get("pattern_bearish_engulfing")),
                pattern_morning_star=self._to_bool(row.get("pattern_morning_star")),
                pattern_evening_star=self._to_bool(row.get("pattern_evening_star")),
                pattern_shooting_star=self._to_bool(row.get("pattern_shooting_star")),
                pattern_hanging_man=self._to_bool(row.get("pattern_hanging_man")),
                pattern_spinning_top=self._to_bool(row.get("pattern_spinning_top")),
                # 突破
                break_high_20=self._to_bool(row.get("break_high_20")),
                break_high_60=self._to_bool(row.get("break_high_60")),
                break_high_120=self._to_bool(row.get("break_high_120")),
                break_high_250=self._to_bool(row.get("break_high_250")),
                # 连续
                consec_up_3=self._to_bool(row.get("consec_up_3")),
                consec_up_5=self._to_bool(row.get("consec_up_5")),
                consec_up_days=self._to_int(row.get("consec_up_days")),
                # 状态标记
                is_st=self._to_bool(row.get("is_st")),
                is_new=self._to_bool(row.get("is_new")),
                limit_up=self._to_bool(row.get("limit_up")),
                limit_down=self._to_bool(row.get("limit_down")),
            ))
        return stocks

    # ------------------------------------------------------------------
    # 类型转换工具
    # ------------------------------------------------------------------
    @staticmethod
    def _to_decimal(val) -> Optional[Decimal]:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None

    @staticmethod
    def _to_int(val) -> Optional[int]:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        try:
            return int(val)
        except Exception:
            return None

    @staticmethod
    def _to_bool(val) -> bool:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return False
        return bool(val)

    @staticmethod
    def _str_or_none(val) -> Optional[str]:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return str(val)

    @staticmethod
    def _to_listed_board(val) -> ListedBoard:
        """将 Parquet listed_board 字段值转为 ListedBoard 枚举"""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return ListedBoard.MAIN
        for member in ListedBoard:
            if member.value == val:
                return member
        return ListedBoard.MAIN

    def get_stock_by_code(self, stock_code: str) -> Optional[StockResponse]:
        """根据股票代码查询单只股票"""
        df = self.df
        mask = df["code"] == stock_code
        filtered_df = df[mask]
        if len(filtered_df) == 0:
            return None
        stocks = self._convert_to_stock_responses(filtered_df.head(1))
        return stocks[0] if stocks else None