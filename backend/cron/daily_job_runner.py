#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化交易 - 每日盘后线性任务调度脚本（v2）
任务顺序：1.健康检查 → 2.股票列表 → 3.行情导入 → 4.复权因子 → 5.基本面
         → 6.指标计算 → 7.信号 → 8.宽表 → 9.Parquet

v2 改进：
  - 文件锁防并发：同一时间只允许一个 runner 实例运行
  - batch_id 机制：基于 task_run_log 表做断点续跑，替代 log 文件解析
  - 每次调度生成唯一 batch_id，所有任务记录共享同一 batch_id
"""
import os
import sys
import fcntl
import time
import json
import uuid
import subprocess
from datetime import datetime, date
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# ===================== 数据库连接 =====================
load_dotenv()

def _get_db_engine():
    """构建 SQLAlchemy Engine（用于写入 task_run_log）"""
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}"
        f"@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DATABASE')}"
    )


# ===================== 配置项 =====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PYTHON = os.path.join(BASE_DIR, "venv", "bin", "python")
LOG_DIR = os.path.join(BASE_DIR, "logs", "cron")
LOCK_FILE = os.path.join(LOG_DIR, ".daily_job_runner.lock")  # 文件锁路径

RETRY_INTERVAL_SEC = 15 * 60   # 重试间隔：15分钟
MAX_RETRIES = 10               # 最大重试次数

# 任务列表【严格按执行顺序填写】
TASKS = [
    {"name": "pipeline_health_check",
     "script": os.path.join("backend", "collector", "etl", "pipeline_health_check.py"),
     "args": ["--pre-import"]},
    {"name": "stock_list_sync",
     "script": os.path.join("backend", "collector", "etl", "sync_stock_list_baostock.py"),
     "args": []},
    {"name": "daily_import",
     "script": os.path.join("backend", "collector", "etl", "import_daily_data.py"),
     "args": []},
    {"name": "adj_factor_sync",
     "script": os.path.join("backend", "collector", "etl", "sync_adj_factor.py"),
     "args": ["--incremental"]},
    {"name": "daily_basic_sync",
     "script": os.path.join("backend", "collector", "etl", "sync_daily_basic.py"),
     "args": ["--latest"]},
    # {"name": "fill_missing_data",
    #  "script": os.path.join("backend", "collector", "etl", "fill_missing_data.py"),
    #  "args": []},
    {"name": "indicators_compute",
     "script": os.path.join("backend", "clean", "etl", "compute_indicators_daily.py"),
     "args": []},
    {"name": "signal_precompute",
     "script": os.path.join("backend", "clean", "etl", "signal_precompute.py"),
     "args": []},
    {"name": "daily_sync",
     "script": os.path.join("backend", "collector", "etl", "daily_snapshot_sync.py"),
     "args": ["--latest"]},
    {"name": "parquet_export",
     "script": os.path.join("backend", "clean", "enrich", "export_parquet.py"),
     "args": []},
]

TASK_DISPLAY_NAMES = {
    "pipeline_health_check": "健康检查",
    "stock_list_sync": "股票列表同步",
    "daily_import": "日线数据下载",
    "adj_factor_sync": "复权因子同步",
    "daily_basic_sync": "基本面数据同步",
    "fill_missing_data": "缺失数据补全",
    "indicators_compute": "技术指标计算",
    "signal_precompute": "生成交易信号",
    "daily_sync": "宽表同步",
    "parquet_export": "导出 Parquet",
    "restart_backend": "重启后端服务",
}


# ===================== 工具函数 =====================

def _parse_task_result(stdout_text: str) -> tuple:
    """从子脚本 stdout 中解析 TASK_RESULT: 行，返回 (rows_affected, extra_metrics)"""
    rows_affected = None
    extra_metrics = None
    for line in reversed(stdout_text.splitlines()):
        if line.startswith("TASK_RESULT:"):
            try:
                payload = json.loads(line[len("TASK_RESULT:"):])
                rows_affected = payload.get("rows_affected")
                extra_metrics = payload.get("extra_metrics")
            except json.JSONDecodeError:
                pass
            break
    return rows_affected, extra_metrics


def get_latest_trade_date(engine) -> str:
    """从数据库查询最近一个交易日，用于填充 data_date"""
    queries = [
        "SELECT MAX(cal_date) FROM trade_calendar WHERE is_open = 1 AND cal_date <= CURRENT_DATE",
        "SELECT MAX(trade_date) FROM stock_quotes",
    ]
    with engine.connect() as conn:
        for q in queries:
            try:
                r = conn.execute(text(q)).scalar()
                if r is not None:
                    return str(r)[:10]
            except Exception:
                continue
    return datetime.now().strftime("%Y-%m-%d")


def generate_batch_id() -> str:
    """生成唯一批次 ID：日期 + 短 UUID 前8位"""
    return f"{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


# ===================== 文件锁（根因 B 修复） =====================

class FileLock:
    """基于 fcntl 的排他文件锁，确保同一时间只有一个 runner 实例"""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self.lock_fd = None

    def acquire(self) -> bool:
        """尝试获取锁，成功返回 True，失败返回 False（已有实例在跑）"""
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        self.lock_fd = open(self.lock_path, "w")
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # 写入当前 PID 和启动时间，方便排查
            self.lock_fd.write(f"{os.getpid()}|{datetime.now().isoformat()}\n")
            self.lock_fd.flush()
            return True
        except (IOError, OSError):
            # 锁被占用，读取持有者信息
            try:
                info = open(self.lock_path).read().strip()
                print(f"[WARN] 另一个 runner 实例正在运行 ({info})，本次退出")
            except Exception:
                print("[WARN] 另一个 runner 实例正在运行，本次退出")
            self.lock_fd.close()
            self.lock_fd = None
            return False

    def release(self):
        """释放锁"""
        if self.lock_fd:
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                self.lock_fd.close()
            except Exception:
                pass
            finally:
                self.lock_fd = None


# ===================== TaskLogger（含 batch_id） =====================

class TaskLogger:
    """将任务执行结果写入 task_run_log 表，每批任务共享同一 batch_id"""

    def __init__(self):
        self.engine = _get_db_engine()
        self.data_date = get_latest_trade_date(self.engine)
        self.batch_id = generate_batch_id()

    def log_start(self, task_name: str, stage: int) -> int:
        """记录任务开始，返回 log_id"""
        insert_sql = text("""
            INSERT INTO task_run_log (task_name, stage, start_time, status, data_date, batch_id)
            VALUES (:task_name, :stage, :start_time, 'running', :data_date, :batch_id)
            RETURNING id
        """)
        try:
            with self.engine.connect() as conn:
                r = conn.execute(insert_sql, {
                    "task_name": task_name,
                    "stage": stage,
                    "start_time": datetime.now(),
                    "data_date": self.data_date,
                    "batch_id": self.batch_id,
                })
                conn.commit()
                return r.scalar()
        except OperationalError as e:
            print(f"  [WARN] task_run_log 写入失败: {e}")
            return -1

    def log_end(self, log_id: int, task_name: str, stage: int,
                success: bool, exit_code: int, error_message: str,
                rows_affected: int = None, extra_metrics: dict = None):
        """更新任务结束状态"""
        if log_id < 0:
            return
        update_sql = text("""
            UPDATE task_run_log SET
                end_time = :end_time, status = :status, exit_code = :exit_code,
                error_message = :error_message, rows_affected = :rows_affected,
                extra_metrics = :extra_metrics
            WHERE id = :id
        """)
        try:
            with self.engine.connect() as conn:
                conn.execute(update_sql, {
                    "id": log_id, "end_time": datetime.now(),
                    "status": "success" if success else "failed",
                    "exit_code": exit_code, "error_message": error_message or None,
                    "rows_affected": rows_affected,
                    "extra_metrics": json.dumps(extra_metrics) if extra_metrics else None,
                })
                conn.commit()
        except OperationalError as e:
            print(f"  [WARN] task_run_log 更新失败: {e}")


# ===================== 断点续跑（根因 C 修复：基于数据库 batch_id） =====================

def get_last_batch_status(engine, data_date: str) -> tuple:
    """
    查询指定 data_date 的最新 batch 执行状态。
    返回 (batch_id, completed_tasks, total_tasks, has_failure_or_running)

    规则：
      - 最新 batch 全部 success → 返回 ("completed", ...)，无需再跑
      - 最新 batch 有 failed/running 任务 → 返回 (batch_id, ...)，可续跑
      - 无任何记录 → 返回 (None, ...)，需全量执行
    """
    sql = text("""
        WITH latest_batch AS (
            SELECT DISTINCT ON (task_name)
                id, task_name, status, batch_id
            FROM task_run_log
            WHERE data_date = :data_date
            ORDER BY task_name, id DESC
        )
        SELECT
            (SELECT batch_id FROM latest_batch LIMIT 1) AS batch_id,
            COUNT(*) FILTER (WHERE status = 'success') AS success_count,
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE status IN ('failed', 'running')) AS bad_count
        FROM latest_batch
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"data_date": data_date}).fetchone()
        if row is None or row[0] is None:
            return None, 0, len(TASKS), False
        batch_id = row[0]
        success_cnt = row[1]
        total_cnt = row[2]
        bad_cnt = row[3]

        if success_cnt == len(TASKS) and bad_cnt == 0:
            # 全部完成
            return "COMPLETED", success_cnt, total_cnt, False
        else:
            return batch_id, success_cnt, total_cnt, bad_cnt > 0


def get_task_db_status(engine, data_date: str, task_name: str,
                        current_batch_id: str = None) -> str:
    """
    查询某任务在指定 data_date 的最新状态。
    返回 'success' / 'failed' / 'running' / 'pending'

    关键修复：排除当前 batch_id 自身的 running 记录（那是 runner 自己刚写入的），
              只关注其他批次或历史记录的状态，避免误判为"正在运行"而跳过。
    """
    if current_batch_id:
        sql = text("""
            SELECT status FROM task_run_log
            WHERE data_date = :data_date
              AND task_name = :task_name
              AND (batch_id IS NULL OR batch_id != :batch_id)
            ORDER BY id DESC LIMIT 1
        """)
        params = {"data_date": data_date, "task_name": task_name,
                  "batch_id": current_batch_id}
    else:
        sql = text("""
            SELECT status FROM task_run_log
            WHERE data_date = :data_date AND task_name = :task_name
            ORDER BY id DESC LIMIT 1
        """)
        params = {"data_date": data_date, "task_name": task_name}

    with engine.connect() as conn:
        r = conn.execute(sql, params).scalar()
        return r if r else "pending"


# ===================== 任务执行 =====================

def run_task(task, task_logger: TaskLogger, stage: int) -> bool:
    """执行单个任务，返回是否成功"""
    task_name = task["name"]
    script_path = os.path.join(BASE_DIR, task["script"])
    log_path = os.path.join(LOG_DIR, f"{task_name}.log")
    cmd = [PYTHON, script_path] + task["args"]

    log_id = task_logger.log_start(task_name, stage)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] 开始执行任务: {task_name}")

    rows_affected = None
    extra_metrics = None

    try:
        proc = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True,
                              encoding="utf-8", check=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {now} 开始执行 {task_name} =====\n")
            if proc.stdout:
                f.write(proc.stdout)
            if proc.stderr:
                f.write("\n--- STDERR ---\n" + proc.stderr)
            elapsed = (datetime.now() - datetime.strptime(now, "%Y-%m-%d %H:%M:%S")).total_seconds()
            f.write(f"===== {task_name} SUCCESS | 耗时 {elapsed:.1f}s =====\n")

        rows_affected, extra_metrics = _parse_task_result(proc.stdout or "")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_name} 执行成功"
              + (f" | 影响行数: {rows_affected}" if rows_affected else ""))

        task_logger.log_end(log_id, task_name, stage, True, 0, None,
                            rows_affected=rows_affected, extra_metrics=extra_metrics)
        return True

    except subprocess.CalledProcessError as e:
        err_msg = f"Exit code: {e.returncode}"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_name} 执行失败，错误码: {e.returncode}")
        if e.stdout:
            rows_affected, extra_metrics = _parse_task_result(e.stdout)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {now} 开始执行 {task_name} =====\n")
            if e.stdout:
                f.write(e.stdout)
            if e.stderr:
                f.write("\n--- STDERR ---\n" + e.stderr)
            f.write(f"===== {task_name} FAILED ({err_msg}) =====\n")
        task_logger.log_end(log_id, task_name, stage, False, e.returncode, err_msg,
                            rows_affected=rows_affected, extra_metrics=extra_metrics)
        return False
    except Exception as e:
        err_msg = str(e)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_name} 异常: {err_msg}")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"===== {task_name} EXCEPTION: {err_msg} =====\n")
        task_logger.log_end(log_id, task_name, stage, False, -1, err_msg)
        return False


def run_task_chain(task_logger: TaskLogger, engine) -> tuple:
    """
    执行一次任务链（基于数据库 batch_id 断点续跑）
    返回 (全部成功?, 失败任务名)
    """
    data_date = task_logger.data_date
    batch_id = task_logger.batch_id
    completed = 0
    failed_task = None

    print(f"\n[INFO] batch_id={batch_id} | data_date={data_date}")

    for i, task in enumerate(TASKS, 1):
        task_name = task["name"]

        # 基于数据库状态判断是否跳过（排除当前 batch 自身记录）
        db_status = get_task_db_status(engine, data_date, task_name,
                                        current_batch_id=batch_id)

        if db_status == "success":
            # 该任务今天已成功过 — 但仍写入新 batch 的记录（保持完整性）
            print(f"  [{i}/{len(TASKS)}] ⏭ {task_name} — 今日已成功（复用旧记录），跳过执行")
            completed += 1
            continue

        if db_status == "running":
            # 检测是否为僵尸进程：查看对应日志文件最近修改时间
            log_path = os.path.join(LOG_DIR, f"{task_name}.log")
            is_zombie = False
            if os.path.exists(log_path):
                try:
                    mtime = os.path.getmtime(log_path)
                    idle_sec = time.time() - mtime
                    if idle_sec > 300:  # 5 分钟无更新 → 判定为僵尸
                        is_zombie = True
                except Exception:
                    pass

            if is_zombie:
                # 僵尸进程：自动清理旧记录，继续执行
                print(f"  [{i}/{len(TASKS)}] 💀 {task_name} — 检测到僵尸进程（日志 {int(idle_sec)}s 未更新），自动清理并重新执行")
                with engine.connect() as conn:
                    conn.execute(text("""
                        UPDATE task_run_log SET status='failed',
                            error_message='僵尸进程自动清理（日志长时间未更新）',
                            end_time=NOW()
                        WHERE data_date=:d AND task_name=:t AND status='running'
                          AND (batch_id IS NULL OR batch_id != :b)
                    """), {"d": data_date, "t": task_name, "b": batch_id})
                    conn.commit()
            else:
                print(f"  [{i}/{len(TASKS)}] ⏳ {task_name} — 正在运行中，跳过")
                failed_task = task_name
                break

        # 需要执行的任务
        print(f"\n--- [{i}/{len(TASKS)}] ---")
        success = run_task(task, task_logger, stage=i)
        if success:
            completed += 1
        else:
            failed_task = task_name
            print(f"\n!!! 任务链中断：{failed_task} 失败，停止后续任务 !!!")
            break

    all_success = (failed_task is None and completed == len(TASKS))
    return all_success, failed_task


# ===================== 主函数 =====================

def main():
    """主函数：文件锁 + batch_id 断点续跑 + 自动重试"""

    # ---- 根因 B：文件锁，防止多实例并发 ----
    file_lock = FileLock(LOCK_FILE)
    if not file_lock.acquire():
        sys.exit(1)

    os.makedirs(LOG_DIR, exist_ok=True)

    try:
        # 初始化
        engine = _get_db_engine()
        task_logger = TaskLogger()

        start_time = datetime.now()
        print("=" * 60)
        print(f"【每日盘后线性任务 v2】开始 | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Python: {PYTHON}")
        print(f"任务数: {len(TASKS)} | batch_id: {task_logger.batch_id}")
        print(f"data_date: {task_logger.data_date}")
        print(f"重试间隔: {RETRY_INTERVAL_SEC // 60}分钟 | 最大重试: {MAX_RETRIES}次")
        print("=" * 60)

        # ---- 根因 C：检查今日是否已完成 ----
        last_batch_id, succ, total, has_bad = get_last_batch_status(
            engine, task_logger.data_date
        )

        if last_batch_id == "COMPLETED":
            print(f"\n[INFO] 今日({task_logger.data_date})全部任务已在 batch 中完成，无需重复执行")
            sys.exit(0)

        if last_batch_id and last_batch_id != "COMPLETED":
            print(f"\n[INFO] 发现未完成的旧 batch={last_batch_id}"
                  f" (成功{succ}/{total}, {'有失败/运行中' if has_bad else ''})"
                  f" → 将创建新 batch={task_logger.batch_id} 续跑")

        # ---- 主循环：断点续跑 + 重试 ----
        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                print(f"\n{'=' * 60}")
                print(f"【第 {attempt}/{MAX_RETRIES} 次重试】| {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'=' * 60}")

            all_success, failed_task = run_task_chain(task_logger, engine)

            if all_success:
                elapsed = (datetime.now() - start_time).total_seconds()
                print("\n" + "=" * 60)
                print(f"【全部完成】{len(TASKS)}/{len(TASKS)} 任务成功"
                      f" | 耗时 {elapsed:.1f}s"
                      f" | batch_id: {task_logger.batch_id}"
                      f" | 第{attempt}轮")
                print("=" * 60)
                sys.exit(0)

            # 未全部成功，判断是否需要重试
            if attempt < MAX_RETRIES:
                next_time = datetime.now() + __import__('datetime').timedelta(
                    seconds=RETRY_INTERVAL_SEC)
                print(f"\n⏸ 等待 {RETRY_INTERVAL_SEC // 60} 分钟后重试..."
                      f" | 下次: {next_time.strftime('%H:%M')}"
                      f" | 已用: {attempt}/{MAX_RETRIES}")
                time.sleep(RETRY_INTERVAL_SEC)

        # 达到最大重试次数仍未完成
        elapsed = (datetime.now() - start_time).total_seconds()
        print("\n" + "=" * 60)
        print(f"【达到最大重试次数】{MAX_RETRIES}次后仍未全部成功"
              f" | 在 [{failed_task}] 中断"
              f" | 总耗时 {elapsed:.1f}s"
              f" | batch_id: {task_logger.batch_id}")
        print("=" * 60)
        sys.exit(1)

    finally:
        # 无论正常退出还是异常，都释放文件锁
        file_lock.release()


if __name__ == "__main__":
    main()
