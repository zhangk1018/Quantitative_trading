-- task_run_log 新增 data_date 列，rows_affected 改为 BIGINT
-- 用于记录任务处理的交易日和影响行数

ALTER TABLE task_run_log
    ADD COLUMN IF NOT EXISTS data_date DATE;

-- rows_affected 原为 INT，改为 BIGINT 支持更大数据量
ALTER TABLE task_run_log
    ALTER COLUMN rows_affected TYPE BIGINT USING rows_affected::BIGINT;

-- 为 data_date 建立索引，方便仪表盘按日期筛选
CREATE INDEX IF NOT EXISTS idx_task_run_log_data_date ON task_run_log(data_date);
