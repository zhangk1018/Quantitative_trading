#!/usr/bin/env python3
"""
信号预计算脚本 - 从 stock_indicators 表读取技术指标，计算交易信号并写入 trade_signals 表
信号类型：
1. macd_cross: MACD 金叉死叉信号（DIF上穿/下穿 DEA）
2. rsi_oversold: RSI 超卖信号（RSI < 30）
3. rsi_overbought: RSI 超买信号（RSI > 70）
4. bollinger_breakout: BOLL 突破信号（价格突破上轨/下轨）
"""
import sys
import os
import json

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import gc
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('signal_precompute')


class SignalPrecompute:
    """信号预计算器"""
    def __init__(self, storage: PostgreSQLStorage):
        self.storage = storage
        self.RSI_OVERSELL_THRESHOLD = 30
        self.RSI_OVERBUY_THRESHOLD = 70
        self.BOLL_WINDOW = 20
        self.BOLL_STD_MULTIPLE = 2
        self.INCREMENT_BACK_DAYS = 5
        self.EPS = 1e-8

    def _build_signal_df(self, mask: pd.Series, df_src: pd.DataFrame, signal_type: str, direction: str,
                         signal_value_col: str, signal_strength: pd.Series, desc: str) -> pd.DataFrame:
        """公共方法：统一组装信号行数据"""
        if not mask.any():
            return pd.DataFrame()
        df_hit = df_src[mask].copy()
        
        # 过滤无效数据：NaN 的 code 或 NaT 的 trade_date
        valid_mask = df_hit["code"].notna() & df_hit["code"].astype(str).str.lower().ne('nan')
        valid_mask &= df_hit["trade_date"].notna()
        if not valid_mask.any():
            return pd.DataFrame()
        
        # 使用 numpy 数组避免索引对齐问题
        df_hit = df_hit[valid_mask].reset_index(drop=True)
        strength_values = signal_strength[mask].values[valid_mask.values]
        strength = pd.Series(strength_values).fillna(0).clip(0, 100).astype(int)
        sig_df = pd.DataFrame({
            "code": df_hit["code"],
            "cycle": "1d",
            "trade_date": df_hit["trade_date"],
            "signal_type": signal_type,
            "signal_direction": direction,
            "signal_value": df_hit[signal_value_col].astype(float),
            "signal_strength": strength,
            "description": desc
        })
        return sig_df

    def _calc_rsi_signal(self, full_df: pd.DataFrame, rsi_col: str, period_label: str) -> List[pd.DataFrame]:
        """通用RSI信号生成，支持多周期复用"""
        sig_results = []
        rsi_df = full_df.dropna(subset=[rsi_col])
        if rsi_df.empty:
            return sig_results

        # 超卖信号
        oversold_mask = rsi_df[rsi_col] < self.RSI_OVERSELL_THRESHOLD
        oversold_strength = ((self.RSI_OVERSELL_THRESHOLD - rsi_df[rsi_col]) / (self.RSI_OVERSELL_THRESHOLD + self.EPS)) * 100
        oversold_sig = self._build_signal_df(
            mask=oversold_mask,
            df_src=rsi_df,
            signal_type="rsi_oversold",
            direction="buy",
            signal_value_col=rsi_col,
            signal_strength=oversold_strength,
            desc=f"RSI{period_label}超卖"
        )
        if not oversold_sig.empty:
            sig_results.append(oversold_sig)

        # 超买信号（分母使用超买区间长度）
        overbought_range = 100 - self.RSI_OVERBUY_THRESHOLD
        overbought_strength = ((rsi_df[rsi_col] - self.RSI_OVERBUY_THRESHOLD) / (overbought_range + self.EPS)) * 100
        overbought_sig = self._build_signal_df(
            mask=rsi_df[rsi_col] > self.RSI_OVERBUY_THRESHOLD,
            df_src=rsi_df,
            signal_type="rsi_overbought",
            direction="sell",
            signal_value_col=rsi_col,
            signal_strength=overbought_strength,
            desc=f"RSI{period_label}超买"
        )
        if not overbought_sig.empty:
            sig_results.append(overbought_sig)
        return sig_results

    def detect_all_signals_vectorized_full_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        全局整批向量化计算（无单股票循环）
        只负责生成信号，不处理增量过滤（过滤由调用方负责）
        """
        if df.empty:
            return pd.DataFrame()
        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.sort_values(["code", "trade_date"]).reset_index(drop=True)
        
        # ---- 字段完整性校验（防止静默跳过） ----
        col_list = df.columns.tolist()
        required_macd = ["dif", "dea"]
        required_rsi = ["rsi6", "rsi12", "rsi24"]
        required_boll = ["close"]  # boll_upper/lower 可选，但 close 必须
        
        logger.info(f"【批次数据校验】股票数量: {len(df['code'].unique())}, 全部字段: {col_list}")
        
        if not all(col in col_list for col in required_macd):
            logger.error(f"MACD 字段缺失: {[col for col in required_macd if col not in col_list]}")
            # 不抛出异常，只记录，因为可能有些股票确实没有MACD数据，但代码会跳过计算
        if not all(col in col_list for col in required_rsi):
            logger.warning(f"RSI 字段缺失: {[col for col in required_rsi if col not in col_list]}")
        if "close" not in col_list:
            logger.error("close 字段缺失，无法计算 BOLL 信号，请检查查询 SQL")

        all_signal_frames = []

        # ========== MACD 金叉死叉 ==========
        if "dif" in df.columns and "dea" in df.columns:
            macd_df = df.dropna(subset=["dif", "dea"])
            if not macd_df.empty:
                macd_df["diff"] = macd_df["dif"] - macd_df["dea"]
                macd_df["prev_diff"] = macd_df.groupby("code")["diff"].shift(1)

                golden_mask = (macd_df["prev_diff"] <= 0) & (macd_df["diff"] > 0)
                golden_strength = macd_df["diff"].abs() * 100
                golden_df = self._build_signal_df(golden_mask, macd_df, "macd_cross", "buy", "dif", golden_strength, "MACD金叉")
                if not golden_df.empty:
                    logger.info(f"批次MACD金叉生成 {len(golden_df)} 条")
                    all_signal_frames.append(golden_df)

                death_mask = (macd_df["prev_diff"] >= 0) & (macd_df["diff"] < 0)
                death_strength = macd_df["diff"].abs() * 100
                death_df = self._build_signal_df(death_mask, macd_df, "macd_cross", "sell", "dif", death_strength, "MACD死叉")
                if not death_df.empty:
                    all_signal_frames.append(death_df)
        else:
            logger.error("严重缺失：数据集无dif/dea字段，MACD信号全部无法生成")

        # ========== RSI 多周期 ==========
        rsi_config_map = [("rsi6", "6"), ("rsi12", "12"), ("rsi24", "24")]
        for rsi_col, label in rsi_config_map:
            if rsi_col not in df.columns:
                continue
            rsi_sigs = self._calc_rsi_signal(df, rsi_col, label)
            all_signal_frames.extend(rsi_sigs)

        # ========== BOLL突破 ==========
        if "close" not in df.columns:
            logger.warning("数据集缺失close收盘价，跳过BOLL突破计算")
        else:
            boll_df = df.dropna(subset=["close"])
            if not boll_df.empty:
                # 若无预计算布林带则本地计算
                if "boll_upper" not in boll_df.columns or "boll_lower" not in boll_df.columns:
                    logger.info("未读取预计算BOLL指标，本地20日窗口计算布林带")
                    boll_df["boll_mid"] = boll_df.groupby("code")["close"].transform(lambda x: x.rolling(self.BOLL_WINDOW).mean())
                    std_series = boll_df.groupby("code")["close"].transform(lambda x: x.rolling(self.BOLL_WINDOW).std())
                    boll_df["boll_upper"] = boll_df["boll_mid"] + self.BOLL_STD_MULTIPLE * std_series
                    boll_df["boll_lower"] = boll_df["boll_mid"] - self.BOLL_STD_MULTIPLE * std_series

                # 上轨突破卖出
                upper_break_mask = boll_df["close"] > boll_df["boll_upper"]
                upper_strength = ((boll_df["close"] - boll_df["boll_upper"]) / (boll_df["boll_upper"] + self.EPS)) * 100
                upper_sig = self._build_signal_df(upper_break_mask, boll_df, "bollinger_breakout", "sell", "close", upper_strength, "突破BOLL上轨")
                if not upper_sig.empty:
                    all_signal_frames.append(upper_sig)

                # 下轨突破买入
                lower_break_mask = boll_df["close"] < boll_df["boll_lower"]
                lower_strength = ((boll_df["boll_lower"] - boll_df["close"]) / (boll_df["boll_lower"] + self.EPS)) * 100
                lower_sig = self._build_signal_df(lower_break_mask, boll_df, "bollinger_breakout", "buy", "close", lower_strength, "突破BOLL下轨")
                if not lower_sig.empty:
                    all_signal_frames.append(lower_sig)

        if not all_signal_frames:
            return pd.DataFrame()

        total_signal_df = pd.concat(all_signal_frames, ignore_index=True)
        total_signal_df["trade_date"] = total_signal_df["trade_date"].dt.date
        return total_signal_df

    def precompute_signals_for_stock(self, code: str, start_date: str = None, end_date: str = None) -> int:
        """单股票独立调用（调试用）"""
        logger.debug(f"单股票计算: {code}")
        indicators_df = self.storage.get_indicators(code=code, cycle='1d', start_date=start_date, end_date=end_date)
        if indicators_df.empty:
            logger.warning(f"{code} 无指标数据，跳过")
            return 0
        quotes_df = self.storage.get_quotes(code=code, cycle='daily', start_date=start_date, end_date=end_date)
        if quotes_df.empty:
            logger.warning(f"{code} 无行情数据，跳过")
            return 0

        combined_df = pd.merge(indicators_df, quotes_df[["trade_date", "close", "volume"]], on="trade_date", how="left")
        combined_df["code"] = code
        combined_df = combined_df.reset_index(drop=True)

        try:
            sig_df = self.detect_all_signals_vectorized_full_batch(combined_df)
        except Exception as e:
            logger.error(f"{code} 信号计算异常: {e}", exc_info=True)
            return 0
        if sig_df.empty:
            logger.debug(f"{code} 无生成信号")
            return 0
        write_cnt = self.storage.save_signals(sig_df)
        logger.debug(f"{code} 入库 {write_cnt} 条信号")
        del combined_df, sig_df
        gc.collect()
        return write_cnt

    def precompute_all_signals_batch(self, start_date: str = None, end_date: str = None, incremental: bool = True) -> Dict[str, int]:
        """
        批量主入口：全局向量化 + 向量化增量过滤
        """
        logger.info("=============================================")
        logger.info("启动全市场批量信号预计算｜全局向量化优化模式")
        logger.info(f"增量模式: {'开启' if incremental else '关闭'}, 前置回溯天数:{self.INCREMENT_BACK_DAYS}")
        logger.info("=============================================")

        stock_base_df = self.storage.get_stock_list()
        if stock_base_df.empty:
            logger.error("获取股票列表失败，终止任务")
            return {"total_stocks": 0, "success_stocks": 0, "total_signals": 0}

        all_codes = stock_base_df["code"].tolist()
        total_stock_cnt = len(all_codes)
        total_write_signals = 0
        stock_with_signal = set()
        chunk_batch_size = 200
        total_chunk_num = (total_stock_cnt + chunk_batch_size - 1) // chunk_batch_size
        last_calc_watermark = {}

        if incremental:
            db_std_codes = [c.split(".")[-1] if "." in c else c for c in all_codes]
            last_calc_watermark = self.storage.get_last_signal_dates_batch(db_std_codes)
            if end_date is None:
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        for chunk_idx in range(total_chunk_num):
            chunk_start = chunk_idx * chunk_batch_size
            chunk_end = min((chunk_idx + 1) * chunk_batch_size, total_stock_cnt)
            raw_chunk_codes = all_codes[chunk_start:chunk_end]
            std_chunk_codes = [c.split(".")[-1] if "." in c else c for c in raw_chunk_codes]
            logger.info(f"==== 处理批次 {chunk_idx+1}/{total_chunk_num} | 股票数量:{len(std_chunk_codes)} ====")

            # 计算批次起始日期（前置数据用于shift）
            batch_start_dt = start_date
            if incremental:
                min_last_date = None
                for c in std_chunk_codes:
                    ld = last_calc_watermark.get(c)
                    if ld is not None and (min_last_date is None or ld < min_last_date):
                        min_last_date = ld
                if min_last_date is not None:
                    batch_start_dt = (pd.Timestamp(min_last_date) - timedelta(days=self.INCREMENT_BACK_DAYS)).strftime("%Y-%m-%d")
                else:
                    batch_start_dt = "2010-01-01"

            batch_full_df = self.storage.get_indicators_with_quotes_batch(
                codes=std_chunk_codes,
                cycle="1d",
                start_date=batch_start_dt,
                end_date=end_date
            )
            if batch_full_df.empty:
                logger.warning("当前批次无指标行情数据，直接跳过")
                continue

            chunk_signal_df = self.detect_all_signals_vectorized_full_batch(batch_full_df)

            if not chunk_signal_df.empty:
                # ---- 向量化增量过滤（merge代替groupby.apply） ----
                if incremental and last_calc_watermark:
                    # 构造 watermark DataFrame
                    watermark_items = [(k, v) for k, v in last_calc_watermark.items() if k in std_chunk_codes]
                    if watermark_items:
                        watermark_df = pd.DataFrame(watermark_items, columns=['code', 'last_date'])
                        watermark_df['last_date'] = pd.to_datetime(watermark_df['last_date']).dt.date
                        # 左连接
                        merged = chunk_signal_df.merge(watermark_df, on='code', how='left')
                        # 保留无记录或 trade_date > last_date 的信号
                        filtered = merged[(merged['last_date'].isna()) | (merged['trade_date'] > merged['last_date'])]
                        chunk_signal_df = filtered.drop(columns=['last_date']).reset_index(drop=True)
                    else:
                        # 无任何股票有历史记录，全部保留
                        pass

                if not chunk_signal_df.empty:
                    # 去重：确保 (code, trade_date, signal_type, signal_direction) 唯一，保留第一条
                    chunk_signal_df = chunk_signal_df.drop_duplicates(
                        subset=['code', 'trade_date', 'signal_type', 'signal_direction'],
                        keep='first'
                    ).reset_index(drop=True)
                    
                    if chunk_signal_df.empty:
                        logger.info("当前批次信号去重后为空")
                    else:
                        insert_count = self.storage.save_signals_batch(chunk_signal_df)
                        total_write_signals += insert_count
                        hit_stocks = chunk_signal_df["code"].unique().tolist()
                        stock_with_signal.update(hit_stocks)
                        logger.info(f"批次完成｜入库信号:{insert_count}条｜产生信号股票:{len(hit_stocks)}只")
                else:
                    logger.info("当前批次无新信号（过滤后为空）")
            else:
                logger.info("当前批次无新信号生成")

            del batch_full_df, chunk_signal_df
            gc.collect()

        logger.info("=============================================")
        logger.info("批量预计算任务全部完成")
        logger.info(f"总股票数:{total_stock_cnt}｜产生信号股票:{len(stock_with_signal)}")
        logger.info(f"累计入库交易信号:{total_write_signals}")
        logger.info("=============================================")
        return {
            "total_stocks": total_stock_cnt,
            "success_stocks": len(stock_with_signal),
            "total_signals": total_write_signals
        }

    def precompute_all_signals(self, start_date: str = None, end_date: str = None, force_full: bool = False) -> Dict[str, int]:
        return self.precompute_all_signals_batch(
            start_date=start_date,
            end_date=end_date,
            incremental=not force_full
        )


def main():
    db_conf = config.get("database", {})
    storage = PostgreSQLStorage({
        "host": db_conf.get("host", "localhost"),
        "port": db_conf.get("port", 5432),
        "database": db_conf.get("database", "quant_trading"),
        "username": db_conf.get("username", ""),
        "password": db_conf.get("password", "")
    })
    try:
        storage.connect()
        storage.init_tables()
        calc_task = SignalPrecompute(storage)
        result_stats = calc_task.precompute_all_signals()
    finally:
        storage.disconnect()
    return result_stats


if __name__ == "__main__":
    stats = main()
    print("\n==== 任务执行统计结果 ====")
    print(f"全部股票总数: {stats['total_stocks']}")
    print(f"生成有效信号股票数: {stats['success_stocks']}")
    print(f"总交易信号入库条数: {stats['total_signals']}")
    print(f'TASK_RESULT:{json.dumps({"rows_affected": stats["total_signals"], "extra_metrics": stats})}')