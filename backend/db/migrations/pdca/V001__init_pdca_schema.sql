-- ============================================================
-- PDCA Schema V001: 初始化全部核心表、索引、约束、触发器
-- 创建日期：2026-08-10
-- 回滚：DROP SCHEMA IF EXISTS pdca CASCADE;
-- ============================================================

BEGIN;

-- 2.1 创建 Schema
CREATE SCHEMA IF NOT EXISTS pdca;

-- 2.2 创建枚举类型（替代 VARCHAR CHECK，更严格）
DO $$ BEGIN
    CREATE TYPE pdca.cycle_status     AS ENUM ('PLAN', 'DO', 'CHECK', 'ACT');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.abc_tag          AS ENUM ('A', 'B', 'C');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.trade_grade      AS ENUM ('A', 'B', 'C');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.long_short       AS ENUM ('long', 'short');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.log_type_enum    AS ENUM ('normal', 'violation');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.violation_type_enum AS ENUM (
        'C_class_trade', 'over_position', 'no_plan_trade', 'cancel_stop_loss'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.plan_status_enum AS ENUM ('draft', 'active', 'executed', 'expired', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.report_status_enum AS ENUM ('draft', 'published');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.severity_enum    AS ENUM ('low', 'medium', 'high', 'critical');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.trigger_source_enum AS ENUM (
        'system_plan', 'news', 'impulse', 'scanner', 'manual'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.exit_reason_enum AS ENUM (
        'take_profit', 'stop_loss', 'impulsive', 'plan_expired', 'others'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.order_type_enum AS ENUM (
        'limit', 'market', 'stop'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pdca.instrument_type_enum AS ENUM (
        'stock', 'futures', 'forex', 'option'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;


-- ============================================================
-- 2.3 核心业务表
-- ============================================================

-- 表0: 账户主表（多账户支持的基础）
CREATE TABLE pdca.account (
    id              SERIAL PRIMARY KEY,
    account_name    VARCHAR(64)  NOT NULL,
    account_type    VARCHAR(32)  DEFAULT 'stock',   -- 'stock' / 'futures' / 'forex'
    currency        VARCHAR(8)   DEFAULT 'CNY',
    initial_capital NUMERIC(16,2) NOT NULL,
    is_active       BOOLEAN      DEFAULT TRUE,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- 表1: 系统配置 & 规则版本表
CREATE TABLE pdca.system_config (
    id              SERIAL PRIMARY KEY,
    config_key      VARCHAR(64)  NOT NULL,
    config_value    TEXT         NOT NULL,
    numeric_value   NUMERIC,            -- 数值型配置（阈值、百分比）
    bool_value      BOOLEAN,            -- 布尔型配置
    description     TEXT,
    version         VARCHAR(16)  NOT NULL,
    modified_at     TIMESTAMPTZ  DEFAULT NOW(),
    modified_by     VARCHAR(64),
    modify_reason   TEXT         NOT NULL,
    CONSTRAINT uq_config_key_version UNIQUE (config_key, version)
);

-- 表2: 账户资金快照表（每日净值 + 出入金记录）
CREATE TABLE pdca.account_snapshot (
    id                  SERIAL PRIMARY KEY,
    account_id          INT          DEFAULT 1,     -- 预留多账户
    snapshot_date       DATE         NOT NULL,
    total_asset         NUMERIC(16,2) NOT NULL,     -- 账户总资产
    available_cash      NUMERIC(16,2) NOT NULL,     -- 可用资金
    position_value      NUMERIC(16,2) NOT NULL,     -- 持仓市值
    deposit             NUMERIC(16,2) DEFAULT 0,    -- 当日入金
    withdrawal          NUMERIC(16,2) DEFAULT 0,    -- 当日出金
    net_deposit         NUMERIC(16,2) GENERATED ALWAYS AS
                            (deposit - withdrawal) STORED,  -- 净出入金（计算列）
    realized_pnl        NUMERIC(16,2) DEFAULT 0,    -- 当日已实现盈亏
    adjusted_nav        NUMERIC(16,2),              -- 调整后净值（剔除出入金影响）
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT uq_account_snapshot UNIQUE (account_id, snapshot_date),
    CONSTRAINT chk_asset_positive CHECK (total_asset >= 0 AND available_cash >= 0 AND position_value >= 0)
);

-- 表3: PDCA 周期主表
CREATE TABLE pdca.pdca_cycle (
    id              SERIAL PRIMARY KEY,
    account_id      INT          DEFAULT 1,
    prev_cycle_id   INT,                            -- 自引用：上一轮PDCA周期ID
    cycle_type      VARCHAR(16)  NOT NULL,          -- 'week' / 'month'
    cycle_name      VARCHAR(64)  NOT NULL,
    status          pdca.cycle_status NOT NULL DEFAULT 'PLAN',
    start_date      DATE         NOT NULL,
    end_date        DATE         NOT NULL,
    goal_text       TEXT,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT uq_cycle_name UNIQUE (cycle_type, cycle_name),
    CONSTRAINT chk_cycle_date CHECK (start_date <= end_date),
    CONSTRAINT fk_prev_cycle FOREIGN KEY (prev_cycle_id)
        REFERENCES pdca.pdca_cycle(id) ON DELETE SET NULL
);

-- 表4: 标的 ABC 分类台账
CREATE TABLE pdca.security_tag (
    id              SERIAL PRIMARY KEY,
    account_id      INT          DEFAULT 1,
    code            VARCHAR(32)  NOT NULL,          -- 股票/品种代码
    security_name   VARCHAR(128),
    tag             pdca.abc_tag NOT NULL,
    auto_suggest_tag pdca.abc_tag,                  -- 系统自动推荐，人工可覆盖
    note            TEXT,
    updated_at      TIMESTAMPTZ  DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,                    -- 软删除
    CONSTRAINT uq_security_tag_code UNIQUE (code)
);

-- 表5: 交易计划模板表
CREATE TABLE pdca.plan_template (
    id              SERIAL PRIMARY KEY,
    template_name   VARCHAR(64)  NOT NULL UNIQUE,
    template_type   VARCHAR(16)  NOT NULL,          -- 'short_term' / 'mid_term' / 'long_term'
    required_fields TEXT[]       NOT NULL,          -- 必填字段列表
    default_values  JSONB,                          -- 字段默认值
    is_system       BOOLEAN      DEFAULT FALSE,     -- 是否为系统内置模板
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- 表6: 交易计划表
CREATE TABLE pdca.trading_plan (
    id              SERIAL PRIMARY KEY,
    account_id      INT          DEFAULT 1,
    pdca_cycle_id   INT          NOT NULL,
    template_id     INT,                            -- 关联模板
    code            VARCHAR(32)  NOT NULL,
    security_name   VARCHAR(128),
    instrument_type pdca.instrument_type_enum DEFAULT 'stock',
    long_short      pdca.long_short NOT NULL,
    plan_status     pdca.plan_status_enum DEFAULT 'draft',
    weekly_view     TEXT         NOT NULL,          -- 周线分析（必填）
    daily_view      TEXT         NOT NULL,          -- 日线分析（必填）
    entry_price     NUMERIC(12,4) NOT NULL,
    stop_loss_price NUMERIC(12,4) NOT NULL,
    target_price    NUMERIC(12,4),
    max_risk_rate   NUMERIC(6,4)  NOT NULL,         -- 本笔计划风险占账户比例
    plan_quantity   INT          NOT NULL,
    abort_condition TEXT,
    is_valid        BOOLEAN      DEFAULT TRUE,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT chk_risk_rate CHECK (max_risk_rate > 0 AND max_risk_rate <= 1),
    CONSTRAINT chk_quantity_positive CHECK (plan_quantity > 0),
    CONSTRAINT chk_plan_stop_loss CHECK (
        (long_short = 'long'  AND stop_loss_price < entry_price) OR
        (long_short = 'short' AND stop_loss_price > entry_price)
    ),
    CONSTRAINT fk_plan_cycle FOREIGN KEY (pdca_cycle_id)
        REFERENCES pdca.pdca_cycle(id) ON DELETE RESTRICT,
    CONSTRAINT fk_plan_template FOREIGN KEY (template_id)
        REFERENCES pdca.plan_template(id) ON DELETE SET NULL,
    CONSTRAINT fk_plan_account FOREIGN KEY (account_id)
        REFERENCES pdca.account(id) ON DELETE RESTRICT
);

-- 表7: 券商适配器配置表
CREATE TABLE pdca.broker_adapter (
    id              SERIAL PRIMARY KEY,
    broker_name     VARCHAR(64)  NOT NULL UNIQUE,
    display_name    VARCHAR(128) NOT NULL,
    is_active       BOOLEAN      DEFAULT TRUE,
    column_mapping  JSONB        NOT NULL,          -- Excel列名 → 数据库字段映射
    date_format     VARCHAR(32)  DEFAULT 'YYYY-MM-DD',
    skip_rows       INT          DEFAULT 0,         -- 跳过表头行数
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- 表8: 逐笔交易电子台账
CREATE TABLE pdca.trading_record (
    id              SERIAL PRIMARY KEY,
    account_id      INT          DEFAULT 1,
    pdca_cycle_id   INT          NOT NULL,
    trading_plan_id INT,                            -- NULL = 无计划交易（违规）
    code            VARCHAR(32)  NOT NULL,
    security_name   VARCHAR(128),
    instrument_type pdca.instrument_type_enum DEFAULT 'stock',
    long_short      pdca.long_short NOT NULL,
    order_type      pdca.order_type_enum DEFAULT 'limit',
    entry_date      DATE         NOT NULL,
    exit_date       DATE,
    entry_price     NUMERIC(12,4) NOT NULL,
    exit_price      NUMERIC(12,4),
    quantity        INT          NOT NULL,
    commission_entry NUMERIC(12,4) DEFAULT 0,
    commission_exit  NUMERIC(12,4) DEFAULT 0,
    slip_point      NUMERIC(12,4) DEFAULT 0,
    channel_height  NUMERIC(12,4),                  -- 价格通道高度，用于打分
    gross_profit    NUMERIC(12,4),                  -- 毛盈亏（计算字段，应用层写入）
    entry_score     NUMERIC(5,2),                   -- 进场得分 0-100
    exit_score      NUMERIC(5,2),                   -- 出场得分 0-100
    trade_score     NUMERIC(5,2),                   -- 交易总得分 0-100
    trade_grade     pdca.trade_grade,               -- A/B/C
    trigger_source  pdca.trigger_source_enum,
    actual_stop_loss NUMERIC(12,4),
    exit_reason     pdca.exit_reason_enum,          -- 出场原因
    settlement_currency VARCHAR(8) DEFAULT 'CNY',
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT chk_quantity_pos CHECK (quantity > 0),
    CONSTRAINT chk_entry_date CHECK (exit_date IS NULL OR exit_date >= entry_date),
    CONSTRAINT chk_entry_score CHECK (entry_score IS NULL OR (entry_score BETWEEN 0 AND 100)),
    CONSTRAINT chk_exit_score  CHECK (exit_score  IS NULL OR (exit_score  BETWEEN 0 AND 100)),
    CONSTRAINT chk_trade_score CHECK (trade_score IS NULL OR (trade_score BETWEEN 0 AND 100)),
    CONSTRAINT fk_record_cycle FOREIGN KEY (pdca_cycle_id)
        REFERENCES pdca.pdca_cycle(id) ON DELETE RESTRICT,
    CONSTRAINT fk_record_plan FOREIGN KEY (trading_plan_id)
        REFERENCES pdca.trading_plan(id) ON DELETE SET NULL,
    CONSTRAINT fk_record_account FOREIGN KEY (account_id)
        REFERENCES pdca.account(id) ON DELETE RESTRICT
);

-- 表9: 行为 & 违规日志表
CREATE TABLE pdca.behavior_log (
    id                SERIAL PRIMARY KEY,
    account_id        INT          DEFAULT 1,
    pdca_cycle_id     INT          NOT NULL,
    trading_record_id INT,
    log_type          pdca.log_type_enum NOT NULL,
    violation_type    pdca.violation_type_enum,
    severity          pdca.severity_enum DEFAULT 'medium',
    log_content       TEXT         NOT NULL,
    happened_at       TIMESTAMPTZ  NOT NULL,
    created_at        TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT fk_blog_cycle FOREIGN KEY (pdca_cycle_id)
        REFERENCES pdca.pdca_cycle(id) ON DELETE CASCADE,
    CONSTRAINT fk_blog_record FOREIGN KEY (trading_record_id)
        REFERENCES pdca.trading_record(id) ON DELETE SET NULL
);

-- 表10: 交易日记表
CREATE TABLE pdca.trading_diary (
    id                  SERIAL PRIMARY KEY,
    account_id          INT          DEFAULT 1,
    trading_record_id   INT,
    pdca_cycle_id       INT          NOT NULL,
    emotion_note        TEXT,
    review_text         TEXT         NOT NULL,
    attach_file_paths   TEXT[],
    three_month_review_done BOOLEAN  DEFAULT FALSE,
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT fk_diary_record FOREIGN KEY (trading_record_id)
        REFERENCES pdca.trading_record(id) ON DELETE SET NULL,
    CONSTRAINT fk_diary_cycle FOREIGN KEY (pdca_cycle_id)
        REFERENCES pdca.pdca_cycle(id) ON DELETE CASCADE
);

-- 表11: Check 复盘报告表
CREATE TABLE pdca.pdca_check_report (
    id                  SERIAL PRIMARY KEY,
    account_id          INT          DEFAULT 1,
    pdca_cycle_id       INT          UNIQUE NOT NULL,
    report_status       pdca.report_status_enum DEFAULT 'draft',
    total_trade_count   INT,
    complete_by_plan_count INT,
    execution_rate      NUMERIC(6,2),
    win_rate            NUMERIC(6,2),
    profit_loss_ratio   NUMERIC(8,4),
    avg_entry_score     NUMERIC(6,2),
    avg_exit_score      NUMERIC(6,2),
    avg_trade_score     NUMERIC(6,2),
    max_drawdown        NUMERIC(8,4),
    violation_total     INT,
    report_content      TEXT,
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT chk_execution_rate CHECK (execution_rate IS NULL OR (execution_rate BETWEEN 0 AND 100)),
    CONSTRAINT chk_win_rate       CHECK (win_rate       IS NULL OR (win_rate       BETWEEN 0 AND 100)),
    CONSTRAINT fk_report_cycle FOREIGN KEY (pdca_cycle_id)
        REFERENCES pdca.pdca_cycle(id) ON DELETE RESTRICT
);

-- 表12: Act 迭代处理记录表
CREATE TABLE pdca.pdca_act_record (
    id                      SERIAL PRIMARY KEY,
    account_id              INT          DEFAULT 1,
    pdca_cycle_id           INT          NOT NULL,
    problem_list            TEXT[],
    rectify_plan            TEXT         NOT NULL,
    bind_next_cycle_goal    TEXT,
    is_freeze_experience    BOOLEAN      DEFAULT FALSE,
    new_config_version      VARCHAR(16),
    created_at              TIMESTAMPTZ  DEFAULT NOW(),
    updated_at              TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT fk_act_cycle FOREIGN KEY (pdca_cycle_id)
        REFERENCES pdca.pdca_cycle(id) ON DELETE RESTRICT
);

-- 表13: 经验知识库表
CREATE TABLE pdca.trade_experience (
    id                  SERIAL PRIMARY KEY,
    account_id          INT          DEFAULT 1,
    trading_record_id   INT,
    title               VARCHAR(255) NOT NULL,
    content             TEXT         NOT NULL,
    tags                VARCHAR(64)[],
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT fk_exp_record FOREIGN KEY (trading_record_id)
        REFERENCES pdca.trading_record(id) ON DELETE SET NULL
);

-- 表14: 操作审计日志表
CREATE TABLE pdca.audit_log (
    id              SERIAL PRIMARY KEY,
    account_id      INT          DEFAULT 1,
    table_name      VARCHAR(64)  NOT NULL,
    record_id       INT,
    action          VARCHAR(16)  NOT NULL,          -- INSERT / UPDATE / DELETE
    old_values      JSONB,
    new_values      JSONB,
    operated_by     VARCHAR(64),
    operated_at     TIMESTAMPTZ  DEFAULT NOW()
);


-- ============================================================
-- 2.4 索引策略
-- ============================================================

-- system_config: 按 key 查询
CREATE INDEX idx_system_config_key ON pdca.system_config(config_key);

-- account_snapshot: 按日期查询资金曲线
CREATE INDEX idx_account_snapshot_date ON pdca.account_snapshot(snapshot_date);

-- pdca_cycle: 按状态查询活跃周期、按日期范围查询、自引用外键
CREATE INDEX idx_cycle_status ON pdca.pdca_cycle(status);
CREATE INDEX idx_cycle_date_range ON pdca.pdca_cycle(start_date, end_date);
CREATE INDEX idx_cycle_prev ON pdca.pdca_cycle(prev_cycle_id);

-- security_tag: 按标签筛选
CREATE INDEX idx_security_tag_tag ON pdca.security_tag(tag);
CREATE INDEX idx_security_tag_code ON pdca.security_tag(code);

-- trading_plan: 按周期、代码、状态查询
CREATE INDEX idx_plan_cycle ON pdca.trading_plan(pdca_cycle_id);
CREATE INDEX idx_plan_code ON pdca.trading_plan(code);
CREATE INDEX idx_plan_status ON pdca.trading_plan(plan_status);
CREATE INDEX idx_plan_cycle_code ON pdca.trading_plan(pdca_cycle_id, code);

-- trading_record: 高频查询列
CREATE INDEX idx_record_cycle ON pdca.trading_record(pdca_cycle_id);
CREATE INDEX idx_record_plan ON pdca.trading_record(trading_plan_id);
CREATE INDEX idx_record_code ON pdca.trading_record(code);
CREATE INDEX idx_record_entry_date ON pdca.trading_record(entry_date);
CREATE INDEX idx_record_trade_grade ON pdca.trading_record(trade_grade);
CREATE INDEX idx_record_code_entry ON pdca.trading_record(code, entry_date);

-- behavior_log: 按周期、违规类型查询
CREATE INDEX idx_blog_cycle ON pdca.behavior_log(pdca_cycle_id);
CREATE INDEX idx_blog_type ON pdca.behavior_log(violation_type);
CREATE INDEX idx_blog_happened_at ON pdca.behavior_log(happened_at);

-- trading_diary: 按周期、关联记录查询
CREATE INDEX idx_diary_cycle ON pdca.trading_diary(pdca_cycle_id);
CREATE INDEX idx_diary_record ON pdca.trading_diary(trading_record_id);

-- trade_experience: 标签搜索（GIN 索引支持数组查询）
CREATE INDEX idx_exp_tags ON pdca.trade_experience USING GIN(tags);
CREATE INDEX idx_exp_record ON pdca.trade_experience(trading_record_id);

-- audit_log: 按时间、表名查询
CREATE INDEX idx_audit_table ON pdca.audit_log(table_name);
CREATE INDEX idx_audit_operated_at ON pdca.audit_log(operated_at);


-- ============================================================
-- 2.5 触发器：自动更新 updated_at
-- ============================================================

CREATE OR REPLACE FUNCTION pdca.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为有 updated_at 字段的表创建触发器
CREATE TRIGGER trg_cycle_updated_at
    BEFORE UPDATE ON pdca.pdca_cycle
    FOR EACH ROW EXECUTE FUNCTION pdca.update_updated_at_column();

CREATE TRIGGER trg_security_tag_updated_at
    BEFORE UPDATE ON pdca.security_tag
    FOR EACH ROW EXECUTE FUNCTION pdca.update_updated_at_column();

CREATE TRIGGER trg_plan_template_updated_at
    BEFORE UPDATE ON pdca.plan_template
    FOR EACH ROW EXECUTE FUNCTION pdca.update_updated_at_column();

CREATE TRIGGER trg_trading_plan_updated_at
    BEFORE UPDATE ON pdca.trading_plan
    FOR EACH ROW EXECUTE FUNCTION pdca.update_updated_at_column();

CREATE TRIGGER trg_trading_record_updated_at
    BEFORE UPDATE ON pdca.trading_record
    FOR EACH ROW EXECUTE FUNCTION pdca.update_updated_at_column();

CREATE TRIGGER trg_trading_diary_updated_at
    BEFORE UPDATE ON pdca.trading_diary
    FOR EACH ROW EXECUTE FUNCTION pdca.update_updated_at_column();

CREATE TRIGGER trg_check_report_updated_at
    BEFORE UPDATE ON pdca.pdca_check_report
    FOR EACH ROW EXECUTE FUNCTION pdca.update_updated_at_column();

CREATE TRIGGER trg_act_record_updated_at
    BEFORE UPDATE ON pdca.pdca_act_record
    FOR EACH ROW EXECUTE FUNCTION pdca.update_updated_at_column();

CREATE TRIGGER trg_trade_experience_updated_at
    BEFORE UPDATE ON pdca.trade_experience
    FOR EACH ROW EXECUTE FUNCTION pdca.update_updated_at_column();

CREATE TRIGGER trg_broker_adapter_updated_at
    BEFORE UPDATE ON pdca.broker_adapter
    FOR EACH ROW EXECUTE FUNCTION pdca.update_updated_at_column();


-- ============================================================
-- 2.6 触发器：自动审计日志
-- ============================================================

CREATE OR REPLACE FUNCTION pdca.log_audit()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO pdca.audit_log (table_name, record_id, action, new_values, operated_at)
        VALUES (TG_TABLE_NAME, NEW.id, 'INSERT', to_jsonb(NEW), NOW());
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO pdca.audit_log (table_name, record_id, action, old_values, new_values, operated_at)
        VALUES (TG_TABLE_NAME, NEW.id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW), NOW());
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO pdca.audit_log (table_name, record_id, action, old_values, operated_at)
        VALUES (TG_TABLE_NAME, OLD.id, 'DELETE', to_jsonb(OLD), NOW());
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- 为关键业务表创建审计触发器
CREATE TRIGGER trg_audit_system_config
    AFTER INSERT OR UPDATE OR DELETE ON pdca.system_config
    FOR EACH ROW EXECUTE FUNCTION pdca.log_audit();

CREATE TRIGGER trg_audit_trading_plan
    AFTER INSERT OR UPDATE OR DELETE ON pdca.trading_plan
    FOR EACH ROW EXECUTE FUNCTION pdca.log_audit();

CREATE TRIGGER trg_audit_trading_record
    AFTER INSERT OR UPDATE OR DELETE ON pdca.trading_record
    FOR EACH ROW EXECUTE FUNCTION pdca.log_audit();


-- ============================================================
-- 2.7 初始数据：系统默认配置
-- ============================================================

-- 默认账户
INSERT INTO pdca.account (account_name, account_type, currency, initial_capital)
VALUES ('默认账户', 'stock', 'CNY', 0);

INSERT INTO pdca.system_config (config_key, config_value, numeric_value, description, version, modify_reason)
VALUES
    ('risk_per_trade', '0.02', 0.02, '单笔最大风险比例（2%）', '1.0.0', '系统初始化'),
    ('risk_per_month', '0.06', 0.06, '月度总风险上限（6%）', '1.0.0', '系统初始化'),
    ('entry_score_threshold_a', '35', 35, '进场得分A级阈值（≤此值为A）', '1.0.0', '系统初始化'),
    ('entry_score_threshold_b', '50', 50, '进场得分B级阈值（≤此值为B，>此值为C）', '1.0.0', '系统初始化'),
    ('trade_grade_a_profit_pct', '30', 30, '交易总得分A级阈值（盈利占通道≥30%）', '1.0.0', '系统初始化'),
    ('trade_grade_b_profit_pct', '10', 10, '交易总得分B级阈值（盈利占通道≥10%）', '1.0.0', '系统初始化'),
    ('review_reminder_days', '90', 90, '二次复盘提醒天数（默认90天=3个月）', '1.0.0', '系统初始化');

-- 初始数据：系统内置交易计划模板
INSERT INTO pdca.plan_template (template_name, template_type, required_fields, default_values, is_system)
VALUES
    ('短线交易模板', 'short_term', 
     ARRAY['weekly_view','daily_view','entry_price','stop_loss_price','max_risk_rate','plan_quantity'],
     '{"long_short":"long","abort_condition":"跌破5日均线或单日跌幅>3%"}',
     TRUE),
    ('中线交易模板', 'mid_term',
     ARRAY['weekly_view','daily_view','entry_price','stop_loss_price','target_price','max_risk_rate','plan_quantity'],
     '{"long_short":"long","abort_condition":"周线趋势破坏或基本面重大变化"}',
     TRUE),
    ('长线交易模板', 'long_term',
     ARRAY['weekly_view','daily_view','entry_price','stop_loss_price','target_price','max_risk_rate','plan_quantity','abort_condition'],
     '{"long_short":"long","abort_condition":"季度财报不及预期或行业政策转向"}',
     TRUE);

-- 初始数据：券商适配器（华泰、中信）
INSERT INTO pdca.broker_adapter (broker_name, display_name, column_mapping, date_format, skip_rows)
VALUES
    ('htsc', '华泰证券',
     '{"code":"证券代码","security_name":"证券名称","entry_date":"成交日期","long_short":"买卖方向","entry_price":"成交均价","quantity":"成交数量","commission_entry":"手续费","settlement_currency":"币种"}',
     'YYYYMMDD', 1),
    ('citics', '中信证券',
     '{"code":"股票代码","security_name":"股票名称","entry_date":"交易日期","long_short":"操作","entry_price":"成交价格","quantity":"成交股数","commission_entry":"佣金","settlement_currency":"货币"}',
     'YYYY-MM-DD', 1);

COMMIT;