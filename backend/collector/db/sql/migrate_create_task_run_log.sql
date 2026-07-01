-- ETL 任务运行监控表
CREATE TABLE IF NOT EXISTS task_run_log (
    id              BIGSERIAL PRIMARY KEY,
    task_name       VARCHAR(100) NOT NULL,
    stage           INT NOT NULL CHECK (stage BETWEEN 1 AND 11),
    start_time      TIMESTAMP NOT NULL,
    end_time        TIMESTAMP,
    status          VARCHAR(20) NOT NULL CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    exit_code       INT,
    error_message   TEXT,
    rows_affected   INT,
    extra_metrics   JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- 索引优化
CREATE INDEX IF NOT EXISTS idx_task_run_log_start_time ON task_run_log (start_time DESC);
CREATE INDEX IF NOT EXISTS idx_task_run_log_status ON task_run_log (status);
CREATE INDEX IF NOT EXISTS idx_task_run_log_stage ON task_run_log (stage);
