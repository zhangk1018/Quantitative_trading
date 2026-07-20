#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化交易 - 每日盘后线性任务调度脚本（v7）
任务顺序：1.健康检查 → 2.股票列表 → 3.行情导入 → 4.复权因子 → 5.缺失补全
→ 6.基本面 → 7.指标计算 → 8.形态识别 → 9.信号 → 10.宽表 → 11.Parquet

v7 核心改进：
- 数据源链升级：Akshare(前复权) → Baostock(前复权) → Tushare(不复权→自动转换) → pytdx(不复权→自动转换)
- 不复权数据源自动通过 stock_adj_factor 表转换为前复权后存储
"""
import os
import sys
import time
import json
import uuid
import subprocess
import argparse
import re
import traceback
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# ===================== 数据库连接 =====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))  # 显式加载

def _get_db_engine():
    """构建 SQLAlchemy Engine"""
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}"
        f"@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DATABASE')}",
        pool_pre_ping=True,
        pool_recycle=3600,
    )

# ===================== 配置项 =====================
LOG_DIR = os.path.join(BASE_DIR, "logs", "cron")
LOCK_FILE = os.path.join(LOG_DIR, ".daily_job_runner.lock")

PYTHON = sys.executable  # 跨平台兼容

MAX_RETRIES = 3               
RETRY_INTERVAL_SEC = 15 * 60  
TASK_TIMEOUT_SEC = 3600       # 1 小时
ZOMBIE_THRESHOLD_SEC = 7200   # 2 小时

# ===================== Stage 常量 =====================
STAGE_PRE_IMPORT = 1  # 阶段1：健康检查 + 股票列表同步
STAGE_IMPORT = 2      # 阶段2：数据下载 + 指标计算 + 导出
PIPELINE_STAGE = 0    # etl_pipeline 整体状态记录专用值，与子任务 stage 语义隔离

# ===================== 阶段定义 =====================
STAGE1_TASKS = [
    {"name": "pipeline_health_check", "script": os.path.join("backend", "collector", "etl", "pipeline_health_check.py"), "args": ["--pre-import"]},
    {"name": "stock_list_sync", "script": os.path.join("backend", "collector", "etl", "sync_stock_list_baostock.py"), "args": []},
]

STAGE2_TASKS = [
    {"name": "daily_import", "script": os.path.join("backend", "collector", "etl", "import_daily_data.py"), "args": ["--incremental"]},
    # 【修改】fill_missing_data 插入在这里
    {"name": "adj_factor_sync", "script": os.path.join("backend", "collector", "etl", "sync_adj_factor.py"), "args": ["--incremental"]},
    {"name": "daily_basic_sync", "script": os.path.join("backend", "collector", "etl", "sync_daily_basic.py"), "args": ["--latest"]},
    {"name": "indicators_compute", "script": os.path.join("backend", "clean", "etl", "compute_indicators_daily.py"), "args": []},
    {"name": "pattern_precompute", "script": os.path.join("backend", "clean", "etl", "pattern_precompute.py"), "args": []},
    {"name": "signal_precompute", "script": os.path.join("backend", "clean", "etl", "signal_precompute.py"), "args": []},
    {"name": "daily_sync", "script": os.path.join("backend", "collector", "etl", "daily_snapshot_sync.py"), "args": ["--latest"]},
    {"name": "parquet_export", "script": os.path.join("backend", "clean", "enrich", "export_parquet.py"), "args": []},
]

FILL_MISSING_TASK = {"name": "fill_missing_data", "script": os.path.join("backend", "collector", "etl", "fill_missing_data.py"), "args": []}

# ===================== 工具函数 =====================
_loggers = {}
def setup_task_logger(task_name: str) -> logging.Logger:
    """带缓存的 Logger，防止重复打印"""
    if task_name in _loggers:
        return _loggers[task_name]
        
    logger = logging.getLogger(f"task_{task_name}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    date_str = datetime.now().strftime("%Y%m%d")
    log_path = os.path.join(LOG_DIR, f"{task_name}_{date_str}.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    
    _loggers[task_name] = logger
    return logger

def _parse_task_result(stdout_text: str) -> tuple:
    """使用 ^ 锚点防止匹配错误日志中的 JSON"""
    rows_affected = None
    extra_metrics = None
    match = re.search(r'^TASK_RESULT:(\{.*\})', stdout_text, re.MULTILINE | re.DOTALL)
    if match:
        try:
            payload = json.loads(match.group(1))
            rows_affected = payload.get("rows_affected")
            extra_metrics = payload.get("extra_metrics")
        except json.JSONDecodeError:
            pass
    return rows_affected, extra_metrics

def get_latest_trade_date(engine) -> str:
    queries = [
        "SELECT MAX(cal_date) FROM trade_calendar WHERE is_open = 1 AND cal_date <= CURRENT_DATE",
        "SELECT MAX(trade_date) FROM stock_quotes",
    ]
    with engine.connect() as conn:
        for q in queries:
            try:
                r = conn.execute(text(q)).scalar()
                if r is not None: return str(r)[:10]
            except Exception: continue
    return datetime.now().strftime("%Y-%m-%d")

def generate_batch_id() -> str:
    return f"{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"

def is_retryable_error(exit_code: int, stderr: str) -> bool:
    if exit_code == 0: return True
    fatal_keywords = ["SyntaxError", "ImportError", "TableNotFound", "ProgrammingError", 
                      "AttributeError", "NameError", "TypeError", "KeyError", "ValueError"]
    for keyword in fatal_keywords:
        if keyword in stderr: return False
    return True

# ===================== 跨平台文件锁 =====================
class FileLock:
    """兼容 Windows (msvcrt) 和 Unix (fcntl)"""
    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self.lock_fd = None

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        self.lock_fd = open(self.lock_path, "w")
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                
            self.lock_fd.write(f"{os.getpid()}|{datetime.now().isoformat()}\n")
            self.lock_fd.flush()
            return True
        except (IOError, OSError):
            try:
                info = open(self.lock_path).read().strip()
                print(f"[WARN] 另一个 runner 实例正在运行 ({info})，本次退出")
            except Exception:
                print("[WARN] 另一个 runner 实例正在运行，本次退出")
            self.lock_fd.close()
            self.lock_fd = None
            return False

    def release(self):
        if self.lock_fd:
            try:
                if os.name == 'nt':
                    import msvcrt
                    self.lock_fd.seek(0)
                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                self.lock_fd.close()
            except Exception: pass
            finally: self.lock_fd = None

# ===================== TaskLogger =====================
class TaskLogger:
    def __init__(self, engine):
        self.engine = engine
        self.data_date = get_latest_trade_date(engine)
        self.batch_id = generate_batch_id()

    def log_start(self, task_name: str, stage: int) -> int:
        insert_sql = text("""
            INSERT INTO task_run_log (task_name, stage, start_time, status, data_date, batch_id)
            VALUES (:task_name, :stage, :start_time, 'running', :data_date, :batch_id) RETURNING id
        """)
        try:
            with self.engine.connect() as conn:
                r = conn.execute(insert_sql, {"task_name": task_name, "stage": stage,
                    "start_time": datetime.now(), "data_date": self.data_date, "batch_id": self.batch_id})
                conn.commit()
                return r.scalar()
        except OperationalError as e:
            print(f"  [WARN] task_run_log 写入失败: {e}")
            return -1

    def log_end(self, log_id: int, task_name: str, stage: int, success: bool, exit_code: int, 
                error_message: str, rows_affected: int = None, extra_metrics: dict = None):
        if log_id < 0: return
        update_sql = text("""
            UPDATE task_run_log SET end_time = :end_time, status = :status, exit_code = :exit_code,
            error_message = :error_message, rows_affected = :rows_affected, extra_metrics = :extra_metrics
            WHERE id = :id
        """)
        try:
            with self.engine.connect() as conn:
                conn.execute(update_sql, {"id": log_id, "end_time": datetime.now(),
                    "status": "success" if success else "failed", "exit_code": exit_code,
                    "error_message": error_message or None, "rows_affected": rows_affected,
                    "extra_metrics": json.dumps(extra_metrics) if extra_metrics else None})
                conn.commit()
        except OperationalError as e:
            print(f"  [WARN] task_run_log 更新失败: {e}")

# ===================== 状态查询与僵尸清理（增加 stage 过滤） =====================
def get_last_batch_status(engine, data_date: str, tasks: list, stage: int = None) -> tuple:
    """返回 (success_count, total, has_bad)"""
    task_names = [t["name"] for t in tasks]
    sql = text("""
        WITH latest_tasks AS (
            SELECT DISTINCT ON (task_name) task_name, status
            FROM task_run_log
            WHERE data_date = :data_date 
              AND task_name = ANY(:task_names)
              AND (stage = :stage OR :stage IS NULL)
            ORDER BY task_name, id DESC
        )
        SELECT 
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status = 'success') AS success_count,
            COUNT(*) FILTER (WHERE status IN ('failed', 'running')) AS bad_count
        FROM latest_tasks
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"data_date": data_date, "task_names": task_names, "stage": stage}).fetchone()
        if row is None or row[0] == 0:
            return 0, len(tasks), False
        total, success_cnt, bad_cnt = row
        return success_cnt, total, bad_cnt > 0

def get_task_db_status(engine, data_date: str, task_name: str, stage: int = None) -> str:
    sql = text("""
        SELECT status FROM task_run_log
        WHERE data_date = :data_date AND task_name = :task_name
          AND (stage = :stage OR :stage IS NULL)
        ORDER BY id DESC LIMIT 1
    """)
    with engine.connect() as conn:
        r = conn.execute(sql, {"data_date": data_date, "task_name": task_name, "stage": stage}).scalar()
        return r if r else "pending"

def is_zombie_task(engine, data_date: str, task_name: str, stage: int = None) -> bool:
    sql = text("""
        SELECT start_time FROM task_run_log
        WHERE data_date = :data_date AND task_name = :task_name 
          AND status = 'running'
          AND (stage = :stage OR :stage IS NULL)
        ORDER BY id DESC LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"data_date": data_date, "task_name": task_name, "stage": stage}).fetchone()
        if row is None: return False
        return (datetime.now() - row[0]).total_seconds() > ZOMBIE_THRESHOLD_SEC

def cleanup_zombie_task(engine, data_date: str, task_name: str, stage: int = None) -> bool:
    sql = text("""
        UPDATE task_run_log SET status = 'failed',
        error_message = :err_msg, end_time = NOW()
        WHERE data_date = :data_date AND task_name = :task_name 
          AND status = 'running'
          AND (stage = :stage OR :stage IS NULL)
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {
            "data_date": data_date, "task_name": task_name,
            "stage": stage,
            "err_msg": f"僵尸进程自动清理（超过 {ZOMBIE_THRESHOLD_SEC//60} 分钟无响应）"
        })
        conn.commit()
        return result.rowcount > 0

# ===================== 任务执行 =====================
def run_task(task, task_logger: TaskLogger, stage: int, engine) -> bool:
    task_name = task["name"]
    script_path = os.path.join(BASE_DIR, task["script"])
    cmd = [PYTHON, script_path] + task["args"]
    
    log_id = task_logger.log_start(task_name, stage)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] 开始执行任务: {task_name}")
    
    task_logger_instance = setup_task_logger(task_name)
    task_logger_instance.info(f"开始执行 {task_name} | CMD: {' '.join(cmd)}")
    
    try:
        proc = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, 
                              encoding="utf-8", timeout=TASK_TIMEOUT_SEC)
        
        if proc.stdout: task_logger_instance.info(proc.stdout)
        if proc.stderr: task_logger_instance.warning(proc.stderr)
        
        elapsed = (datetime.now() - datetime.strptime(now, "%Y-%m-%d %H:%M:%S")).total_seconds()
        task_logger_instance.info(f"完成 {task_name}，耗时 {elapsed:.1f}s，退出码 {proc.returncode}")
        
        rows_affected, extra_metrics = _parse_task_result(proc.stdout or "")
        
        if proc.returncode == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {task_name} 成功" + (f" | 行数: {rows_affected}" if rows_affected else ""))
            task_logger.log_end(log_id, task_name, stage, True, 0, None, rows_affected, extra_metrics)
            return True
        else:
            raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)

    except subprocess.TimeoutExpired:
        err_msg = f"任务超时 (超过 {TASK_TIMEOUT_SEC // 60} 分钟)"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏰ {task_name} {err_msg}")
        task_logger_instance.error(err_msg)
        task_logger.log_end(log_id, task_name, stage, False, -2, err_msg)
        return False
        
    except subprocess.CalledProcessError as e:
        err_msg = f"Exit code: {e.returncode}"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ {task_name} 失败，错误码: {e.returncode}")
        if e.stdout: task_logger_instance.error(e.stdout)
        if e.stderr: task_logger_instance.error(e.stderr)
            
        stderr = e.stderr or ""
        retryable = is_retryable_error(e.returncode, stderr)
        if not retryable:
            err_msg += " (不可重试错误，建议检查代码)"
            
        rows_affected, extra_metrics = _parse_task_result(e.stdout or "")
        task_logger.log_end(log_id, task_name, stage, False, e.returncode, err_msg, rows_affected, extra_metrics)
        return False
        
    except Exception as e:
        err_msg = str(e)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 💥 {task_name} 异常: {err_msg}")
        task_logger_instance.error(f"异常: {err_msg}", exc_info=True)
        task_logger.log_end(log_id, task_name, stage, False, -1, err_msg)
        return False

def run_task_chain(task_logger: TaskLogger, engine, tasks: list, stage: int) -> tuple:
    data_date = task_logger.data_date
    batch_id = task_logger.batch_id
    completed = 0
    failed_task = None
    
    print(f"\n[INFO] batch_id={batch_id} | data_date={data_date} | 任务数={len(tasks)} | stage={stage}")
    
    for i, task in enumerate(tasks, 1):
        task_name = task["name"]
        
        # 查询全局最新状态（按阶段过滤）
        db_status = get_task_db_status(engine, data_date, task_name, stage)
            
        if db_status == "success":
            print(f"  [{i}/{len(tasks)}] ⏭ {task_name} — 今日已成功，跳过")
            completed += 1
            continue
            
        if db_status == "running":
            # 文件锁保证单实例，任何 running 状态都是遗留状态 → 直接清理并继续执行
            print(f"  [{i}/{len(tasks)}] 💀 {task_name} — 检测到遗留 running 状态，自动清理并重新执行")
            cleanup_zombie_task(engine, data_date, task_name, stage)
            # 清理后重置状态为 pending，继续执行
            db_status = "pending"

        print(f"\n--- [{i}/{len(tasks)}] 执行 {task_name} ---")
        success = run_task(task, task_logger, stage=stage, engine=engine)
        if success:
            completed += 1
        else:
            failed_task = task_name
            print(f"\n!!! 任务链中断：{failed_task} 失败 !!!")
            break
            
    return (failed_task is None and completed == len(tasks)), failed_task

# ===================== 主函数 =====================
def main():
    parser = argparse.ArgumentParser(description='每日盘后线性任务调度器 v6')
    parser.add_argument('--stage', type=int, choices=[STAGE_PRE_IMPORT, STAGE_IMPORT], help='执行阶段: 1=步骤1-2, 2=步骤3-11')
    parser.add_argument('--fill-missing', action='store_true', help='在阶段2中执行缺失数据补全')
    parser.add_argument('--skip-adj-factor', action='store_true', help='跳过复权因子同步（使用 pytdx 前复权数据时不需要）')
    parser.add_argument('--dry-run', action='store_true', help='试运行模式：只打印计划执行的任务')
    args = parser.parse_args()

    if args.stage == STAGE_PRE_IMPORT:
        tasks = STAGE1_TASKS
        current_stage = STAGE_PRE_IMPORT
        stage_label = "阶段1 (15:30) | 健康检查 + 股票列表同步"
    elif args.stage == STAGE_IMPORT:
        tasks = list(STAGE2_TASKS)
        current_stage = STAGE_IMPORT
        # 动态注入 fill_missing_data 到 daily_import 之后
        if args.fill_missing:
            daily_import_idx = next((i for i, t in enumerate(tasks) if t["name"] == "daily_import"), None)
            if daily_import_idx is not None:
                tasks.insert(daily_import_idx + 1, FILL_MISSING_TASK)
        stage_label = "阶段2 (16:30) | 数据下载 + 指标计算 + 导出"
    else:
        tasks = STAGE1_TASKS + STAGE2_TASKS
        current_stage = None  # 全量模式，stage 过滤不生效（retry 循环中拆分 stage1→stage2 执行）
        stage_label = "全量 (全部任务)"

    # 跳过复权因子同步（pytdx 前复权数据不需要）
    if args.skip_adj_factor:
        tasks = [t for t in tasks if t["name"] != "adj_factor_sync"]
        if current_stage == STAGE_IMPORT or current_stage is None:
            print(f"⏭️  已跳过复权因子同步（--skip-adj-factor）")

    file_lock = FileLock(LOCK_FILE)
    if not file_lock.acquire():
        sys.exit(1)

    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        engine = _get_db_engine()
        task_logger = TaskLogger(engine)
        
        start_time = datetime.now()
        print("=" * 60)
        print(f"【每日盘后线性任务 v6】| {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"执行阶段: {stage_label}")
        print(f"Python: {PYTHON}")
        print(f"任务数: {len(tasks)} | batch_id: {task_logger.batch_id}")
        print(f"data_date: {task_logger.data_date}")
        print("=" * 60)

        # 启动时清理：文件锁保证单实例，清理当前阶段所有遗留 running 记录
        cleaned = 0
        for task in tasks:
            if get_task_db_status(engine, task_logger.data_date, task["name"], current_stage) == "running":
                cleanup_zombie_task(engine, task_logger.data_date, task["name"], current_stage)
                cleaned += 1
        if cleaned:
            print(f"[INFO] 启动时清理了 {cleaned} 个遗留 running 记录")
        else:
            print("[INFO] 无遗留 running 记录需清理")

        # Dry-run 模式
        if args.dry_run:
            print("\n🔍 [DRY-RUN] 试运行模式，以下任务将被执行：")
            for i, task in enumerate(tasks, 1):
                status = get_task_db_status(engine, task_logger.data_date, task["name"], current_stage)
                if status == "success":
                    icon = "⏭"
                elif status == "running":
                    icon = "⏳"  # 运行中
                else:
                    icon = "▶️"
                print(f"  [{i}/{len(tasks)}] {icon} {task['name']} (当前状态: {status})")
            sys.exit(0)

        # 检查是否该阶段全部任务已完成（忽略批次）
        success_cnt, total, has_bad = get_last_batch_status(engine, task_logger.data_date, tasks, current_stage)
        if success_cnt == total and not has_bad:
            print(f"\n[INFO] 今日({task_logger.data_date})该阶段全部任务已完成，无需重复执行")
            sys.exit(0)

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                print(f"\n{'=' * 60}\n【第 {attempt}/{MAX_RETRIES} 次重试】\n{'=' * 60}")
                
            if current_stage is not None:
                all_success, failed_task = run_task_chain(task_logger, engine, tasks, current_stage)
            else:
                # 全量模式：先执行阶段1，成功后执行阶段2，确保 stage 值正确写入 DB
                all_success, failed_task = run_task_chain(task_logger, engine, STAGE1_TASKS, STAGE_PRE_IMPORT)
                if all_success:
                    all_success, failed_task = run_task_chain(task_logger, engine, STAGE2_TASKS, STAGE_IMPORT)
            
            if all_success:
                elapsed = (datetime.now() - start_time).total_seconds()
                print("\n" + "=" * 60)
                print(f"【全部完成】{len(tasks)}/{len(tasks)} 任务成功 | 耗时 {elapsed:.1f}s | batch_id: {task_logger.batch_id}")
                print("=" * 60)
                # 记录整体流水线状态
                _pid = task_logger.log_start('etl_pipeline', PIPELINE_STAGE)
                task_logger.log_end(_pid, 'etl_pipeline', PIPELINE_STAGE, True, 0, None, None,
                                    {"elapsed_seconds": round(elapsed, 1), "total_tasks": len(tasks), "failed_task": None})
                sys.exit(0)
                
            if failed_task:
                sql = text("""
                    SELECT error_message FROM task_run_log
                    WHERE data_date = :data_date AND task_name = :task_name
                      AND (stage = :stage OR :stage IS NULL)
                    ORDER BY id DESC LIMIT 1
                """)
                with engine.connect() as conn:
                    row = conn.execute(sql, {"data_date": task_logger.data_date, "task_name": failed_task, "stage": current_stage}).fetchone()
                    if row and row[0] and "不可重试错误" in row[0]:
                        print(f"\n!!! 任务 {failed_task} 发生不可重试错误，终止重试 !!!")
                        elapsed = (datetime.now() - start_time).total_seconds()
                        _pid = task_logger.log_start('etl_pipeline', PIPELINE_STAGE)
                        task_logger.log_end(_pid, 'etl_pipeline', PIPELINE_STAGE, False, 1,
                                            f"不可重试错误: {failed_task}", None,
                                            {"elapsed_seconds": round(elapsed, 1), "total_tasks": len(tasks), "failed_task": failed_task})
                        sys.exit(1)

            if attempt < MAX_RETRIES:
                next_time = datetime.now() + timedelta(seconds=RETRY_INTERVAL_SEC)
                print(f"\n⏸ 等待 {RETRY_INTERVAL_SEC // 60} 分钟后重试... | 下次: {next_time.strftime('%H:%M:%S')}")
                time.sleep(RETRY_INTERVAL_SEC)

        elapsed = (datetime.now() - start_time).total_seconds()
        print("\n" + "=" * 60)
        print(f"【达到最大重试次数】{MAX_RETRIES}次后仍未全部成功 | 在 [{failed_task}] 中断")
        print("=" * 60)
        _pid = task_logger.log_start('etl_pipeline', PIPELINE_STAGE)
        task_logger.log_end(_pid, 'etl_pipeline', PIPELINE_STAGE, False, 1,
                            f"重试{MAX_RETRIES}次后未全部成功，在 [{failed_task}] 中断", None,
                            {"elapsed_seconds": round(elapsed, 1), "total_tasks": len(tasks), "failed_task": failed_task})
        sys.exit(1)

    finally:
        file_lock.release()

if __name__ == "__main__":
    main()