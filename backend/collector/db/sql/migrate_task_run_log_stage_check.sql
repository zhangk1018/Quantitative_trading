-- 迁移: 放宽 task_run_log.stage CHECK 约束，允许 stage=0 作为管道整体状态记录专用值
-- 背景: daily_job_runner.py 使用 stage=0 写入 etl_pipeline 整体状态记录，
--       但原约束 CHECK (stage BETWEEN 1 AND 11) 拒绝 0，导致整体状态记录丢失。
-- 修复: 改为 CHECK (stage BETWEEN 0 AND 11)，允许 stage=0 作为管道级元数据记录。

-- 先删除旧约束（需要知道约束名）
ALTER TABLE task_run_log DROP CONSTRAINT IF EXISTS task_run_log_stage_check;

-- 添加新约束
ALTER TABLE task_run_log ADD CONSTRAINT task_run_log_stage_check CHECK (stage BETWEEN 0 AND 11);

-- 验证
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conname = 'task_run_log_stage_check';