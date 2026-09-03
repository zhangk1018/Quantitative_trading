-- =====================================================================
-- V010: 港股/美股改造 —— stock_daily_basic 增加基本面补充列
-- 依赖方: 协作单 30.0 V2（M2）/ 方案 v2 §1.3、§3.2
-- =====================================================================
-- 背景：`sync_hk_basic.py` 从 Yahoo info 拉取的港股/美股基本面含
--   currency（币种，前端展示）/ exchange（交易所）/ timezone（时区）/
--   year_high / year_low（52 周高低），但 stock_daily_basic 当前无这些列，
--   脚本只能跳过。本迁移补齐，使港美股基本面对齐。
-- 幂等性：全部 ADD COLUMN IF NOT EXISTS，可重复执行（metadata-only 加列，不锁大表）。
-- 数据库：PostgreSQL 18.6
-- =====================================================================

ALTER TABLE stock_daily_basic ADD COLUMN IF NOT EXISTS currency  VARCHAR(10) DEFAULT 'CNY';
ALTER TABLE stock_daily_basic ADD COLUMN IF NOT EXISTS exchange  VARCHAR(20) DEFAULT NULL;
ALTER TABLE stock_daily_basic ADD COLUMN IF NOT EXISTS timezone  VARCHAR(40) DEFAULT NULL;
ALTER TABLE stock_daily_basic ADD COLUMN IF NOT EXISTS year_high NUMERIC(12, 4);
ALTER TABLE stock_daily_basic ADD COLUMN IF NOT EXISTS year_low  NUMERIC(12, 4);

-- =====================================================================
-- 校验
-- =====================================================================
SELECT c.table_name, c.column_name
FROM information_schema.columns c
WHERE c.table_schema = 'public'
  AND c.table_name = 'stock_daily_basic'
  AND c.column_name IN ('currency','exchange','timezone','year_high','year_low')
ORDER BY c.column_name;