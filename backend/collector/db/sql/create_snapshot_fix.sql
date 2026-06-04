-- 创建宽表数据（修复版）
-- 解决 stock_basic.code 格式不匹配问题

-- 删除旧表并重命名新表
DROP TABLE IF EXISTS stock_daily_snapshot_old;
ALTER TABLE stock_daily_snapshot RENAME TO stock_daily_snapshot_old;

-- 创建新的宽表
CREATE TABLE stock_daily_snapshot AS
SELECT 
    q.code,
    COALESCE(b.name, '') AS stock_name,
    CASE 
        WHEN q.code LIKE '60%' THEN '主板'
        WHEN q.code LIKE '000%' THEN '主板'
        WHEN q.code LIKE '002%' THEN '中小板'
        WHEN q.code LIKE '300%' THEN '创业板'
        WHEN q.code LIKE '688%' THEN '科创板'
        ELSE '其他'
    END AS listed_board,
    COALESCE(b.industry, '') AS industry,
    COALESCE(b.industry, '') AS sub_industry,
    q.trade_date,
    CURRENT_TIMESTAMP AS created_at,
    CURRENT_TIMESTAMP AS updated_at,
    q.open,
    q.high,
    q.low,
    q.close,
    q.pre_close,
    q.volume,
    q.amount,
    q.adjust_type,
    ROUND(q.close - q.pre_close, 2) AS change,
    ROUND((q.close - q.pre_close) / NULLIF(q.pre_close, 0) * 100, 2) AS change_pct,
    NULL AS turnover_rate,
    NULL AS pe,
    NULL AS pb,
    NULL AS market_cap,
    NULL AS circ_mv,
    i.ma5,
    i.ma10,
    i.ma20,
    NULL AS v_ma5,
    i.rsi6 AS rsi_6,
    i.macd,
    NULL AS boll_upper,
    NULL AS boll_mid,
    NULL AS boll_lower,
    CASE WHEN b.name LIKE '%ST%' THEN TRUE ELSE FALSE END AS is_st,
    FALSE AS is_new,
    CASE WHEN ROUND((q.close - q.pre_close) / NULLIF(q.pre_close, 0) * 100, 2) >= 19.9 THEN TRUE ELSE FALSE END AS limit_up,
    CASE WHEN ROUND((q.close - q.pre_close) / NULLIF(q.pre_close, 0) * 100, 2) <= -19.9 THEN TRUE ELSE FALSE END AS limit_down
FROM stock_quotes q
LEFT JOIN stock_basic b ON q.code = RIGHT(b.code, 6)
LEFT JOIN stock_indicators i ON q.code = i.code AND q.trade_date = i.trade_date AND q.cycle = i.cycle
WHERE q.cycle = '1d';

-- 添加索引
CREATE INDEX idx_snapshot_date_change ON stock_daily_snapshot (trade_date, change_pct DESC);
CREATE INDEX idx_snapshot_date_pe ON stock_daily_snapshot (trade_date, pe);
CREATE INDEX idx_snapshot_date_market_cap ON stock_daily_snapshot (trade_date, market_cap DESC);
CREATE INDEX idx_snapshot_code_date ON stock_daily_snapshot (code, trade_date DESC);

-- 添加唯一约束
ALTER TABLE stock_daily_snapshot ADD CONSTRAINT uk_snapshot_code_date UNIQUE (code, trade_date);

-- 统计
SELECT '宽表创建完成' AS result, COUNT(*) AS count FROM stock_daily_snapshot;
