"""
Field group metadata for the left-side filter panel.
All pattern_* fields from the canonical catalog + momentum fields.
At runtime, fields not present in the loaded DataFrame are silently dropped.
"""
from __future__ import annotations
import db_loader as loader

_PATTERN_GROUPS = [
    {
        "id": "single_candle",
        "label": "单K形态",
        "fields": [
            {"key": "pattern_bull_candle",           "label": "阳线"},
            {"key": "pattern_bear_candle",           "label": "阴线"},
            {"key": "pattern_hammer",                "label": "锤头线"},
            {"key": "pattern_long_upper_shadow",     "label": "长上影线"},
            {"key": "pattern_long_lower_shadow",     "label": "长下影线"},
            {"key": "pattern_gravestone_doji",       "label": "墓碑十字"},
            {"key": "pattern_dragonfly_doji",        "label": "蜻蜓十字"},
            {"key": "pattern_big_bull",              "label": "大阳线"},
            {"key": "pattern_big_bear",              "label": "大阴线"},
            {"key": "pattern_medium_bull",           "label": "中阳线"},
            {"key": "pattern_medium_bear",           "label": "中阴线"},
            {"key": "pattern_small_bull",            "label": "小阳线"},
            {"key": "pattern_small_bear",            "label": "小阴线"},
            {"key": "pattern_no_body",               "label": "无实体线"},
            {"key": "pattern_no_upper_bull",         "label": "光头阳线"},
            {"key": "pattern_no_upper_bear",         "label": "光头阴线"},
            {"key": "pattern_no_lower_bull",         "label": "光脚阳线"},
            {"key": "pattern_no_lower_bear",         "label": "光脚阴线"},
            {"key": "pattern_t_shape",               "label": "T字线"},
            {"key": "pattern_inverted_t_shape",      "label": "倒T字线"},
            {"key": "pattern_low_open_high_close",   "label": "低开高走"},
            {"key": "pattern_high_open_low_close",   "label": "高开低走"},
            {"key": "pattern_gap_up",                "label": "跳空高开"},
            {"key": "pattern_gap_down",              "label": "跳空低开"},
            {"key": "pattern_close_above_prev_close","label": "收盘站上前收"},
            {"key": "pattern_close_below_prev_close","label": "收盘跌破前收"},
            {"key": "pattern_gap_reclaim_prev_close","label": "低开收回前收"},
            {"key": "pattern_gap_fade_below_prev_close","label": "高开回落失守前收"},
            {"key": "pattern_close_high",            "label": "收盘近最高"},
            {"key": "pattern_flat_open_high_close",  "label": "平开高走"},
            {"key": "pattern_flat_open_low_close",   "label": "平开低走"},
            {"key": "pattern_gap_up_close_bull",     "label": "高开收阳"},
            {"key": "pattern_gap_down_close_bear",   "label": "低开收阴"},
            {"key": "pattern_open_near_high_close_high","label": "开盘即最高附近收盘"},
            {"key": "pattern_open_near_low_close_low","label": "开盘即最低附近收盘"},
            {"key": "pattern_flat_open",             "label": "平开"},
            {"key": "pattern_gap_up_fill",           "label": "高开补缺"},
            {"key": "pattern_gap_down_fill",         "label": "低开补缺"},
            {"key": "pattern_pin_bar",               "label": "Pin Bar"},
            {"key": "pattern_reversal_prelude",      "label": "反包前兆"},
            {"key": "pattern_high_resistance",       "label": "高位受阻"},
            {"key": "pattern_low_stabilization",     "label": "低位止跌"},
            {"key": "pattern_break_prev_high",       "label": "向上突破前高"},
            {"key": "pattern_break_prev_low",        "label": "向下跌破前低"},
            {"key": "pattern_false_break",           "label": "假突破回落"},
            {"key": "pattern_false_breakdown_recovery","label": "假跌破回升"},
        ],
    },
    {
        "id": "double_candle",
        "label": "双K形态",
        "fields": [
            {"key": "pattern_bullish_engulfing",     "label": "阳包阴"},
            {"key": "pattern_bearish_engulfing",     "label": "阴包阳"},
            {"key": "pattern_inside_bar",            "label": "孕线"},
            {"key": "pattern_dark_cloud",            "label": "乌云盖顶"},
            {"key": "pattern_piercing",              "label": "刺透形态"},
            {"key": "pattern_tweezer_top",           "label": "镊子顶"},
            {"key": "pattern_tweezer_bottom",        "label": "镊子底"},
            {"key": "pattern_gap_break",             "label": "跳空上攻"},
            {"key": "pattern_gap_down_break",        "label": "跳空下跌"},
            {"key": "pattern_gap_up_no_fill",        "label": "跳空不补上行"},
            {"key": "pattern_gap_down_no_fill",      "label": "跳空不补下行"},
            {"key": "pattern_reversal_bar",          "label": "反转包线"},
            {"key": "pattern_flat_top",              "label": "平头顶"},
            {"key": "pattern_flat_bottom",           "label": "平头底"},
            {"key": "pattern_island_reversal",       "label": "岛形反转"},
            {"key": "pattern_t_limit",               "label": "T字板"},
            {"key": "pattern_limit_reversal_wrap",   "label": "涨停反包"},
            {"key": "pattern_vol_up",                "label": "放量上涨"},
            {"key": "pattern_vol_down",              "label": "缩量下跌"},
            {"key": "pattern_double_volume_bar",     "label": "倍量柱"},
            {"key": "pattern_breakout_volume_confirm","label": "突破放量确认"},
        ],
    },
    {
        "id": "triple_candle",
        "label": "三K形态",
        "fields": [
            {"key": "pattern_morning_star",          "label": "早晨之星"},
            {"key": "pattern_evening_star",          "label": "黄昏之星"},
            {"key": "pattern_morning_doji_star",     "label": "启明星"},
            {"key": "pattern_evening_doji_star",     "label": "黄昏十字星"},
            {"key": "pattern_three_black_crows",     "label": "三只乌鸦"},
            {"key": "pattern_red_three",             "label": "红三兵"},
            {"key": "pattern_three_outside_up",      "label": "三外升"},
            {"key": "pattern_three_outside_down",    "label": "三外降"},
            {"key": "pattern_rising_three_methods",  "label": "上升三法"},
            {"key": "pattern_falling_three_methods", "label": "下降三法"},
            {"key": "pattern_three_up",              "label": "三连阳"},
            {"key": "pattern_three_down",            "label": "三连阴"},
            {"key": "pattern_three_yang_kaitai",     "label": "三阳开泰"},
            {"key": "pattern_three_yin_breakdown",   "label": "三阴破位"},
        ],
    },
    {
        "id": "trend_structure",
        "label": "趋势结构",
        "fields": [
            {"key": "pattern_up_trend",              "label": "上升趋势"},
            {"key": "pattern_down_trend",            "label": "下降趋势"},
            {"key": "pattern_sideways",              "label": "横盘整理"},
            {"key": "pattern_golden_cross",          "label": "均线金叉"},
            {"key": "pattern_duck_head",             "label": "老鸭头"},
            {"key": "pattern_double_bottom",         "label": "双底"},
            {"key": "pattern_arc_bottom",            "label": "圆弧底"},
            {"key": "pattern_ma_bull",               "label": "均线多头排列"},
            {"key": "pattern_high_tight",            "label": "高位强势整理"},
            {"key": "pattern_pullback_hold",         "label": "回踩不破"},
            {"key": "pattern_trend_continue",        "label": "趋势中继"},
            {"key": "pattern_ma_spread_bull",        "label": "均线发散多头"},
        ],
    },
    {
        "id": "volume_price",
        "label": "量价形态",
        "fields": [
            {"key": "pattern_box_breakout",          "label": "箱体放量突破"},
            {"key": "pattern_vol_price_up",          "label": "量价齐升"},
            {"key": "pattern_platform_break",        "label": "平台突破"},
            {"key": "pattern_triangle_squeeze",      "label": "三角收敛突破"},
            {"key": "pattern_limit_turnover_strong", "label": "涨停换手强"},
            {"key": "pattern_price_volume_bear_divergence","label": "价量顶背离"},
            {"key": "pattern_price_volume_bull_divergence","label": "价量底背离"},
            {"key": "pattern_price_down_volume_up",  "label": "价跌量增"},
            {"key": "pattern_volume_staircase",      "label": "量能阶梯"},
            {"key": "pattern_pullback_volume_shrink","label": "回调缩量"},
            {"key": "pattern_high_turnover",         "label": "高换手"},
            {"key": "pattern_limit_up_volume_shrink","label": "一字板缩量"},
            {"key": "pattern_false_breakout_volume_weak","label": "假突破量弱"},
            {"key": "pattern_floor_volume_price",    "label": "地量价稳"},
            {"key": "pattern_blowoff_volume_price",  "label": "天量滞涨"},
            {"key": "pattern_v_reversal",            "label": "V型反转"},
        ],
    },
    {
        "id": "compound",
        "label": "复合形态",
        "fields": [
            {"key": "pattern_first_limit",           "label": "首板"},
            {"key": "pattern_multi_limit",           "label": "连板"},
            {"key": "pattern_one_word_limit",        "label": "一字板"},
            {"key": "pattern_limit_down_to_up",      "label": "地天板"},
            {"key": "pattern_lotus_breakout",        "label": "莲花突破"},
            {"key": "pattern_midway_refuel",         "label": "中继加油"},
            {"key": "pattern_consolidation_platform","label": "整理平台"},
            {"key": "pattern_n_breakout",            "label": "N字突破"},
            {"key": "pattern_gap_breakaway",         "label": "跳空突破"},
            {"key": "pattern_channel_breakout",      "label": "通道突破"},
            {"key": "pattern_flag_breakout",         "label": "旗形突破"},
        ],
    },
    {
        "id": "momentum",
        "label": "动量因子",
        "fields": [
            {"key": "break_high_20",   "label": "突破20日新高"},
            {"key": "break_high_60",   "label": "突破60日新高"},
            {"key": "consec_up_3",     "label": "连续上涨3日"},
            {"key": "consec_up_5",     "label": "连续上涨5日"},
        ],
    },
]


def get_groups() -> list[dict]:
    """Return groups filtered to columns that exist in the loaded DataFrame."""
    # 使用 loader_instance 避免 reload 后 df 为 None
    df = loader.loader_instance.df
    if df is None:
        return []
    
    df_cols = set(df.columns)
    result = []
    for group in _PATTERN_GROUPS:
        fields = [
            {**f, "count": loader.loader_instance.field_counts.get(f["key"], 0)}
            for f in group["fields"]
            if f["key"] in df_cols
        ]
        # 即使没有 pattern 字段，也返回分组结构（fields 可能为空）
        result.append({**group, "fields": fields})
    
    # 如果没有 pattern 列，添加行业和地区作为默认筛选组
    if not any(f["key"] in df_cols for group in _PATTERN_GROUPS for f in group["fields"]):
        result = [
            {
                "id": "industry",
                "label": "行业",
                "fields": [{"key": "industry_" + ind.replace(" ", "_"), "label": ind, "count": 0} 
                          for ind in get_industry_options()]
            },
            {
                "id": "area",
                "label": "地区",
                "fields": [{"key": "area_" + area.replace(" ", "_"), "label": area, "count": 0} 
                          for area in get_area_options()]
            }
        ]
    
    return result


def get_industry_options() -> list[str]:
    df = loader.loader_instance.df
    if df is None:
        return []
    return sorted(df["industry"].dropna().unique().tolist())


def get_area_options() -> list[str]:
    df = loader.loader_instance.df
    if df is None:
        return []
    return sorted(df["area"].dropna().unique().tolist())
