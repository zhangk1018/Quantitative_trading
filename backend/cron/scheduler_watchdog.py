#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scheduler_watchdog.py —— 定时任务「错过检测 + 自动补执行」守护器（协作单 60.0）

■ 根因（2026-10-27 事故，决定性证据来自 `log show` 系统日志）
  macOS launchd 的 `StartCalendarInterval` 是**一次性日历触发**：
    - 若触发时刻该服务未被加载（登录域重建 / plist 重载 / 休眠未按时唤醒），
      该次触发被**永久跳过**，launchd 不会补跑；
    - 若系统休眠错过触发点，唤醒后已过点的 slot 不再补跑。
  `daily_job_runner.py` 只在「被 launchd 启动之后」做断点续跑（task_run_log 台账）
  与 3×15min 进程内重试，**没有任何自我唤醒能力** → 错过即数据断档。
  实证：2026-10-27 14:59:06 与 15:02:40 launchd 两次
  `removing service: com.quant.daily-job-runner.stage1`；15:38:10 重新 Bootstrap 后
  15:30 的 StartCalendarInterval 只能排到「下周二 15:30」，当日 stage1 永久丢失
  （logs/cron/daily_stage1.stdout.log 停在前一交易日）。

■ 本守护器职责
  由 launchd 以 `StartInterval`（默认每 30 分钟）+ `RunAtLoad`（登录/加载即跑）常驻周期调用：
    1. 错过检测：对照「调度时刻表」判定「已过点且当日仍无成功记录」的槽位；
    2. 自动补执行：调用**既有 runner**（daily_job_runner / hk_job_runner / us_job_runner），
       业务逻辑零改动——复用其台账断点续跑、任务级幂等与失败重试；
    3. 状态持久化：scheduler_slot_log 记录检测/尝试/结果（幂等去重）；
    4. 失败重试上限：每槽位每日最多 MAX_ATTEMPTS 次，超出转 exhausted 并 CRITICAL 告警；
    5. 异常告警：错过 / 补执行成功 / 补执行失败 / 重试耗尽 均落 alerts.log。

■ 覆盖的槽位（`SLOTS`，与 scripts/launchctl/*.plist 一一对应，单测锁定防漂移）
    cn-stage1 / cn-stage2 / cn-stage3（沪深日级三阶段）
    cn-weekly / cn-monthly（沪深周K/月K 聚合）
    hk-job / hk-weekly（港股全链路 / 港股周K 聚合）
    us-job / us-weekly（美股全链路 / 美股周K 聚合）
    overseas-monthly（港/美股月K 聚合，单进程内含 hk+us 两条台账）
  注：聚合类槽位（cn-weekly 等）的「已满足」判据同样是「当日 task_run_log 有 success 记录」，
  因此要求 `compute_bar_aggregation.py` 写入台账（协作单 61.0 起已支持）。

■ 设计要点（与现有业务完全兼容）
  - 「是否已满足」以 `task_run_log`（start_time::date = 调度日）为**唯一事实来源**，
    不新增影子状态，因此正常时段的调度行为零影响；
  - 补执行走既有 runner → 任务级 `success` 跳过、阶段门禁（协作单 56.0）、
    硬超时（57.0）等既有保护全部继续生效；
  - 有 `running` 记录（正常调度正在跑）时判定 in_progress，不重复触发；
  - 判定留 Grace（默认 10 分钟）避免与正常调度抢跑；
  - 判定时点取**当日最早的触发时刻**：多时刻槽位（如港股周K 周五 19:30 + 周六 09:30）
    在首个时刻前不会误判，避免「数据源尚未产出就抢先补跑并写成功」的假恢复；
  - 单实例文件锁 + 每次尝试冷却（默认 30 分钟），杜绝并发与风暴。

■ 用法
    venv/bin/python backend/cron/scheduler_watchdog.py              # 检测并按需补执行
    venv/bin/python backend/cron/scheduler_watchdog.py --dry-run    # 只检测打印，不执行
    venv/bin/python backend/cron/scheduler_watchdog.py --status     # 打印各槽位当前状态
    venv/bin/python backend/cron/scheduler_watchdog.py --only cn-stage2 hk-job

■ 环境变量（均可选）
    SCHED_WATCHDOG_MAX_ATTEMPTS   每槽位每日补执行上限（默认 3）
    SCHED_WATCHDOG_COOLDOWN_SEC   两次补执行最小间隔秒（默认 1800）
    SCHED_WATCHDOG_GRACE_SEC      到点后多久才判定「错过」（默认 600）
    SCHED_WATCHDOG_LOOKBACK_DAYS  额外回看天数（默认 1，覆盖整晚关机后次日恢复）
    SCHED_WATCHDOG_RUN_TIMEOUT    单次补执行超时秒（默认 7200）
    SCHED_WATCHDOG_DISABLED_SLOTS 逗号分隔的停用槽位 key（如 cn-stage1,hk-job）

■ 退出码
    0 = 无待补执行，或补执行全部成功
    1 = 存在补执行失败（未达上限，下次会再试）
    2 = 存在槽位达重试上限（exhausted，需人工介入；该情况同时落 CRITICAL 告警）
"""
import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# ===================== 路径与日志 =====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))  # 显式加载数据库连接配置

sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
from utils.alerting import append_alerts          # noqa: E402
from utils.logger import setup_logger             # noqa: E402

logger = setup_logger('scheduler_watchdog')

PYTHON = sys.executable
LOG_DIR = os.path.join(BASE_DIR, 'logs', 'cron')
LOCK_FILE = os.path.join(LOG_DIR, '.scheduler_watchdog.lock')

# ===================== 可调参数 =====================
MAX_ATTEMPTS_DEFAULT = 3
COOLDOWN_SEC_DEFAULT = 30 * 60
GRACE_SEC_DEFAULT = 10 * 60
# 默认额外回看 1 天：覆盖「设备整晚关机/休眠，次日开机才恢复」的场景，
# 使前一交易日错过的槽位也能被补执行。非调度日由 is_scheduled_day 过滤，不会误触发。
LOOKBACK_DAYS_DEFAULT = 1
RUN_TIMEOUT_SEC_DEFAULT = 7200
# 遗留 running 判定阈值：进程被杀（断电/关机/崩溃）后 task_run_log 会残留 running，
# 不能被永久视为「正在运行」而阻塞补执行。与 daily_job_runner.ZOMBIE_THRESHOLD_SEC 对齐。
ZOMBIE_SEC_DEFAULT = 7200

# 调度槽位状态机
STATUS_DETECTED = 'detected'
STATUS_CATCHING_UP = 'catching_up'
STATUS_SUCCESS = 'success'
STATUS_FAILED = 'failed'
STATUS_EXHAUSTED = 'exhausted'

# ===================== 调度时刻表（与 scripts/launchctl/*.plist 严格对齐） =====================
MON_FRI = frozenset({1, 2, 3, 4, 5})   # ISO: 1=周一 … 7=周日
TUE_SAT = frozenset({2, 3, 4, 5, 6})
DAILY = frozenset({1, 2, 3, 4, 5, 6, 7})

_CAL_WEEKDAY = 'weekday'               # 仅按星期判定
_CAL_CN = 'cn'                         # 叠加 A 股 trade_calendar（is_open=1）


def _sched(weekdays: frozenset, hour: int, minute: int) -> Tuple[Tuple[int, int, int], ...]:
    """按 plist 的写法展开 StartCalendarInterval：星期集合 × 单一时刻 → 若干 (wd, h, m)。"""
    return tuple((wd, hour, minute) for wd in sorted(weekdays))


@dataclass(frozen=True)
class Slot:
    """一个「调度槽位」：某个 runner 在某个/某些时刻的预期执行。

    `schedule` 与 plist 的 `StartCalendarInterval` 数组**一一对应**（元素为 (ISO 星期, 时, 分)），
    因此天然支持「同一任务多个触发时刻」（如港股周K：周五 19:30 主 + 周六 09:30 兜底）。
    """
    key: str                                    # 唯一标识（写 scheduler_slot_log.slot_key）
    market: str                                 # cn / hk / us
    label: str                                  # 中文描述
    schedule: Tuple[Tuple[int, int, int], ...]  # ((ISO 星期, 时, 分), ...)，与 plist 一致
    tasks: tuple                                # task_run_log 中判定该槽位「是否已完成」的任务名
    runner: str                                 # 相对 BASE_DIR 的 runner 脚本
    runner_args: tuple = ()                     # runner 附加参数
    calendar: str = _CAL_WEEKDAY

    def weekdays(self) -> frozenset:
        """允许触发的 ISO 星期集合。"""
        return frozenset(wd for wd, _, _ in self.schedule)

    def times_on(self, day: date) -> Tuple[dtime, ...]:
        """该日该槽位的全部触发时刻（升序）。"""
        return tuple(sorted(dtime(h, m) for wd, h, m in self.schedule
                            if wd == day.isoweekday()))

    def due_time_on(self, day: date) -> Optional[dtime]:
        """该日最早需要「已执行」的时刻；非调度日返回 None。"""
        times = self.times_on(day)
        return times[0] if times else None

    def earliest_time(self) -> dtime:
        """全周最早触发时刻（用于排序与台账 scheduled_at 兜底）。"""
        return min(dtime(h, m) for _, h, m in self.schedule)


SLOTS: Tuple[Slot, ...] = (
    Slot('cn-stage1', 'cn', '阶段1 健康检查+股票列表同步+复权因子同步',
         _sched(MON_FRI, 15, 30),
         ('pipeline_health_check', 'stock_list_sync', 'adj_factor_sync'),
         os.path.join('backend', 'cron', 'daily_job_runner.py'), ('--stage', '1'), _CAL_CN),
    Slot('cn-stage2', 'cn', '阶段2 日线行情导入',
         _sched(MON_FRI, 16, 30),
         ('daily_import', 'index_sync'),
         os.path.join('backend', 'cron', 'daily_job_runner.py'), ('--stage', '2'), _CAL_CN),
    Slot('cn-stage3', 'cn', '阶段3 补全→基本面→指标→形态→信号→宽表→Parquet',
         _sched(MON_FRI, 17, 30),
         ('fill_missing_data', 'daily_basic_sync', 'indicators_compute',
          'pattern_precompute', 'signal_precompute', 'daily_sync', 'parquet_export'),
         os.path.join('backend', 'cron', 'daily_job_runner.py'), ('--stage', '3'), _CAL_CN),
    Slot('cn-weekly', 'cn', '沪深周K聚合（含 index）',
         _sched(MON_FRI, 18, 30),
         ('cn:周K',),
         os.path.join('backend', 'collector', 'etl', 'compute_bar_aggregation.py'),
         ('--cycle', '1w')),
    Slot('cn-monthly', 'cn', '沪深月K聚合（含 index）',
         _sched(MON_FRI, 18, 45),
         ('cn:月K',),
         os.path.join('backend', 'collector', 'etl', 'compute_bar_aggregation.py'),
         ('--cycle', '1m')),
    Slot('hk-job', 'hk', '港股 ETL 全链路（列表→日线→指标→形态→信号→宽表→Parquet）',
         _sched(MON_FRI, 18, 30),
         ('hk:股票列表', 'hk:日线清洗', 'hk:指标', 'hk:形态', 'hk:信号', 'hk:宽表', 'hk:Parquet'),
         os.path.join('backend', 'cron', 'hk_job_runner.py'), ()),
    Slot('hk-weekly', 'hk', '港股周K聚合（按 HSI 日历划分 ISO 周）',
         _sched(frozenset({5}), 19, 30) + _sched(frozenset({6}), 9, 30),
         ('hk:周K',),
         os.path.join('backend', 'collector', 'etl', 'compute_bar_aggregation.py'),
         ('--cycle', '1w', '--market', 'hk')),
    Slot('us-job', 'us', '美股 ETL 全链路（列表→日线→基本面→指标→形态→信号→宽表→Parquet）',
         _sched(TUE_SAT, 8, 30),
         ('us:股票列表', 'us:日线清洗', 'us:基本面', 'us:指标', 'us:形态',
          'us:信号', 'us:宽表', 'us:Parquet'),
         os.path.join('backend', 'cron', 'us_job_runner.py'), ()),
    Slot('us-weekly', 'us', '美股周K聚合（按 .IXIC 日历划分 ISO 周）',
         _sched(frozenset({6}), 9, 30),
         ('us:周K',),
         os.path.join('backend', 'collector', 'etl', 'compute_bar_aggregation.py'),
         ('--cycle', '1w', '--market', 'us')),
    Slot('overseas-monthly', 'hk,us', '港/美股月K聚合（按各自数据源日历划分自然月）',
         _sched(DAILY, 10, 0),
         ('hk:月K', 'us:月K'),
         os.path.join('backend', 'collector', 'etl', 'compute_bar_aggregation.py'),
         ('--cycle', '1m', '--market', 'hk,us')),
)

SLOT_BY_KEY: Dict[str, Slot] = {s.key: s for s in SLOTS}


def expected_task_names(slot: Slot) -> Tuple[str, ...]:
    """槽位期望的任务名集合（处理 hk 基本面的可选步骤）。"""
    if slot.key == 'hk-job' and os.environ.get('HKJOB_RUN_BASIC') == '1':
        return slot.tasks + ('hk:基本面',)
    return slot.tasks


# ===================== 单实例文件锁 =====================
class SingleInstanceLock:
    """跨平台单实例锁（fcntl / msvcrt）。不删除锁文件，避免释放竞态导致双持有。"""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self.fd = None

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        fd = open(self.lock_path, 'w')
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd.write(f"{os.getpid()}|{datetime.now().isoformat()}\n")
            fd.flush()
            self.fd = fd
            return True
        except OSError:
            fd.close()
            return False

    def release(self):
        if self.fd is None:
            return
        try:
            if os.name == 'nt':
                import msvcrt
                self.fd.seek(0)
                msvcrt.locking(self.fd.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        except Exception:
            pass
        finally:
            try:
                self.fd.close()
            finally:
                self.fd = None


# ===================== 数据库 =====================
def get_db_engine():
    """构建 SQLAlchemy Engine（与 daily_job_runner 保持一致）。"""
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}"
        f"@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DATABASE')}",
        pool_pre_ping=True,
        pool_recycle=3600,
    )


_SQL_TASK_STATUSES_DAY = text("""
    SELECT DISTINCT ON (task_name) task_name, status, start_time
    FROM task_run_log
    WHERE task_name = ANY(:names) AND start_time::date = :day
    ORDER BY task_name, id DESC
""")

# 补执行后的复核用窗口查询：补执行总是把台账写在「补执行当日」，
# 若仍按日期等值匹配，回看日期的补执行会被误判为「仍缺失」→ 误记 failed/exhausted。
_SQL_TASK_STATUSES_SINCE = text("""
    SELECT DISTINCT ON (task_name) task_name, status, start_time
    FROM task_run_log
    WHERE task_name = ANY(:names) AND start_time >= :since
    ORDER BY task_name, id DESC
""")

_SQL_CN_TRADING_DAY = text(
    "SELECT is_open FROM trade_calendar WHERE cal_date = :day LIMIT 1"
)

_SQL_GET_SLOT_ROW = text("""
    SELECT id, status, attempts, last_attempt_at, last_error
    FROM scheduler_slot_log
    WHERE slot_key = :k AND biz_date = :d
""")

_SQL_INSERT_SLOT_ROW = text("""
    INSERT INTO scheduler_slot_log
        (slot_key, biz_date, market, label, scheduled_at, first_seen_at,
         last_attempt_at, attempts, status, last_error, detail)
    VALUES (:slot_key, :biz_date, :market, :label, :scheduled_at, :first_seen_at,
            :last_attempt_at, :attempts, :status, :last_error, CAST(:detail AS JSONB))
    ON CONFLICT (slot_key, biz_date) DO NOTHING
""")

_SQL_UPDATE_SLOT_ROW = text("""
    UPDATE scheduler_slot_log
    SET status = :status,
        attempts = :attempts,
        last_attempt_at = :last_attempt_at,
        last_error = :last_error,
        detail = CAST(:detail AS JSONB),
        updated_at = NOW()
    WHERE slot_key = :slot_key AND biz_date = :biz_date
""")


# ===================== 槽位判定 =====================
def is_scheduled_day(engine, slot: Slot, day: date) -> bool:
    """该日是否为槽位的调度日（星期 + 可选 A 股交易日历）。"""
    if day.isoweekday() not in slot.weekdays():
        return False
    if slot.calendar != _CAL_CN:
        return True
    try:
        with engine.connect() as conn:
            v = conn.execute(_SQL_CN_TRADING_DAY, {"day": day}).scalar()
    except Exception as e:              # 查询异常时按「是调度日」处理，交由后续步骤自然失败
        logger.warning(f"⚠️ trade_calendar 查询失败（{type(e).__name__}: {e}），按调度日处理")
        return True
    return bool(v)


def query_slot_status(engine, slot: Slot, day: date,
                      zombie_sec: int = ZOMBIE_SEC_DEFAULT,
                      now: Optional[datetime] = None,
                      since: Optional[datetime] = None) -> Dict:
    """查询槽位在指定调度日的任务完成情况。

    Args:
        now: 判定基准时刻（默认当前时间）；显式传入便于测试与历史回放。
        since: 为 None 时按 **`start_time::date = day` 严格匹配**（检测语义：该日确实执行过，
            不做跨日遮蔽）；传入时间时改用 **`start_time >= since` 窗口**（补执行后的复核语义，
            用于确认「补执行当日新写入的台账」已生效）。

    残留 `running` 记录（进程被杀/断电）超过 `zombie_sec` 时不再视为「正在运行」，
    否则一次异常中断会让该槽位永久无法补执行。

    Returns:
        dict(success, total, running, missing, error)
    """
    names = list(expected_task_names(slot))
    if since is not None:
        sql, params = _SQL_TASK_STATUSES_SINCE, {"names": names, "since": since}
    else:
        sql, params = _SQL_TASK_STATUSES_DAY, {"names": names, "day": day}
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except Exception as e:
        return {"success": 0, "total": len(names), "running": False,
                "missing": names, "error": f"{type(e).__name__}: {e}"}
    statuses = {r[0]: r[1] for r in rows}
    missing = [n for n in names if statuses.get(n) != 'success']

    running = False
    ref_now = now or datetime.now()
    for r in rows:
        if len(r) < 3 or r[1] != 'running':
            continue
        started = r[2]
        if started is not None and (ref_now - started).total_seconds() > zombie_sec:
            logger.warning(f"💀 [{slot.key}@{day}] {r[0]} 存在残留 running 记录"
                           f"（起始 {started}，超 {zombie_sec // 60} 分钟），按僵尸处理")
            continue
        running = True
    return {
        "success": len(names) - len(missing),
        "total": len(names),
        "running": running,
        "missing": missing,
        "error": None,
    }


def evaluate_slot(engine, slot: Slot, day: date, now: datetime,
                  grace_sec: int) -> Tuple[str, str]:
    """判定槽位状态。

    Returns:
        (kind, message)，kind ∈
        not_scheduled | not_due | satisfied | in_progress | unknown | missed
    """
    if not is_scheduled_day(engine, slot, day):
        return 'not_scheduled', f'{day} 非 {slot.key} 调度日（星期/交易日历）'
    due = slot.due_time_on(day)
    scheduled_at = datetime.combine(day, due)
    if now < scheduled_at + timedelta(seconds=grace_sec):
        times = '/'.join(f'{t.hour:02d}:{t.minute:02d}' for t in slot.times_on(day))
        return 'not_due', (f'未到判定时刻：当日计划 {times}，'
                           f'宽限 {grace_sec // 60} 分钟后判定（当前 {now:%H:%M}）')
    st = query_slot_status(engine, slot, day, now=now)
    if st['error']:
        return 'unknown', f"任务状态查询失败，本次跳过：{st['error']}"
    if not st['missing']:
        return 'satisfied', f"{st['total']}/{st['total']} 个任务当日已全部成功"
    if st['running']:
        return 'in_progress', f"有任务正在运行，跳过：{[n for n in st['missing']]}"
    return 'missed', (f"已过点仍缺 {len(st['missing'])}/{st['total']} 个任务："
                      f"{st['missing']}")


# ===================== 台账读写 =====================
def get_slot_row(engine, slot_key: str, day: date) -> Optional[Dict]:
    try:
        with engine.connect() as conn:
            row = conn.execute(_SQL_GET_SLOT_ROW, {"k": slot_key, "d": day}).fetchone()
    except Exception as e:
        logger.warning(f"⚠️ scheduler_slot_log 读取失败: {e}")
        return None
    if row is None:
        return None
    return {"id": row[0], "status": row[1], "attempts": int(row[2] or 0),
            "last_attempt_at": row[3], "last_error": row[4]}


def upsert_slot_row(engine, slot: Slot, day: date, status: str, attempts: int,
                    last_error: Optional[str] = None, detail: Optional[dict] = None,
                    scheduled_at: Optional[datetime] = None,
                    last_attempt_at: Optional[datetime] = None,
                    create: bool = False) -> bool:
    """写入/更新槽位台账行。create=True 时仅在无行时插入。"""
    common = {
        "slot_key": slot.key,
        "biz_date": day,
        "status": status,
        "attempts": attempts,
        "last_attempt_at": last_attempt_at,
        "last_error": last_error,
        "detail": json.dumps(detail, ensure_ascii=False) if detail else None,
    }
    params = dict(common)
    if create:
        params.update({
            "market": slot.market,
            "label": slot.label,
            "scheduled_at": scheduled_at or datetime.combine(
                day, slot.due_time_on(day) or slot.earliest_time()),
            "first_seen_at": datetime.now(),
        })
    try:
        with engine.connect() as conn:
            conn.execute(_SQL_INSERT_SLOT_ROW if create else _SQL_UPDATE_SLOT_ROW, params)
            conn.commit()
        return True
    except OperationalError as e:
        logger.warning(f"⚠️ scheduler_slot_log 写入失败: {e}")
        return False
    except Exception as e:
        logger.warning(f"⚠️ scheduler_slot_log 写入异常: {type(e).__name__}: {e}")
        return False


# ===================== 告警 =====================
def _alert(level: str, slot: Slot, message: str) -> None:
    """落 alerts.log（看板/晨检统一入口）。"""
    append_alerts([{'level': level, 'market': slot.market,
                    'message': f"[调度看护] {message}"}])


# ===================== 补执行 =====================
def invoke_runner(slot: Slot, timeout: int) -> Tuple[bool, str]:
    """调用既有 runner 补执行槽位（业务逻辑零改动）。"""
    script = os.path.join(BASE_DIR, slot.runner)
    cmd = [PYTHON, script] + list(slot.runner_args)
    env = os.environ.copy()
    backend_dir = os.path.join(BASE_DIR, 'backend')
    existing = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = f"{backend_dir}:{existing}" if existing else backend_dir
    logger.info(f"▶️ 补执行 [{slot.key}] {slot.label} → {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True,
                              encoding='utf-8', timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return False, f"补执行超时（>{timeout}s）"
    except OSError as e:
        return False, f"补执行启动失败: {e}"

    stdout_tail = (proc.stdout or '')[-4000:]
    stderr_tail = (proc.stderr or '')[-1000:]
    if stdout_tail.strip():
        logger.info(f"  [{slot.key}] stdout 尾部:\n" + "\n".join(
            stdout_tail.strip().splitlines()[-12:]))
    if proc.returncode == 0:
        logger.info(f"✅ 补执行 [{slot.key}] 成功（exit=0）")
        return True, ""
    logger.error(f"❌ 补执行 [{slot.key}] 失败（exit={proc.returncode}）")
    if stderr_tail.strip():
        logger.error(f"  [{slot.key}] stderr 尾部:\n" + "\n".join(
            stderr_tail.strip().splitlines()[-8:]))
    return False, f"exit={proc.returncode}: {(stderr_tail or stdout_tail)[-400:]}"


# ===================== 主流程 =====================
def _resolve_int(env_name: str, default: int, cli_value: Optional[int] = None) -> int:
    if cli_value is not None:
        return cli_value
    raw = os.environ.get(env_name)
    if raw is None or str(raw).strip() == '':
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        logger.warning(f"⚠️ {env_name}={raw!r} 非法，回退默认 {default}")
        return default


def run_watchdog(engine, now: Optional[datetime] = None, dry_run: bool = False,
                 only: Optional[List[str]] = None, max_attempts: Optional[int] = None,
                 grace_sec: Optional[int] = None, cooldown_sec: Optional[int] = None,
                 lookback_days: Optional[int] = None,
                 run_timeout: Optional[int] = None) -> Dict:
    """执行一轮看护：检测错过槽位并按需补执行。

    Returns:
        dict(with_actions, failures, exhausted, results)
    """
    now = now or datetime.now()
    max_attempts = _resolve_int('SCHED_WATCHDOG_MAX_ATTEMPTS', MAX_ATTEMPTS_DEFAULT, max_attempts)
    grace_sec = _resolve_int('SCHED_WATCHDOG_GRACE_SEC', GRACE_SEC_DEFAULT, grace_sec)
    cooldown_sec = _resolve_int('SCHED_WATCHDOG_COOLDOWN_SEC', COOLDOWN_SEC_DEFAULT, cooldown_sec)
    lookback_days = _resolve_int('SCHED_WATCHDOG_LOOKBACK_DAYS', LOOKBACK_DAYS_DEFAULT, lookback_days)
    run_timeout = _resolve_int('SCHED_WATCHDOG_RUN_TIMEOUT', RUN_TIMEOUT_SEC_DEFAULT, run_timeout)

    disabled = {s.strip() for s in os.environ.get('SCHED_WATCHDOG_DISABLED_SLOTS', '').split(',') if s.strip()}
    only_set = set(only) if only else None

    results: List[Dict] = []
    failures: List[str] = []
    exhausted: List[str] = []

    today = now.date()
    days = [today - timedelta(days=i) for i in range(0, max(0, lookback_days) + 1)]
    days.reverse()                      # 先补较早的槽位（保持阶段先后）

    # 槽位按计划时刻排序，天然满足「阶段1→2→3」「先沪深后港美」的依赖顺序
    ordered_slots = sorted(SLOTS, key=lambda s: (s.earliest_time(), s.key))

    for day in days:
        for slot in ordered_slots:
            if only_set is not None and slot.key not in only_set:
                continue
            if slot.key in disabled:
                results.append(_result(slot, day, 'disabled', '槽位已通过环境变量停用'))
                continue

            kind, msg = evaluate_slot(engine, slot, day, now, grace_sec)
            if kind != 'missed':
                results.append(_result(slot, day, kind, msg))
                # 补执行成功后 task_run_log 出现成功记录，顺手把台账收敛为 success
                if kind == 'satisfied' and not dry_run:
                    row = get_slot_row(engine, slot.key, day)
                    if row and row['status'] != STATUS_SUCCESS:
                        upsert_slot_row(engine, slot, day, STATUS_SUCCESS, row['attempts'],
                                        detail={'recovered': True, 'by': 'task_run_log'})
                continue

            # 判 missed 后先看台账：已由**前一轮补执行**恢复的（回看日期尤其常见）不再动
            row = get_slot_row(engine, slot.key, day)
            attempts = row['attempts'] if row else 0

            if row and row['status'] == STATUS_SUCCESS:
                results.append(_result(
                    slot, day, 'recovered',
                    f"曾错过，已由补执行恢复（attempts={attempts}，task_run_log 按日期无该日记录属预期）"))
                continue
            if row and row['status'] == STATUS_EXHAUSTED:
                results.append(_result(slot, day, 'exhausted',
                                       f"补执行 {max_attempts} 次后仍缺任务，已停止自动补跑"))
                exhausted.append(f"{slot.key}@{day}")
                continue
            if attempts >= max_attempts:
                logger.error(f"🛑 [{slot.key}@{day}] 补执行已达上限 {max_attempts} 次，转 exhausted")
                if not dry_run:
                    upsert_slot_row(engine, slot, day, STATUS_EXHAUSTED, attempts,
                                    last_error=f"补执行 {max_attempts} 次后仍缺任务：{msg}",
                                    detail={'missing': _missing_of(engine, slot, day)})
                _alert('CRITICAL', slot,
                       f"{slot.key}@{day} 错过且补执行 {max_attempts} 次仍未完成，已停止自动补跑，"
                       f"需人工介入（{msg}）")
                results.append(_result(slot, day, 'exhausted', msg))
                exhausted.append(f"{slot.key}@{day}")
                continue
            if row and row['last_attempt_at']:
                elapsed = (now - row['last_attempt_at']).total_seconds()
                if elapsed < cooldown_sec:
                    results.append(_result(
                        slot, day, 'cooldown',
                        f"距上次补执行 {int(elapsed)}s < 冷却 {cooldown_sec}s，本次跳过"))
                    continue

            results.append(_result(slot, day, 'missed', msg))
            if dry_run:
                results.append(_result(slot, day, 'would_catchup',
                                       f"[DRY-RUN] 将补执行（已尝试 {attempts}/{max_attempts} 次）"))
                continue

            # ---- 正式补执行 ----
            if row is None:
                upsert_slot_row(engine, slot, day, STATUS_DETECTED, 0,
                                detail={'missing': _missing_of(engine, slot, day)},
                                create=True)
                _alert('WARNING', slot,
                       f"{slot.key}@{day} 到点未执行（疑似 launchd 错过触发/系统休眠），已启动自动补执行")
                logger.warning(f"🔔 [{slot.key}@{day}] 检测到错过，开始自动补执行")

            # 复核用「时间窗口」：补执行把台账写在当日，回看日期须按 >= day 00:00 判
            ok, err = invoke_runner(slot, run_timeout)
            st_after = query_slot_status(engine, slot, day, now=now,
                                        since=datetime.combine(day, dtime(0, 0)))
            recovered = ok and not st_after['missing']

            if recovered:
                upsert_slot_row(engine, slot, day, STATUS_SUCCESS, attempts + 1,
                                detail={'missing': [], 'success': st_after['success'],
                                        'total': st_after['total']},
                                last_attempt_at=datetime.now())
                _alert('WARNING', slot,
                       f"{slot.key}@{day} 错过后自动补执行成功（{st_after['success']}/"
                       f"{st_after['total']} 任务），数据未断档")
                logger.info(f"✅ [{slot.key}@{day}] 补执行成功，台账已置 success")
            else:
                reason = err or f"补执行后仍有缺失任务：{st_after['missing']}"
                upsert_slot_row(engine, slot, day, STATUS_FAILED, attempts + 1,
                                last_error=reason,
                                detail={'missing': st_after['missing']},
                                last_attempt_at=datetime.now())
                _alert('CRITICAL', slot,
                       f"{slot.key}@{day} 自动补执行失败（第 {attempts + 1}/{max_attempts} 次）：{reason}")
                failures.append(f"{slot.key}@{day}")

    with_actions = any(r['kind'] in ('missed', 'would_catchup') for r in results)
    return {"with_actions": with_actions, "failures": failures,
            "exhausted": exhausted, "results": results}


def _missing_of(engine, slot: Slot, day: date) -> List[str]:
    return query_slot_status(engine, slot, day).get('missing', [])


def _result(slot: Slot, day: date, kind: str, message: str) -> Dict:
    return {"slot": slot.key, "market": slot.market, "biz_date": str(day),
            "kind": kind, "message": message}


def print_status(engine, now: Optional[datetime] = None) -> None:
    """打印各槽位当日状态（人工排查用）。"""
    now = now or datetime.now()
    grace = _resolve_int('SCHED_WATCHDOG_GRACE_SEC', GRACE_SEC_DEFAULT)
    today = now.date()
    print('=' * 78)
    print(f"调度看护状态 | {now:%Y-%m-%d %H:%M:%S} | 宽限 {grace // 60} 分钟")
    print('=' * 78)
    for slot in sorted(SLOTS, key=lambda s: (s.earliest_time(), s.key)):
        kind, msg = evaluate_slot(engine, slot, today, now, grace)
        row = get_slot_row(engine, slot.key, today)
        row_desc = (f"{row['status']}(attempts={row['attempts']})" if row else '-')
        plan = '/'.join(f'{wd}:{h:02d}:{m:02d}' for wd, h, m in slot.schedule)
        print(f"  {slot.key:<17} 计划 {plan} | "
              f"{kind:<14} | 台账 {row_desc}")
        print(f"                    {msg}")
    print('=' * 78)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='定时任务「错过检测 + 自动补执行」守护器（协作单 60.0）')
    parser.add_argument('--dry-run', action='store_true', help='只检测打印，不写台账、不补执行')
    parser.add_argument('--status', action='store_true', help='打印各槽位当日状态后退出')
    parser.add_argument('--only', nargs='*', metavar='SLOT', help='只处理指定槽位 key')
    parser.add_argument('--max-attempts', type=int, help='每槽位每日补执行上限')
    parser.add_argument('--grace-sec', type=int, help='到点后多久判定「错过」')
    parser.add_argument('--cooldown-sec', type=int, help='两次补执行最小间隔秒')
    parser.add_argument('--lookback-days', type=int, help='额外回看天数（默认 1）')
    args = parser.parse_args()

    if args.only:
        unknown = [k for k in args.only if k not in SLOT_BY_KEY]
        if unknown:
            print(f"[ERROR] 未知槽位: {unknown}；可用: {list(SLOT_BY_KEY)}")
            return 1

    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        engine = get_db_engine()
    except Exception as e:
        logger.error(f"❌ 数据库引擎构建失败: {e}")
        return 1

    if args.status:
        try:
            print_status(engine)
        except Exception as e:
            logger.error(f"❌ 状态查询失败: {e}")
            return 1
        return 0

    lock = SingleInstanceLock(LOCK_FILE)
    if not lock.acquire():
        logger.info("ℹ️ 已有 scheduler_watchdog 实例在运行，本次退出")
        return 0
    try:
        summary = run_watchdog(
            engine,
            dry_run=args.dry_run,
            only=args.only,
            max_attempts=args.max_attempts,
            grace_sec=args.grace_sec,
            cooldown_sec=args.cooldown_sec,
            lookback_days=args.lookback_days,
        )
    except Exception as e:
        logger.error(f"❌ 看护执行异常: {type(e).__name__}: {e}", exc_info=True)
        return 1
    finally:
        lock.release()

    actionable = [r for r in summary['results'] if r['kind'] != 'satisfied']
    if actionable:
        print("-" * 78)
        for r in actionable:
            print(f"  [{r['kind']:<14}] {r['slot']}@{r['biz_date']}: {r['message']}")
        print("-" * 78)
    else:
        print(f"✅ 全部槽位正常（{len(summary['results'])} 个槽位已检查）")

    if summary['exhausted']:
        logger.error(f"🛑 达重试上限的槽位: {summary['exhausted']}")
        return 2
    if summary['failures']:
        logger.error(f"❗ 补执行失败（下次将重试）: {summary['failures']}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())