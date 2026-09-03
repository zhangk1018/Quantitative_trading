-- =====================================================================
-- V009: 港股/美股改造 —— 复权存储列 (raw_* / adj_*) + 除权日 factor_date
-- 依赖方: 协作单 30.0 V2（M2）/ 方案 v2 §1.2、§5
-- =====================================================================
-- 背景/口径（方案 §1.2 最终决策）：
--   yfinance 的 `Adj Close` 是【后复权】(Back-adjusted)。为避免"每日重算静态前复权价"
--   导致的 DB/Parquet IO 爆炸 + 前端 K 线历史价每日跳变，后端统一存：
--       raw_open/raw_high/raw_low/raw_close —— 原始价（auto_adjust=False 的 OHLC）
--       adj_open/adj_high/adj_low/adj_close —— Yahoo 后复权价（Adj Close 口径）
--   指标/回测/前端画图统一用 adj_close；绝不在后端落每日变化的前复权价。
-- stock_adj_factor.factor_date：记录除权除息生效日，供前端 K 线标注。
-- =====================================================================
-- 幂等性：全部 ADD COLUMN IF NOT EXISTS，可重复执行。
-- 仅对【小区可见变化】加列，不锁大表（所有语句均为 metadata-only 加列）。
-- 数据库：PostgreSQL 18.6
-- =====================================================================

-- =====================================================================
-- 1. stock_quotes 加原始价/后复权列（默认 NULL，仅港股/美股写入；A股继续用 open/high/low/close）
-- =====================================================================
ALTER TABLE stock_quotes ADD COLUMN IF NOT EXISTS raw_open  NUMERIC(12, 4);
ALTER TABLE stock_quotes ADD COLUMN IF NOT EXISTS raw_high  NUMERIC(12, 4);
ALTER TABLE stock_quotes ADD COLUMN IF NOT EXISTS raw_low   NUMERIC(12, 4);
ALTER TABLE stock_quotes ADD COLUMN IF NOT EXISTS raw_close NUMERIC(12, 4);
ALTER TABLE stock_quotes ADD COLUMN IF NOT EXISTS adj_open  NUMERIC(12, 4);
ALTER TABLE stock_quotes ADD COLUMN IF NOT EXISTS adj_high  NUMERIC(12, 4);
ALTER TABLE stock_quotes ADD COLUMN IF NOT EXISTS adj_low   NUMERIC(12, 4);
ALTER TABLE stock_quotes ADD COLUMN IF NOT EXISTS adj_close NUMERIC(12, 4);

-- =====================================================================
-- 2. stock_adj_factor 加 factor_date（除权除息生效日，前端标注用）
-- =====================================================================
ALTER TABLE stock_adj_factor ADD COLUMN IF NOT EXISTS factor_date DATE;

-- =====================================================================
-- 校验：查看新增列是否就位
-- =====================================================================
SELECT c.table_name, c.column_name
FROM information_schema.columns c
WHERE c.table_schema = 'public'
  AND c.table_name IN ('stock_quotes', 'stock_adj_factor')
  AND c.column_name IN ('raw_open','raw_close','adj_open','adj_close','factor_date')
ORDER BY c.table_name, c.column_name;