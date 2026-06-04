-- ==========================================
-- PostgreSQL 数据库索引创建脚本
-- ==========================================
-- ⚠️ 生产上线前必须执行此脚本
-- 否则 ON CONFLICT DO UPDATE 将失效或性能骤降
-- ==========================================
-- 使用方法: psql -h localhost -U quant_user -d quant_trading -f create_indexes.sql

-- ==========================================
-- 1. stock_quotes 表唯一索引（支持 ON CONFLICT）
-- ==========================================
-- 日线行情唯一约束
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_quotes_unique
    ON stock_quotes(code, cycle, trade_date)
    WHERE cycle = '1d';

-- stock_quotes 常用查询索引
CREATE INDEX IF NOT EXISTS idx_quotes_code_cycle
    ON stock_quotes(code, cycle);

CREATE INDEX IF NOT EXISTS idx_quotes_trade_date
    ON stock_quotes(trade_date);

CREATE INDEX IF NOT EXISTS idx_quotes_code_date
    ON stock_quotes(code, trade_date DESC);

-- ==========================================
-- 2. stock_quotes_minute 表唯一索引（支持 ON CONFLICT）
-- ==========================================
-- 分钟线行情唯一约束
CREATE UNIQUE INDEX IF NOT EXISTS idx_minute_quotes_unique
    ON stock_quotes_minute(code, cycle, trade_date, trade_time);

-- stock_quotes_minute 常用查询索引
CREATE INDEX IF NOT EXISTS idx_minute_quotes_code_cycle
    ON stock_quotes_minute(code, cycle);

CREATE INDEX IF NOT EXISTS idx_minute_quotes_trade_date
    ON stock_quotes_minute(trade_date);

CREATE INDEX IF NOT EXISTS idx_minute_quotes_code_date
    ON stock_quotes_minute(code, trade_date DESC);

-- ==========================================
-- 3. stock_indicators 表唯一索引（支持 ON CONFLICT）
-- ==========================================
-- 技术指标唯一约束
CREATE UNIQUE INDEX IF NOT EXISTS idx_indicators_unique
    ON stock_indicators(code, cycle, trade_date, trade_time);

-- stock_indicators 常用查询索引
CREATE INDEX IF NOT EXISTS idx_indicators_code_cycle
    ON stock_indicators(code, cycle);

CREATE INDEX IF NOT EXISTS idx_indicators_trade_date
    ON stock_indicators(trade_date);

CREATE INDEX IF NOT EXISTS idx_indicators_code_date
    ON stock_indicators(code, trade_date DESC);

-- ==========================================
-- 4. stock_basic 表索引
-- ==========================================
CREATE INDEX IF NOT EXISTS idx_stock_basic_code
    ON stock_basic(code);

CREATE INDEX IF NOT EXISTS idx_stock_basic_delist
    ON stock_basic(delist_date)
    WHERE delist_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_stock_basic_exchange
    ON stock_basic(exchange);

-- ==========================================
-- 5. task_progress 表索引
-- ==========================================
CREATE INDEX IF NOT EXISTS idx_task_progress_status
    ON task_progress(status);

CREATE INDEX IF NOT EXISTS idx_task_progress_updated
    ON task_progress(updated_at DESC);

-- ==========================================
-- 6. trade_calendar 表索引
-- ==========================================
CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_calendar_date
    ON trade_calendar(cal_date);

CREATE INDEX IF NOT EXISTS idx_trade_calendar_exchange
    ON trade_calendar(exchange, is_open);

-- ==========================================
-- 7. 清理旧数据优化索引
-- (这些索引对 DELETE 操作至关重要)
-- ==========================================
CREATE INDEX IF NOT EXISTS idx_quotes_cleanup
    ON stock_quotes(trade_date)
    WHERE cycle = '1d';

CREATE INDEX IF NOT EXISTS idx_minute_quotes_cleanup
    ON stock_quotes_minute(trade_date);

-- ==========================================
-- 验证索引创建
-- ==========================================
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
    AND indexname LIKE 'idx_%'
    OR indexname LIKE '%_unique'
ORDER BY tablename, indexname;

-- ==========================================
-- 检查索引大小
-- ==========================================
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;
