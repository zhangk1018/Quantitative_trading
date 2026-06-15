#!/usr/bin/env python3
"""
PyWenCai 数据源 — 同花顺问财接口

通过自然语言查询获取全市场基本面数据（PE/PB/市值/换手率/量比）。
特点：完全免费、无需 Token、全市场一次性拉取（~45秒）。

作为 daily_basic 的主用数据源，Baostock 作为备用。
"""
import re
import time
import traceback
import logging
import pandas as pd
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger('pywencai')

# 请求间隔（秒），避免触发同花顺频率限制
REQUEST_INTERVAL = 5
# 最大重试次数（针对 504 等临时错误）
MAX_RETRIES = 3


class PyWencaiDataSource:
    """PyWenCai（同花顺问财）数据源"""

    @property
    def name(self) -> str:
        return "PyWenCai"

    def __init__(self):
        self._connected = False
        self._last_request_time = 0

    def connect(self) -> bool:
        try:
            import pywencai
            self._wc = pywencai
            self._connected = True
            logger.info("✅ PyWenCai 连接成功")
            return True
        except ImportError:
            logger.warning("⚠️ pywencai 未安装，请执行: pip install pywencai")
            return False
        except Exception as e:
            logger.error(f"❌ PyWenCai 连接失败: {e}")
            return False

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def health_check(self) -> bool:
        """健康检查：尝试执行一次简单查询"""
        try:
            self._ensure_connected()
            return self._connected
        except Exception:
            return False

    def _ensure_connected(self):
        if not self._connected:
            raise RuntimeError("PyWenCai 未连接，请先调用 connect()")

    def _wait_for_rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    @staticmethod
    def _normalize_code(raw_code: str) -> str:
        """
        将问财代码格式转为内部格式。
        问财: '600000' / '600000.SH' / '000988.SZ'
        内部: '600000' / '000001' (纯数字)
        """
        code = str(raw_code).strip()
        # 去掉 .SH / .SZ 后缀
        code = re.sub(r'\.(SH|SZ|sh|sz)$', '', code)
        return code

    def get_daily_basic(self, trade_date: str, **kwargs) -> pd.DataFrame:
        """
        获取指定日期的全市场日频基本面数据。

        通过单次合并查询获取所有基本面字段：
          close, pe, pe_ttm, pb, total_mv, circ_mv,
          turnover_rate, volume_ratio, ps_ttm, dv_ratio, dv_ttm, float_share

        Args:
            trade_date: 交易日期，格式 YYYY-MM-DD

        Returns:
            DataFrame: 包含 code, trade_date, close, turnover_rate,
                       volume_ratio, pe, pe_ttm, pb, total_mv, circ_mv,
                       ps_ttm, dv_ratio, dv_ttm, float_share
        """
        self._ensure_connected()

        logger.info(f"📡 PyWenCai 获取 {trade_date} 基本面数据...")

        # 单次合并查询，一次性获取所有字段
        # 测试结果：5207 条数据，约 72 秒（原多次查询约 7 分钟）
        df = self._single_query(
            '全部A股 股票代码 最新价 市盈率 市净率 总市值 流通市值 '
            '换手率 量比 市销率TTM 股息率 流通A股'
        )

        if df is None or df.empty:
            logger.warning(f"  ⚠️ PyWenCai 查询无数据")
            return pd.DataFrame()

        # 检查关键字段是否存在
        required_fields = ['code', 'close', 'pe_ttm', 'pb', 'total_mv', 'circ_mv',
                           'turnover_rate', 'volume_ratio', 'ps_ttm', 'dv_ratio',
                           'dv_ttm', 'float_share']
        missing = [f for f in required_fields if f not in df.columns]
        if missing:
            logger.warning(f"  ⚠️ 缺少字段: {missing}")

        df['trade_date'] = trade_date

        # 排列字段顺序
        cols_order = [
            'code', 'trade_date', 'close',
            'turnover_rate', 'volume_ratio',
            'pe', 'pe_ttm', 'pb',
            'total_mv', 'circ_mv',
            'ps_ttm', 'dv_ratio', 'dv_ttm', 'float_share',
        ]
        final_cols = [c for c in cols_order if c in df.columns]
        result = df[final_cols]

        logger.info(f"  ✅ PyWenCai 获取完成: {len(result)} 条记录")
        return result

    def _query_fundamentals(self, trade_date: str) -> Optional[pd.DataFrame]:
        """查询基本面指标（拆分单字段查询，避免超时）"""
        results = {}

        # 逐个字段查询
        queries = [
            ('全部A股 股票代码 股票简称 最新价', ['close']),
            ('全部A股 股票代码 市盈率TTM', ['pe_ttm', 'pe']),
            ('全部A股 股票代码 市净率', ['pb']),
            ('全部A股 股票代码 总市值', ['total_mv']),
            ('全部A股 股票代码 流通市值', ['circ_mv']),
        ]

        for query, fields in queries:
            df = self._single_query(query)
            if df is not None and not df.empty:
                # 关键修复：每个查询只保留 code + 目标字段
                # （避免多个查询返回相同附带列[name/最新涨跌幅/股票市场类型/market_code]导致merge冲突）
                target_cols = ['code'] + [f for f in fields if f in df.columns]
                df = df[target_cols]
                results[query] = (df, fields)
                logger.debug(f"    成功获取: {query} -> {len(df)} 条, 列: {list(df.columns)}")
            else:
                logger.warning(f"    ⚠️ 获取失败: {query}")

        if not results:
            return None

        # 合并所有数据（以第一个结果为基础）
        first_df, _ = list(results.values())[0]
        merged = first_df.copy()

        # 关键修复：跳过第一个查询（已作为 first_df），避免重复 merge 产生 close_x/close_y
        for query, (df, fields) in list(results.items())[1:]:
            if len(df) == 0:
                continue
            # 按 code 合并（每个 df 只有 code + 目标字段，无冲突）
            merged = merged.merge(df, on='code', how='outer')

        # 只保留需要的列
        keep = [c for c in ['code', 'close', 'pe', 'pe_ttm', 'pb', 'total_mv', 'circ_mv']
                if c in merged.columns]

        return merged[keep] if keep else None

    def _single_query(self, query: str) -> Optional[pd.DataFrame]:
        """单次查询（带重试）"""
        for attempt in range(1, MAX_RETRIES + 1):
            self._wait_for_rate_limit()
            try:
                t0 = time.time()
                result = self._wc.get(query=query, loop=True)
                t1 = time.time()
                logger.debug(f"    查询耗时: {t1-t0:.1f}s (第{attempt}次)")

                if isinstance(result, (int, float)):
                    if attempt < MAX_RETRIES:
                        logger.warning(f"    ⚠️ 返回错误码: {result}，重试 ({attempt}/{MAX_RETRIES})...")
                        time.sleep(REQUEST_INTERVAL)
                        continue
                    return None

                if result is None or (hasattr(result, 'empty') and result.empty):
                    return None

                if isinstance(result, dict) and 'data' in result:
                    df = result['data']
                elif isinstance(result, pd.DataFrame):
                    df = result
                else:
                    return None

                # 关键修复：先丢弃 PyWenCai 自带的 'code' 列
                # （避免与下面把'股票代码' rename 为 'code' 冲突，导致 merge 时 KeyError: 0）
                if 'code' in df.columns:
                    df = df.drop(columns=['code'])

                # 字段映射
                col_map = {}
                for col in df.columns:
                    lower = col.lower()
                    if '代码' in col and '股票' in col:
                        col_map[col] = 'code'
                    elif '简称' in col:
                        col_map[col] = 'name'
                    elif '最新价' in lower or '收盘价' in lower:
                        col_map[col] = 'close'
                    elif 'pe,ttm' in lower or ('ttm' in lower and 'pe' in lower):
                        col_map[col] = 'pe_ttm'
                    elif 'pe' in lower and 'ttm' not in lower and 'ps' not in lower and '预测' not in col:
                        col_map[col] = 'pe'
                    elif '市净率' in lower or ('pb' in lower and 'ps' not in lower):
                        col_map[col] = 'pb'
                    elif '总市值' in lower:
                        col_map[col] = 'total_mv'
                    elif '流通市值' in lower or 'a股市值' in lower:
                        col_map[col] = 'circ_mv'
                    elif '换手率' in lower:
                        col_map[col] = 'turnover_rate'
                    elif '量比' in lower:
                        col_map[col] = 'volume_ratio'
                    elif '市销率' in lower or ('ps' in lower and 'ttm' in lower):
                        col_map[col] = 'ps_ttm'
                    elif '股息率' in lower and '近12个月' in col:
                        col_map[col] = 'dv_ttm'
                    elif '股息率' in lower and '股票获利率' in col:
                        col_map[col] = 'dv_ratio'
                    elif '股息率' in lower:
                        col_map[col] = 'dv_ttm'
                    elif '流通a股' in lower or '流通股本' in lower:
                        col_map[col] = 'float_share'

                df = df.rename(columns=col_map)

                # 标准化 code
                if 'code' in df.columns:
                    df['code'] = df['code'].apply(self._normalize_code)

                # 关键修复：PyWenCai 可能返回多个 'a股市值[20260609]' / 'a股市值[+20260609]' 都重命名为 circ_mv
                # 保留第一个出现的，去重避免 merge 冲突
                df = df.loc[:, ~df.columns.duplicated()].copy()

                return df

            except Exception as e:
                logger.error(f"    ❌ 查询失败: {type(e).__name__}: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(REQUEST_INTERVAL)
                else:
                    return None

        return None

    def _query_volume(self, trade_date: str) -> Optional[pd.DataFrame]:
        """查询换手率和量比（拆分单字段查询，避免超时）"""
        results = {}

        queries = [
            ('全部A股 股票代码 换手率', ['turnover_rate']),
            ('全部A股 股票代码 量比', ['volume_ratio']),
        ]

        for query, fields in queries:
            df = self._single_query(query)
            if df is not None and not df.empty:
                # 关键修复：每个查询只保留 code + 目标字段（避免 merge 冲突）
                target_cols = ['code'] + [f for f in fields if f in df.columns]
                df = df[target_cols]
                results[query] = (df, fields)
                logger.debug(f"    成功获取: {query} -> {len(df)} 条, 列: {list(df.columns)}")
            else:
                logger.warning(f"    ⚠️ 获取失败: {query}")

        if not results:
            return None

        # 合并数据
        first_df, _ = list(results.values())[0]
        merged = first_df.copy()

        # 关键修复：跳过第一个查询（已作为 first_df），避免重复 merge
        for query, (df, fields) in list(results.items())[1:]:
            if len(df) == 0:
                continue
            merged = merged.merge(df, on='code', how='outer')

        keep = [c for c in ['code', 'turnover_rate', 'volume_ratio'] if c in merged.columns]
        return merged[keep] if keep else None

    def _query_ps(self, trade_date: str) -> Optional[pd.DataFrame]:
        """查询市销率TTM（ps_ttm）"""
        df = self._single_query('全部A股 股票代码 市销率TTM')
        if df is None or df.empty:
            logger.warning("  ⚠️ PyWenCai 市销率查询无数据")
            return None
        target_cols = ['code'] + ([c for c in ['ps_ttm'] if c in df.columns])
        result = df[target_cols] if all(c in df.columns for c in target_cols) else df[['code']]
        logger.info(f"  ✅ 市销率: {len(result)} 条")
        return result

    def _query_dividend(self, trade_date: str) -> Optional[pd.DataFrame]:
        """查询股息率（dv_ratio, dv_ttm）"""
        df = self._single_query('全部A股 股票代码 股息率')
        if df is None or df.empty:
            logger.warning("  ⚠️ PyWenCai 股息率查询无数据")
            return None
        target_cols = ['code'] + [c for c in ['dv_ratio', 'dv_ttm'] if c in df.columns]
        result = df[target_cols] if all(c in df.columns for c in target_cols) else df[['code']]
        logger.info(f"  ✅ 股息率: {len(result)} 条")
        return result

    def _query_float_share(self, trade_date: str) -> Optional[pd.DataFrame]:
        """查询流通股本（float_share）"""
        df = self._single_query('全部A股 股票代码 流通股本')
        if df is None or df.empty:
            logger.warning("  ⚠️ PyWenCai 流通股本查询无数据")
            return None
        target_cols = ['code'] + [c for c in ['float_share'] if c in df.columns]
        result = df[target_cols] if all(c in df.columns for c in target_cols) else df[['code']]
        logger.info(f"  ✅ 流通股本: {len(result)} 条")
        return result
