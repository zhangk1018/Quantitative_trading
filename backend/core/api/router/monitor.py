"""
router/monitor.py - 数据监控看板 API 路由

提供数据完整性、管道状态、下载进度、数据质量、系统健康等监控指标。
所有端点返回统一 ApiResponse 信封。
"""

import os
import re
import sys
import time
import queue
import threading
import functools
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Query
import psycopg2
import psycopg2.extras
import psycopg2.pool

from shared.schemas import ApiResponse

# 添加 backend 目录到路径以导入 monitoring 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from monitoring.system_monitor import SystemMonitor

logger = logging.getLogger(__name__)
router = APIRouter(tags=["数据监控"])


# ============================================
# 监控阈值配置（统一管理，便于不同市场/环境调整）
# ============================================


class MonitorConfig:
    """监控阈值配置 - 可通过环境变量覆盖"""
    # 覆盖数：低于此值视为"数据不足"
    MIN_COVERAGE_COUNT = int(os.getenv("MONITOR_MIN_COVERAGE_COUNT", "3000"))
    # 各任务最低数据条数
    TASK_MIN_COUNTS = {
        "daily_import":      int(os.getenv("MONITOR_MIN_DAILY_IMPORT", "4000")),
        "daily_sync":        int(os.getenv("MONITOR_MIN_DAILY_SYNC", "4000")),
        "daily_basic_sync":  int(os.getenv("MONITOR_MIN_BASIC_SYNC", "4000")),
        "adj_factor_sync":   int(os.getenv("MONITOR_MIN_ADJ_FACTOR", "4000")),
        "indicators_compute": int(os.getenv("MONITOR_MIN_INDICATORS", "4000")),
        "signal_precompute": int(os.getenv("MONITOR_MIN_SIGNALS", "100")),
    }
    # 2年活跃窗口（覆盖新数据准确性的时间范围）
    ACTIVE_DAYS = int(os.getenv("MONITOR_ACTIVE_DAYS", "730"))
    # 覆盖率阈值（成功/部分/失败的分界）
    COVERAGE_SUCCESS = float(os.getenv("MONITOR_COVERAGE_SUCCESS", "95"))  # >=95% 视为成功
    COVERAGE_FAIL = float(os.getenv("MONITOR_COVERAGE_FAIL", "50"))        # <50% 视为失败
    # 异常端点错误码
    ERR_QUERY_FAILED = 503  # 数据库查询失败


# ============================================
# 数据库连接辅助
# ============================================

# 北京时区（统一时区基准，监控数据按北京时间归集）
BEIJING_TZ = timezone(timedelta(hours=8))


def _now_beijing() -> datetime:
    """返回带时区标记的当前北京时间"""
    return datetime.now(BEIJING_TZ)


def _get_last_trade_date(ref_date: datetime) -> str:
    """
    计算最近一个交易日（跳过周末，简化处理不含节假日）。
    - 周一~周五 15:30 之后：返回当天
    - 周一~周五 15:30 之前：返回前一个工作日
    - 周六/周日：返回周五
    """
    weekday = ref_date.weekday()  # 0=Mon, 6=Sun
    hour = ref_date.hour

    if weekday >= 5:  # Sat=5, Sun=6
        delta = weekday - 4  # Sat->1, Sun->2 days back to Friday
        target = ref_date - timedelta(days=delta)
    elif hour < 15:  # 工作日 15:00 前，市场未收盘
        # 周一回退到周五，其他工作日回退到前一天
        delta = 3 if weekday == 0 else 1
        target = ref_date - timedelta(days=delta)
    else:
        target = ref_date
    return target.strftime("%Y-%m-%d")


def _get_db_conn():
    """获取数据库连接（优先从连接池获取，超时则创建直接连接）"""
    global _monitor_pool
    if _monitor_pool is None:
        try:
            _monitor_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=2, maxconn=10,
                host=os.getenv('PG_HOST', 'localhost'),
                port=os.getenv('PG_PORT', '5432'),
                database=os.getenv('PG_DATABASE', 'quant_trading'),
                user=os.getenv('PG_USER', 'quant_user'),
                password=os.getenv('PG_PASSWORD', ''),
            )
        except Exception:
            return psycopg2.connect(
                host=os.getenv('PG_HOST', 'localhost'),
                port=os.getenv('PG_PORT', '5432'),
                database=os.getenv('PG_DATABASE', 'quant_trading'),
                user=os.getenv('PG_USER', 'quant_user'),
                password=os.getenv('PG_PASSWORD', ''),
            )
    # 用线程+超时获取连接，避免池耗尽时无限阻塞
    q = queue.Queue()
    def _get():
        try:
            q.put(_monitor_pool.getconn())
        except Exception as e:
            q.put(e)
    t = threading.Thread(target=_get, daemon=True)
    t.start()
    t.join(timeout=5)
    if t.is_alive():
        logger.warning("连接池耗尽，创建直接连接替代")
        return psycopg2.connect(
            host=os.getenv('PG_HOST', 'localhost'),
            port=os.getenv('PG_PORT', '5432'),
            database=os.getenv('PG_DATABASE', 'quant_trading'),
            user=os.getenv('PG_USER', 'quant_user'),
            password=os.getenv('PG_PASSWORD', ''),
        )
    result = q.get_nowait()
    if isinstance(result, Exception):
        logger.warning(f"连接池错误: {result}，创建直接连接")
        return psycopg2.connect(
            host=os.getenv('PG_HOST', 'localhost'),
            port=os.getenv('PG_PORT', '5432'),
            database=os.getenv('PG_DATABASE', 'quant_trading'),
            user=os.getenv('PG_USER', 'quant_user'),
            password=os.getenv('PG_PASSWORD', ''),
        )
    return result


def _put_db_conn(conn):
    """归还连接到连接池（兼容直连）"""
    global _monitor_pool
    if _monitor_pool is not None:
        try:
            _monitor_pool.putconn(conn)
        except Exception:
            # 直连（非池连接）或池已关闭，直接 close
            try:
                conn.close()
            except Exception:
                pass
    else:
        try:
            conn.close()
        except Exception:
            pass


_monitor_pool = None  # 模块级连接池（延迟初始化）

# ============================================
# 数据缓存（监控看板使用，减少重复查询压力）
# ============================================

class _CacheEntry:
    """缓存条目，带过期时间"""
    def __init__(self, data, ttl_seconds=60):
        self.data = data
        self.expires_at = time.time() + ttl_seconds

    def is_valid(self):
        return time.time() < self.expires_at


# 各端点缓存
_cache = {}


def _cached(key: str, ttl_seconds: int = 60):
    """缓存装饰器：缓存函数返回值，TTL 秒内有效"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            entry = _cache.get(key)
            if entry and entry.is_valid():
                return entry.data
            data = func(*args, **kwargs)
            _cache[key] = _CacheEntry(data, ttl_seconds)
            return data
        return wrapper
    return decorator


def _execute_query(as_dict: bool = True, conn=None):
    """
    查询执行上下文管理器（统一处理连接/游标生命周期和异常）

    用法:
        with _execute_query() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    Args:
        as_dict: 是否返回字典（RealDictCursor）；False 时返回元组
        conn: 可选，复用已有连接（不传则创建新连接）
    """
    class _Ctx:
        def __enter__(inner):
            inner.own_conn = conn is None
            inner.conn = conn if conn else _get_db_conn()
            inner.cur = inner.conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor if as_dict else None
            )
            return inner.cur

        def __exit__(inner, exc_type, exc, tb):
            try:
                if inner.cur is not None:
                    inner.cur.close()
            except Exception:
                pass
            if inner.own_conn:
                _put_db_conn(inner.conn)
            return False  # 不吞异常

    return _Ctx()


def _query_dict(sql: str, params: tuple = None, conn=None) -> List[Dict[str, Any]]:
    """执行查询并以字典列表返回（异常时返回空列表）"""
    try:
        with _execute_query(as_dict=True, conn=conn) as cur:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"数据库查询失败: {e}")
        return []


def _query_one(sql: str, params: tuple = None, conn=None) -> Optional[Dict[str, Any]]:
    rows = _query_dict(sql, params, conn=conn)
    return rows[0] if rows else None


def _query_scalar(sql: str, params: tuple = None, conn=None):
    """查询单值（异常时返回 None）"""
    try:
        with _execute_query(as_dict=False, conn=conn) as cur:
            cur.execute(sql, params or ())
            val = cur.fetchone()
            return val[0] if val else None
    except Exception as e:
        logger.error(f"数据库查询失败: {e}")
        return None


# ============================================
# 端点 1：数据完整性总览
# ============================================

@router.get("/monitor/data-summary/", summary="数据完整性总览")
@_cached("data_summary", ttl_seconds=60)
def get_data_summary():
    """
    返回四张核心表的最新数据日期、股票覆盖数、覆盖率等。
    """
    result = {"tables": {}, "coverage": {}, "stocks": {}, "warnings": []}

    # 使用专用连接执行所有查询，减少连接建立/释放开销
    _conn = _get_db_conn()
    try:
        _qs = lambda sql, p=None: _query_scalar(sql, p, conn=_conn)
        _q1 = lambda sql, p=None: _query_one(sql, p, conn=_conn)
        _qd = lambda sql, p=None: _query_dict(sql, p, conn=_conn)

        # 各表最新日期（优化：COUNT DISTINCT 只查最新交易日，避免遍历全部分区）
        for table, cycle_filter, use_cycle_col in [
            ("stock_quotes", "AND cycle = '1d'", True),
            ("stock_indicators", "AND cycle = '1d'", True),
            ("trade_signals", "", False),
        ]:
            latest = _qs(f"SELECT MAX(trade_date) FROM {table} WHERE 1=1 {cycle_filter}")
            if latest:
                if use_cycle_col:
                    count = _qs(
                        f"SELECT COUNT(DISTINCT code) FROM {table} WHERE trade_date = %s AND cycle = '1d'",
                        (latest,),
                    )
                else:
                    count = _qs(
                        f"SELECT COUNT(DISTINCT code) FROM {table} WHERE trade_date = %s",
                        (latest,),
                    )
                result["tables"][table] = {
                    "latest_date": str(latest),
                    "stock_count": count or 0,
                }

        # 最新交易日
        latest_quote = _qs("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
        if latest_quote:
            covered_count = _qs(
                "SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle = '1d' AND trade_date = %s",
                (latest_quote,)
            ) or 0
            if covered_count < MonitorConfig.MIN_COVERAGE_COUNT:
                latest_quote = _qs(
                    "SELECT trade_date FROM stock_quotes WHERE cycle = '1d' AND trade_date < %s GROUP BY trade_date ORDER BY trade_date DESC LIMIT 1",
                    (latest_quote,)
                )

        if latest_quote:
            active_cutoff_date = _now_beijing() - timedelta(days=MonitorConfig.ACTIVE_DAYS)
            active_cutoff = active_cutoff_date.strftime("%Y-%m-%d")

            covered = _qs(
                "SELECT COUNT(DISTINCT q.code) FROM stock_quotes q WHERE q.cycle = '1d' AND q.trade_date = %s AND EXISTS (SELECT 1 FROM stock_quotes q2 WHERE q2.cycle = '1d' AND q2.code = q.code AND q2.trade_date >= %s)",
                (latest_quote, active_cutoff_date),
            ) or 0
            total = _qs(
                "SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle = '1d' AND trade_date >= %s",
                (active_cutoff_date,),
            ) or 0
            coverage_rate = round(covered / total * 100, 2) if total else 0

            missing_in_quote = _qs(
                "SELECT COUNT(*) FROM (SELECT DISTINCT code FROM stock_quotes WHERE cycle = '1d' AND trade_date >= %s) active_t WHERE NOT EXISTS (SELECT 1 FROM stock_quotes q WHERE q.cycle = '1d' AND q.trade_date = %s AND q.code = active_t.code)",
                (active_cutoff_date, latest_quote),
            ) or 0

            extra_in_quote = _qs(
                "SELECT COUNT(DISTINCT q.code) FROM stock_quotes q WHERE q.cycle = '1d' AND q.trade_date = %s AND NOT EXISTS (SELECT 1 FROM stock_quotes q2 WHERE q2.cycle = '1d' AND q2.code = q.code AND q2.trade_date >= %s)",
                (latest_quote, active_cutoff_date),
            ) or 0

            # 缺失股票分类
            missing_codes = []
            if missing_in_quote > 0:
                missing_rows = _qd(
                    "SELECT b.code, b.name, b.delist_date FROM stock_basic b WHERE EXISTS (SELECT 1 FROM stock_quotes q2 WHERE q2.cycle = '1d' AND q2.code = b.code AND q2.trade_date >= %s) AND NOT EXISTS (SELECT 1 FROM stock_quotes q WHERE q.cycle = '1d' AND q.trade_date = %s AND b.code = q.code)",
                    (active_cutoff_date, latest_quote),
                )
                missing_codes = missing_rows or []

            missing_delisted = missing_suspended = missing_merged = missing_suspended_recent = 0
            real_missing_codes = []

            if missing_codes:
                missing_codes_list = [r["code"] for r in missing_codes]
                recent_data = _qd(
                    "SELECT DISTINCT code FROM stock_quotes WHERE code = ANY(%s) AND trade_date >= %s::date - INTERVAL '30 days' AND trade_date < %s",
                    (missing_codes_list, latest_quote, latest_quote),
                )
                recent_codes = set(r["code"] for r in (recent_data or []))

                for r in missing_codes:
                    code, name, delist_date = r["code"], r["name"] or "", r["delist_date"]
                    if "退" in name or delist_date is not None:
                        missing_delisted += 1
                    elif name.startswith("ST") or name.startswith("*ST") or name.startswith("S*ST") or "ST" in name:
                        missing_suspended += 1
                    elif code in recent_codes:
                        missing_suspended_recent += 1
                    else:
                        missing_merged += 1
                        if len(real_missing_codes) < 20:
                            real_missing_codes.append(f"{code} {name}")

            missing_real = missing_merged + missing_suspended_recent
            active_stocks = total - missing_delisted - missing_merged
            effective_coverage_rate = round(covered / active_stocks * 100, 2) if active_stocks else 0

            result["coverage"] = {
                "latest_date": str(latest_quote),
                "covered_stocks": covered,
                "total_stocks": total,
                "coverage_rate": coverage_rate,
                "effective_coverage_rate": effective_coverage_rate,
                "active_stocks": active_stocks,
                "scope_note": f"仅统计最近 2 年（{active_cutoff} 以来）有行情的 {total} 只活跃股票",
                "missing_stocks": missing_in_quote,
                "extra_stocks": extra_in_quote,
                "missing_breakdown": {
                    "delisted": missing_delisted,
                    "suspended": missing_suspended,
                    "merged": missing_merged,
                    "suspended_recent": missing_suspended_recent,
                    "real_missing": missing_real,
                },
            }

            if missing_real > 0:
                codes_str = (", ".join(real_missing_codes[:5]) + (f" 等{missing_real}只" if missing_real > 5 else "")) if real_missing_codes else f"共{missing_real}只"
                result["warnings"].append({
                    "level": "warning", "type": "real_missing",
                    "message": f"有 {missing_real} 只活跃股票缺少最新交易日数据: {codes_str}",
                    "missing_codes": real_missing_codes,
                    "suggestion": "运行 `python backend/collector/etl/import_daily_data.py --incremental` 补充缺失数据"
                })

            if missing_suspended_recent > 0:
                result["warnings"].append({
                    "level": "info", "type": "suspended_recent",
                    "message": f"有 {missing_suspended_recent} 只股票近期停牌（非ST），最新交易日无数据属正常",
                    "suggestion": "停牌股票恢复交易后数据会自动补入"
                })

            if coverage_rate < 50 and total > 0:
                result["warnings"].append({
                    "level": "critical", "type": "low_coverage",
                    "message": f"覆盖率异常低 ({coverage_rate}%)，最新交易日 {latest_quote} 只有 {covered} 只股票数据",
                    "suggestion": "请检查定时任务配置和日志"
                })

            trade_date = latest_quote if isinstance(latest_quote, datetime) else datetime.fromisoformat(str(latest_quote))
            if trade_date.weekday() >= 5:
                result["warnings"].append({
                    "level": "info", "type": "weekend_data",
                    "message": f"最新交易日 {latest_quote} 是周末，股市不交易，覆盖率低是正常的",
                    "suggestion": "请等待下一个交易日（周一）的数据更新"
                })

        # 总股票数
        result["stocks"]["total"] = _qs("SELECT COUNT(*) FROM stock_basic") or 0
        result["stocks"]["delisted"] = _qs("SELECT COUNT(*) FROM stock_basic WHERE delist_date IS NOT NULL") or 0
        result["stocks"]["suspended"] = _qs(
            "SELECT COUNT(*) FROM stock_basic WHERE (name LIKE 'ST%%' OR name LIKE '*ST%%' OR name LIKE 'S%%ST%%' OR name LIKE 'S*ST%%') AND delist_date IS NULL AND name NOT LIKE '%%退%%'"
        ) or 0
        result["stocks"]["active"] = result["stocks"]["total"] - result["stocks"]["delisted"] - result["stocks"]["suspended"]

        return ApiResponse(code=200, message="success", data=result)
    finally:
        _put_db_conn(_conn)


# ============================================
# 端点 2：覆盖率趋势
# ============================================

@router.get("/monitor/coverage-trend/", summary="覆盖率趋势")
@_cached("coverage_trend", ttl_seconds=60)
def get_coverage_trend(days: int = Query(30, ge=1, le=365)):
    """返回最近 N 天每日的股票覆盖数"""
    rows = _query_dict(
        f"""
        SELECT trade_date, COUNT(DISTINCT code) AS stock_count
        FROM stock_quotes
        WHERE cycle = '1d' AND trade_date >= CURRENT_DATE - INTERVAL '%s days'
        GROUP BY trade_date
        ORDER BY trade_date ASC
        """,
        (days,),
    )
    total = _query_scalar("SELECT COUNT(*) FROM stock_basic") or 0
    trend = []
    for r in rows:
        coverage_rate = round(r["stock_count"] / total * 100, 2) if total else 0
        trend.append({
            "date": str(r["trade_date"]),
            "stock_count": r["stock_count"],
            "coverage_rate": coverage_rate,
        })
    return ApiResponse(code=200, message="success", data={"trend": trend, "total_stocks": total})


# ============================================
# 端点 3：管道执行状态（今日）
# ============================================

# 管道阶段定义：反映数据处理进度的三个阶段
PIPELINE_STAGES = [
    {"id": "download", "name": "数据下载", "task_patterns": ["日线数据导入", "分钟线数据导入"]},
    {"id": "clean", "name": "数据清洗", "task_patterns": ["数据修复", "数据清洗", "缺失值处理"]},
    {"id": "complete", "name": "数据补全", "task_patterns": ["指标计算", "复权因子", "基本面同步"]},
]


def _get_stage_status(stage, year, month, day):
    """获取单个阶段的状态"""
    # 构建查询条件：匹配任意一个任务模式
    patterns = stage['task_patterns']
    if not patterns:
        return None
    
    # 构建 OR 条件
    or_conditions = " OR ".join(["task_name LIKE %s"] * len(patterns))
    
    # 查询今日该阶段的所有相关任务
    sql = f"""
        SELECT status, progress, message, created_at, updated_at
        FROM task_progress
        WHERE ({or_conditions})
          AND EXTRACT(YEAR FROM created_at + INTERVAL '8 hours')::int = %s
          AND EXTRACT(MONTH FROM created_at + INTERVAL '8 hours')::int = %s
          AND EXTRACT(DAY FROM created_at + INTERVAL '8 hours')::int = %s
        ORDER BY created_at DESC LIMIT 1
    """
    params = tuple([f"%{p}%" for p in patterns]) + (year, month, day)
    row = _query_one(sql, params)
    
    return row


@router.get("/monitor/pipeline-status/", summary="管道执行状态（今日）")
def get_pipeline_status():
    """返回今日管道各阶段的执行状态"""
    # 统一使用全局 BEIJING_TZ（避免重复定义）
    today_beijing = _now_beijing().strftime("%Y-%m-%d")
    year, month, day = map(int, today_beijing.split('-'))
    
    stages = []
    for stage in PIPELINE_STAGES:
        row = _get_stage_status(stage, year, month, day)
        
        if row:
            # 计算持续时间（使用 updated_at - created_at）
            duration_seconds = None
            if row.get('updated_at') and row.get('created_at'):
                try:
                    start = datetime.fromisoformat(str(row['created_at']).replace('Z', '+00:00'))
                    end = datetime.fromisoformat(str(row['updated_at']).replace('Z', '+00:00'))
                    duration_seconds = round((end - start).total_seconds(), 1)
                except Exception:
                    pass
            
            stages.append({
                "id": stage["id"],
                "name": stage["name"],
                "status": row["status"],
                "progress": float(row["progress"]) if row["progress"] else 0,
                "message": row["message"] or "",
                "duration_seconds": duration_seconds,
                "start_time": row["created_at"],
                "end_time": row["updated_at"] if row["status"] == "completed" else None,
            })
        else:
            # 如果没有找到直接的任务记录，根据其他阶段状态推断
            stages.append({
                "id": stage["id"],
                "name": stage["name"],
                "status": "pending",
                "progress": 0,
                "message": "等待执行",
                "duration_seconds": None,
                "start_time": None,
                "end_time": None,
            })
    
    return ApiResponse(code=200, message="success", data={"date": today_beijing, "stages": stages})


# ============================================
# 每日任务链 A→F（数据库状态优先，日志兜底）
# ============================================

def _check_task_from_db(task_key: str) -> Dict[str, Any]:
    """
    从数据库直接检查任务的数据状态，不依赖日志文件。

    关键判断：必须"今日"有执行才算成功；仅历史数据不能冒充今日成功
    - 今日已执行且数据正常 → success
    - 今日已执行但数据覆盖率<COVERAGE_SUCCESS% → partial
    - 今日未执行（无今日日志/无今日数据） → pending（待执行）
    - 数据库无任何数据 → pending

    Returns:
        dict: {status: success|partial|pending|unknown, message, data_date, data_count, ...}
    """
    # 各任务对应的表和检查条件（min_count 从 MonitorConfig 读取，可通过环境变量调整）
    TASK_DB_CONFIG = {
        "pipeline_health_check": {  # A: 管道健康检查
            "table": "task_run_log",
            "date_col": "data_date",
            "task_name": "pipeline_health_check",
        },
        "stock_list_sync": {        # B: 股票列表同步
            "table": "stock_list",
            "date_col": "updated_at",
        },
        "daily_import": {           # C: 行情导入
            "table": "stock_quotes",
            "date_col": "trade_date",
            "cycle_col": "cycle",
            "cycle_val": "1d",
        },
        "adj_factor_sync": {        # D: 复权因子同步
            "table": "stock_adj_factor",
            "date_col": "trade_date",
        },
        "daily_basic_sync": {       # E: 基本面同步
            "table": "stock_daily_basic",
            "date_col": "trade_date",
        },
        "indicators_compute": {      # F: 技术指标计算
            "table": "stock_indicators",
            "date_col": "trade_date",
            "cycle_col": "cycle",
            "cycle_val": "1d",
        },
        "signal_precompute": {      # G: 信号预计算
            "table": "trade_signals",
            "date_col": "trade_date",
        },
        "snapshot_sync": {          # H: 宽表同步
            "table": "stock_daily_snapshot",
            "date_col": "trade_date",
        },
        "parquet_export": {         # I: Parquet 导出
            "table": "task_run_log",
            "date_col": "data_date",
            "task_name": "parquet_export",
        },
    }

    cfg = TASK_DB_CONFIG.get(task_key)
    if not cfg:
        return {"status": "unknown", "message": "未知任务"}

    table = cfg["table"]
    date_col = cfg["date_col"]
    task_name = cfg.get("task_name")  # task_run_log 专用：按 task_name 过滤

    if task_name:
        # task_run_log 类型：按 task_name + data_date 查询
        latest_date = _query_scalar(
            f"SELECT MAX({date_col}) FROM {table} WHERE task_name = %s",
            (task_name,),
        )
    else:
        latest_date = _query_scalar(f"SELECT MAX({date_col}) FROM {table}")

    if not latest_date:
        return {"status": "pending", "message": "无数据"}

    latest_str = str(latest_date)

    # ========== 判断最新数据是否已更新 ==========
    # 业务规则：数据日期必须 >= 最近一个交易日（非周末/节假日的最近工作日）
    # 否则即使有历史数据，也只能算"待执行"，不能冒充今日成功
    today_beijing = _now_beijing()
    expected_trade_date = _get_last_trade_date(today_beijing)

    # stock_list_sync 为元数据表，非每日更新，跳过日期比较
    if task_key != "stock_list_sync" and str(latest_date) < expected_trade_date:
        return {
            "status": "pending",
            "message": f"数据未更新（最新 {latest_str}，期望 >= {expected_trade_date}）",
            "data_date": latest_str,
            "data_count": None,
        }

    # 构建 WHERE 条件
    where_parts = [f"{date_col} = %s"]
    params = [latest_date]
    if cfg.get("cycle_col"):
        where_parts.append(f"{cfg['cycle_col']} = %s")
        params.append(cfg["cycle_val"])
    if task_name:
        where_parts.append("task_name = %s")
        params.append(task_name)

    where_clause = " AND ".join(where_parts)
    count = _query_scalar(f"SELECT COUNT(*) FROM {table} WHERE {where_clause}", tuple(params)) or 0

    # 动态计算 min_count：
    # - task_run_log 类型（pipeline_health_check, parquet_export）：有记录按 status 判断
    # - stock_list_sync：有数据即成功
    # - daily_import（stock_quotes 1d）：直接用 count 自身作为成功判定（>0 即有数据）
    # - 其他任务：用 stock_quotes 当日股票数作为动态基准（节假日不会误报 partial）
    if task_name:
        # task_run_log 类型：检查是否有 status='success' 的记录
        success_count = _query_scalar(
            f"SELECT COUNT(*) FROM {table} WHERE task_name = %s AND data_date = %s AND status = 'success'",
            (task_name, latest_date),
        ) or 0
        min_count = max(1, success_count)  # 有成功记录就算成功
    elif task_key == "stock_list_sync":
        # stock_list 为元数据表，非每日更新，有数据即成功
        min_count = max(1, count)
    elif task_key == "daily_import":
        min_count = max(1, count)  # 有数据就算成功
    else:
        dynamic_min = _query_scalar(
            "SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE trade_date = %s AND cycle = '1d'",
            (latest_date,),
        )
        min_count = dynamic_min if dynamic_min and dynamic_min > 0 else MonitorConfig.TASK_MIN_COUNTS.get(task_key, 1000)
    coverage = count / min_count * 100 if min_count > 0 else 0

    if count >= min_count:
        # 数据充足，检查完整性（覆盖率）
        # 以 stock_quotes 为基准算覆盖率
        if task_key == "snapshot_sync":
            quote_count = _query_scalar(
                "SELECT COUNT(*) FROM stock_quotes WHERE trade_date=%s AND cycle='1d'",
                (latest_date,)
            ) or 0
            if quote_count > 0:
                coverage = count / quote_count * 100
                if coverage < MonitorConfig.COVERAGE_SUCCESS:
                    return {
                        "status": "partial",
                        "message": f"覆盖率 {coverage:.1f}%（{count}/{quote_count}）",
                        "data_date": latest_str,
                        "data_count": count,
                    }

        return {
            "status": "success",
            "message": f"共 {count} 条",
            "data_date": latest_str,
            "data_count": count,
        }
    elif count > 0:
        return {
            "status": "partial",
            "message": f"数据不足 {count}/{min_count} 条",
            "data_date": latest_str,
            "data_count": count,
        }
    else:
        return {"status": "pending", "message": "今日无数据"}




TASK_CHAIN = [
    # 阶段1 (15:30)
    {"id": "A", "name": "管道健康检查", "key": "pipeline_health_check", "desc": "pipeline_health_check"},
    {"id": "B", "name": "股票列表同步", "key": "stock_list_sync", "desc": "sync_stock_list_baostock"},
    # 阶段2 (16:30)
    {"id": "C", "name": "增量导入行情", "key": "daily_import", "desc": "import_daily_data"},
    {"id": "D", "name": "复权因子同步", "key": "adj_factor_sync", "desc": "sync_adj_factor"},
    {"id": "E", "name": "基本面同步", "key": "daily_basic_sync", "desc": "sync_daily_basic"},
    {"id": "F", "name": "技术指标计算", "key": "indicators_compute", "desc": "compute_indicators"},
    {"id": "G", "name": "信号预计算", "key": "signal_precompute", "desc": "signal_precompute"},
    {"id": "H", "name": "宽表同步", "key": "snapshot_sync", "desc": "daily_snapshot_sync"},
    {"id": "I", "name": "Parquet 导出", "key": "parquet_export", "desc": "parquet_export"},
]

# 日志目录（项目根目录下的 logs/cron）
_LOG_DIR = Path(__file__).parents[4] / "logs" / "cron"


def _parse_task_log(task_key: str) -> Dict[str, Any]:
    """解析单个任务的日志文件，返回状态信息"""
    log_path = _LOG_DIR / f"{task_key}.log"
    if not log_path.exists():
        return {"status": "pending", "message": "无执行记录"}

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return {"status": "unknown", "message": "日志读取失败"}

    # 查找今日的执行记录
    today_str = _now_beijing().strftime("%Y-%m-%d")

    # 策略：找到所有执行块，优先返回有明确结果的块（success/failed）
    # 日志格式: ===== 2026-06-09 14:26:30 开始执行 daily_import =====
    today_blocks = list(re.finditer(
        rf'===== (\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}) 开始执行 .* =====',
        content
    ))

    if not today_blocks:
        return {"status": "pending", "message": "今日未执行"}

    # 从后往前遍历，找第一个有明确结果的块
    selected_block = None
    for block_match in reversed(today_blocks):
        block_start = block_match.start()
        block_content = content[block_start:]
        if ('SUCCESS' in block_content or '执行成功' in block_content or '完成' in block_content[-500:]
                or ('FAILED' in block_content and '=====' in block_content)
                or ('EXCEPTION' in block_content and ('=====' in block_content or 'Traceback' in block_content))):
            selected_block = block_match
            break

    # 如果没有有结果的块，取最后一个（可能正在运行或中断）
    if not selected_block:
        selected_block = today_blocks[-1]

    last_block = selected_block
    block_start = last_block.start()
    block_date = last_block.group(1)

    # 只看这个块之后的内容
    block_content = content[block_start:]

    # 判断状态：先检查成功（高优先级），再检查失败
    if 'SUCCESS' in block_content or '执行成功' in block_content:
        duration = None
        dur_match = re.search(r'耗时\s*([\d.]+)\s*s', block_content)
        if dur_match:
            duration = float(dur_match.group(1))
        return {
            "status": "success",
            "message": "执行成功",
            "start_time": block_date,
            "duration_seconds": duration,
        }

    if '完成' in block_content[-500:]:
        duration = None
        dur_match = re.search(r'耗时\s*([\d.]+)\s*s', block_content)
        if dur_match:
            duration = float(dur_match.group(1))
        return {
            "status": "success",
            "message": "执行成功",
            "start_time": block_date,
            "duration_seconds": duration,
        }

    # 失败检测：用字符串包含判断，避免正则边界问题
    # 注意：EXCEPTION 可能没有闭合 ===== 分隔符（程序崩溃时不会输出结束标记）
    if ('EXCEPTION' in block_content and '=====' in block_content) or \
       ('EXCEPTION' in block_content and 'Traceback' in block_content) or \
       ('FAILED' in block_content and '=====' in block_content):
        return {
            "status": "failed",
            "message": _extract_error_msg(block_content),
            "start_time": block_date,
        }

    # 有开始记录但没有结束标记 → 可能正在运行或中断
    # 检查是否是今天的最后一条记录（可能还在跑）
    lines_after = content[block_start:].strip().split('\n')
    last_lines = '\n'.join(lines_after[-5:])

    # 如果最后修改时间在5分钟内，认为正在运行
    try:
        mtime = log_path.stat().st_mtime
        age_seconds = time.time() - mtime
        if age_seconds < 300:  # 5分钟内有更新
            return {"status": "running", "message": "执行中...", "start_time": block_date}
    except Exception:
        pass

    return {"status": "unknown", "message": "状态不明", "start_time": block_date}


def _extract_error_msg(content: str) -> str:
    """从日志中提取错误信息"""
    # 找 FAILED 或 EXCEPTION 行附近的内容
    # 兼容有/无闭合分隔符两种情况
    for pattern in [
        r'(FAILED.*?)(?:\n=====|\Z)',
        r'(EXCEPTION:.*?)(?:\n=====|\Z)',
        r'(Traceback \(most recent call last\):.*?)(?:\n=====|\Z)',
        r'(失败[^\n]*)'
    ]:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            msg = match.group(1).strip()
            return msg[:100]  # 截断过长信息
    return "执行失败"


@router.get("/monitor/task-chain/", summary="每日任务链 A→I 状态")
def get_task_chain_status():
    """
    返回每日盘后 A→I 任务链的执行状态（按实际执行顺序排列）。

    执行顺序：管道健康检查 → 股票列表同步 → 增量导入行情 → 复权因子同步 → 基本面同步
            → 技术指标计算 → 信号预计算 → 宽表同步 → Parquet 导出

    数据源：仅以数据库为准（用户硬性要求）。
    - 今日对应表有数据且条数达标 → success
    - 今日有数据但条数不达标 → partial
    - 今日对应表无数据（最新数据日期 != 今日）→ pending（待执行）
    - 数据库完全无该表数据 → pending

    注意：日志文件不再参与业务判断，仅保留 _parse_task_log 供 debug 端点使用。
    """
    tasks = []
    has_success = False
    has_pending = False
    has_partial = False
    has_failed = False

    for task in TASK_CHAIN:
        # 唯一数据源：数据库
        db_info = _check_task_from_db(task["key"])
        status = db_info.get("status", "pending")

        tasks.append({
            "id": task["id"],
            "name": task["name"],
            "key": task["key"],
            "status": status,
            "message": db_info.get("message", ""),
            "data_count": db_info.get("data_count"),
            "data_date": db_info.get("data_date"),
            "start_time": None,
            "duration_seconds": None,
        })

        if status == "failed":
            has_failed = True
        elif status == "partial":
            has_partial = True
        elif status == "pending":
            has_pending = True
        elif status == "success":
            has_success = True

    # 整体状态优先级：failed > partial > pending > success
    if has_failed:
        overall = "failed"
    elif has_partial:
        overall = "partial"
    elif has_pending:
        overall = "pending"
    else:
        overall = "success"

    return ApiResponse(code=200, message="success", data={
        "date": _now_beijing().strftime("%Y-%m-%d"),
        "overall": overall,
        "tasks": tasks,
    })


# ============================================
# 端点 4：管道历史趋势
# ============================================

@router.get("/monitor/pipeline-history/", summary="管道历史趋势")
def get_pipeline_history(days: int = Query(30, ge=1, le=365)):
    """返回最近 N 天各任务的执行统计"""
    rows = _query_dict(
        f"""
        SELECT
            DATE(created_at) AS run_date,
            task_name,
            status,
            COUNT(*) AS run_count,
            AVG(EXTRACT(EPOCH FROM (COALESCE(end_time, created_at) - start_time))) AS avg_duration
        FROM task_progress
        WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
          AND task_name IN ('daily_basic_sync', 'daily_import', 'indicators_compute',
                            'adj_factor_sync', 'signals_precompute', 'missing_value_fix')
        GROUP BY run_date, task_name, status
        ORDER BY run_date ASC, task_name ASC
        """,
        (days,),
    )
    return ApiResponse(code=200, message="success", data={"history": rows})


# ============================================
# 端点 5：下载进度
# ============================================

@router.get("/monitor/download-progress/", summary="当前下载进度")
def get_download_progress():
    """返回当前正在运行或最近完成的下载任务进度"""
    row = _query_one(
        """
        SELECT task_name, status, progress, message, start_time, end_time,
               EXTRACT(EPOCH FROM (COALESCE(end_time, CURRENT_TIMESTAMP) - start_time)) AS duration_seconds
        FROM task_progress
        WHERE task_name LIKE '%import%' OR task_name LIKE '%daily_import%'
        ORDER BY created_at DESC LIMIT 1
        """
    )
    if not row:
        return ApiResponse(code=200, message="success", data={"has_task": False})

    # 解析进度信息
    msg = row["message"] or ""
    progress_data = {"current": 0, "total": 0, "success": 0, "failed": 0, "skipped": 0}

    m = re.search(r'成功\s*(\d+)', msg)
    if m:
        progress_data["success"] = int(m.group(1))
    m = re.search(r'失败\s*(\d+)', msg)
    if m:
        progress_data["failed"] = int(m.group(1))
    m = re.search(r'跳过\s*(\d+)', msg)
    if m:
        progress_data["skipped"] = int(m.group(1))
    m = re.search(r'(\d+)/(\d+)', msg)
    if m:
        progress_data["current"] = int(m.group(1))
        progress_data["total"] = int(m.group(2))

    return ApiResponse(code=200, message="success", data={
        "has_task": True,
        "task_name": row["task_name"],
        "status": row["status"],
        "progress": float(row["progress"]) if row["progress"] else 0,
        "message": msg,
        "duration_seconds": round(float(row["duration_seconds"]), 1) if row["duration_seconds"] else None,
        "start_time": str(row["start_time"]) if row["start_time"] else None,
        "detail": progress_data,
    })


# ============================================
# 端点 7：同步水位线异常
# ============================================

@router.get("/monitor/sync-checkpoints/", summary="同步水位线异常")
def get_sync_checkpoints(
    status: str = Query("failed", regex="^(failed|pending|in_progress|success)$"),
    limit: int = Query(50, ge=1, le=200),
):
    """返回同步水位线异常记录"""
    rows = _query_dict(
        """
        SELECT code, cycle, last_sync_datetime, sync_status, fail_reason, sync_count, updated_at
        FROM sync_checkpoints
        WHERE sync_status = %s
        ORDER BY updated_at DESC LIMIT %s
        """,
        (status, limit),
    )
    data = []
    for r in rows:
        data.append({
            "code": r["code"],
            "cycle": r["cycle"],
            "last_sync_datetime": str(r["last_sync_datetime"]) if r.get("last_sync_datetime") else None,
            "sync_status": r["sync_status"],
            "fail_reason": (r.get("fail_reason") or "")[:120],
            "sync_count": r["sync_count"] or 0,
            "updated_at": str(r["updated_at"]),
        })
    return ApiResponse(code=200, message="success", data={"records": data, "total": len(data)})


# ============================================
# 端点 8：系统健康状态
# ============================================


@router.get("/monitor/health-check/", summary="系统健康状态")
def get_health_check():
    """返回数据库连接、数据源可用性、分区覆盖等系统健康状态"""
    try:
        # 使用新的 SystemMonitor 进行健康检查
        db_config = {
            'host': os.getenv('PG_HOST', 'localhost'),
            'port': os.getenv('PG_PORT', '5432'),
            'database': os.getenv('PG_DATABASE', 'quant_trading'),
            'user': os.getenv('PG_USER', 'quant_user'),
            'password': os.getenv('PG_PASSWORD')
        }
        
        monitor = SystemMonitor(db_config)
        summary = monitor.get_system_summary()
        
        # 添加分区信息
        partitions = {}
        try:
            conn = _get_db_conn()
            cur = conn.cursor()
            parts = _query_dict("""
                SELECT parent.relname AS table_name, child.relname AS partition_name
                FROM pg_inherits
                JOIN pg_class child ON pg_inherits.inhrelid = child.oid
                JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
                WHERE parent.relname IN ('stock_quotes', 'stock_indicators')
                ORDER BY parent.relname, child.relname
            """)
            for p in parts or []:
                tbl = p["table_name"]
                if tbl not in partitions:
                    partitions[tbl] = []
                partitions[tbl].append(p["partition_name"])
            cur.close()
            _put_db_conn(conn)
        except Exception as e:
            logger.warning(f"获取分区信息失败：{e}")
        
        result = {
            "timestamp": summary["timestamp"],
            "overall_health": summary["overall_health"],
            "database": {
                "status": summary["database"]["status"],
                "connected": summary["database"]["connected"],
                "tables": summary["database"]["tables"],
                "latest_trade_date": summary["database"].get("latest_trade_date"),
                "data_freshness": summary["database"].get("data_freshness"),
            },
            "partitions": partitions,
            "coverage": summary["coverage"],
            "data_sources": {
                "tushare": bool(os.getenv("TUSHARE_TOKEN")),
                "baostock": True
            }
        }
        
        return ApiResponse(code=200, message="success", data=result)
        
    except Exception as e:
        logger.error(f"健康检查失败：{e}", exc_info=True)
        return ApiResponse(code=500, message=f"健康检查失败：{str(e)}", data=None)


# ============================================
# 端点：执行股票代码标准化（运维工具）
# ============================================

@router.post("/monitor/standardize-codes/", summary="执行股票代码标准化")
def standardize_codes():
    """
    将所有相关表中的股票代码统一为纯数字格式：
    - sh.600027 / sz.000001 → 600027 / 000001
    - 000001.SZ / 600027.SH → 000001 / 600027
    - 处理 stock_quotes 中因格式不同导致的重复记录

    实现策略：分批小事务提交，避免长事务锁表

    去重规则说明（PARTITION BY code, trade_date, cycle, adjust_type ORDER BY id DESC）：
    - 业务键：(code, trade_date, cycle, adjust_type) 必须唯一
    - 冲突时保留 id 最大者（id 是 PostgreSQL serial 主键，monotonically increasing，
      与"最新插入"等价；旧数据来自不同数据源时取最新一份，符合"以最新数据为准"原则）
    - 替代方案：保留 trade_date 更晚者，但因业务键已含 trade_date 维度，相同 trade_date
      下的多份记录实际是冗余的，按 id DESC 保留"最后写入"即可保证不丢新增数据
    """
    result = {
        "started_at": _now_beijing().isoformat(),
        "steps": [],
    }
    conn = _get_db_conn()
    conn.autocommit = True  # 每条 SQL 独立提交，避免长事务
    try:
        cur = conn.cursor()

        # ========== Step 1: 标准化 stock_quotes（UPDATE 转换，不删除） ==========
        # 关键安全：将带后缀的 code（如 '000001.SZ'）改为纯数字 '000001'
        # 不会丢数据：转换后若与原纯数字记录产生主键冲突，再去重保留较新记录
        logger.info("开始标准化 stock_quotes 中带后缀的记录（UPDATE 转换）...")
        updated = 0
        batch = 5000
        max_iter = 50  # 安全上限
        for i in range(max_iter):
            cur.execute(
                """
                UPDATE stock_quotes
                SET code = SPLIT_PART(code, '.', 1)
                WHERE (code, trade_date, cycle, adjust_type) IN (
                    SELECT code, trade_date, cycle, adjust_type FROM stock_quotes
                    WHERE code LIKE '%%.%%'
                    LIMIT %s
                )
                """,
                (batch,),
            )
            n = cur.rowcount or 0
            updated += n
            if n == 0 or n < batch:
                break
            if i % 5 == 0:
                logger.info(f"已转换 {updated} 条带后缀记录...")
        result["steps"].append({"table": "stock_quotes", "action": "update_suffix", "rows": updated})

        # ========== Step 1.5: 转换后若产生主键冲突，保留 id 最大者（最新插入） ==========
        # 冲突场景：'000001.SZ' → '000001' 后与已有的 '000001' 记录重复
        # 仅在确实存在冲突时执行（避免无谓全表扫描）
        cur.execute("""
            WITH dups AS (
                SELECT code, trade_date, cycle, adjust_type,
                       ROW_NUMBER() OVER (
                         PARTITION BY code, trade_date, cycle, adjust_type
                         ORDER BY id DESC   -- 见 docstring 去重规则说明
                       ) AS rn
                FROM stock_quotes
            ),
            dup_count AS (
                SELECT COUNT(*) AS n FROM dups WHERE rn > 1
            )
            SELECT n FROM dup_count
        """)
        dup_n = cur.fetchone()[0] if cur.rowcount else 0
        if dup_n and dup_n > 0:
            cur.execute("""
                DELETE FROM stock_quotes sq
                USING (
                    SELECT ctid, ROW_NUMBER() OVER (
                        PARTITION BY code, trade_date, cycle, adjust_type
                        ORDER BY id DESC
                    ) AS rn
                    FROM stock_quotes
                ) d
                WHERE sq.ctid = d.ctid AND d.rn > 1
            """)
            result["steps"].append({"table": "stock_quotes", "action": "dedup_after_update", "rows": cur.rowcount or 0})
        else:
            result["steps"].append({"table": "stock_quotes", "action": "dedup_after_update", "rows": 0})

        # ========== Step 2: 标准化 stock_basic ==========
        cur.execute("""
            UPDATE stock_basic
            SET code = LOWER(SUBSTRING(code FROM 4))
            WHERE code ~ '^[A-Za-z]{2}\\.\\d+$'
        """)
        result["steps"].append({"table": "stock_basic", "action": "update", "rows": cur.rowcount})

        # ========== Step 3: 标准化 stock_indicators ==========
        cur.execute("""
            UPDATE stock_indicators
            SET code = SPLIT_PART(code, '.', 1)
            WHERE code LIKE '%.SZ' OR code LIKE '%.SH' OR code LIKE '%.BJ'
        """)
        result["steps"].append({"table": "stock_indicators", "action": "update", "rows": cur.rowcount})

        # ========== Step 4: 标准化 stock_adj_factor ==========
        cur.execute("""
            UPDATE stock_adj_factor
            SET code = SPLIT_PART(code, '.', 1)
            WHERE code LIKE '%.SZ' OR code LIKE '%.SH' OR code LIKE '%.BJ'
        """)
        result["steps"].append({"table": "stock_adj_factor", "action": "update", "rows": cur.rowcount})

        # ========== Step 5: 标准化 trade_signals ==========
        cur.execute("""
            UPDATE trade_signals
            SET code = SPLIT_PART(code, '.', 1)
            WHERE code LIKE '%.SZ' OR code LIKE '%.SH' OR code LIKE '%.BJ'
        """)
        result["steps"].append({"table": "trade_signals", "action": "update", "rows": cur.rowcount})

        result["status"] = "success"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.exception("股票代码标准化失败")
    finally:
        try:
            _put_db_conn(conn)
        except Exception:
            pass
    result["finished_at"] = _now_beijing().isoformat()
    return ApiResponse(code=200, message="success", data=result)


# ============================================
# 端点 9：字段完整性（空值率统计）
# ============================================

@router.get("/monitor/field-completeness/", summary="字段完整性检查")
def get_field_completeness():
    """
    检查各核心表的字段空值率，按表分组返回统计结果。
    空值率 = NULL值记录数 / 总记录数 × 100%
    """
    result = {"tables": {}, "overall_status": "ok", "issues": []}

    latest_quotes = _query_scalar("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d'")
    latest_snapshot = _query_scalar("SELECT MAX(trade_date) FROM stock_daily_snapshot")
    latest_indicators = _query_scalar("SELECT MAX(trade_date) FROM stock_indicators WHERE cycle='1d'")
    latest_adj = _query_scalar("SELECT MAX(trade_date) FROM stock_adj_factor")

    # --- stock_quotes 最新交易日字段空值 ---
    if latest_quotes:
        row = _query_dict(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN open IS NULL THEN 1 ELSE 0 END) AS null_open,
                SUM(CASE WHEN high IS NULL THEN 1 ELSE 0 END) AS null_high,
                SUM(CASE WHEN low IS NULL THEN 1 ELSE 0 END) AS null_low,
                SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) AS null_close,
                SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END) AS null_volume,
                SUM(CASE WHEN amount IS NULL THEN 1 ELSE 0 END) AS null_amount,
                SUM(CASE WHEN change_pct IS NULL THEN 1 ELSE 0 END) AS null_change_pct
            FROM stock_quotes
            WHERE cycle='1d' AND trade_date=%s
            """,
            (latest_quotes,),
        )
        if row:
            r = row[0]
            total = int(r["total"]) or 1
            fields = []
            for fname in ["open", "high", "low", "close", "volume", "amount", "change_pct"]:
                null_cnt = int(r.get(f"null_{fname}", 0))
                rate = round(null_cnt / total * 100, 2)
                fields.append({"field": fname, "null_count": null_cnt, "null_rate": rate})
                if null_cnt > 0:
                    result["issues"].append({
                        "table": "stock_quotes",
                        "field": fname,
                        "null_count": null_cnt,
                        "null_rate": rate,
                        "severity": "warning" if rate < 5 else "error",
                    })
            result["tables"]["stock_quotes"] = {
                "latest_date": str(latest_quotes),
                "total_rows": total,
                "fields": fields,
            }

    # --- stock_daily_snapshot 最新交易日字段空值 ---
    if latest_snapshot:
        # 先查询 snapshot 有哪些字段
        col_row = _query_dict(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='stock_daily_snapshot' AND table_schema='public'
              AND column_name NOT IN ('id','code','trade_date','created_at','updated_at')
            ORDER BY ordinal_position
            """
        )
        snapshot_cols = [c["column_name"] for c in col_row]

        if snapshot_cols:
            # 动态构建空值检查 SQL
            null_sum_exprs = ", ".join(
                f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END) AS null_{c}"
                for c in snapshot_cols
            )
            sql = f"""
                SELECT COUNT(*) AS total, {null_sum_exprs}
                FROM stock_daily_snapshot
                WHERE trade_date=%s
            """
            row = _query_dict(sql, (latest_snapshot,))
            if row:
                r = row[0]
                total = int(r["total"]) or 1
                fields = []
                for c in snapshot_cols:
                    null_cnt = int(r.get(f"null_{c}", 0))
                    rate = round(null_cnt / total * 100, 2)
                    fields.append({"field": c, "null_count": null_cnt, "null_rate": rate})
                    if null_cnt > 0:
                        result["issues"].append({
                            "table": "stock_daily_snapshot",
                            "field": c,
                            "null_count": null_cnt,
                            "null_rate": rate,
                            "severity": "warning" if rate < 20 else "error",
                        })
                result["tables"]["stock_daily_snapshot"] = {
                    "latest_date": str(latest_snapshot),
                    "total_rows": total,
                    "fields": fields,
                }

    # --- stock_indicators 最新交易日字段空值 ---
    if latest_indicators:
        col_row = _query_dict(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='stock_indicators' AND table_schema='public'
              AND column_name NOT IN ('id','code','cycle','trade_date','trade_time','trade_datetime','created_at')
            ORDER BY ordinal_position
            """
        )
        indicator_cols = [c["column_name"] for c in col_row]

        if indicator_cols:
            null_sum_exprs = ", ".join(
                f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END) AS null_{c}"
                for c in indicator_cols
            )
            sql = f"""
                SELECT COUNT(*) AS total, {null_sum_exprs}
                FROM stock_indicators
                WHERE cycle='1d' AND trade_date=%s
            """
            row = _query_dict(sql, (latest_indicators,))
            if row:
                r = row[0]
                total = int(r["total"]) or 1
                fields = []
                for c in indicator_cols:
                    null_cnt = int(r.get(f"null_{c}", 0))
                    rate = round(null_cnt / total * 100, 2)
                    fields.append({"field": c, "null_count": null_cnt, "null_rate": rate})
                    if null_cnt > 0:
                        result["issues"].append({
                            "table": "stock_indicators",
                            "field": c,
                            "null_count": null_cnt,
                            "null_rate": rate,
                            "severity": "warning" if rate < 20 else "error",
                        })
                result["tables"]["stock_indicators"] = {
                    "latest_date": str(latest_indicators),
                    "total_rows": total,
                    "fields": fields,
                }

    # --- stock_adj_factor 总体空值 ---
    if latest_adj:
        row = _query_dict(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN adj_factor IS NULL THEN 1 ELSE 0 END) AS null_adj_factor
            FROM stock_adj_factor
            """
        )
        if row:
            r = row[0]
            total = int(r["total"]) or 1
            null_cnt = int(r["null_adj_factor"])
            rate = round(null_cnt / total * 100, 2)
            result["tables"]["stock_adj_factor"] = {
                "latest_date": str(latest_adj),
                "total_rows": total,
                "fields": [{"field": "adj_factor", "null_count": null_cnt, "null_rate": rate}],
            }
            if null_cnt > 0:
                result["issues"].append({
                    "table": "stock_adj_factor",
                    "field": "adj_factor",
                    "null_count": null_cnt,
                    "null_rate": rate,
                    "severity": "error",
                })

    # 计算每个表的综合完整性得分（排除空率>=95%的已知数据源限制字段）
    for tbl_info in result["tables"].values():
        fields = tbl_info.get("fields", [])
        active_fields = [f for f in fields if f["null_rate"] < 95]
        if active_fields:
            avg_score = round(
                sum((1 - f["null_rate"] / 100) for f in active_fields) / len(active_fields) * 100, 2
            )
        else:
            avg_score = 0.0
        tbl_info["completeness_score"] = avg_score

    # 各表平均分作为总评分
    scores = [t["completeness_score"] for t in result["tables"].values()]
    overall_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    result["overall_score"] = overall_score

    # 评分 >= 95 视为 ok 状态
    if result["issues"]:
        result["overall_status"] = "ok" if overall_score >= 95 else (
            "warning" if all(i["severity"] == "warning" for i in result["issues"]) else "error"
        )

    return ApiResponse(code=200, message="success", data=result)


# ============================================
# 端点 10：数据一致性检查
# ============================================

@router.get("/monitor/consistency-check/", summary="数据一致性检查")
def get_consistency_check(
    show_diff_codes: bool = Query(False, description="是否返回缺失股票代码列表"),
):
    """
    跨表一致性检查，包括：
    1. quotes vs indicators — indicators 是否覆盖所有行情股票
    2. quotes vs adj_factor — 复权因子是否覆盖
    3. quotes vs snapshot — 快照是否覆盖
    4. 交易日历 vs quotes — 非交易日污染 & 交易日缺失
    5. 停牌/ST数据隔离检查 — 确认ST股票在 quotes 中有数据
    """
    result = {"checks": [], "overall_status": "ok"}
    latest_quote = _query_scalar("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d'")
    total_stocks = _query_scalar("SELECT COUNT(*) FROM stock_basic") or 0
    latest_adj = _query_scalar("SELECT MAX(trade_date) FROM stock_adj_factor")

    # --- Check 1: quotes vs indicators ---
    if latest_quote:
        quote_stocks = _query_scalar(
            "SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle='1d' AND trade_date=%s",
            (latest_quote,),
        ) or 0
        indicator_stocks = _query_scalar(
            "SELECT COUNT(DISTINCT code) FROM stock_indicators WHERE cycle='1d' AND trade_date=%s",
            (latest_quote,),
        ) or 0
        diff1 = quote_stocks - indicator_stocks

        # 区分真正缺失（>=60天行情无指标）vs 数据不足（<60天新股）
        real_missing = 0
        if diff1 > 0:
            real_missing = _query_scalar(
                """
                SELECT COUNT(*) FROM (
                    SELECT q.code
                    FROM stock_quotes q
                    WHERE q.cycle='1d' AND q.trade_date=%s
                      AND NOT EXISTS (
                        SELECT 1 FROM stock_indicators i
                        WHERE i.cycle='1d' AND i.trade_date=%s AND i.code=q.code
                      )
                    GROUP BY q.code
                    HAVING COUNT(*) >= 60
                ) m
                """,
                (latest_quote, latest_quote),
            ) or 0

        status = "ok" if real_missing == 0 else "error"
        check1 = {
            "name": "quotes ↔ indicators",
            "status": status,
            "quote_stocks": quote_stocks,
            "indicator_stocks": indicator_stocks,
            "diff_count": diff1,
            "real_missing": real_missing,
            "new_stocks_lt_60d": diff1 - real_missing,
            "diff_pct": round(diff1 / quote_stocks * 100, 2) if quote_stocks else 0,
        }
        if diff1 > 0 and show_diff_codes:
            diff_codes = _query_dict(
                """
                SELECT DISTINCT q.code
                FROM stock_quotes q
                WHERE q.cycle='1d' AND q.trade_date=%s
                  AND NOT EXISTS (
                    SELECT 1 FROM stock_indicators i
                    WHERE i.cycle='1d' AND i.trade_date=%s AND i.code=q.code
                  )
                ORDER BY q.code
                """,
                (latest_quote, latest_quote),
            )
            check1["diff_codes"] = [r["code"] for r in diff_codes]
        result["checks"].append(check1)

    # --- Check 2: 交易日 vs 周末/节假日污染 ---
    weekend_quote_count = _query_scalar(
        """
        SELECT COUNT(*) FROM stock_quotes q
        WHERE q.cycle='1d'
          AND EXTRACT(DOW FROM q.trade_date) IN (0, 6)
          AND q.trade_date >= '2020-01-01'
        LIMIT 1
        """
    ) or 0
    has_weekend_pollution = weekend_quote_count > 0

    # 交易日缺失检查：检查 trade_calendar 中 is_open=1 的日期在 quotes 中是否有数据
    missing_trade_days = _query_scalar(
        """
        SELECT COUNT(*) FROM trade_calendar tc
        WHERE tc.is_open = 1
          AND tc.cal_date >= '2020-01-01'
          AND tc.cal_date <= CURRENT_DATE
          AND NOT EXISTS (
            SELECT 1 FROM stock_quotes q
            WHERE q.cycle='1d' AND q.trade_date = tc.cal_date
            LIMIT 1
          )
        """
    ) or 0

    check2_status = "ok"
    if has_weekend_pollution:
        check2_status = "error"
    if missing_trade_days > 0:
        check2_status = "error" if missing_trade_days > 5 else "warning"

    check2 = {
        "name": "交易日历 vs quotes",
        "status": check2_status,
        "has_weekend_pollution": has_weekend_pollution,
        "missing_trade_days_since_2020": missing_trade_days,
    }
    result["checks"].append(check2)

    # --- Check 3: 复权因子覆盖 ---
    adj_stocks = _query_scalar("SELECT COUNT(DISTINCT code) FROM stock_adj_factor") or 0
    adj_latest_date = latest_adj
    adj_days = 0
    if latest_adj:
        adj_days = _query_scalar(
            "SELECT COUNT(DISTINCT trade_date) FROM stock_adj_factor"
        ) or 0

    check3_status = "ok"
    if adj_days == 1 and adj_stocks >= 5000:
        check3_status = "warning"  # 只有1天但覆盖了大部分股票
    elif adj_days == 0 or adj_stocks == 0:
        check3_status = "error"
    elif adj_days < 30:
        check3_status = "warning"

    check3 = {
        "name": "quotes ↔ adj_factor",
        "status": check3_status,
        "adj_factor_stocks": adj_stocks,
        "adj_factor_days": adj_days,
        "adj_latest_date": str(adj_latest_date) if adj_latest_date else None,
        "notes": "只有1天数据（2026-06-01），缺少历史复权因子" if adj_days == 1 else None,
    }
    if check3["notes"]:
        result.setdefault("warnings", []).append({
            "level": "critical",
            "type": "adj_factor_missing_history",
            "message": "复权因子只有1天数据，前台回测使用的前复权价格可能错误",
            "suggestion": "立即运行复权因子全量同步脚本 backend/collector/etl/sync_adj_factor.py",
        })
    result["checks"].append(check3)

    # --- Check 4: stock_daily_snapshot 覆盖 ---
    latest_snapshot = _query_scalar("SELECT MAX(trade_date) FROM stock_daily_snapshot")
    if latest_snapshot and latest_quote:
        snapshot_stocks = _query_scalar(
            "SELECT COUNT(DISTINCT code) FROM stock_daily_snapshot WHERE trade_date=%s",
            (latest_snapshot,),
        ) or 0
        quote_stocks_at_snapshot_date = _query_scalar(
            "SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle='1d' AND trade_date=%s",
            (latest_snapshot,),
        ) or 0
        diff4 = quote_stocks_at_snapshot_date - snapshot_stocks
        check4 = {
            "name": "quotes ↔ daily_snapshot",
            "status": "ok" if diff4 == 0 else "warning" if diff4 < 100 else "error",
            "snapshot_latest_date": str(latest_snapshot),
            "snapshot_stocks": snapshot_stocks,
            "quote_stocks_at_date": quote_stocks_at_snapshot_date,
            "diff_count": diff4,
        }
    else:
        check4 = {
            "name": "quotes ↔ daily_snapshot",
            "status": "error",
            "snapshot_latest_date": None,
            "snapshot_stocks": 0,
            "quote_stocks_at_date": 0,
            "diff_count": 0,
        }
    result["checks"].append(check4)

    # --- Check 5: ST/停牌隔离校验 ---
    if latest_quote:
        st_with_data = _query_scalar(
            """
            SELECT COUNT(*) FROM stock_basic b
            WHERE (b.name LIKE 'ST%%' OR b.name LIKE '*ST%%' OR b.name LIKE 'S%%ST%%')
              AND b.delist_date IS NULL
              AND EXISTS (
                SELECT 1 FROM stock_quotes q
                WHERE q.cycle='1d' AND q.trade_date=%s AND q.code=b.code
              )
            """,
            (latest_quote,),
        ) or 0
        st_total = _query_scalar(
            """
            SELECT COUNT(*) FROM stock_basic b
            WHERE (b.name LIKE 'ST%%' OR b.name LIKE '*ST%%' OR b.name LIKE 'S%%ST%%')
              AND b.delist_date IS NULL
            """
        ) or 0
        st_missing = st_total - st_with_data
        check5 = {
            "name": "ST/停牌隔离校验",
            "status": "ok" if st_missing == 0 else "warning",
            "st_total": st_total,
            "st_with_data": st_with_data,
            "st_missing": st_missing,
        }
        result["checks"].append(check5)

    # 更新整体状态
    error_checks = [c for c in result["checks"] if c["status"] == "error"]
    warning_checks = [c for c in result["checks"] if c["status"] == "warning"]
    if error_checks:
        result["overall_status"] = "error"
    elif warning_checks:
        result["overall_status"] = "warning"

    return ApiResponse(code=200, message="success", data=result)


# ============================================
# 端点 11：异常值检测
# ============================================

@router.get("/monitor/anomaly-detection/", summary="异常值检测")
def get_anomaly_detection(
    days: int = Query(5, ge=1, le=30, description="检查最近N天的数据"),
):
    """
    检查最新交易日数据中的异常值：
    1. OHLC 逻辑异常（high<low, open/close超出范围）
    2. 价格异常（close<=0, 涨跌幅>100%）
    3. 成交量异常（volume<0, volume为0的股票）
    4. 复权价格负值检测
    5. 连续多日volume=0的非停牌股票
    """
    result = {"checks": [], "overall_status": "ok"}
    latest_quote = _query_scalar("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d'")
    if not latest_quote:
        return ApiResponse(code=200, message="success", data=result)

    # --- Check 1: OHLC 逻辑异常 ---
    ohlc_anomalies = _query_dict(
        """
        SELECT
            SUM(CASE WHEN high < low THEN 1 ELSE 0 END) AS high_lt_low,
            SUM(CASE WHEN open > high OR open < low THEN 1 ELSE 0 END) AS open_outside,
            SUM(CASE WHEN close > high OR close < low THEN 1 ELSE 0 END) AS close_outside,
            SUM(CASE WHEN close <= 0 THEN 1 ELSE 0 END) AS neg_close,
            SUM(CASE WHEN volume < 0 THEN 1 ELSE 0 END) AS neg_volume
        FROM stock_quotes
        WHERE cycle='1d' AND trade_date=%s
        """,
        (latest_quote,),
    )
    if ohlc_anomalies:
        r = ohlc_anomalies[0]
        ohlc_total = sum(int(r.get(k, 0)) for k in ["high_lt_low", "open_outside", "close_outside", "neg_close", "neg_volume"])
        result["checks"].append({
            "name": "OHLC 逻辑异常",
            "status": "ok" if ohlc_total == 0 else "error",
            "latest_date": str(latest_quote),
            "details": {
                "high_lt_low": int(r["high_lt_low"]),
                "open_outside_high_low": int(r["open_outside"]),
                "close_outside_high_low": int(r["close_outside"]),
                "neg_close": int(r["neg_close"]),
                "neg_volume": int(r["neg_volume"]),
            },
        })

    # --- Check 2: 涨跌幅异常 ---
    pct_anomalies = _query_dict(
        """
        SELECT
            SUM(CASE WHEN change_pct > 100 OR change_pct < -100 THEN 1 ELSE 0 END) AS extreme_pct,
            SUM(CASE WHEN change_pct IS NULL THEN 1 ELSE 0 END) AS null_pct
        FROM stock_quotes
        WHERE cycle='1d' AND trade_date=%s
        """,
        (latest_quote,),
    )
    if pct_anomalies:
        r = pct_anomalies[0]
        extreme_pct = int(r["extreme_pct"])
        result["checks"].append({
            "name": "涨跌幅异常",
            "status": "ok" if extreme_pct == 0 else "warning",
            "latest_date": str(latest_quote),
            "details": {
                "change_pct_gt_100_or_lt_neg100": extreme_pct,
                "null_change_pct": int(r["null_pct"]),
            },
        })

    # --- Check 3: 成交量异常 ---
    vol_anomalies = _query_dict(
        """
        SELECT
            SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) AS zero_volume,
            SUM(CASE WHEN amount = 0 THEN 1 ELSE 0 END) AS zero_amount,
            SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END) AS null_volume,
            SUM(CASE WHEN amount IS NULL THEN 1 ELSE 0 END) AS null_amount
        FROM stock_quotes
        WHERE cycle='1d' AND trade_date=%s
        """,
        (latest_quote,),
    )
    if vol_anomalies:
        r = vol_anomalies[0]
        vol_issues = sum(int(r.get(k, 0)) for k in ["zero_volume", "null_volume", "null_amount"])
        result["checks"].append({
            "name": "成交量/成交额异常",
            "status": "ok" if vol_issues == 0 else "warning",
            "latest_date": str(latest_quote),
            "details": {
                "zero_volume": int(r["zero_volume"]),
                "zero_amount": int(r["zero_amount"]),
                "null_volume": int(r["null_volume"]),
                "null_amount": int(r["null_amount"]),
            },
        })

    # --- Check 4: 连续多日 volume=0 的非停牌股票 ---
    consecutive_zero_vol = _query_dict(
        f"""
        WITH daily_zero_vol AS (
            SELECT code, trade_date
            FROM stock_quotes
            WHERE cycle='1d' AND trade_date >= %s - INTERVAL '%s days'
              AND (volume = 0 OR volume IS NULL)
        ),
        zero_counts AS (
            SELECT code, COUNT(*) AS zero_days
            FROM daily_zero_vol
            GROUP BY code
            HAVING COUNT(*) >= 3
        )
        SELECT z.code, z.zero_days, b.name
        FROM zero_counts z
        JOIN stock_basic b ON b.code = z.code
        WHERE b.delist_date IS NULL
          AND b.name NOT LIKE 'ST%%' AND b.name NOT LIKE '*ST%%'
        ORDER BY z.zero_days DESC
        LIMIT 50
        """,
        (latest_quote, days),
    )
    result["checks"].append({
        "name": "连续多日零成交量（非停牌）",
        "status": "ok" if not consecutive_zero_vol else "warning",
        "lookback_days": days,
        "count": len(consecutive_zero_vol),
        "stocks": [{"code": r["code"], "name": r["name"], "zero_days": r["zero_days"]} for r in consecutive_zero_vol] if consecutive_zero_vol else [],
    })

    # --- Check 5: 前复权价格负值（chk adj_factor 是否存在close<0的前复权记录）---
    neg_adj_close = _query_dict(
        """
        SELECT q.code, q.trade_date, q.close, b.name
        FROM stock_quotes q
        JOIN stock_basic b ON b.code = q.code
        WHERE q.cycle='1d' AND q.trade_date >= %s - INTERVAL '30 days'
          AND q.close < 0
        ORDER BY q.trade_date DESC
        LIMIT 20
        """,
        (latest_quote,),
    )
    result["checks"].append({
        "name": "复权价格负值检测",
        "status": "ok" if not neg_adj_close else "error",
        "count": len(neg_adj_close),
        "samples": [
            {"code": r["code"], "name": r["name"], "trade_date": str(r["trade_date"]), "close": float(r["close"])}
            for r in neg_adj_close[:5]
        ] if neg_adj_close else [],
    })

    # 整体状态
    error_checks = [c for c in result["checks"] if c["status"] == "error"]
    warning_checks = [c for c in result["checks"] if c["status"] == "warning"]
    if error_checks:
        result["overall_status"] = "error"
    elif warning_checks:
        result["overall_status"] = "warning"

    return ApiResponse(code=200, message="success", data=result)


# ============================================
# 增强端点 6：数据质量统计（已增强版）
# ============================================

@router.get("/monitor/data-quality/", summary="数据质量统计（增强版）")
def get_data_quality(
    limit_codes: int = Query(50, ge=1, le=500, description="返回的失败股票代码列表数量"),
):
    """
    返回脏数据统计、错误类型分布、同步失败记录、NaN统计、指标计算失败股票清单等。
    """
    result = {}

    # 脏数据统计
    result["dirty"] = {}
    dirty_total = _query_scalar("SELECT COUNT(*) FROM stock_quotes_dirty")
    dirty_pending = _query_scalar("SELECT COUNT(*) FROM stock_quotes_dirty WHERE status = 'pending'")
    result["dirty"]["total"] = dirty_total or 0
    result["dirty"]["pending"] = dirty_pending or 0

    # 错误类型分布
    type_rows = _query_dict(
        "SELECT error_type, COUNT(*) AS cnt FROM stock_quotes_dirty GROUP BY error_type ORDER BY cnt DESC"
    )
    result["dirty"]["by_type"] = [{"type": r["error_type"], "count": r["cnt"]} for r in type_rows]

    # 同步失败记录
    failed_checkpoints = _query_scalar(
        "SELECT COUNT(*) FROM sync_checkpoints WHERE sync_status = 'failed'"
    )
    result["sync_failed"] = failed_checkpoints or 0

    # 同步失败股票列表（提供详情）
    failed_stocks = _query_dict(
        """
        SELECT code, cycle, fail_reason, updated_at
        FROM sync_checkpoints
        WHERE sync_status = 'failed'
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        (limit_codes,),
    )
    result["sync_failed_stocks"] = [
        {
            "code": r["code"],
            "cycle": r["cycle"],
            "fail_reason": (r.get("fail_reason") or "")[:120],
            "updated_at": str(r["updated_at"]),
        }
        for r in failed_stocks
    ]

    # 最近错误日志
    recent_errors = _query_dict(
        "SELECT code, trade_date, error_type, error_message, created_at FROM data_error_log ORDER BY created_at DESC LIMIT 20"
    )
    result["recent_errors"] = [
        {
            "code": r.get("code"),
            "trade_date": str(r["trade_date"]) if r.get("trade_date") else None,
            "error_type": r["error_type"],
            "error_message": (r["error_message"] or "")[:100],
            "created_at": str(r["created_at"]),
        }
        for r in recent_errors
    ]

    # --- 新增：NaN 统计（stock_daily_snapshot）---
    latest_snapshot = _query_scalar("SELECT MAX(trade_date) FROM stock_daily_snapshot")
    nan_stats = {}
    if latest_snapshot:
        col_row = _query_dict(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='stock_daily_snapshot' AND table_schema='public'
              AND column_name NOT IN ('id','code','trade_date','created_at','updated_at')
            ORDER BY ordinal_position
            """
        )
        snapshot_cols = [c["column_name"] for c in col_row]
        if snapshot_cols:
            null_exprs = ", ".join(
                f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END) AS null_{c}"
                for c in snapshot_cols
            )
            sql = f"""
                SELECT COUNT(*) AS total, {null_exprs}
                FROM stock_daily_snapshot WHERE trade_date=%s
            """
            row = _query_dict(sql, (latest_snapshot,))
            if row:
                r = row[0]
                total = int(r["total"]) or 1
                for c in snapshot_cols:
                    null_cnt = int(r.get(f"null_{c}", 0))
                    if null_cnt > 0:
                        nan_stats[c] = {
                            "null_count": null_cnt,
                            "null_rate": round(null_cnt / total * 100, 2),
                        }
    result["nan_statistics"] = nan_stats

    # --- 新增：指标计算失败股票清单 ---
    latest_quote = _query_scalar("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d'")
    if latest_quote:
        missing_indicator_codes = _query_dict(
            """
            SELECT DISTINCT q.code
            FROM stock_quotes q
            WHERE q.cycle='1d' AND q.trade_date=%s
              AND NOT EXISTS (
                SELECT 1 FROM stock_indicators i
                WHERE i.cycle='1d' AND i.trade_date=%s AND i.code=q.code
              )
            ORDER BY q.code
            LIMIT %s
            """,
            (latest_quote, latest_quote, limit_codes),
        )
        total_missing_indicators = _query_scalar(
            """
            SELECT COUNT(DISTINCT q.code)
            FROM stock_quotes q
            WHERE q.cycle='1d' AND q.trade_date=%s
              AND NOT EXISTS (
                SELECT 1 FROM stock_indicators i
                WHERE i.cycle='1d' AND i.trade_date=%s AND i.code=q.code
              )
            """,
            (latest_quote, latest_quote),
        ) or 0
        result["indicator_failed_stocks"] = {
            "total_missing": total_missing_indicators,
            "sample_codes": [r["code"] for r in missing_indicator_codes],
            "note": "这些股票有行情数据但缺少技术指标，可能是指标计算脚本执行时出错被吞掉",
        }

    return ApiResponse(code=200, message="success", data=result)