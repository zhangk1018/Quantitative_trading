-- V019: 价格列扩精度 NUMERIC(10,2) → NUMERIC(12,4)（协作单 45.0，方案 A）
--
-- 背景：港股 hfq 为仿射口径（hfq = a*raw + b）。修正复权 O/H/L 后，「加性偏移远大于
-- 当前价」的细价股在 2 位小数下会被量化（碧桂园 02007：复权价 5.42 而真实日内波幅仅
-- 0.0096，量子 0.01 与波幅同量级）。实测港股 2025-01-01 起 94.9 万行：波幅 <0.02 占
-- 36.3%（2,107 只）、<0.01 占 26.0%（2,013 只），其中本次修复新显形 10.5%/690 只。
--
-- 覆盖面（方案 A 必须两表同扩，否则修复到不了消费端）：
--   - stock_quotes            ：日/周/月K 成交价列（含 69 个年分区，父表 ALTER 递归生效）
--   - stock_daily_snapshot    ：宽表（选股视图 / 回测逐日判定 / parquet 导出的实际来源，287 万行）
-- 未纳入（本次评估后另行处理）：stock_daily_basic.close、stock_quotes_minute*、*_bak_* 备份表。
--
-- ⚠️ 破坏性 / 重写型迁移：
--   - 分区表 ALTER COLUMN TYPE 递归重写全部分区并重建索引，需 ACCESS EXCLUSIVE 锁
--     （期间两表读写全阻塞）；16.5M 行 / 8.3GB + 287 万行，预估 10~30 分钟，需临时磁盘。
--   - 值语义无损（仅增小数位与上限，不截断）；反向 ALTER 会四舍五入回 2 位。
--   - 每表五列写在**同一条 ALTER TABLE**，确保只重写一次（分开写会重写 5 次）。
--   - lock_timeout 20s：拿不到锁快速失败，避免排队把后端读全堵住（人工重试）。
--   - 视图 public.v_stock_daily_snapshot_etl 依赖 q.open 等列，须先 DROP 再原样重建。
--   - 回滚：ALTER COLUMN ... TYPE NUMERIC(10,2)（损失精度，不回退数据）。
--
-- 数据库: PostgreSQL 18.6

SET LOCAL lock_timeout = '20s';

-- 1) 搬迁依赖视图（定义见第 3 步，原样重建）
DROP VIEW IF EXISTS public.v_stock_daily_snapshot_etl;

-- 2) 扩精度（每表一条 ALTER，五列同句 → 只触发一次重写）
ALTER TABLE stock_quotes
    ALTER COLUMN open TYPE NUMERIC(12, 4),
        ALTER COLUMN high TYPE NUMERIC(12, 4),
        ALTER COLUMN low TYPE NUMERIC(12, 4),
        ALTER COLUMN close TYPE NUMERIC(12, 4),
        ALTER COLUMN pre_close TYPE NUMERIC(12, 4);
ALTER TABLE stock_daily_snapshot
    ALTER COLUMN open TYPE NUMERIC(12, 4),
        ALTER COLUMN high TYPE NUMERIC(12, 4),
        ALTER COLUMN low TYPE NUMERIC(12, 4),
        ALTER COLUMN close TYPE NUMERIC(12, 4),
        ALTER COLUMN pre_close TYPE NUMERIC(12, 4);

-- 3) 原样重建依赖视图
CREATE VIEW public.v_stock_daily_snapshot_etl AS
 SELECT q.code,
    b.name AS stock_name,
        CASE
            WHEN q.code::text ~~ '60%'::text THEN '主板'::text
            WHEN q.code::text ~~ '000%'::text THEN '主板'::text
            WHEN q.code::text ~~ '002%'::text THEN '中小板'::text
            WHEN q.code::text ~~ '300%'::text THEN '创业板'::text
            WHEN q.code::text ~~ '688%'::text THEN '科创板'::text
            ELSE '其他'::text
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
    round(q.close - q.pre_close, 2) AS change,
    round((q.close - q.pre_close) / NULLIF(q.pre_close, 0::numeric) * 100::numeric, 2) AS change_pct,
    NULL::text AS turnover_rate,
    NULL::text AS pe,
    NULL::text AS pb,
    NULL::text AS market_cap,
    NULL::text AS circ_mv,
    i.ma5,
    i.ma10,
    i.ma20,
    i.rsi6 AS rsi_6,
    i.macd,
    NULL::text AS boll_upper,
    NULL::text AS boll_mid,
    NULL::text AS boll_lower,
    false AS is_st,
    false AS is_new,
    false AS limit_up,
    false AS limit_down
   FROM stock_quotes q
     LEFT JOIN stock_basic b ON q.code::text = b.code::text
     LEFT JOIN stock_indicators i ON q.code::text = i.code::text AND q.trade_date = i.trade_date AND q.cycle::text = i.cycle::text
  WHERE q.cycle::text = '1d'::text;

-- 4) 校验：两表五个价格列均为 (12,4)
SELECT table_name, column_name, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_name IN ('stock_quotes', 'stock_daily_snapshot')
  AND column_name IN ('open', 'high', 'low', 'close', 'pre_close')
ORDER BY table_name, column_name;
