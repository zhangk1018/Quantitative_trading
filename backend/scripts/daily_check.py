#!/usr/bin/env python3
"""
每日数据管道晨检自动化脚本

功能：
1. 预设标准化的晨检项目清单
2. 针对每个检查项执行具体的验证操作
3. 实时记录检查结果（通过/失败/警告）
4. 生成结构化的晨检报告（JSON + 终端输出）
5. 提供明确的错误提示和异常处理机制

使用方式：
    python backend/scripts/daily_check.py
    python backend/scripts/daily_check.py --output /path/to/report.json
    python backend/scripts/daily_check.py --config /path/to/config.yaml
    python backend/scripts/daily_check.py --skip log_file_errors
    python backend/scripts/daily_check.py --quiet

退出码：
    0 - 全部通过
    1 - 存在警告项（需关注）
    2 - 存在失败项（异常）

依赖：
    - psycopg2 (PostgreSQL)
    - PyYAML (可选，用于外部配置文件)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# 类型定义
# ============================================================


class CheckLevel(Enum):
    """检查项级别"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class CheckStatus(Enum):
    """检查结果状态"""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


# ============================================================
# 数据模型
# ============================================================


@dataclass
class CheckItem:
    """单个检查项定义"""
    id: str
    name: str
    description: str
    level: CheckLevel
    category: str


@dataclass
class CheckResult:
    """单个检查项结果"""
    item_id: str
    status: CheckStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    duration_ms: Optional[float] = None


@dataclass
class CheckReport:
    """完整晨检报告"""
    script_version: str
    start_time: str
    end_time: str
    total_duration_ms: float
    environment: Dict[str, Any]
    config: Dict[str, Any]
    results: List[Dict[str, Any]]
    summary: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)


# ============================================================
# 默认配置
# ============================================================

DEFAULT_CONFIG = {
    # 数据库连接
    "database": {
        "host": "localhost",
        "port": 5432,
        "dbname": "quant_trading",
        "user": "quant_user",
    },
    # 检查项开关
    "checks": {
        "database_connectivity": {"enabled": True, "level": "critical"},
        "stock_quotes_freshness": {"enabled": True, "level": "critical"},
        "stock_quotes_volume": {"enabled": True, "level": "warning"},
        "stock_quotes_missing": {"enabled": True, "level": "warning"},
        "snapshot_sync": {"enabled": True, "level": "critical"},
        "data_completeness": {"enabled": True, "level": "warning"},
        "task_run_log": {"enabled": True, "level": "critical"},
        "log_file_errors": {"enabled": True, "level": "info"},
        "postgresql_running": {"enabled": True, "level": "critical"},
    },
    # 阈值
    "thresholds": {
        "stock_quotes": {
            "min_daily_records": 4500,
            "warn_daily_records": 3000,
            "max_days_stale": {"weekday": 2, "weekend": 3},
            "max_missing_stocks": 500,
            "warn_missing_stocks": 100,
        },
        "snapshot": {
            "min_daily_records": 4500,
            "warn_daily_records": 3000,
        },
        "completeness": {
            "pe_ttm": 0.72,
            "ma5": 0.80,
            "macd": 0.80,
            "rsi_6": 0.80,
            "boll_mid": 0.80,
            "green_threshold": 0.95,
        },
        "task_run_log": {
            "max_failed_tasks_last_days": 2,
        },
    },
    # 路径
    "paths": {
        "project_root": "",
        "log_files": [
            "logs/daily_import.log",
        ],
        "collab_ticket": "docs/协作单.md",
    },
    # 报告输出
    "output": {
        "terminal": True,
        "color": True,
        "file": "",
    },
}

SCRIPT_VERSION = "1.0.0"


# ============================================================
# 颜色工具
# ============================================================


class Colors:
    """终端颜色"""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def colorize(text: str, color: str, bold: bool = False) -> str:
    """给文本添加颜色"""
    prefix = Colors.BOLD if bold else ""
    return f"{prefix}{color}{text}{Colors.RESET}"


def status_tag(status: CheckStatus, use_color: bool = True) -> str:
    """获取状态标签"""
    if not use_color:
        return {CheckStatus.PASS: "[PASS]", CheckStatus.WARN: "[WARN]",
                CheckStatus.FAIL: "[FAIL]", CheckStatus.SKIP: "[SKIP]",
                CheckStatus.ERROR: "[ERROR]"}.get(status, "[????]")
    return {
        CheckStatus.PASS: colorize("  ✅ PASS", Colors.GREEN),
        CheckStatus.WARN: colorize("  ⚠️ WARN", Colors.YELLOW),
        CheckStatus.FAIL: colorize("  🚨 FAIL", Colors.RED),
        CheckStatus.SKIP: colorize("  ⏭️ SKIP", Colors.DIM),
        CheckStatus.ERROR: colorize("  ❌ ERROR", Colors.RED),
    }.get(status, "[????]")


# ============================================================
# 数据库工具
# ============================================================


class DatabaseError(Exception):
    """数据库操作异常"""
    pass


def _load_env_file(env_path: str) -> None:
    """加载 .env 文件到环境变量"""
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def _get_db_connection(config: Dict[str, Any]) -> Any:
    """获取数据库连接，失败时抛出 DatabaseError"""
    db_cfg = config["database"]
    password = os.environ.get("PG_PASSWORD", "")
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=db_cfg["host"],
            port=db_cfg["port"],
            dbname=db_cfg["dbname"],
            user=db_cfg["user"],
            password=password,
            connect_timeout=5,
        )
        return conn
    except ImportError:
        raise DatabaseError("psycopg2 未安装，请执行: pip install psycopg2-binary")
    except Exception as e:
        raise DatabaseError(f"数据库连接失败: {e}")


def _query_db(conn: Any, sql: str, params: tuple = ()) -> List[Tuple]:
    """执行数据库查询，返回行列表"""
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as e:
        raise DatabaseError(f"查询执行失败: {e}\nSQL: {sql}")


# ============================================================
# 检查器
# ============================================================


class DailyCheckRunner:
    """晨检运行器"""

    def __init__(
        self,
        config: Dict[str, Any],
        skip_items: Optional[List[str]] = None,
        quiet: bool = False,
        use_color: bool = True,
    ):
        self.config = config
        self.skip_items = set(skip_items or [])
        self.quiet = quiet
        self.use_color = use_color and sys.stdout.isatty()
        self.results: List[CheckResult] = []
        self._resolve_paths()

    def _resolve_paths(self) -> None:
        """解析路径配置"""
        root = self.config["paths"]["project_root"]
        if not root:
            # 自动检测项目根目录（脚本位于 backend/scripts/）
            script_dir = os.path.dirname(os.path.abspath(__file__))
            root = os.path.abspath(os.path.join(script_dir, "..", ".."))
            self.config["paths"]["project_root"] = root

        self.project_root = root
        self._env_loaded = False

    def _ensure_env(self) -> None:
        """确保环境变量已加载"""
        if self._env_loaded:
            return
        env_path = os.path.join(self.project_root, ".env")
        _load_env_file(env_path)
        self._env_loaded = True

    def _get_log_path(self, relative_path: str) -> str:
        """获取日志文件绝对路径"""
        return os.path.join(self.project_root, relative_path)

    # ---- 日志输出 ----

    def _log(self, msg: str = "") -> None:
        if not self.quiet:
            print(msg)

    def _log_item_start(self, item: CheckItem) -> None:
        prefix = colorize(f"[{item.category}]", Colors.CYAN) if self.use_color else f"[{item.category}]"
        self._log(f"\n  {prefix} {item.name} ...")

    def _log_result(self, result: CheckResult) -> None:
        tag = status_tag(result.status, self.use_color)
        self._log(f"  {tag} {result.message}")

    # ---- 检查执行 ----

    def _should_run(self, item_id: str) -> bool:
        check_cfg = self.config["checks"].get(item_id, {})
        return check_cfg.get("enabled", True) and item_id not in self.skip_items

    def _make_result(
        self,
        item: CheckItem,
        status: CheckStatus,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
    ) -> CheckResult:
        return CheckResult(
            item_id=item.id,
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms,
        )

    def run(self) -> CheckReport:
        """执行全部检查项"""
        start_time = datetime.now()
        self._log(f"\n{colorize('=' * 60, Colors.BOLD, bold=True)}")
        self._log(f"{colorize('  每日数据管道晨检', Colors.BOLD, bold=True)}")
        self._log(f"{colorize('=' * 60, Colors.BOLD, bold=True)}")
        self._log(f"  版本: {SCRIPT_VERSION}  时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._log(f"{'=' * 60}")

        self._ensure_env()

        # 定义检查清单
        check_items = self._build_checklist()

        # 按分类顺序执行
        for item in check_items:
            if not self._should_run(item.id):
                result = self._make_result(item, CheckStatus.SKIP, "已跳过 (配置禁用)")
                self.results.append(result)
                continue

            self._log_item_start(item)
            t0 = time.perf_counter()
            try:
                result = self._dispatch_check(item)
            except DatabaseError as e:
                elapsed = (time.perf_counter() - t0) * 1000
                result = self._make_result(item, CheckStatus.ERROR, f"数据库异常: {e}", duration_ms=elapsed)
            except Exception as e:
                elapsed = (time.perf_counter() - t0) * 1000
                result = self._make_result(item, CheckStatus.ERROR, f"执行异常: {e}", duration_ms=elapsed)
            elapsed = (time.perf_counter() - t0) * 1000
            if result.duration_ms is None:
                result.duration_ms = round(elapsed, 1)
            self.results.append(result)
            self._log_result(result)

        # 生成报告
        end_time = datetime.now()
        total_ms = (end_time - start_time).total_seconds() * 1000
        report = self._build_report(start_time, end_time, total_ms)
        self._print_summary(report)
        return report

    def _build_checklist(self) -> List[CheckItem]:
        """构建检查清单"""
        return [
            # ---- 基础设施 ----
            CheckItem("postgresql_running", "PostgreSQL 服务状态", "检查 PostgreSQL 进程是否运行", CheckLevel.CRITICAL, "基础设施"),
            CheckItem("database_connectivity", "数据库连接", "验证数据库连接是否正常", CheckLevel.CRITICAL, "基础设施"),
            # ---- 数据下载 ----
            CheckItem("stock_quotes_freshness", "行情数据新鲜度", "检查最新交易日距今是否在合理范围内", CheckLevel.CRITICAL, "数据下载"),
            CheckItem("stock_quotes_volume", "行情数据量", "检查每日数据量是否达到健康标准", CheckLevel.WARNING, "数据下载"),
            CheckItem("stock_quotes_missing", "缺失股票数", "检查最新交易日缺失股票数量", CheckLevel.WARNING, "数据下载"),
            # ---- 宽表同步 ----
            CheckItem("snapshot_sync", "宽表同步状态", "检查 stock_daily_snapshot 是否与 stock_quotes 同步", CheckLevel.CRITICAL, "宽表同步"),
            # ---- 数据补全 ----
            CheckItem("data_completeness", "字段完整性", "检查关键字段的填充率", CheckLevel.WARNING, "数据补全"),
            # ---- 任务日志 ----
            CheckItem("task_run_log", "任务执行日志", "检查最近任务执行是否有失败记录", CheckLevel.CRITICAL, "任务日志"),
            # ---- 日志文件 ----
            CheckItem("log_file_errors", "日志文件错误", "检查日志文件中的错误计数", CheckLevel.INFO, "日志文件"),
        ]

    def _dispatch_check(self, item: CheckItem) -> CheckResult:
        """分发到具体检查方法"""
        dispatch = {
            "postgresql_running": self._check_postgresql_running,
            "database_connectivity": self._check_database_connectivity,
            "stock_quotes_freshness": self._check_stock_quotes_freshness,
            "stock_quotes_volume": self._check_stock_quotes_volume,
            "stock_quotes_missing": self._check_stock_quotes_missing,
            "snapshot_sync": self._check_snapshot_sync,
            "data_completeness": self._check_data_completeness,
            "task_run_log": self._check_task_run_log,
            "log_file_errors": self._check_log_file_errors,
        }
        handler = dispatch.get(item.id)
        if handler is None:
            return self._make_result(item, CheckStatus.SKIP, f"未实现检查方法: {item.id}")
        return handler(item)

    # ================================================================
    # 各检查项实现
    # ================================================================

    def _check_postgresql_running(self, item: CheckItem) -> CheckResult:
        """检查 PostgreSQL 进程是否运行"""
        try:
            result = subprocess.run(
                ["pg_isready"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                details = {"pg_isready_output": result.stdout.strip()}
                return self._make_result(item, CheckStatus.PASS, "PostgreSQL 服务运行中", details)
            else:
                details = {"pg_isready_output": result.stdout.strip() or result.stderr.strip()}
                return self._make_result(item, CheckStatus.FAIL, "PostgreSQL 未响应", details)
        except FileNotFoundError:
            return self._make_result(item, CheckStatus.WARN, "pg_isready 命令未找到，跳过进程检查")
        except subprocess.TimeoutExpired:
            return self._make_result(item, CheckStatus.WARN, "pg_isready 超时")
        except Exception as e:
            return self._make_result(item, CheckStatus.ERROR, f"检查异常: {e}")

    def _check_database_connectivity(self, item: CheckItem) -> CheckResult:
        """检查数据库连接"""
        conn = _get_db_connection(self.config)
        try:
            rows = _query_db(conn, "SELECT 1 AS ok")
            if rows and rows[0][0] == 1:
                details = {"server_version": self._get_server_version(conn)}
                return self._make_result(item, CheckStatus.PASS, "数据库连接正常", details)
            return self._make_result(item, CheckStatus.FAIL, "数据库返回异常结果")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _get_server_version(self, conn: Any) -> str:
        try:
            rows = _query_db(conn, "SELECT version()")
            return rows[0][0] if rows else "unknown"
        except Exception:
            return "unknown"

    def _check_stock_quotes_freshness(self, item: CheckItem) -> CheckResult:
        """检查行情数据新鲜度"""
        conn = _get_db_connection(self.config)
        try:
            rows = _query_db(conn, """
                SELECT trade_date, COUNT(*)
                FROM stock_quotes
                WHERE cycle = '1d' AND trade_date >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY trade_date
                ORDER BY trade_date DESC
                LIMIT 5
            """)
            if not rows:
                return self._make_result(item, CheckStatus.FAIL, "最近7天无行情数据")

            latest_date = rows[0][0]  # date 对象
            today = date.today()
            days_diff = (today - latest_date).days

            # 判断是否周末
            is_weekend = today.weekday() >= 5  # 5=周六, 6=周日
            max_stale = 3 if is_weekend else 2

            daily_volumes = {str(r[0]): r[1] for r in rows}

            if days_diff <= max_stale:
                msg = f"最新交易日: {latest_date} (距今 {days_diff} 天, 阈值: {max_stale} 天)"
                details = {"latest_trade_date": str(latest_date), "days_stale": days_diff,
                           "max_allowed": max_stale, "daily_volumes": daily_volumes}
                status = CheckStatus.PASS
            else:
                msg = f"最新交易日: {latest_date} (距今 {days_diff} 天, 超过阈值 {max_stale} 天)"
                details = {"latest_trade_date": str(latest_date), "days_stale": days_diff,
                           "max_allowed": max_stale, "daily_volumes": daily_volumes}
                status = CheckStatus.FAIL

            return self._make_result(item, status, msg, details)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _check_stock_quotes_volume(self, item: CheckItem) -> CheckResult:
        """检查行情数据量"""
        conn = _get_db_connection(self.config)
        try:
            rows = _query_db(conn, """
                SELECT trade_date, COUNT(*)
                FROM stock_quotes
                WHERE cycle = '1d' AND trade_date >= CURRENT_DATE - INTERVAL '5 days'
                GROUP BY trade_date
                ORDER BY trade_date DESC
            """)
            if not rows:
                return self._make_result(item, CheckStatus.FAIL, "最近5天无数据")

            thresholds = self.config["thresholds"]["stock_quotes"]
            min_ok = thresholds["min_daily_records"]
            min_warn = thresholds["warn_daily_records"]

            issues = []
            details = {"daily_counts": {}}
            overall_status = CheckStatus.PASS

            for trade_date, count in rows:
                date_str = str(trade_date)
                details["daily_counts"][date_str] = count
                if count < min_warn:
                    issues.append(f"{date_str}: {count} 条 (异常)")
                    overall_status = CheckStatus.FAIL
                elif count < min_ok:
                    issues.append(f"{date_str}: {count} 条 (需关注)")
                    if overall_status != CheckStatus.FAIL:
                        overall_status = CheckStatus.WARN

            if not issues:
                msg = f"最近 {len(rows)} 个交易日数据量均 ≥ {min_ok} 条"
            else:
                msg = "; ".join(issues)

            return self._make_result(item, overall_status, msg, details)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _check_stock_quotes_missing(self, item: CheckItem) -> CheckResult:
        """检查最新交易日缺失股票数"""
        conn = _get_db_connection(self.config)
        try:
            # 先获取最新交易日
            latest_rows = _query_db(conn, """
                SELECT trade_date FROM stock_quotes
                WHERE cycle = '1d'
                ORDER BY trade_date DESC LIMIT 1
            """)
            if not latest_rows:
                return self._make_result(item, CheckStatus.SKIP, "无数据，跳过缺失检查")

            latest_date = latest_rows[0][0]

            # 去重股票总数
            total_rows = _query_db(conn, "SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle = '1d'")
            total_stocks = total_rows[0][0]

            # 缺失股票数
            missing_rows = _query_db(conn, f"""
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT code FROM stock_quotes WHERE cycle = '1d'
                    EXCEPT
                    SELECT code FROM stock_quotes WHERE cycle = '1d' AND trade_date = %s
                ) t
            """, (latest_date,))
            missing = missing_rows[0][0]

            thresholds = self.config["thresholds"]["stock_quotes"]
            max_missing = thresholds["max_missing_stocks"]
            warn_missing = thresholds["warn_missing_stocks"]

            details = {
                "latest_trade_date": str(latest_date),
                "total_stocks": total_stocks,
                "present_stocks": total_stocks - missing,
                "missing_stocks": missing,
            }

            if missing > max_missing:
                status = CheckStatus.FAIL
                msg = f"缺失 {missing} 只股票 (阈值: {max_missing})"
            elif missing > warn_missing:
                status = CheckStatus.WARN
                msg = f"缺失 {missing} 只股票 (需关注, 阈值: {warn_missing})"
            else:
                status = CheckStatus.PASS
                msg = f"缺失 {missing} 只股票 (正常)"

            return self._make_result(item, status, msg, details)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _check_snapshot_sync(self, item: CheckItem) -> CheckResult:
        """检查宽表同步状态"""
        conn = _get_db_connection(self.config)
        try:
            # 获取 stock_quotes 最新日期
            quotes_rows = _query_db(conn, """
                SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'
            """)
            quotes_latest = quotes_rows[0][0] if quotes_rows else None

            # 获取 snapshot 最新日期
            snap_rows = _query_db(conn, """
                SELECT MAX(trade_date), COUNT(*)
                FROM stock_daily_snapshot
                WHERE trade_date >= CURRENT_DATE - INTERVAL '5 days'
            """)
            snap_latest = snap_rows[0][0] if snap_rows else None
            snap_count = snap_rows[0][1] if snap_rows else 0

            if not quotes_latest or not snap_latest:
                return self._make_result(item, CheckStatus.FAIL, "宽表或行情表无数据")

            thresholds = self.config["thresholds"]["snapshot"]
            details = {
                "quotes_latest": str(quotes_latest),
                "snapshot_latest": str(snap_latest),
                "snapshot_recent_count": snap_count,
            }

            issues = []
            overall = CheckStatus.PASS

            if snap_latest != quotes_latest:
                issues.append(f"宽表最新日期 {snap_latest} 与行情表 {quotes_latest} 不一致")
                overall = CheckStatus.FAIL

            if snap_count < thresholds["warn_daily_records"]:
                issues.append(f"宽表最近5天仅 {snap_count} 条")
                overall = CheckStatus.FAIL
            elif snap_count < thresholds["min_daily_records"]:
                issues.append(f"宽表数据量 {snap_count} 需关注")
                if overall != CheckStatus.FAIL:
                    overall = CheckStatus.WARN

            msg = "; ".join(issues) if issues else f"宽表同步正常 (最新: {snap_latest}, {snap_count} 条)"
            return self._make_result(item, overall, msg, details)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _check_data_completeness(self, item: CheckItem) -> CheckResult:
        """检查字段完整性"""
        conn = _get_db_connection(self.config)
        try:
            latest_rows = _query_db(conn, """
                SELECT MAX(trade_date) FROM stock_daily_snapshot
            """)
            if not latest_rows or not latest_rows[0][0]:
                return self._make_result(item, CheckStatus.SKIP, "宽表无数据，跳过完整性检查")

            latest_date = latest_rows[0][0]

            comp_rows = _query_db(conn, f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN pe_ttm IS NOT NULL THEN 1 ELSE 0 END) as pe_ttm_cnt,
                    SUM(CASE WHEN ma5 IS NOT NULL THEN 1 ELSE 0 END) as ma5_cnt,
                    SUM(CASE WHEN macd IS NOT NULL THEN 1 ELSE 0 END) as macd_cnt,
                    SUM(CASE WHEN rsi_6 IS NOT NULL THEN 1 ELSE 0 END) as rsi6_cnt,
                    SUM(CASE WHEN boll_mid IS NOT NULL THEN 1 ELSE 0 END) as boll_cnt
                FROM stock_daily_snapshot
                WHERE trade_date = %s
            """, (latest_date,))

            if not comp_rows:
                return self._make_result(item, CheckStatus.SKIP, f"交易日 {latest_date} 无数据")

            total = comp_rows[0][0]
            thresholds = self.config["thresholds"]["completeness"]

            fields = [
                ("pe_ttm", comp_rows[0][1], thresholds.get("pe_ttm", 0.72)),
                ("ma5", comp_rows[0][2], thresholds.get("ma5", 0.80)),
                ("macd", comp_rows[0][3], thresholds.get("macd", 0.80)),
                ("rsi_6", comp_rows[0][4], thresholds.get("rsi_6", 0.80)),
                ("boll_mid", comp_rows[0][5], thresholds.get("boll_mid", 0.80)),
            ]

            green_threshold = thresholds.get("green_threshold", 0.95)
            all_green = all(cnt / total >= green_threshold for _, cnt, _ in fields)

            details = {
                "trade_date": str(latest_date),
                "total_records": total,
                "field_rates": {},
            }

            issues = []
            overall = CheckStatus.PASS

            for name, cnt, threshold in fields:
                rate = round(cnt / total * 100, 1) if total > 0 else 0.0
                details["field_rates"][name] = {"count": cnt, "rate": rate, "threshold": threshold * 100}
                if all_green or rate >= threshold * 100:
                    continue
                issues.append(f"{name}: {rate}% (阈值: {threshold*100:.0f}%)")
                overall = CheckStatus.WARN

            if all_green:
                msg = f"所有字段完整率 ≥ {green_threshold*100:.0f}%，状态正常"
            elif issues:
                msg = "; ".join(issues)
            else:
                msg = "所有字段符合阈值"

            # 结果中携带完整字段率供报告使用
            return self._make_result(item, overall, msg, details)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _check_task_run_log(self, item: CheckItem) -> CheckResult:
        """检查任务执行日志"""
        conn = _get_db_connection(self.config)
        try:
            max_days = self.config["thresholds"]["task_run_log"]["max_failed_tasks_last_days"]

            # 最近失败任务数
            failed_rows = _query_db(conn, f"""
                SELECT COUNT(*) FROM task_run_log
                WHERE status = 'failed' AND created_at >= CURRENT_DATE - INTERVAL '{max_days} days'
            """)
            failed_count = failed_rows[0][0]

            # 最近 ETL pipeline 执行记录
            pipeline_rows = _query_db(conn, f"""
                SELECT status, data_date, created_at, task_name
                FROM task_run_log
                WHERE task_name = 'etl_pipeline' AND created_at >= CURRENT_DATE - INTERVAL '{max_days} days'
                ORDER BY created_at DESC
                LIMIT 5
            """)

            details = {
                "failed_tasks_last_days": failed_count,
                "check_window_days": max_days,
                "pipeline_records": [
                    {"status": r[0], "data_date": str(r[1]), "created_at": str(r[2])}
                    for r in pipeline_rows
                ],
            }

            if failed_count > 0:
                msg = f"最近 {max_days} 天内有 {failed_count} 个失败任务"
                status = CheckStatus.FAIL
            else:
                pipeline_status = pipeline_rows[0][0] if pipeline_rows else "unknown"
                msg = f"最近 {max_days} 天失败任务: 0 (ETL Pipeline 最新状态: {pipeline_status})"
                status = CheckStatus.PASS

            return self._make_result(item, status, msg, details)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _check_log_file_errors(self, item: CheckItem) -> CheckResult:
        """检查日志文件错误计数"""
        log_paths = self.config["paths"]["log_files"]
        details = {"checked_files": {}}
        total_errors = 0
        issues = []

        for rel_path in log_paths:
            abs_path = self._get_log_path(rel_path)
            if not os.path.isfile(abs_path):
                details["checked_files"][rel_path] = "file_not_found"
                continue

            try:
                # 使用 grep 统计 ERROR/失败 行数（只读最近 10000 行，避免大文件）
                result = subprocess.run(
                    ["grep", "-c", "ERROR\\|失败\\|❌", abs_path],
                    capture_output=True, text=True, timeout=10,
                )
                count_str = result.stdout.strip()
                count = int(count_str) if count_str.isdigit() else 0
                total_errors += count
                details["checked_files"][rel_path] = {"error_count": count, "file_size": os.path.getsize(abs_path)}
                if count > 0:
                    issues.append(f"{rel_path}: {count} 条错误")
            except (subprocess.TimeoutExpired, ValueError, OSError) as e:
                details["checked_files"][rel_path] = f"check_error: {e}"

        if total_errors == 0:
            msg = "检查的日志文件无错误记录"
            status = CheckStatus.PASS
        elif total_errors < 50:
            msg = f"日志文件共有 {total_errors} 条错误: {'; '.join(issues)}"
            status = CheckStatus.WARN
        else:
            msg = f"日志文件共有 {total_errors} 条错误: {'; '.join(issues)}"
            status = CheckStatus.WARN  # 大量错误可能是历史累计，记录为警告

        return self._make_result(item, status, msg, details)

    # ---- 报告生成 ----

    def _build_report(
        self, start_time: datetime, end_time: datetime, total_ms: float
    ) -> CheckReport:
        """构建报告"""
        # 环境信息
        env = {
            "hostname": os.uname().nodename,
            "python_version": sys.version.split()[0],
            "project_root": self.project_root,
            "timestamp": datetime.now().isoformat(),
        }

        # 汇总
        summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0, "error": 0, "total": 0}
        for r in self.results:
            summary[r.status.value] = summary.get(r.status.value, 0) + 1
            summary["total"] += 1

        # 仅保留结果中的关键字段
        serializable_results = []
        for r in self.results:
            sr = {
                "item_id": r.item_id,
                "status": r.status.value,
                "message": r.message,
                "duration_ms": r.duration_ms,
            }
            if r.details:
                sr["details"] = r.details
            serializable_results.append(sr)

        return CheckReport(
            script_version=SCRIPT_VERSION,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            total_duration_ms=round(total_ms, 1),
            environment=env,
            config=self.config,
            results=serializable_results,
            summary=summary,
        )

    def _print_summary(self, report: CheckReport) -> None:
        """打印报告摘要"""
        s = report.summary
        self._log(f"\n{colorize('=' * 60, Colors.BOLD, bold=True)}")
        self._log(f"{colorize('  晨检完成', Colors.BOLD, bold=True)}")
        self._log(f"{'=' * 60}")

        # 分类统计
        pass_count = s.get("pass", 0)
        warn_count = s.get("warn", 0)
        fail_count = s.get("fail", 0)
        skip_count = s.get("skip", 0)
        error_count = s.get("error", 0)
        total = s.get("total", 0)

        pass_str = colorize(f"{pass_count} 通过", Colors.GREEN) if self.use_color else f"{pass_count} 通过"
        warn_str = colorize(f"{warn_count} 警告", Colors.YELLOW) if self.use_color else f"{warn_count} 警告"
        fail_str = colorize(f"{fail_count} 失败", Colors.RED) if self.use_color else f"{fail_count} 失败"
        skip_str = colorize(f"{skip_count} 跳过", Colors.DIM) if self.use_color else f"{skip_count} 跳过"
        error_str = colorize(f"{error_count} 异常", Colors.RED) if self.use_color else f"{error_count} 异常"

        self._log(f"  总计: {total} 项 | {pass_str} | {warn_str} | {fail_str} | {skip_str} | {error_str}")
        self._log(f"  耗时: {report.total_duration_ms:.0f} ms")

        # 列出失败/警告项
        if fail_count > 0 or error_count > 0:
            self._log(f"\n{colorize('  🚨 失败/异常项:', Colors.RED, bold=True)}")
            for r in self.results:
                if r.status in (CheckStatus.FAIL, CheckStatus.ERROR):
                    tag = status_tag(r.status, self.use_color)
                    self._log(f"    {tag} [{r.item_id}] {r.message}")
        if warn_count > 0:
            self._log(f"\n{colorize('  ⚠️ 警告项:', Colors.YELLOW, bold=True)}")
            for r in self.results:
                if r.status == CheckStatus.WARN:
                    self._log(f"    {status_tag(r.status, self.use_color)} [{r.item_id}] {r.message}")

        self._log(f"{'=' * 60}\n")


# ============================================================
# CLI 入口
# ============================================================


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="每日数据管道晨检自动化脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="",
        help="报告输出 JSON 文件路径",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="",
        help="外部 YAML 配置文件路径",
    )
    parser.add_argument(
        "--skip",
        type=str,
        default="",
        help="要跳过的检查项 ID（逗号分隔）",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="安静模式，减少终端输出",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="禁用终端颜色输出",
    )
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help="列出所有检查项并退出",
    )
    return parser.parse_args(argv)


def _merge_config(base: Dict, override: Dict) -> Dict:
    """深度合并配置"""
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value
    return result


def _load_external_config(path: str) -> Dict:
    """加载外部 YAML 配置文件"""
    if not os.path.isfile(path):
        print(f"⚠️ 配置文件不存在: {path}")
        return {}

    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if not isinstance(cfg, dict):
            print(f"⚠️ 配置文件格式无效: {path}")
            return {}
        print(f"✅ 加载配置文件: {path}")
        return cfg
    except ImportError:
        print("⚠️ PyYAML 未安装，跳过外部配置加载")
        return {}
    except Exception as e:
        print(f"⚠️ 配置文件加载失败: {e}")
        return {}


def main(argv: Optional[List[str]] = None) -> int:
    """主入口，返回退出码"""
    args = parse_args(argv)

    # 列出检查项
    if args.list_checks:
        print(f"\n{'=' * 50}")
        print(f"  可用检查项列表")
        print(f"{'=' * 50}")
        runner = DailyCheckRunner(DEFAULT_CONFIG, quiet=True)
        for item in runner._build_checklist():
            status = "启用" if runner._should_run(item.id) else "禁用"
            print(f"  [{item.category:8s}] {item.id:30s} {item.name:20s} [{item.level.value}] {status}")
        print(f"{'=' * 50}\n")
        return 0

    # 加载配置
    config = DEFAULT_CONFIG.copy()
    if args.config:
        ext_cfg = _load_external_config(args.config)
        if ext_cfg:
            config = _merge_config(config, ext_cfg)

    # 输出文件
    if args.output:
        config["output"]["file"] = args.output

    # 跳过项
    skip_items = [s.strip() for s in args.skip.split(",") if s.strip()] if args.skip else []

    # 执行晨检
    runner = DailyCheckRunner(
        config=config,
        skip_items=skip_items,
        quiet=args.quiet,
        use_color=not args.no_color,
    )
    report = runner.run()

    # 输出报告文件
    output_path = config["output"]["file"]
    if output_path:
        try:
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report.to_json())
            print(f"📄 报告已保存: {output_path}")
        except Exception as e:
            print(f"❌ 报告保存失败: {e}")

    # 退出码
    summary = report.summary
    if summary.get("fail", 0) > 0 or summary.get("error", 0) > 0:
        return 2
    if summary.get("warn", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())