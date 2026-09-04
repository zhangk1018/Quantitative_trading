#!/usr/bin/env python3
"""
港股/美股下载公共能力：限流 + 断点续传游标。

背景：
- 限流：AkShare（新浪）源未启用批间休眠，循环内连续请求易触发数据源限流（表现为「拉取为空」）。
  这里统一按 MarketConfig.batch_interval_min_sleep / max_sleep 在每个标的处理后随机休眠，
  与 Yahoo 源（yahoo.py `_interval_sleep`）的限流语义保持一致。
- 断点续传：仅靠 etl_control.last_sync_date 重启后需从头重跑全部标的。这里复用同一张表新增的
  last_processed_code 游标列，每处理一个标的即回写游标，中断后从游标之后继续，跳过已处理标的的网络请求。

本模块供 import_hk_daily.py / import_us_daily.py 复用，避免两脚本各自维护重复实现。
"""
import random
import time
from typing import List, Optional

import psycopg2


def get_market_last_processed_code(
    conn: psycopg2.extensions.connection, market: str
) -> Optional[str]:
    """读取 etl_control 中断点续传游标（market 对应行 last_processed_code）。无则返回 None。"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_processed_code FROM etl_control WHERE market = %s",
                (market,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None
    except psycopg2.DatabaseError as e:
        logger_safe_warning(f"⚠️ 读取 etl_control last_processed_code 失败: {e}")
        return None


def set_market_last_processed_code(
    conn: psycopg2.extensions.connection, market: str, code: Optional[str]
) -> None:
    """回写/清空 etl_control 的 last_processed_code（code=None 表示整批跑完清空游标）。

    仅 UPDATE 已存在的 market 行，不 INSERT：
    - etl_control.last_sync_date 为 NOT NULL，而游标写入并不携带日期；
      若走 `INSERT ... ON CONFLICT`，在冲突未被识别前 PostgreSQL 会先按插入路径
      校验 last_sync_date 的 NOT NULL，从而抛错。
    - market 行由 set_last_sync_date 在首次同步成功后创建，故此处在行已存在前提下
      直接 UPDATE 即可（行不存在时游标不持久化，属可接受——数据仍正常写入）。
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE etl_control SET last_processed_code = %s, updated_at = CURRENT_TIMESTAMP "
                "WHERE market = %s",
                (code, market),
            )
        conn.commit()
    except psycopg2.DatabaseError as e:
        conn.rollback()
        logger_safe_warning(f"⚠️ 写 etl_control last_processed_code 失败: {e}")


def resume_codes(codes: List[str], last_proc: Optional[str]) -> int:
    """根据断点续传游标，丢弃已处理的标的，返回剩余待处理列表（不变更入参）。

    codes 需按升序（与下载遍历顺序一致）。
    - 无游标：全部待处理。
    - 游标在列表中：从游标后一个继续。
    - 游标不在列表（列表变化）防御：按 code > 游标 过滤（假设 code 字典序即处理顺序）。

    Args:
        codes: 全部待处理代码列表（有序）
        last_proc: 上次处理到的 code；None 表示无游标

    Returns:
        剩余待处理列表
    """
    if not last_proc:
        return codes
    try:
        idx = codes.index(last_proc)
        return codes[idx + 1:]
    except ValueError:
        return [c for c in codes if c > last_proc]


def rate_limit_sleep(cfg) -> None:
    """按市场配置的批间随机休眠区间，在下载循环每次迭代后限流。"""
    try:
        lo = float(getattr(cfg, "batch_interval_min_sleep", 0.0) or 0.0)
        hi = float(getattr(cfg, "batch_interval_max_sleep", 0.0) or 0.0)
    except (TypeError, ValueError):
        lo = hi = 0.0
    if hi < lo:
        lo, hi = hi, lo
    if hi <= 0:
        return
    time.sleep(random.uniform(lo, hi))


def logger_safe_warning(msg: str) -> None:
    """延迟导入 logging，避免模块顶层耦合具体 logger 名。"""
    import logging
    logging.getLogger(__name__).warning(msg)