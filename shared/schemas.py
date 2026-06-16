"""
schemas.py - Pydantic v2 数据模型（前后端唯一契约）

【设计目标】
定义所有 API 接口的请求/响应数据结构，作为前后端的"唯一真相源"。
- 后台 FastAPI: 直接用作 Request/Response model
- 前台 TypeScript: 字段名/字段类型必须严格镜像
- ETL 脚本: 数据落库前用 model_validate() 校验

【硬约束】
1. as_of_date 必须在所有查询请求中显式传递（防前视偏差）
2. 价格/金额字段使用 Decimal 类型保证精度
3. 响应必须通过 model_validate()/model_dump() 序列化
4. 字段重命名需保留 2 个版本的兼容期

【变更流程】
任何字段的新增/删除/重命名，必须：
1. 同步更新 shared/constants.py 中的白名单
2. 同步更新 frontend/ 下的 TypeScript 类型
3. 在 AI_COLLABORATION.md 登记变更
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any, Dict, Generic, TypeVar, Literal
from datetime import date
from decimal import Decimal

from shared.constants import (
    ListedBoard,
    ALLOWED_SORT_FIELDS,
    AdjMethod,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ApiCode,
)

# 定义泛型类型变量
T = TypeVar('T')


# ============================================
# 筛选相关模型（用于 FilterPanel 元数据）
# ============================================

class FilterField(BaseModel):
    """筛选项字段"""
    key: str = Field(..., description="筛选条件键名")
    label: str = Field(..., description="显示标签")
    count: int = Field(0, description="命中数量")


class FilterGroup(BaseModel):
    """筛选条件分组"""
    id: str = Field(..., description="分组ID")
    label: str = Field(..., description="分组标签")
    fields: List[FilterField] = Field(..., description="筛选项列表")


# ============================================
# 筛选响应模型（/api/stocks）
# ============================================

class ScreenerRequest(BaseModel):
    """筛选请求模型"""
    filters: Dict[str, Any] = Field(default_factory=dict, description="筛选条件")
    sort_by: str = Field(default="change_pct", description="排序字段")
    sort_order: str = Field(default="desc", description="排序方向")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页数量")
    as_of_date: Optional[str] = Field(None, description="数据截止日期（YYYYMMDD），防前视偏差")


class ScreenerResponse(BaseModel):
    """筛选响应模型（含分页）"""
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    data: List["StockResponse"] = Field(..., description="股票列表")


# ============================================
# 响应模型
# ============================================

class StockResponse(BaseModel):
    """
    股票列表响应模型

    示例数据：
    {
        "stock_code": "000001.SZ",
        "stock_name": "平安银行",
        "listed_board": "上海主板",
        "industry": "银行",
        ...
    }
    """

    # --- 基础字段 ---
    stock_code: str = Field(..., description="股票代码", examples=["000001.SZ", "600000.SH"])
    stock_name: str = Field(..., description="股票名称", examples=["平安银行", "浦发银行"])
    listed_board: ListedBoard = Field(..., description="上市板块")
    industry: Optional[str] = Field(None, description="行业分类", examples=["银行", "地产", "医药"])
    sub_industry: Optional[str] = Field(None, description="细分行业")

    # --- 行情字段 ---
    trade_date: date = Field(..., description="交易日期")
    pre_close: Optional[Decimal] = Field(None, description="前收盘价", ge=0)
    open: Optional[Decimal] = Field(None, description="开盘价", ge=0)
    close: Optional[Decimal] = Field(None, description="收盘价", ge=0)
    high: Optional[Decimal] = Field(None, description="最高价", ge=0)
    low: Optional[Decimal] = Field(None, description="最低价", ge=0)
    volume: Optional[int] = Field(None, description="成交量（手）", ge=0)
    amount: Optional[Decimal] = Field(None, description="成交额（元）", ge=0)
    volume_ratio: Optional[Decimal] = Field(None, description="量比")
    vol_ratio_5: Optional[Decimal] = Field(None, description="5日量比")
    net_mf_vol: Optional[Decimal] = Field(None, description="净流入量（手）")
    net_mf_amount: Optional[Decimal] = Field(None, description="净流入额（元）")

    # --- 详细资金流向字段 ---
    buy_sm_amount: Optional[Decimal] = Field(None, description="小单买入（万元）")
    sell_sm_amount: Optional[Decimal] = Field(None, description="小单卖出（万元）")
    buy_md_amount: Optional[Decimal] = Field(None, description="中单买入（万元）")
    sell_md_amount: Optional[Decimal] = Field(None, description="中单卖出（万元）")
    buy_lg_amount: Optional[Decimal] = Field(None, description="大单买入（万元）")
    sell_lg_amount: Optional[Decimal] = Field(None, description="大单卖出（万元）")
    buy_elg_amount: Optional[Decimal] = Field(None, description="特大单买入（万元）")
    sell_elg_amount: Optional[Decimal] = Field(None, description="特大单卖出（万元）")

    change: Optional[Decimal] = Field(None, description="涨跌额（元）")
    change_pct: Optional[Decimal] = Field(None, description="涨跌幅（%）")
    turnover_rate: Optional[Decimal] = Field(None, description="换手率（%）", ge=0)

    # --- 财务与估值字段 ---
    pe: Optional[Decimal] = Field(None, description="市盈率（TTM）")
    pb: Optional[Decimal] = Field(None, description="市净率")
    pe_ttm: Optional[Decimal] = Field(None, description="市盈率（TTM）")
    ps: Optional[Decimal] = Field(None, description="市销率")
    ps_ttm: Optional[Decimal] = Field(None, description="市销率（TTM）")
    dv_ratio: Optional[Decimal] = Field(None, description="股息率")
    dv_ttm: Optional[Decimal] = Field(None, description="股息率（TTM）")
    market_cap: Optional[Decimal] = Field(None, description="总市值（万元）", ge=0)
    circ_mv: Optional[Decimal] = Field(None, description="流通市值（万元）", ge=0)
    float_share: Optional[Decimal] = Field(None, description="流通股（万股）", ge=0)

    # --- 技术指标字段 ---
    ma5: Optional[Decimal] = Field(None, description="5日均线价")
    ma10: Optional[Decimal] = Field(None, description="10日均线价")
    ma20: Optional[Decimal] = Field(None, description="20日均线价")
    v_ma5: Optional[int] = Field(None, description="5日均量（手）")
    rsi_6: Optional[Decimal] = Field(None, description="RSI6（相对强弱指标）", ge=0, le=100)
    macd: Optional[Decimal] = Field(None, description="MACD值")
    diff: Optional[Decimal] = Field(None, description="DIF值（MACD快线）")
    dea: Optional[Decimal] = Field(None, description="DEA值（MACD慢线）")
    boll_upper: Optional[Decimal] = Field(None, description="布林带上轨")
    boll_mid: Optional[Decimal] = Field(None, description="布林带中轨")
    boll_lower: Optional[Decimal] = Field(None, description="布林带下轨")
    rsi_12: Optional[Decimal] = Field(None, description="RSI12（相对强弱指标）", ge=0, le=100)
    rsi_24: Optional[Decimal] = Field(None, description="RSI24（相对强弱指标）", ge=0, le=100)
    kdj_k: Optional[Decimal] = Field(None, description="KDJ_K值")
    kdj_d: Optional[Decimal] = Field(None, description="KDJ_D值")
    kdj_j: Optional[Decimal] = Field(None, description="KDJ_J值")
    cci: Optional[Decimal] = Field(None, description="CCI指标")
    consec_up_days: Optional[int] = Field(None, description="连涨天数", ge=0)

    # --- 形态识别字段 ---
    pattern_hammer: bool = Field(False, description="锤子线")
    pattern_bullish_engulfing: bool = Field(False, description="看涨吞没")
    pattern_bearish_engulfing: bool = Field(False, description="看跌吞没")
    pattern_morning_star: bool = Field(False, description="早晨之星")
    pattern_evening_star: bool = Field(False, description="黄昏之星")

    # --- 技术指标 pattern 字段（2026-06-16 新增）---
    ma_long_align: bool = Field(False, description="多头排列")
    ma_short_align: bool = Field(False, description="空头排列")
    macd_low_golden_cross: bool = Field(False, description="MACD低位金叉")
    macd_bottom_divergence: bool = Field(False, description="MACD底背离")
    macd_high_death_cross: bool = Field(False, description="MACD高位死叉")
    macd_top_divergence: bool = Field(False, description="MACD顶背离")
    boll_break_upper: bool = Field(False, description="升穿上轨")
    boll_break_middle_up: bool = Field(False, description="升穿中轨")
    boll_break_middle_down: bool = Field(False, description="跌穿中轨")
    boll_break_lower: bool = Field(False, description="跌穿下轨")
    rsi_low_golden_cross: bool = Field(False, description="RSI低位金叉")
    rsi_high_death_cross: bool = Field(False, description="RSI高位死叉")
    rsi_top_divergence: bool = Field(False, description="RSI顶背离")
    rsi_bottom_divergence: bool = Field(False, description="RSI底背离")

    # --- 突破信号字段 ---
    break_high_20: bool = Field(False, description="突破20日高点")
    break_high_60: bool = Field(False, description="突破60日高点")

    # --- 连续走势字段 ---
    consec_up_3: bool = Field(False, description="连涨3天")
    consec_up_5: bool = Field(False, description="连涨5天")

    # --- 筛选通用字段 ---
    is_st: bool = Field(False, description="是否ST股票")
    is_new: bool = Field(False, description="是否新股（上市<1年）")
    limit_up: bool = Field(False, description="是否涨停")
    limit_down: bool = Field(False, description="是否跌停")

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None
        }


# ============================================
# 请求模型
# ============================================

class StocksRequest(BaseModel):
    """
    股票列表查询请求模型

    硬约束：
    1. limit 最大值为 200（防止内存溢出）
    2. as_of_date 必须显式传递（防前视偏差）
    3. sort_by 需要在 Service 层进行白名单校验
    """

    filters: Optional[str] = Field(None, description="K线形态筛选条件（逗号分隔）")
    listed_board: Optional[ListedBoard] = Field(None, description="上市板块筛选")
    industry: Optional[str] = Field(None, description="行业筛选（逗号分隔，OR逻辑）")
    area: Optional[str] = Field(None, description="地区筛选（逗号分隔，OR逻辑）")
    sort_by: str = Field("change_pct", description="排序字段")
    sort_asc: bool = Field(False, description="是否升序排列")
    offset: int = Field(0, ge=0, description="分页偏移量")
    limit: int = Field(100, ge=1, le=200, description="每页数量（最大200）")
    as_of_date: date = Field(..., description="数据截止日期（防前视偏差，必填）")

    @field_validator('sort_by')
    @classmethod
    def validate_sort_by(cls, v):
        if v not in ALLOWED_SORT_FIELDS:
            raise ValueError(f"Invalid sort_by: '{v}'. Allowed: {sorted(ALLOWED_SORT_FIELDS)}")
        return v


# ============================================
# 统一响应信封
# ============================================

class ApiResponse(BaseModel, Generic[T]):
    """
    统一 API 响应信封

    所有 API 接口必须返回此格式，禁止裸返回 DataFrame/Dict

    成功响应示例：
    {
        "code": 200,
        "message": "success",
        "data": {...}
    }

    错误响应示例：
    {
        "code": 400,
        "message": "参数错误: invalid sort_by",
        "data": null
    }
    """

    code: int = Field(ApiCode.SUCCESS, description="HTTP 状态码映射")
    message: str = Field("success", description="响应消息或错误描述")
    data: Optional[T] = Field(None, description="响应数据（可为对象、数组或 null）")


# ============================================
# 元数据响应模型（/api/meta）
# ============================================

class MetaResponse(BaseModel):
    """
    元数据响应模型

    用于前端初始化筛选面板的行业/地区选项
    """

    trade_date: str = Field(..., description="最新交易日期（YYYYMMDD）")
    total: int = Field(..., description="股票总数")
    groups: List[dict] = Field(..., description="筛选条件分组")
    industry_options: List[str] = Field(..., description="行业选项列表")
    area_options: List[str] = Field(..., description="地区选项列表")


# ============================================
# K线数据响应模型（/api/kline/{code}）
# ============================================

class KLineItem(BaseModel):
    """单根K线数据（含技术指标）"""

    trade_date: date = Field(..., description="交易日期")
    open: Decimal = Field(..., description="开盘价", ge=0)
    high: Decimal = Field(..., description="最高价", ge=0)
    low: Decimal = Field(..., description="最低价", ge=0)
    close: Decimal = Field(..., description="收盘价", ge=0)
    volume: int = Field(..., description="成交量", ge=0)
    amount: Decimal = Field(..., description="成交额", ge=0)

    # 技术指标（信号生成需要）
    ma5: Optional[Decimal] = Field(None, description="5日均线")
    ma10: Optional[Decimal] = Field(None, description="10日均线")
    ma20: Optional[Decimal] = Field(None, description="20日均线")
    rsi_6: Optional[Decimal] = Field(None, description="RSI6")
    macd: Optional[Decimal] = Field(None, description="MACD")
    boll_upper: Optional[Decimal] = Field(None, description="布林上轨")
    boll_mid: Optional[Decimal] = Field(None, description="布林中轨")
    boll_lower: Optional[Decimal] = Field(None, description="布林下轨")

    class Config:
        from_attributes = True


class KLineResponse(BaseModel):
    """K线响应模型"""

    stock_code: str = Field(..., description="股票代码")
    data: List[KLineItem] = Field(..., description="K线数据列表")
    count: int = Field(..., description="数据条数")
    # 复权信息
    adj_method: AdjMethod = Field(AdjMethod.NONE, description="复权方式")
    latest_factor: Optional[Decimal] = Field(None, description="最新复权因子（adj_factor）")
    warning: Optional[str] = Field(None, description="处理过程中产生的警告信息，如复权失败等")


# ============================================
# 买卖信号响应模型（/api/signals/{code}）
# ============================================

class SignalItem(BaseModel):
    """单个买卖信号"""

    trade_date: date = Field(..., description="信号日期")
    signal_type: str = Field(..., description="信号类型（如 rsi_oversold, macd_cross, bollinger_breakout 等）")
    direction: Literal["buy", "sell"] = Field(..., description="信号方向（buy=看多, sell=看空）")
    price: float = Field(..., description="信号价格", ge=0)
    reason: str = Field(..., description="信号原因（如 MACD金叉）")

    class Config:
        from_attributes = True


class SignalResponse(BaseModel):
    """买卖信号响应模型"""

    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    listed_board: Optional[str] = Field(None, description="上市板块")
    signal_type: Optional[str] = Field(None, description="信号类型")
    start_date: Optional[str] = Field(None, description="开始日期")
    end_date: Optional[str] = Field(None, description="结束日期")
    signals: List[SignalItem] = Field(..., description="信号列表")
    count: int = Field(..., description="信号数量")
