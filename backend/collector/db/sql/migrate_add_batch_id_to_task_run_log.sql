-- 迁移：task_run_log 新增 batch_id 字段
-- 用于标识同一次调度运行的所有任务记录，支持基于数据库的断点续跑

ALTER TABLE task_run_log
    ADD COLUMN IF NOT EXISTS batch_id VARCHAR(32);

CREATE INDEX IF NOT EXISTS idx_task_run_log_batch_id ON task_run_log(batch_id);

COMMENT ON COLUMN task_run_log.batch_id IS '批次ID，同一次runner调度的所有任务共享同一batch_id';
