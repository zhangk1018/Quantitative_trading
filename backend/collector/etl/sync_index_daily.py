#!/usr/bin/env python3
"""
指数日线采集入库脚本（合作单 37.0：指数 K 线未入库）

采集沪深300 + 上证指数日线，写入 stock_quotes 表：
- 代码口径：沪深300 = `000300`，上证指数 = `999999`（与 `/api/kline` 归一化一致）
- market = 'index'：与 A 股快照/指标/选股（market='cn'，源 stock_basic）隔离，
  确保指数不混入选股/快照全量导出（回归要求），同时 `/api/kline`（按 code 查，不按 market）可命中。
- cycle = '1d'，adjust_type = 'qfq'（指数无除权，直接存原始价）

数据源优先级链（协作单 37.0 选型结论）：
  BaoStock (sh.000300 / sh.000001, 主) → AkShare(sina `stock_zh_index_daily`, 备)

用法：
  # 增量（默认，与日线导入一起跑）
  ./venv/bin/python backend/collector/etl/sync_index_daily.py --incremental

  # 全量回填历史（首次）
  ./venv/bin/python backend/collector/etl/sync_index_daily.py --full
"""
from __future__ import annotations

import os
import sys
import json
import argparse
import time
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, Dict

import pandas as pd

# 确保 backend 包可导入
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402
import baostock as bs  # noqa: E402
import akshare as ak  # noqa: E402
import psycopg2  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(BACKEND_DIR), ".env"))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger('sync_index_daily')

# 指数代码表：store_code=入库/接口归一化代码；bs_code=Baostock；ak_sina=AkShare sina 源
INDEX_CODES: Dict[str, Dict[str, str]] = {
    '000300': {'name': '沪深300', 'bs_code': 'sh.000300', 'ak_sina': 'sh000300'},
    '999999': {'name': '上证指数', 'bs_code': 'sh.000001', 'ak_sina': 'sh000001'},
}

# 默认全量/增量回溯窗口（天），保证约一年以上数据，可覆盖回测预热
DEFAULT_BACKFILL_DAYS = 400


def get_db_conn():
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5432')),
        database=os.getenv('PG_DATABASE', 'quant_trading'),
        user=os.getenv('PG_USER', 'quant_user'),
        password=os.getenv('PG_PASSWORD', ''),
    )


def fetch_baostock(index_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Baostock 主源：指数日线（原始价格，无复权概念）。"""
    lg = bs.login()
    if lg.error_code != '0':
        logger.warning(f"BaoStock 登录失败({index_code}): {lg.error_msg}")
        return None
    try:
        rs = bs.query_history_k_data_plus(
            index_code, "date,code,open,high,low,close,preclose,volume,amount",
            start_date=start_date, end_date=end_date, frequency="d")
        if rs.error_code != '0':
            logger.warning(f"BaoStock 查询失败({index_code}): {rs.error_msg}")
            return None
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["date", "code", "open", "high", "low",
                                         "close", "preclose", "volume", "amount"])
        for c in ["open", "high", "low", "close", "preclose", "volume", "amount"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.rename(columns={"preclose": "pre_close"})
        return df
    except Exception as e:  # noqa: BLE001
        logger.warning(f"BaoStock 拉取异常({index_code}): {e}")
        return None
    finally:
        try:
            bs.logout()
        except Exception:  # noqa: BLE001
            pass


def fetch_akshare_sina(sina_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """AkShare(sina 源) 备源：指数日线。"""
    try:
        df = ak.stock_zh_index_daily(symbol=sina_code)
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["pre_close"] = df["close"].shift(1).fillna(df["open"])
        # 过滤出目标区间
        df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
        return df[["date", "open", "high", "low", "close", "pre_close", "volume"]]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"AkShare(sina) 拉取异常({sina_code}): {e}")
        return None


def get_last_date(conn, store_code: str) -> Optional[str]:
    """查询指定指数在 stock_quotes 中的最大交易日期（market='index'）。"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT MAX(trade_date)::text FROM stock_quotes
            WHERE code = %s AND cycle = '1d' AND market = 'index'
        """, (store_code,))
        row = cur.fetchone()
        return row[0] if row and row[0] else None


def save_index_quotes(conn, code: str, df: pd.DataFrame) -> int:
    """批量 upsert 指数日线。market='index' 隔离，避免混入 A 股快照/选股。"""
    if df is None or df.empty:
        return 0
    df = df.copy()
    df["code"] = code
    df["cycle"] = '1d'
    df["market"] = 'index'
    df["adjust_type"] = 'qfq'
    if "amount" not in df.columns:
        df["amount"] = None
    if "volume" not in df.columns:
        df["volume"] = 0
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
    for c in ["open", "high", "low", "close", "pre_close", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df.columns else None
    df = df.dropna(subset=["open", "high", "low", "close"])

    df["trade_date"] = df["date"]
    df["trade_datetime"] = pd.to_datetime(df["trade_date"]) + pd.Timedelta("15:00:00")

    # 构造 INSERT ... ON CONFLICT ，利用 (code, cycle, trade_date, adjust_type) 唯一约束
    values = [
        (row["code"], row["market"], row["cycle"], row["trade_date"],
         row["open"], row["high"], row["low"], row["close"],
         row["pre_close"], row["volume"], row["amount"], row["adjust_type"],
         row["trade_datetime"])
        for _, row in df.iterrows()
    ]
    from psycopg2.extras import execute_values
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO stock_quotes (code, market, cycle, trade_date, open, high, low, close,
                                      pre_close, volume, amount, adjust_type, trade_datetime)
            VALUES %s
            ON CONFLICT (code, cycle, trade_date, adjust_type) DO UPDATE SET
                market = EXCLUDED.market,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                pre_close = EXCLUDED.pre_close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                trade_datetime = EXCLUDED.trade_datetime
        """, values, page_size=2000)
    conn.commit()
    return len(df)


def sync_index(store_code: str, start_date: str, end_date: str) -> Tuple[bool, int, str]:
    """同步单只指数，BaoStock 主源优先，失败降级 AkShare(sina)。返回 (成功?, 写入行数, 来源)。"""
    meta = INDEX_CODES[store_code]
    logger.info(f"📈 同步 {meta['name']} ({store_code}) {start_date} ~ {end_date}")

    df = fetch_baostock(meta['bs_code'], start_date, end_date)
    source = 'BaoStock'
    if df is None or df.empty:
        logger.warning(f"{meta['name']}: BaoStock 无数据，降级 AkShare(sina)")
        df = fetch_akshare_sina(meta['ak_sina'], start_date, end_date)
        source = 'AkShare(sina)'

    # 增量且已有历史数据、但窗口内无新数据（如非交易日）：视为"已最新"，不报错
    if df is None or df.empty:
        with get_db_conn() as conn:
            last_date = get_last_date(conn, store_code)
        if last_date is not None:
            logger.info(f"ℹ️ {meta['name']}: 库内最新 {last_date}，本次窗口 {start_date}~{end_date} 无新增交易日，已是最新 → 跳过")
            return True, 0, 'skip'
        logger.error(f"❌ {meta['name']}: 主备源均无数据且库内无历史")
        return False, 0, source

    with get_db_conn() as conn:
        count = save_index_quotes(conn, store_code, df)
    logger.info(f"✅ {meta['name']} ({store_code}): 写入 {count} 条（来源 {source}）")
    return True, count, source


def main():
    parser = argparse.ArgumentParser(description='指数日线采集入库脚本')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--incremental', action='store_true', help='增量导入（从库内最新日期起回溯 DEFAULT_BACKFILL_DAYS 天）')
    group.add_argument('--full', action='store_true', help='全量回填历史（默认从 DEFAULT_BACKFILL_DAYS 天前起）')
    parser.add_argument('--code', type=str, default=None, help='指定指数代码（000300/999999），默认全部')
    parser.add_argument('--start', type=str, default=None, help='起始日期（YYYY-MM-DD，--full 时优先于默认回溯窗口）')
    args = parser.parse_args()

    today = datetime.now().strftime('%Y-%m-%d')

    selected = {k: v for k, v in INDEX_CODES.items() if not args.code or k == args.code}

    total_written = 0
    ok_count = 0
    fail_count = 0
    conn = get_db_conn()
    try:
        for store_code, meta in selected.items():
            # 计算起始日期
            if args.incremental:
                last_date = get_last_date(conn, store_code)
                if last_date:
                    start = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
                    logger.info(f"  {meta['name']}: 库内最新 {last_date}，从 {start} 增量")
                else:
                    start = (datetime.now() - timedelta(days=DEFAULT_BACKFILL_DAYS)).strftime('%Y-%m-%d')
                    logger.info(f"  {meta['name']}: 库内无数据，起始 {start}")
            else:
                if args.start:
                    start = args.start
                    logger.info(f"  {meta['name']}: --start 指定起始 {start}")
                else:
                    start = (datetime.now() - timedelta(days=DEFAULT_BACKFILL_DAYS)).strftime('%Y-%m-%d')

            ok, count, source = sync_index(store_code, start, today)
            total_written += count
            if ok:
                ok_count += 1
            else:
                fail_count += 1
    finally:
        conn.close()

    result = {"rows_affected": total_written,
              "extra_metrics": {"success": ok_count, "fail": fail_count, "indices": list(selected.keys()),
                                "mode": "incremental" if args.incremental else "full"}}
    print(f'TASK_RESULT:{json.dumps(result)}')
    logger.info(f"指数同步完成: 成功 {ok_count}, 失败 {fail_count}, 共写入 {total_written} 条")
    sys.stdout.flush()
    # 全部失败视为非零退出
    sys.exit(1 if ok_count == 0 and fail_count > 0 else 0)


if __name__ == '__main__':
    main()