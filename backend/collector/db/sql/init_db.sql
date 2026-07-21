-- ==========================================
-- PostgreSQL 数据库初始化脚本（v5.0）
-- ==========================================
-- ⚠️ 重要：本脚本仅用于全新部署（greenfield）
--   已部署的旧版本数据库请使用迁移脚本升级：
--     → backend/collector/db/sql/migrate_v3_to_v3.2.sql
-- ==========================================
-- 版本记录
-- v4.0 (2026-06-08): 分区改为年度方案；新增 stock_adj_factor、stock_daily_snapshot、
--   trade_signals、stock_list、stock_quotes_minute 表
-- v4.1 (2026-06-10): 新增 user_watchlist 表（自选股功能）
-- v4.2 (2026-07-01): 新增 ma60、MACD 金叉死叉、14 技术形态列
-- v5.0 (2026-07-09): 合并所有迁移变更至基线；新增 task_run_log 表；
--   stock_indicators 新增 BOLL 列；user_watchlist 支持多组；
--   stock_quotes/stock_indicators 主键改为 (code, cycle, trade_datetime)
-- ==========================================
-- 幂等性：本脚本可重复执行，所有 CREATE/ALTER 均使用 IF NOT EXISTS 或条件判断
-- ==========================================

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
-- 2. 创建股票列表表（来自 Baostock/Tushare 元数据）
-- ==========================================
CREATE TABLE IF NOT EXISTS stock_list (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(10),
    industry VARCHAR(100),
    market VARCHAR(20),
    market_name VARCHAR(50),
    list_date DATE,
    out_date DATE,
    type VARCHAR(20),
    status VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 3. 创建股票行情数据表（分区表-年度分区）
-- 主键: (code, cycle, trade_datetime) — 移除冗余 id 列
-- ==========================================
CREATE TABLE IF NOT EXISTS stock_quotes (
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
    PRIMARY KEY (code, cycle, trade_datetime)
) PARTITION BY RANGE (trade_date);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_quotes_cycle') THEN
        ALTER TABLE stock_quotes ADD CONSTRAINT chk_quotes_cycle CHECK (cycle IN ('5m', '15m', '30m', '60m', '1d', '1w', '1m'));
    END IF;
END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_quotes_adjust_type') THEN
        ALTER TABLE stock_quotes ADD CONSTRAINT chk_quotes_adjust_type CHECK (adjust_type IN ('qfq', 'hfq', 'none'));
    END IF;
END $$;

-- 创建年度分区（1990~2027年，覆盖A股完整历史）
DO $$
DECLARE
    y INTEGER;
    start_date DATE;
    end_date DATE;
BEGIN
    FOR y IN 1990..2027 LOOP
        start_date := make_date(y, 1, 1);
        end_date := make_date(y + 1, 1, 1);
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS stock_quotes_%s PARTITION OF stock_quotes FOR VALUES FROM (%L) TO (%L)',
            y, start_date, end_date
        );
    END LOOP;
END;
$$;

-- ==========================================
-- 4. 创建分钟线数据表（分区表-月度分区）
-- ==========================================
CREATE TABLE IF NOT EXISTS stock_quotes_minute (
    id BIGSERIAL,
    code VARCHAR(10) NOT NULL,
    cycle VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    trade_time TIMESTAMPTZ NOT NULL,
    open NUMERIC(10, 2),
    high NUMERIC(10, 2),
    low NUMERIC(10, 2),
    close NUMERIC(10, 2),
    volume BIGINT,
    amount NUMERIC(18, 2),
    vwap NUMERIC(10, 4),
    adjust_type VARCHAR(10) DEFAULT 'qfq',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(id, trade_date)
) PARTITION BY RANGE (trade_date);

-- 创建月度分区（2025~2026年）
DO $$
DECLARE
    y INTEGER;
    m INTEGER;
    start_date DATE;
    end_date DATE;
    part_name TEXT;
BEGIN
    FOR y IN 2025..2026 LOOP
        FOR m IN 1..12 LOOP
            start_date := make_date(y, m, 1);
            end_date := (start_date + INTERVAL '1 month')::DATE;
            part_name := 'stock_quotes_minute_' || y || LPAD(m::TEXT, 2, '0');
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF stock_quotes_minute FOR VALUES FROM (%L) TO (%L)',
                part_name, start_date, end_date
            );
        END LOOP;
    END LOOP;
END;
$$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_minute_cycle') THEN
        ALTER TABLE stock_quotes_minute ADD CONSTRAINT chk_minute_cycle CHECK (cycle IN ('5m', '15m', '30m', '60m'));
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uk_sq_min_code_cycle_time
ON stock_quotes_minute (code, cycle, trade_date, trade_time);

-- ==========================================
-- 5. 创建技术指标表（分区表-年度分区）
-- 主键: (code, cycle, trade_datetime) — 移除冗余 id 列
-- 含 BOLL 列（通过迁移脚本 migrate_add_boll_columns.sql 添加）
-- ==========================================
CREATE TABLE IF NOT EXISTS stock_indicators (
    code VARCHAR(10) NOT NULL,
    cycle VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    trade_datetime TIMESTAMPTZ NOT NULL,
    ma5 NUMERIC(10,2), ma10 NUMERIC(10,2), ma20 NUMERIC(10,2), ma60 NUMERIC(10,2),
    macd NUMERIC(10,4), dif NUMERIC(10,4), dea NUMERIC(10,4),
    rsi6 NUMERIC(6,2), rsi12 NUMERIC(6,2), rsi24 NUMERIC(6,2),
    kdj_k REAL, kdj_d REAL, kdj_j REAL,
    boll_upper NUMERIC(10, 2), boll_mid NUMERIC(10, 2), boll_lower NUMERIC(10, 2),
    ema5 NUMERIC(12, 4) DEFAULT NULL, ema10 NUMERIC(12, 4) DEFAULT NULL,
    ema20 NUMERIC(12, 4) DEFAULT NULL, ema60 NUMERIC(12, 4) DEFAULT NULL,
    atr NUMERIC(12, 4) DEFAULT NULL,
    vol_ratio NUMERIC(12, 4) DEFAULT NULL,
    turnover_rate NUMERIC(12, 4) DEFAULT NULL,
    calc_version VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    trade_time TIMESTAMPTZ,
    PRIMARY KEY (code, cycle, trade_datetime)
) PARTITION BY RANGE (trade_date);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_indicators_cycle') THEN
        ALTER TABLE stock_indicators ADD CONSTRAINT chk_indicators_cycle CHECK (cycle IN ('5m', '15m', '30m', '60m', '1d', '1w', '1m'));
    END IF;
END $$;

-- 创建年度分区（2015~2027年）
DO $$
DECLARE
    y INTEGER;
    start_date DATE;
    end_date DATE;
BEGIN
    FOR y IN 2015..2027 LOOP
        start_date := make_date(y, 1, 1);
        end_date := make_date(y + 1, 1, 1);
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS stock_indicators_%s PARTITION OF stock_indicators FOR VALUES FROM (%L) TO (%L)',
            y, start_date, end_date
        );
    END LOOP;
END;
$$;

-- ==========================================
-- 6. 创建复权因子表
-- ==========================================
CREATE TABLE IF NOT EXISTS stock_adj_factor (
    code VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    adj_factor NUMERIC(10, 4) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, trade_date)
);

-- ==========================================
-- 7. 创建股票每日快照宽表
-- 含所有迁移变更：技术形态列、ma60、MACD 金叉死叉
-- ==========================================
CREATE TABLE IF NOT EXISTS stock_daily_snapshot (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    listed_board VARCHAR(20),
    industry VARCHAR(50),
    sub_industry VARCHAR(50),
    trade_date DATE NOT NULL,
    open NUMERIC(10, 2),
    high NUMERIC(10, 2),
    low NUMERIC(10, 2),
    close NUMERIC(10, 2),
    pre_close NUMERIC(10, 2),
    volume BIGINT,
    amount NUMERIC(18, 2),
    adjust_type VARCHAR(10) DEFAULT 'qfq',
    change NUMERIC(10, 2),
    change_pct NUMERIC(8, 2),
    turnover_rate NUMERIC(8, 2),
    pe NUMERIC(10, 2),
    pb NUMERIC(10, 2),
    market_cap NUMERIC(18, 2),
    circ_mv NUMERIC(18, 2),
    ma5 NUMERIC(10, 2),
    ma10 NUMERIC(10, 2),
    ma20 NUMERIC(10, 2),
    v_ma5 BIGINT,
    rsi_6 NUMERIC(6, 2),
    macd NUMERIC(10, 4),
    boll_upper NUMERIC(10, 2),
    boll_mid NUMERIC(10, 2),
    boll_lower NUMERIC(10, 2),
    -- 以下为迁移添加的列
    ma60 NUMERIC(10,3),
    is_macd_golden_cross BOOLEAN DEFAULT FALSE,
    is_macd_dead_cross BOOLEAN DEFAULT FALSE,
    -- MA patterns (migrate_add_tech_patterns.sql)
    ma_long_align BOOLEAN DEFAULT FALSE,
    ma_short_align BOOLEAN DEFAULT FALSE,
    -- MACD patterns
    macd_low_golden_cross BOOLEAN DEFAULT FALSE,
    macd_bottom_divergence BOOLEAN DEFAULT FALSE,
    macd_high_death_cross BOOLEAN DEFAULT FALSE,
    macd_top_divergence BOOLEAN DEFAULT FALSE,
    -- BOLL patterns
    boll_break_upper BOOLEAN DEFAULT FALSE,
    boll_break_middle_up BOOLEAN DEFAULT FALSE,
    boll_break_middle_down BOOLEAN DEFAULT FALSE,
    boll_break_lower BOOLEAN DEFAULT FALSE,
    -- RSI patterns
    rsi_low_golden_cross BOOLEAN DEFAULT FALSE,
    rsi_high_death_cross BOOLEAN DEFAULT FALSE,
    rsi_top_divergence BOOLEAN DEFAULT FALSE,
    rsi_bottom_divergence BOOLEAN DEFAULT FALSE,
    -- 状态标记
    is_st BOOLEAN DEFAULT FALSE,
    is_new BOOLEAN DEFAULT FALSE,
    limit_up BOOLEAN DEFAULT FALSE,
    limit_down BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (code, trade_date)
);

COMMENT ON TABLE stock_daily_snapshot IS '股票每日快照宽表（盘后ETL物理化合并）';

-- ==========================================
-- 8. 创建交易信号表
-- ==========================================
CREATE TABLE IF NOT EXISTS trade_signals (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) NOT NULL,
    cycle VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    signal_type VARCHAR(50) NOT NULL,
    signal_value NUMERIC(10, 4),
    signal_strength INTEGER,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, cycle, trade_date, signal_type)
);

-- ==========================================
-- 9. 创建脏数据死信表
-- ==========================================
CREATE TABLE IF NOT EXISTS stock_quotes_dirty (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(10),
    cycle VARCHAR(10),
    trade_datetime TIMESTAMPTZ,
    raw_data JSON,
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
-- 10. 创建同步水位线表
-- ==========================================
CREATE TABLE IF NOT EXISTS sync_checkpoints (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(10) NOT NULL,
    cycle VARCHAR(10) NOT NULL,
    last_sync_datetime TIMESTAMPTZ NOT NULL,
    last_continuous_sync_datetime TIMESTAMPTZ,
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
-- 11-17. 创建辅助表 (交易日历、任务、字典等)
-- ==========================================
CREATE TABLE IF NOT EXISTS trade_calendar (cal_date DATE PRIMARY KEY, is_open SMALLINT NOT NULL, holiday_name VARCHAR(100), created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS task_progress (id SERIAL PRIMARY KEY, task_name VARCHAR(100) NOT NULL, code VARCHAR(10), status VARCHAR(20) DEFAULT 'pending', progress INTEGER DEFAULT 0, message TEXT, created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS task_metrics (id SERIAL PRIMARY KEY, task VARCHAR(100) NOT NULL, date DATE NOT NULL, stocks_total INTEGER DEFAULT 0, stocks_success INTEGER DEFAULT 0, stocks_fail INTEGER DEFAULT 0, status VARCHAR(20), latency_sec NUMERIC(10, 2), created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, UNIQUE(task, date));
CREATE TABLE IF NOT EXISTS stock_fundamental_pit (id SERIAL PRIMARY KEY, code VARCHAR(10) NOT NULL, report_date DATE NOT NULL, announce_date DATE NOT NULL, net_profit NUMERIC(18, 2), revenue NUMERIC(18, 2), pe_ttm NUMERIC(10, 2), pb NUMERIC(10, 2), eps NUMERIC(10, 4), roe NUMERIC(10, 2), data_version VARCHAR(10) DEFAULT 'v1', created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, UNIQUE(code, report_date, announce_date));
CREATE TABLE IF NOT EXISTS data_dict (id SERIAL PRIMARY KEY, table_name VARCHAR(50) NOT NULL, column_name VARCHAR(50), column_type VARCHAR(50), description TEXT, "constraint" VARCHAR(100), default_value TEXT, is_required BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS data_error_log (id SERIAL PRIMARY KEY, code VARCHAR(10), trade_datetime TIMESTAMPTZ, error_type VARCHAR(50) NOT NULL, error_message TEXT, raw_data JSONB, created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS data_audit_log (id SERIAL PRIMARY KEY, operator VARCHAR(50) NOT NULL, operation_type VARCHAR(20) NOT NULL, table_name VARCHAR(50) NOT NULL, data_range JSONB, record_count INTEGER, operation_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, description TEXT);

-- ==========================================
-- 18. ETL 任务运行监控表（task_run_log）
-- 由 migrate_create_task_run_log.sql 引入
-- ==========================================
CREATE TABLE IF NOT EXISTS task_run_log (
    id              BIGSERIAL PRIMARY KEY,
    task_name       VARCHAR(100) NOT NULL,
    stage           INT NOT NULL CHECK (stage BETWEEN 0 AND 11),
    start_time      TIMESTAMP NOT NULL,
    end_time        TIMESTAMP,
    status          VARCHAR(20) NOT NULL CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    exit_code       INT,
    error_message   TEXT,
    rows_affected   BIGINT,
    data_date       DATE,
    batch_id        VARCHAR(32),
    extra_metrics   JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ==========================================
-- 19. 创建索引
-- ==========================================
-- stock_quotes 索引
CREATE INDEX IF NOT EXISTS idx_quotes_code_cycle_time_desc ON stock_quotes(code, cycle, trade_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_quotes_code_cycle_time ON stock_quotes(code, cycle, trade_datetime);
CREATE INDEX IF NOT EXISTS idx_quotes_code_time ON stock_quotes(code, trade_datetime);
CREATE INDEX IF NOT EXISTS idx_quotes_cycle_time ON stock_quotes(cycle, trade_datetime);

-- stock_quotes_minute 索引
CREATE INDEX IF NOT EXISTS idx_quotes_minute_code_cycle ON stock_quotes_minute(code, cycle);
CREATE INDEX IF NOT EXISTS idx_quotes_minute_code_date ON stock_quotes_minute(code, trade_date);
CREATE INDEX IF NOT EXISTS idx_quotes_minute_trade_time ON stock_quotes_minute(trade_time);

-- stock_indicators 索引
CREATE INDEX IF NOT EXISTS idx_indicators_code_cycle_time_desc ON stock_indicators(code, cycle, trade_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_indicators_code_cycle_time ON stock_indicators(code, cycle, trade_datetime);
CREATE INDEX IF NOT EXISTS idx_indicators_code_time ON stock_indicators(code, trade_datetime);

-- stock_daily_snapshot 索引
CREATE INDEX IF NOT EXISTS idx_snapshot_code_date ON stock_daily_snapshot (code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_snapshot_date ON stock_daily_snapshot (trade_date);
CREATE INDEX IF NOT EXISTS idx_snapshot_industry ON stock_daily_snapshot (industry);
CREATE INDEX IF NOT EXISTS idx_snapshot_change_pct ON stock_daily_snapshot (trade_date, change_pct DESC);
CREATE INDEX IF NOT EXISTS idx_snapshot_pe ON stock_daily_snapshot (trade_date, pe);
CREATE INDEX IF NOT EXISTS idx_snapshot_pb ON stock_daily_snapshot (trade_date, pb);

-- 辅助表索引
CREATE INDEX IF NOT EXISTS idx_dirty_code_cycle ON stock_quotes_dirty(code, cycle);
CREATE INDEX IF NOT EXISTS idx_dirty_error_type ON stock_quotes_dirty(error_type);
CREATE INDEX IF NOT EXISTS idx_dirty_status ON stock_quotes_dirty(status);
CREATE INDEX IF NOT EXISTS idx_checkpoint_status ON sync_checkpoints(sync_status);
CREATE INDEX IF NOT EXISTS idx_trade_signals_trade_date ON trade_signals(trade_date);
CREATE INDEX IF NOT EXISTS idx_trade_signals_signal_type ON trade_signals(signal_type);

-- task_run_log 索引
CREATE INDEX IF NOT EXISTS idx_task_run_log_start_time ON task_run_log (start_time DESC);
CREATE INDEX IF NOT EXISTS idx_task_run_log_status ON task_run_log (status);
CREATE INDEX IF NOT EXISTS idx_task_run_log_stage ON task_run_log (stage);
CREATE INDEX IF NOT EXISTS idx_task_run_log_data_date ON task_run_log(data_date);
CREATE INDEX IF NOT EXISTS idx_task_run_log_batch_id ON task_run_log(batch_id);

-- ==========================================
-- 20. 用户自选股表（user_watchlist）
-- 支持多组：UNIQUE 约束为 (user_id, code, group_name)
-- 含 is_system 标记（系统分组不可删除）
-- ==========================================
CREATE TABLE IF NOT EXISTS user_watchlist (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    code VARCHAR(10) NOT NULL,
    group_name VARCHAR(64) DEFAULT '默认分组',
    sort_order INTEGER DEFAULT 0,
    is_system BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_watchlist_user_code_group
    ON user_watchlist(user_id, code, group_name);
CREATE INDEX IF NOT EXISTS idx_user_watchlist_user_id ON user_watchlist(user_id);

-- ==========================================
-- 21-23. 约束、触发器与字典注册
-- ==========================================
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_is_open') THEN
        ALTER TABLE trade_calendar ADD CONSTRAINT chk_is_open CHECK (is_open IN (0, 1));
    END IF;
END $$;

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

INSERT INTO data_dict (table_name, column_name, column_type, description, "constraint", default_value, is_required)
SELECT table_name, column_name, data_type, NULL, CASE WHEN is_nullable = 'NO' THEN 'NOT NULL' ELSE NULL END, column_default, is_nullable = 'NO'
FROM information_schema.columns WHERE table_schema = 'public'
ON CONFLICT ON CONSTRAINT uq_dict_table_col DO NOTHING;

SELECT 'Database initialization completed successfully!' AS message;