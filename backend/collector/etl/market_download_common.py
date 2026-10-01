#!/usr/bin/env python3
"""
港股/美股下载公共能力：限流 + 断点续传游标。

背景：
- 限流：AkShare（新浪）源未启用批间休眠，循环内连续请求易触发数据源限流（表现为「拉取为空」）。
  这里统一按 MarketConfig.batch_interval_min_sleep / max_sleep 在每个标的处理后随机休眠，
  与 Yahoo 源（yahoo.py `_interval_sleep`）的限流语义保持一致。
- 断点续传：仅靠 etl_control.last_sync_date 重启后需从头重跑全部标的。这里复用同一张表新增的
  last_processed_code 游标列，每处理一个标的即回写游标，中断后从游标之后继续，跳过已处理标的的网络请求。
- 游标窗口绑定：游标必须与**日期窗口**绑定（last_processed_window 列）。若不加绑定，上一轮窗口
  留下的游标会在本轮（窗口已变）被继续复用，把游标之前尚未覆盖新窗口的标的静默跳过，造成永久数据缺口。

本模块供 import_hk_daily.py / import_us_daily.py 复用，避免两脚本各自维护重复实现。
"""
import random
import time
from datetime import datetime
from typing import List, Optional, Set, Tuple

import psycopg2


def trading_days_between(
    days: Optional[Set], start: str, end_excl: str
) -> Optional[Set]:
    """从某市场的交易日集合中裁剪出半开区间 `[start, end_excl)` 的部分。

    各市场交易日集合由各自数据源提供（港股恒生指数 / 美股纳斯达克指数，见
    AkShareDataSource.download_hk_trade_dates / download_us_trade_dates），此处仅做
    区间裁剪，供下载脚本判定「窗口内是否仍有待补交易日」。

    Args:
        days: 该市场全部交易日集合；None/空集（数据源探测失败）原样返回 None
        start: 起始日期（YYYY-MM-DD，含）
        end_excl: 结束日期（YYYY-MM-DD，不含）

    Returns:
        区间内的交易日集合；入参不可用时返回 None（调用方须保守处理）
    """
    if not days:
        return None
    s = datetime.strptime(start, '%Y-%m-%d').date()
    e = datetime.strptime(end_excl, '%Y-%m-%d').date()
    return {d for d in days if s <= d < e}


def coverage_gaps(
    conn: psycopg2.extensions.connection,
    market: str,
    days: Optional[Set],
    min_ratio: float = 0.90,
    cycle: str = '1d',
) -> List[Tuple]:
    """统计各交易日的入库覆盖率，返回**未达标**的交易日清单（防静默缺口）。

    断点游标 + 回写 last_sync_date 的组合下，被游标跳过的标的会永久缺失该窗口数据且
    无任何报错（静默缺口）。故推进增量进度前必须逐交易日校验入库覆盖率：基线取
    stock_basic 中该市场标的数，低于 min_ratio 即视为未真正覆盖全市场。

    Args:
        conn: psycopg2 连接
        market: 市场标识（hk/us）
        days: 需要校验的交易日集合；None/空集返回空清单（由调用方决定是否保守处理）
        min_ratio: 覆盖率阈值（默认 0.90）
        cycle: K 线周期（默认 '1d'）

    Returns:
        [(交易日, 实际入库数, 覆盖率, 基线数)]；全部达标时为空清单。
        数据库错误抛 psycopg2.DatabaseError，由调用方决定保守策略。
    """
    if not days:
        return []
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM stock_basic WHERE market = %s", (market,))
        row = cur.fetchone()
        total = int(row[0]) if row and row[0] else 0
        if total <= 0:
            return []
        gaps: List[Tuple] = []
        for d in sorted(days):
            cur.execute(
                "SELECT COUNT(DISTINCT code) FROM stock_quotes "
                "WHERE market = %s AND cycle = %s AND trade_date = %s",
                (market, cycle, d),
            )
            n = int(cur.fetchone()[0] or 0)
            if n / total < min_ratio:
                gaps.append((d, n, n / total, total))
        return gaps


def market_window_key(start: str, end: str) -> str:
    """构造下载窗口标识（`起始日~结束日`），用于把断点游标绑定到具体日期窗口。

    Args:
        start: 窗口起始日（YYYY-MM-DD）
        end: 窗口结束日（YYYY-MM-DD）

    Returns:
        窗口标识字符串（如 `2026-09-25~2026-09-28`）
    """
    return f"{start}~{end}"


def get_market_last_processed_code(
    conn: psycopg2.extensions.connection, market: str, window: Optional[str] = None
) -> Optional[str]:
    """读取 etl_control 中断点续传游标（market 对应行 last_processed_code）。无则返回 None。

    Args:
        conn: psycopg2 连接
        market: 市场标识（hk/us）
        window: 当前日期窗口标识（market_window_key 生成）。传入时做**窗口绑定校验**：
            仅当库中游标记录的窗口与之相同才返回游标，否则视为无游标（完整处理，
            避免跨窗口复用游标造成静默缺口）。None 表示不做校验（沿用旧行为）。

    Returns:
        可复用的游标 code；无游标或窗口不匹配时返回 None
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_processed_code, last_processed_window FROM etl_control WHERE market = %s",
                (market,),
            )
            row = cur.fetchone()
        if not row or not row[0]:
            return None
        code, stored_window = row[0], row[1]
        if window and stored_window != window:
            logger_safe_warning(
                f"⚠️ 断点游标 {code} 属窗口 {stored_window}，与当前窗口 {window} 不一致，"
                f"忽略游标并完整处理（防跨窗口静默缺口）"
            )
            return None
        return code
    except psycopg2.DatabaseError as e:
        logger_safe_warning(f"⚠️ 读取 etl_control last_processed_code 失败: {e}")
        return None


def set_market_last_processed_code(
    conn: psycopg2.extensions.connection,
    market: str,
    code: Optional[str],
    window: Optional[str] = None,
) -> None:
    """回写/清空 etl_control 的 last_processed_code（code=None 表示整批跑完清空游标）。

    Args:
        conn: psycopg2 连接
        market: 市场标识（hk/us）
        code: 已处理到的 code；None 表示整批跑完，清空游标
        window: 与游标绑定的日期窗口标识（market_window_key 生成）；code 为 None 时一并清空

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
                "UPDATE etl_control SET last_processed_code = %s, last_processed_window = %s, "
                "updated_at = CURRENT_TIMESTAMP WHERE market = %s",
                (code, window if code else None, market),
            )
        conn.commit()
    except psycopg2.DatabaseError as e:
        conn.rollback()
        logger_safe_warning(f"⚠️ 写 etl_control last_processed_code 失败: {e}")


def resume_codes(codes: List[str], last_proc: Optional[str]) -> List[str]:
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