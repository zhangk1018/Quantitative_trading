-- ==========================================
-- stock_daily_snapshot 宽表创建脚本
-- 用于存储盘后 ETL 物理化合并的高频查询字段
-- ==========================================

-- 创建宽表（非分区表，每日更新）
CREATE TABLE IF NOT EXISTS stock_daily_snapshot (
    -- 主键
    id BIGSERIAL PRIMARY KEY,
    
    -- 基础标识字段
    code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    listed_board VARCHAR(20),
    industry VARCHAR(50),
    sub_industry VARCHAR(50),
    
    -- 日期字段
    trade_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- 行情基础字段（从 stock_quotes JOIN）
    open NUMERIC(10, 2),
    high NUMERIC(10, 2),
    low NUMERIC(10, 2),
    close NUMERIC(10, 2),
    pre_close NUMERIC(10, 2),
    volume BIGINT,
    amount NUMERIC(18, 2),
    adjust_type VARCHAR(10) DEFAULT 'qfq',
    
    -- 高频查询字段（ETL 计算）
    change NUMERIC(10, 2),              -- 涨跌额
    change_pct NUMERIC(8, 2),           -- 涨跌幅（%）
    turnover_rate NUMERIC(8, 2),        -- 换手率（%）
    
    -- 估值指标（从 stock_fundamental_pit JOIN 最近报告期）
    pe NUMERIC(10, 2),                  -- 市盈率（TTM）
    pb NUMERIC(10, 2),                  -- 市净率
    market_cap NUMERIC(18, 2),          -- 总市值（万元）
    circ_mv NUMERIC(18, 2),             -- 流通市值（万元）
    
    -- 技术指标（从 stock_indicators JOIN）
    ma5 NUMERIC(10, 2),                 -- 5日均线
    ma10 NUMERIC(10, 2),                -- 10日均线
    ma20 NUMERIC(10, 2),                -- 20日均线
    v_ma5 BIGINT,                       -- 5日均量
    rsi_6 NUMERIC(6, 2),                -- RSI6
    macd NUMERIC(10, 4),                -- MACD值
    boll_upper NUMERIC(10, 2),          -- 布林带上轨
    boll_mid NUMERIC(10, 2),            -- 布林带中轨
    boll_lower NUMERIC(10, 2),          -- 布林带下轨
    
    -- 状态标记字段（ETL 计算）
    is_st BOOLEAN DEFAULT FALSE,        -- 是否ST股票
    is_new BOOLEAN DEFAULT FALSE,       -- 是否新股（上市<1年）
    limit_up BOOLEAN DEFAULT FALSE,     -- 是否涨停
    limit_down BOOLEAN DEFAULT FALSE    -- 是否跌停
);

-- 创建唯一约束（每日每只股票一条记录）
ALTER TABLE stock_daily_snapshot
ADD CONSTRAINT unique_snapshot_code_date UNIQUE (code, trade_date);

-- 创建索引（优化高频查询）
CREATE INDEX IF NOT EXISTS idx_snapshot_code_date ON stock_daily_snapshot (code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_snapshot_date ON stock_daily_snapshot (trade_date);
CREATE INDEX IF NOT EXISTS idx_snapshot_industry ON stock_daily_snapshot (industry);
CREATE INDEX IF NOT EXISTS idx_snapshot_change_pct ON stock_daily_snapshot (trade_date, change_pct DESC);
CREATE INDEX IF NOT EXISTS idx_snapshot_pe ON stock_daily_snapshot (trade_date, pe);
CREATE INDEX IF NOT EXISTS idx_snapshot_pb ON stock_daily_snapshot (trade_date, pb);

-- 添加表注释
COMMENT ON TABLE stock_daily_snapshot IS '股票每日快照宽表（盘后ETL物理化合并，优化高频查询性能）';
COMMENT ON COLUMN stock_daily_snapshot.change_pct IS '涨跌幅（%）';
COMMENT ON COLUMN stock_daily_snapshot.turnover_rate IS '换手率（%）';
COMMENT ON COLUMN stock_daily_snapshot.is_st IS '是否ST股票';
COMMENT ON COLUMN stock_daily_snapshot.limit_up IS '是否涨停';
COMMENT ON COLUMN stock_daily_snapshot.limit_down IS '是否跌停';

-- ==========================================
-- ETL 合并视图（用于验证数据）
-- ==========================================
CREATE OR REPLACE VIEW v_stock_daily_snapshot_etl AS
SELECT 
    q.code,
    b.name AS stock_name,
    -- 简化处理：根据代码判断板块
    CASE 
        WHEN q.code LIKE '60%' THEN '主板'
        WHEN q.code LIKE '000%' THEN '主板'
        WHEN q.code LIKE '002%' THEN '中小板'
        WHEN q.code LIKE '300%' THEN '创业板'
        WHEN q.code LIKE '688%' THEN '科创板'
        ELSE '其他'
    END AS listed_board,
    b.industry,
    b.industry AS sub_industry,
    q.trade_date,
    q.open,
    q.high,
    q.low,
    q.close,
    q.pre_close,
    q.volume,
    q.amount,
    q.adjust_type,
    -- 计算涨跌额和涨跌幅
    ROUND(q.close - q.pre_close, 2) AS change,
    ROUND((q.close - q.pre_close) / NULLIF(q.pre_close, 0) * 100, 2) AS change_pct,
    -- 换手率（从 stock_indicators 获取或计算）
    NULL AS turnover_rate,
    -- 估值指标（从 stock_fundamental_pit 获取最近报告期）
    NULL AS pe,
    NULL AS pb,
    NULL AS market_cap,
    NULL AS circ_mv,
    -- 技术指标（从 stock_indicators JOIN）
    i.ma5,
    i.ma10,
    i.ma20,
    i.rsi6 AS rsi_6,
    i.macd,
    i.boll_upper,
    i.boll_middle AS boll_mid,
    i.boll_lower,
    -- 状态标记
    FALSE AS is_st,
    FALSE AS is_new,
    FALSE AS limit_up,
    FALSE AS limit_down
FROM stock_quotes q
LEFT JOIN stock_basic b ON q.code = b.code
LEFT JOIN stock_indicators i ON q.code = i.code AND q.trade_date = i.trade_date AND q.cycle = i.cycle
WHERE q.cycle = '1d';

-- ==========================================
-- 初始化快照数据（首次执行）
-- ==========================================
-- INSERT INTO stock_daily_snapshot (
--     code, stock_name, listed_board, industry, sub_industry,
--     trade_date, open, high, low, close, pre_close, volume, amount, adjust_type,
--     change, change_pct, ma5, ma10, ma20, rsi_6, macd, boll_upper, boll_mid, boll_lower,
--     is_st, is_new, limit_up, limit_down
-- )
-- SELECT * FROM v_stock_daily_snapshot_etl;
