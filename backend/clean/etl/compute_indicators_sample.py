#!/usr/bin/env python3
"""
技术指标计算脚本 - 从 stock_quotes 表读取价格数据，计算技术指标并写入 stock_indicators 表

本版本修复了 MACD 字段映射错误，增加了多周期 RSI 和布林带计算，
并优化了异常处理、日志和配置管理，确保与 signal_precompute.py 的字段要求完全匹配。
"""
import sys
import os
import gc
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# 将 backend 目录加入 Python 路径
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import pandas as pd
import numpy as np
from collector.storage.postgresql_storage import PostgreSQLStorage
from clean.processor.technical_indicator import TechnicalIndicator
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('indicator_compute')

# ===================== 配置常量 =====================
class IndicatorConfig:
    """技术指标计算配置"""
    # 数据范围
    DEFAULT_START_DATE = '2026-01-01'
    MAX_STOCKS = 200  # 简化版只处理前 N 只，设为 -1 表示全量
    
    # 技术指标参数
    RSI_PERIODS = [6, 12, 24]
    BOLL_WINDOW = 20
    BOLL_STD = 2
    MA_PERIODS = [5, 10, 20, 60]
    
    # 数据库相关
    CYCLE = '1d'
    ADJUST_TYPE = 'qfq'
    ADJUST_FACTOR = 1.0  # 简化版，未使用真实复权因子
    
    # 重试与并发
    FETCH_RETRY = 2
    BATCH_SAVE_SIZE = 1000  # 批量插入的行数
    
    # 日志开关
    DEBUG_MODE = False  # 是否输出详细调试信息


# ===================== 辅助函数 =====================
def calc_rsi(series: pd.Series, period: int) -> pd.Series:
    """
    计算指定周期的 RSI 指标
    :param series: 价格序列（通常是收盘价）
    :param period: 周期
    :return: RSI 值序列
    """
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    # 避免除零
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_bollinger_bands(df: pd.DataFrame, price_col: str = 'close',
                         window: int = 20, std_mult: int = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    计算布林带
    :return: (mid, upper, lower)
    """
    mid = df[price_col].rolling(window).mean()
    std = df[price_col].rolling(window).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    return mid, upper, lower


def safe_astype_float(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """安全地将指定列转换为 float，无法转换的设为 NaN"""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


# ===================== 核心函数 =====================
def compute_indicators_for_stock(
    storage: PostgreSQLStorage,
    code: str,
    start_date: str = IndicatorConfig.DEFAULT_START_DATE,
    end_date: Optional[str] = None,
    config: IndicatorConfig = IndicatorConfig()
) -> int:
    """
    为单只股票计算技术指标并保存到数据库
    :return: 成功保存的指标条数，0 表示无数据或失败
    """
    if end_date is None:
        end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    db_code = code.split('.')[-1] if '.' in code else code
    logger.debug(f"开始处理 {code} (db_code={db_code})")

    # ---- 1. 获取价格数据（含重试） ----
    for attempt in range(1, config.FETCH_RETRY + 1):
        try:
            quotes_df = storage.get_quotes(
                code=db_code,
                cycle=config.CYCLE,
                start_date=start_date,
                end_date=end_date
            )
            break
        except Exception as e:
            logger.warning(f"{code} 数据读取失败 (尝试 {attempt}/{config.FETCH_RETRY}): {e}")
            if attempt == config.FETCH_RETRY:
                logger.error(f"{code} 数据读取最终失败，跳过")
                return 0
            time.sleep(1)
    
    if quotes_df.empty:
        logger.warning(f"{code} 无价格数据（{start_date}~{end_date}），跳过")
        return 0
    
    if len(quotes_df) < 60:
        logger.warning(f"{code} 价格数据不足60天（实际{len(quotes_df)}），跳过")
        return 0

    # ---- 2. 数据预处理 ----
    quotes_df = quotes_df.copy()
    # 添加复权信息（简化版）
    quotes_df['adjust_type'] = config.ADJUST_TYPE
    quotes_df['adjust_factor'] = config.ADJUST_FACTOR
    # 转换数值列类型
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
    quotes_df = safe_astype_float(quotes_df, numeric_cols)
    # 删除全为 NaN 的行（通常不会）
    quotes_df = quotes_df.dropna(subset=['close']).reset_index(drop=True)

    # ---- 3. 计算技术指标 ----
    try:
        # 使用 TechnicalIndicator 计算 MA、MACD 等（若可用）
        ind_df = TechnicalIndicator.calculate_all(quotes_df, require_adjust=False)
        if ind_df is not None and not ind_df.empty:
            # 打印列名以便调试（仅 DEBUG 模式）
            if config.DEBUG_MODE:
                logger.debug(f"{code} TechnicalIndicator 返回列: {ind_df.columns.tolist()}")
        else:
            # 如果计算器返回空，则创建一个空 DataFrame，后续手动填充
            ind_df = pd.DataFrame()
    except Exception as e:
        logger.warning(f"{code} TechnicalIndicator.calculate_all 失败: {e}")
        ind_df = pd.DataFrame()

    # ---- 4. 构建最终指标 DataFrame ----
    result_df = pd.DataFrame()
    result_df['code'] = db_code
    result_df['cycle'] = config.CYCLE
    result_df['trade_date'] = quotes_df['trade_date']

    # ---- 4.1 MA 指标（从 ind_df 或自行计算） ----
    for ma_period in config.MA_PERIODS:
        col_name = f'ma{ma_period}'
        if ind_df is not None and not ind_df.empty and col_name in ind_df.columns:
            result_df[col_name] = ind_df[col_name]
        else:
            # 自行计算
            result_df[col_name] = quotes_df['close'].rolling(ma_period).mean()

    # ---- 4.2 MACD 指标（必须确保 dif 和 dea 正确） ----
    # 优先从 ind_df 获取，如果列名不确定，尝试常见的几种命名
    macd_dif = None
    macd_dea = None
    if ind_df is not None and not ind_df.empty:
        # 常见的列名组合（按优先级）
        possible_macd_cols = [
            ('macd', 'macdsignal'),          # TA-Lib 默认
            ('MACD', 'MACD_SIGNAL'),         # 可能是大写
            ('dif', 'dea'),                  # 直接就是我们需要的
        ]
        for dif_col, dea_col in possible_macd_cols:
            if dif_col in ind_df.columns and dea_col in ind_df.columns:
                macd_dif = ind_df[dif_col]
                macd_dea = ind_df[dea_col]
                if config.DEBUG_MODE:
                    logger.debug(f"{code} MACD 使用列 {dif_col}, {dea_col}")
                break
    # 如果仍未获取，则自行计算
    if macd_dif is None:
        # 使用收盘价计算 MACD（12,26,9）
        exp1 = quotes_df['close'].ewm(span=12, adjust=False).mean()
        exp2 = quotes_df['close'].ewm(span=26, adjust=False).mean()
        macd_dif = exp1 - exp2
        macd_dea = macd_dif.ewm(span=9, adjust=False).mean()
        if config.DEBUG_MODE:
            logger.debug(f"{code} MACD 采用自行计算")
    result_df['dif'] = macd_dif
    result_df['dea'] = macd_dea
    # 可选：柱状线，信号脚本不使用，但可保留
    result_df['macd_hist'] = (macd_dif - macd_dea) * 2

    # ---- 4.3 RSI 多周期（自行计算，覆盖 ind_df 中的 RSI） ----
    for period in config.RSI_PERIODS:
        col_name = f'rsi{period}'
        result_df[col_name] = calc_rsi(quotes_df['close'], period)

    # ---- 4.4 布林带（自行计算） ----
    mid, upper, lower = calc_bollinger_bands(
        quotes_df, 'close', config.BOLL_WINDOW, config.BOLL_STD
    )
    result_df['boll_mid'] = mid
    result_df['boll_upper'] = upper
    result_df['boll_lower'] = lower

    # ---- 4.5 其他辅助字段（signal_precompute 可能需要） ----
    # trade_time, trade_datetime 用于兼容性
    result_df['trade_time'] = result_df['trade_date'].apply(
        lambda x: pd.Timestamp(x).strftime('%Y-%m-%d 15:00:00')
    )
    result_df['trade_datetime'] = pd.to_datetime(result_df['trade_time'])

    # ---- 5. 数据清理 ----
    # 将 INF 和 -INF 转为 NaN
    numeric_cols_all = ['ma5', 'ma10', 'ma20', 'ma60', 'dif', 'dea', 'macd_hist'] + \
                       [f'rsi{p}' for p in config.RSI_PERIODS] + \
                       ['boll_mid', 'boll_upper', 'boll_lower']
    for col in numeric_cols_all:
        if col in result_df.columns:
            result_df[col] = result_df[col].replace([np.inf, -np.inf], np.nan)
            # 注意：不填充 NaN，保留数据库可存储 NaN（推荐），或根据需要填充 0
            # 这里保留 NaN，但数据库列需支持 NULL

    # 对于必须非空的列（如 rsi 可能全空），但数据库字段可为 NULL，故保留

    # ---- 6. 保存到数据库 ----
    try:
        # 按批次保存，避免一次插入过多
        total_rows = len(result_df)
        saved = 0
        if total_rows == 0:
            return 0
        # 分批保存
        for start_idx in range(0, total_rows, config.BATCH_SAVE_SIZE):
            batch = result_df.iloc[start_idx:start_idx + config.BATCH_SAVE_SIZE]
            cnt = storage.save_indicators(batch)
            saved += cnt
        logger.debug(f"{code} 保存 {saved} 条指标记录")
        return saved
    except Exception as e:
        logger.error(f"{code} 保存到数据库失败: {e}", exc_info=True)
        return 0


def main():
    """主函数"""
    # 初始化数据库连接
    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', ''),
    })
    
    try:
        storage.connect()
        # 确保表存在（只是检查，不创建）
        # storage.init_tables()  # 如果有初始化方法可调用
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return

    logger.info("=" * 70)
    logger.info("开始计算技术指标（优化版）")
    logger.info(f"配置: 开始日期={IndicatorConfig.DEFAULT_START_DATE}, 最大股票数={IndicatorConfig.MAX_STOCKS}")
    logger.info("=" * 70)

    # 获取股票列表
    try:
        stocks_df = storage.get_stock_list()
    except Exception as e:
        logger.error(f"获取股票列表失败: {e}")
        storage.disconnect()
        return

    if stocks_df.empty:
        logger.error("无股票列表")
        storage.disconnect()
        return

    codes = stocks_df['code'].tolist()
    if IndicatorConfig.MAX_STOCKS > 0:
        codes = codes[:IndicatorConfig.MAX_STOCKS]
    total = len(codes)
    logger.info(f"待处理股票: {total} 只")

    # 初始化统计
    success_count = 0
    total_rows = 0
    failed_stocks = []

    start_time = time.time()
    for i, code in enumerate(codes, 1):
        try:
            cnt = compute_indicators_for_stock(storage, code)
            if cnt > 0:
                success_count += 1
                total_rows += cnt
            else:
                failed_stocks.append(code)
            # 进度日志
            if i % 10 == 0 or i == total:
                elapsed = time.time() - start_time
                logger.info(f"进度: {i}/{total} ({i/total*100:.1f}%) | 成功 {success_count} | 已耗时 {elapsed:.1f}s")
        except Exception as e:
            logger.error(f"{code} 处理异常: {e}", exc_info=True)
            failed_stocks.append(code)
            continue

    # 统计
    elapsed_total = time.time() - start_time
    logger.info("=" * 70)
    logger.info(f"✅ 技术指标计算完成，总耗时 {elapsed_total:.2f}s")
    logger.info(f"成功股票: {success_count}/{total}")
    logger.info(f"生成指标记录: {total_rows} 条")
    if failed_stocks:
        logger.warning(f"失败股票列表: {failed_stocks}")
    logger.info("=" * 70)

    storage.disconnect()

    return {
        'total': total,
        'success': success_count,
        'count': total_rows,
        'failed': failed_stocks
    }


if __name__ == '__main__':
    stats = main()
    print("\n📊 统计信息:")
    print(f"  处理股票: {stats['success']}/{stats['total']}")
    print(f"  生成指标: {stats['count']} 条")
    if stats['failed']:
        print(f"  失败股票: {', '.join(stats['failed'])}")