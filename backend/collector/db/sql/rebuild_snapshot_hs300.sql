-- 重建宽表 SQL（沪深300测试数据：最近交易日 + 前300只股票）
TRUNCATE TABLE stock_daily_snapshot;

INSERT INTO stock_daily_snapshot (
    trade_date, code, stock_name, listed_board, industry, sub_industry,
    open, high, low, close, pre_close, volume, amount, adjust_type,
    change, change_pct, ma5, ma10, ma20, rsi_6, macd,
    is_st, is_new, limit_up, limit_down
)
SELECT
    q.trade_date,
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
    COALESCE(s.industry, '') AS industry,
    '' AS sub_industry,
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
    i.ma5,
    i.ma10,
    i.ma20,
    i.rsi6 AS rsi_6,
    i.macd,
    CASE WHEN b.name LIKE '%ST%' OR b.name LIKE '%*ST%' THEN TRUE ELSE FALSE END AS is_st,
    FALSE AS is_new,
    CASE WHEN ROUND((q.close - q.pre_close) / NULLIF(q.pre_close, 0) * 100, 2) >= 19.9 THEN TRUE ELSE FALSE END AS limit_up,
    CASE WHEN ROUND((q.close - q.pre_close) / NULLIF(q.pre_close, 0) * 100, 2) <= -19.9 THEN TRUE ELSE FALSE END AS limit_down
FROM (
    SELECT DISTINCT q2.code, q2.trade_date
    FROM stock_quotes q2
    WHERE q2.cycle = '1d' AND q2.trade_date = '2026-06-01'
    ORDER BY q2.code
    LIMIT 300
) q_base
JOIN stock_quotes q ON q.code = q_base.code AND q.trade_date = q_base.trade_date AND q.cycle = '1d'
LEFT JOIN stock_basic b ON RIGHT(b.code, 6) = q.code
LEFT JOIN stock_list s ON s.code = q.code
LEFT JOIN stock_indicators i ON i.code = q.code AND i.trade_date = q.trade_date AND i.cycle = q.cycle;
