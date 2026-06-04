-- ==========================================
-- PostgreSQL 数据库初始化脚本（v3.2 最终封版）
-- ==========================================
-- ⚠️ 重要：本脚本仅用于全新部署（greenfield）
--   已部署的 v3.0 / v3.1 数据库请使用迁移脚本升级：
--     → scripts/migrate_v3_to_v3.2.sql
-- ==========================================
-- 1. 创建股票基本信息表
-- ==========================================
CREATE TABLE IF NOT EXISTS stock_basic (
    code VARCHAR(10) PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    exchange VARCHAR(20),
    industry VARCHAR(100),
    list_date DATE,
    delist_date DATE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 2. 创建股票行情数据表（分区表）
-- ==========================================
-- 兼容生产库结构：保留 trade_date 字段用于分区，trade_datetime 用于精确时间
CREATE TABLE IF NOT EXISTS stock_quotes (
    id SERIAL,
    code VARCHAR(10) NOT NULL,
    cycle VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    trade_datetime TIMESTAMPTZ NOT NULL,
    open NUMERIC(10,2),
    high NUMERIC(10,2),
    low NUMERIC(10,2),
    close NUMERIC(10,2),
    volume BIGINT,
    amount NUMERIC(18,2),
    adjust_type VARCHAR(10) DEFAULT 'qfq',
    pre_close NUMERIC(10,2),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, trade_date)
) PARTITION BY RANGE (trade_date);

ALTER TABLE stock_quotes ADD CONSTRAINT chk_quotes_cycle CHECK (cycle IN ('5m', '15m', '30m', '60m', '1d', '1w', '1m'));
ALTER TABLE stock_quotes ADD CONSTRAINT chk_quotes_adjust_type CHECK (adjust_type IN ('qfq', 'hfq', 'none'));

-- ==========================================
-- 3. 创建行情数据月度分区（2024年~2026年6月示例）
-- ==========================================
DO $$
DECLARE
    y INTEGER;
    m INTEGER;
    start_date DATE;
    end_date DATE;
    part_name TEXT;
BEGIN
    FOR y IN 2024..2026 LOOP
        FOR m IN 1..12 LOOP
            IF y = 2026 AND m > 6 THEN EXIT; END IF;
            
            start_date := make_date(y, m, 1);
            end_date := (start_date + INTERVAL '1 month')::DATE;
            part_name := 'stock_quotes_y' || y || 'm' || LPAD(m::TEXT, 2, '0');
            
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF stock_quotes FOR VALUES FROM (%L) TO (%L)',
                part_name, start_date, end_date
            );
        END LOOP;
    END LOOP;
END;
$$;

-- ==========================================
-- 4. 创建技术指标表（分区表）
-- ==========================================
-- 兼容生产库结构
CREATE TABLE IF NOT EXISTS stock_indicators (
    id SERIAL,
    code VARCHAR(10) NOT NULL,
    cycle VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    ma5 NUMERIC(10,2), ma10 NUMERIC(10,2), ma20 NUMERIC(10,2), ma60 NUMERIC(10,2),
    macd NUMERIC(10,4), dif NUMERIC(10,4), dea NUMERIC(10,4),
    rsi6 NUMERIC(6,2), rsi12 NUMERIC(6,2), rsi24 NUMERIC(6,2),
    kdj_k REAL, kdj_d REAL, kdj_j REAL,
    boll_upper REAL, boll_middle REAL, boll_lower REAL,
    calc_version VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    trade_time TIMESTAMPTZ,
    trade_datetime TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, trade_date)
) PARTITION BY RANGE (trade_date);

ALTER TABLE stock_indicators ADD CONSTRAINT chk_indicators_cycle CHECK (cycle IN ('5m', '15m', '30m', '60m', '1d', '1w', '1m'));

-- ==========================================
-- 5. 创建技术指标月度分区（2024年~2026年6月示例）
-- ==========================================
DO $$
DECLARE
    y INTEGER;
    m INTEGER;
    start_date DATE;
    end_date DATE;
    part_name TEXT;
BEGIN
    FOR y IN 2024..2026 LOOP
        FOR m IN 1..12 LOOP
            IF y = 2026 AND m > 6 THEN EXIT; END IF;
            
            start_date := make_date(y, m, 1);
            end_date := (start_date + INTERVAL '1 month')::DATE;
            part_name := 'stock_indicators_y' || y || 'm' || LPAD(m::TEXT, 2, '0');
            
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF stock_indicators FOR VALUES FROM (%L) TO (%L)',
                part_name, start_date, end_date
            );
        END LOOP;
    END LOOP;
END;
$$;

-- ==========================================
-- 6. 创建脏数据死信表
-- ==========================================
CREATE TABLE IF NOT EXISTS stock_quotes_dirty (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(10),
    cycle VARCHAR(10),
    trade_datetime TIMESTAMPTZ,
    raw_data JSON, -- [RULE-3.2] 降级为 JSON，极速写入
    error_type VARCHAR(50) NOT NULL,
    error_message TEXT NOT NULL,
    error_codes VARCHAR(200),
    source VARCHAR(50),
    fetch_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    resolve_time TIMESTAMPTZ,
    resolve_note TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 7. 创建同步水位线表
-- ==========================================
CREATE TABLE IF NOT EXISTS sync_checkpoints (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(10) NOT NULL,
    cycle VARCHAR(10) NOT NULL,
    last_sync_datetime TIMESTAMPTZ NOT NULL,
    last_continuous_sync_datetime TIMESTAMPTZ, -- [RULE-4.1] 连续水位线
    is_continuous BOOLEAN DEFAULT TRUE,
    sync_status VARCHAR(20) DEFAULT 'success',
    sync_count INTEGER DEFAULT 0,
    fail_reason TEXT,
    task_id VARCHAR(50),
    source VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, cycle)
);

-- ==========================================
-- 8-14. 创建辅助表 (交易日历、任务、字典等)
-- ==========================================
CREATE TABLE IF NOT EXISTS trade_calendar (cal_date DATE PRIMARY KEY, is_open SMALLINT NOT NULL, holiday_name VARCHAR(100), created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS task_progress (id SERIAL PRIMARY KEY, task_name VARCHAR(100) NOT NULL, code VARCHAR(10), status VARCHAR(20) DEFAULT 'pending', progress INTEGER DEFAULT 0, message TEXT, created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS task_metrics (id SERIAL PRIMARY KEY, task VARCHAR(100) NOT NULL, date DATE NOT NULL, stocks_total INTEGER DEFAULT 0, stocks_success INTEGER DEFAULT 0, stocks_fail INTEGER DEFAULT 0, status VARCHAR(20), latency_sec NUMERIC(10, 2), created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, UNIQUE(task, date));
CREATE TABLE IF NOT EXISTS stock_fundamental_pit (id SERIAL PRIMARY KEY, code VARCHAR(10) NOT NULL, report_date DATE NOT NULL, announce_date DATE NOT NULL, net_profit NUMERIC(18, 2), revenue NUMERIC(18, 2), pe_ttm NUMERIC(10, 2), pb NUMERIC(10, 2), eps NUMERIC(10, 4), roe NUMERIC(10, 2), data_version VARCHAR(10) DEFAULT 'v1', created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, UNIQUE(code, report_date, announce_date));
CREATE TABLE IF NOT EXISTS data_dict (id SERIAL PRIMARY KEY, table_name VARCHAR(50) NOT NULL, column_name VARCHAR(50), column_type VARCHAR(50), description TEXT, constraint VARCHAR(100), default_value TEXT, is_required BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS data_error_log (id SERIAL PRIMARY KEY, code VARCHAR(10), trade_datetime TIMESTAMPTZ, error_type VARCHAR(50) NOT NULL, error_message TEXT, raw_data JSONB, created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS data_audit_log (id SERIAL PRIMARY KEY, operator VARCHAR(50) NOT NULL, operation_type VARCHAR(20) NOT NULL, table_name VARCHAR(50) NOT NULL, data_range JSONB, record_count INTEGER, operation_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, description TEXT);

-- ==========================================
-- 15. 创建索引
-- ==========================================
-- stock_quotes 索引
CREATE INDEX IF NOT EXISTS idx_quotes_code_cycle_time_desc ON stock_quotes(code, cycle, trade_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_quotes_code_cycle_time ON stock_quotes(code, cycle, trade_datetime);
CREATE INDEX IF NOT EXISTS idx_quotes_code_time ON stock_quotes(code, trade_datetime); -- [ACTION-4] 跨周期时序扫描专用
CREATE INDEX IF NOT EXISTS idx_quotes_cycle_time ON stock_quotes(cycle, trade_datetime);

-- stock_indicators 索引
CREATE INDEX IF NOT EXISTS idx_indicators_code_cycle_time_desc ON stock_indicators(code, cycle, trade_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_indicators_code_cycle_time ON stock_indicators(code, cycle, trade_datetime);
CREATE INDEX IF NOT EXISTS idx_indicators_code_time ON stock_indicators(code, trade_datetime); -- [ACTION-4] 跨周期时序扫描专用

-- 辅助表索引
CREATE INDEX IF NOT EXISTS idx_dirty_code_cycle ON stock_quotes_dirty(code, cycle);
CREATE INDEX IF NOT EXISTS idx_dirty_error_type ON stock_quotes_dirty(error_type);
CREATE INDEX IF NOT EXISTS idx_dirty_status ON stock_quotes_dirty(status);
CREATE INDEX IF NOT EXISTS idx_checkpoint_status ON sync_checkpoints(sync_status);

-- ==========================================
-- 16-18. 约束、触发器与字典注册
-- ==========================================
ALTER TABLE trade_calendar ADD CONSTRAINT IF NOT EXISTS chk_is_open CHECK (is_open IN (0, 1));

CREATE OR REPLACE FUNCTION fn_update_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = CURRENT_TIMESTAMP; RETURN NEW; END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    tbl TEXT;
    v_pg_version INTEGER;
    v_is_partitioned BOOLEAN;
BEGIN
    v_pg_version := current_setting('server_version_num')::INTEGER;
    FOR tbl IN SELECT table_name FROM information_schema.columns WHERE column_name = 'updated_at' AND table_schema = 'public' LOOP
        SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_inherits i ON c.oid = i.inhrelid WHERE c.relname = tbl) INTO v_is_partitioned;
        
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_updated_at ON %I;', tbl, tbl);
        EXECUTE format('CREATE TRIGGER trg_%s_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();', tbl, tbl);
        
        IF v_pg_version < 110000 AND v_is_partitioned THEN
            FOR tbl IN SELECT child.relname FROM pg_inherits JOIN pg_class parent ON pg_inherits.inhparent = parent.oid JOIN pg_class child ON pg_inherits.inhrelid = child.oid WHERE parent.relname = tbl LOOP
                EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_updated_at ON %I;', tbl, tbl);
                EXECUTE format('CREATE TRIGGER trg_%s_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();', tbl, tbl);
            END LOOP;
        END IF;
    END LOOP;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_dict_table_col') THEN
        ALTER TABLE data_dict ADD CONSTRAINT uq_dict_table_col UNIQUE (table_name, column_name);
    END IF;
END;
$$;

INSERT INTO data_dict (table_name, column_name, column_type, description, constraint, default_value, is_required)
SELECT table_name, column_name, data_type, NULL, CASE WHEN is_nullable = 'NO' THEN 'NOT NULL' ELSE NULL END, column_default, is_nullable = 'NO'
FROM information_schema.columns WHERE table_schema = 'public'
ON CONFLICT ON CONSTRAINT uq_dict_table_col DO NOTHING;

SELECT 'Database initialization completed successfully!' AS message;