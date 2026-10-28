-- V025: 调度槽位台账 scheduler_slot_log —— 定时任务「错过检测 + 自动补执行」状态持久化
--
-- 背景（2026-10-27 事故）：
--   macOS launchd 的 StartCalendarInterval 是**一次性日历触发**。若触发时刻该服务未被加载
--   （登录域重建 / plist 重载 / 系统休眠未按时唤醒），则该次触发被**永久跳过**，launchd 不会补跑。
--   daily_job_runner.py 只在「被启动之后」做断点续跑与 3×15min 重试，无法自我唤醒 → 错过即数据断档。
--   实证：2026-10-27 14:59:06 与 15:02:40 launchd 两次 `removing service:
--   com.quant.daily-job-runner.stage1`，15:38:10 重新 Bootstrap 后 15:30 的
--   StartCalendarInterval 只能排到「下周二 15:30」，当日 stage1 永久丢失。
--
-- 本表由 backend/cron/scheduler_watchdog.py 读写，记录每个「调度槽位 × 营业日」的
-- 检测时间、补执行尝试次数、最终结果与错误，用于：
--   ① 幂等：同一槽位同一天只补执行有限次，避免重复触发与雪崩；
--   ② 失败重试上限：attempts 达上限转 exhausted，停止自动补跑并 CRITICAL 告警；
--   ③ 审计：为晨检/看板提供「错过 → 补执行」的完整链路证据。
-- 说明：槽位是否「已满足」以 task_run_log 为唯一事实来源；本表只在**检测到错过**时落行。

CREATE TABLE IF NOT EXISTS scheduler_slot_log (
    id              BIGSERIAL    PRIMARY KEY,
    slot_key        VARCHAR(64)  NOT NULL,                  -- 槽位标识，如 cn-stage2 / hk-job / us-job
    biz_date        DATE         NOT NULL,                  -- 该槽位所属的调度日（本地日期）
    market          VARCHAR(16),                            -- cn / hk / us
    label           VARCHAR(128),                           -- 中文名，便于人工阅读
    scheduled_at    TIMESTAMP    NOT NULL,                  -- 该槽位原定触发时刻
    first_seen_at   TIMESTAMP    NOT NULL DEFAULT NOW(),    -- 首次检测到「错过」的时刻
    last_attempt_at TIMESTAMP,                              -- 最近一次补执行尝试时刻
    attempts        INTEGER      NOT NULL DEFAULT 0,        -- 已补执行次数（受上限约束）
    status          VARCHAR(24)  NOT NULL DEFAULT 'detected',
    last_error      TEXT,                                   -- 最近一次失败摘要
    detail          JSONB,                                  -- 结构化详情（缺失任务清单等）
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT scheduler_slot_log_slot_biz_uniq UNIQUE (slot_key, biz_date)
);

CREATE INDEX IF NOT EXISTS idx_scheduler_slot_log_biz_status
    ON scheduler_slot_log (biz_date, status);

COMMENT ON TABLE scheduler_slot_log IS
    '定时任务槽位台账：错过检测/补执行/重试计数（backend/cron/scheduler_watchdog.py）';
COMMENT ON COLUMN scheduler_slot_log.status IS
    'detected=检测到错过 | catching_up=补执行中 | success=已恢复 | failed=补执行失败(可重试) | exhausted=达重试上限';
COMMENT ON COLUMN scheduler_slot_log.detail IS
    '结构化详情，如 {"missing": ["daily_import"], "total": 2, "success": 1}';