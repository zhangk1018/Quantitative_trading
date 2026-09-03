-- =====================================================================
-- V008: 港股/美股改造 —— 数据表增加市场维度列 (market/currency/exchange/timezone)
-- 依赖方: 协作单 30.0 V1 / 方案 v2 §5
-- =====================================================================
-- ⚠️ 本迁移涉及分区表（stock_quotes / stock_indicators）与千万级 stock_quotes 数据。
--    "重建唯一约束"部分会触发全表索引重建并锁表，
--    **必须周末凌晨低峰期人工执行，不放日常 launchd**（见 script 末尾引导注释）。
-- 幂等性: 全部 ADD COLUMN IF NOT EXISTS / CREATE ... IF NOT EXISTS / DO 条件判断，可重复执行。
-- 数据库: PostgreSQL 18.6
-- =====================================================================

-- =====================================================================
-- 1. stock_basic 加市场维度列（存量默认 cn）
-- =====================================================================
ALTER TABLE stock_basic ADD COLUMN IF NOT EXISTS market    VARCHAR(10) DEFAULT 'cn';
ALTER TABLE stock_basic ADD COLUMN IF NOT EXISTS currency  VARCHAR(10) DEFAULT 'CNY';
ALTER TABLE stock_basic ADD COLUMN IF NOT EXISTS exchange  VARCHAR(20) DEFAULT NULL;
ALTER TABLE stock_basic ADD COLUMN IF NOT EXISTS timezone  VARCHAR(40) DEFAULT NULL;

-- =====================================================================
-- 2. 行情/基本面/宽表/指标表 加 market 列（存量默认 cn）
-- =====================================================================
ALTER TABLE stock_quotes        ADD COLUMN IF NOT EXISTS market VARCHAR(10) DEFAULT 'cn';
ALTER TABLE stock_daily_basic   ADD COLUMN IF NOT EXISTS market VARCHAR(10) DEFAULT 'cn';
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS market VARCHAR(10) DEFAULT 'cn';
ALTER TABLE stock_indicators    ADD COLUMN IF NOT EXISTS market VARCHAR(10) DEFAULT 'cn';
ALTER TABLE stock_adj_factor    ADD COLUMN IF NOT EXISTS market VARCHAR(10) DEFAULT 'cn';
ALTER TABLE trade_signals       ADD COLUMN IF NOT EXISTS market VARCHAR(10) DEFAULT 'cn';

-- =====================================================================
-- 3. 新增 fx_rates 汇率表（多市场回测资金结算必需，方案 §5/§6.1）
-- =====================================================================
CREATE TABLE IF NOT EXISTS fx_rates (
    pair           VARCHAR(10)  NOT NULL,          -- 如 HKDCNY=X / USDCNY=X
    trade_date     DATE         NOT NULL,
    rate           NUMERIC(18,6) NOT NULL,         -- 1 外币 = ? 本位币
    base_currency  VARCHAR(10)  NOT NULL DEFAULT 'CNY',
    created_at     TIMESTAMPTZ  DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pair, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_fx_rates_pair_date ON fx_rates(pair, trade_date);

-- =====================================================================
-- 4. 新增 etl_control 增量控制表（方案 §3.2，增量同步起点）
-- =====================================================================
CREATE TABLE IF NOT EXISTS etl_control (
    market         VARCHAR(10) NOT NULL,
    last_sync_date DATE        NOT NULL,
    updated_at     TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (market)
);
CREATE INDEX IF NOT EXISTS idx_etl_control_market_date ON etl_control(market, last_sync_date);

-- =====================================================================
-- 5. 非分区表唯一约束纳入 market（新增唯一约束，幂等用 ON CONFLICT(market,code,...)）
--    stock_adj_factor / stock_daily_basic / trade_signals / stock_daily_snapshot
-- =====================================================================

-- stock_adj_factor: 现有 PK (code,trade_date) 保留，新增 (market,code,trade_date) 唯一
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_adj_factor_market_code_date') THEN
        ALTER TABLE stock_adj_factor ADD CONSTRAINT uk_adj_factor_market_code_date
            UNIQUE (market, code, trade_date);
    END IF;
END;
$$;

-- stock_daily_basic: 现有 PK (code,trade_date) 保留，新增 (market,code,trade_date) 唯一
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_daily_basic_market_code_date') THEN
        ALTER TABLE stock_daily_basic ADD CONSTRAINT uk_daily_basic_market_code_date
            UNIQUE (market, code, trade_date);
    END IF;
END;
$$;

-- stock_daily_snapshot: 现有 unique (code,trade_date)；新增 (market,code,trade_date)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_snapshot_market_code_date') THEN
        ALTER TABLE stock_daily_snapshot ADD CONSTRAINT uk_snapshot_market_code_date
            UNIQUE (market, code, trade_date);
    END IF;
END;
$$;

-- trade_signals: 现有 unique (code,cycle,trade_date,signal_type)；新增 (market,code,cycle,trade_date,signal_type)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_trade_signals_market') THEN
        ALTER TABLE trade_signals ADD CONSTRAINT uk_trade_signals_market
            UNIQUE (market, code, cycle, trade_date, signal_type);
    END IF;
END;
$$;

-- =====================================================================
-- 6. 分区表（stock_quotes / stock_indicators）market 过滤索引
--    ✅ K 定案（2026-09-03 方案 B）：分区表【不加】market 唯一键，
--       保留原唯一约束 (code,cyle,trade_date,adjust_type) / (code,cyle,trade_date,trade_datetime)，
--       另加【非唯一】过滤索引 (market, code, trade_date) 支撑按市场查询/过滤。
--       理由：A股 600519.SH / 港股 9988.HK / 美股 AAPL 的 code 语法天然互斥，
--              market 入唯一键无实际消歧价值，且分区表逐分区 CONCURRENTLY 建唯一索引
--              工程风险高、仅限周末人工，收益小于成本。
--    ⚠️ 前置条件：分区 owner 需已统一为 quant_user（见 K 定案①）；否则父表建索引
--       传播到非 owner 分区会报 must be owner。（owner 统一独立于本迁移单独执行）
-- =====================================================================
CREATE INDEX IF NOT EXISTS idx_quotes_market_code_date
    ON stock_quotes(market, code, trade_date);
CREATE INDEX IF NOT EXISTS idx_indicators_market_code_date
    ON stock_indicators(market, code, trade_date);

-- =====================================================================
-- 校验：查看各表 market 列是否就位
-- =====================================================================
SELECT c.table_name, c.column_name
FROM information_schema.columns c
WHERE c.table_schema = 'public'
  AND c.column_name = 'market'
ORDER BY c.table_name;