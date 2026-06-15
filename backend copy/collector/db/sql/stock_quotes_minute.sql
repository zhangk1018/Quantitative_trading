-- ==========================================
-- 分钟线数据表（分区表）
-- ==========================================
-- 周期：5m, 15m, 30m, 60m
-- 分区策略：按月按 RANGE (trade_date)
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

-- ==========================================
-- 创建 2025-2026 月度分区（示例）
-- ==========================================
-- 2025年
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202501 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202502 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202503 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202504 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202505 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202506 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202507 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202508 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202509 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202510 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202511 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202512 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');

-- 2026年
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202601 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202602 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202603 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202604 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202605 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202606 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202607 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202608 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202609 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202610 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202611 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE IF NOT EXISTS stock_quotes_minute_202612 PARTITION OF stock_quotes_minute FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

-- ==========================================
-- 创建索引
-- ==========================================
CREATE INDEX IF NOT EXISTS idx_quotes_minute_code_cycle ON stock_quotes_minute(code, cycle);
CREATE INDEX IF NOT EXISTS idx_quotes_minute_code_date ON stock_quotes_minute(code, trade_date);
CREATE INDEX IF NOT EXISTS idx_quotes_minute_trade_time ON stock_quotes_minute(trade_time);

-- ==========================================
-- 业务约束
-- ==========================================
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_minute_cycle') THEN
        ALTER TABLE stock_quotes_minute ADD CONSTRAINT chk_minute_cycle CHECK (cycle IN ('5m', '15m', '30m', '60m'));
    END IF;
END $$;

-- ==========================================
-- 生产级加固约束（追加至末尾）
-- ==========================================
-- 1. 主键（已在 CREATE TABLE 中定义: PRIMARY KEY(id, trade_date)）

-- 2. 唯一约束（防重复K线）
-- 防止同一标的/周期/时刻重复K线入库
CREATE UNIQUE INDEX uk_sq_min_code_cycle_time
ON stock_quotes_minute (code, cycle, trade_date, trade_time);

-- 3. 高频查询索引（覆盖 90% 分钟级查询）
CREATE INDEX idx_sq_min_code_cycle_date
ON stock_quotes_minute (code, cycle, trade_date);

-- 4. 业务约束（周期校验）
-- 拦截非法周期写入，保障下游指标计算逻辑一致性
-- 注：周期约束已在上方 DO 块中以幂等方式创建（chk_minute_cycle）