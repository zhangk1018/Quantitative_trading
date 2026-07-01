-- migrate_add_ma60_and_macd_cross.sql
-- 为 stock_daily_snapshot 表新增 ma60 和通用 MACD 金叉死叉字段
-- 工单: [6.12-SNAPSHOT-API-20260624] 前端全量计算架构后端支撑端点
-- 日期: 2026-07-01

-- 1. 新增 ma60 字段（60日均线价）
ALTER TABLE stock_daily_snapshot
ADD COLUMN IF NOT EXISTS ma60 NUMERIC(10,3);

-- 2. 新增通用 MACD 金叉标记（DIF 上穿 DEA，不区分 0 轴位置）
ALTER TABLE stock_daily_snapshot
ADD COLUMN IF NOT EXISTS is_macd_golden_cross BOOLEAN DEFAULT FALSE;

-- 3. 新增通用 MACD 死叉标记（DIF 下穿 DEA，不区分 0 轴位置）
ALTER TABLE stock_daily_snapshot
ADD COLUMN IF NOT EXISTS is_macd_dead_cross BOOLEAN DEFAULT FALSE;

-- 4. 添加注释
COMMENT ON COLUMN stock_daily_snapshot.ma60 IS '60日均线价';
COMMENT ON COLUMN stock_daily_snapshot.is_macd_golden_cross IS 'MACD通用金叉：当日DIF上穿DEA（前一日DIF<DEA且当日DIF>DEA）';
COMMENT ON COLUMN stock_daily_snapshot.is_macd_dead_cross IS 'MACD通用死叉：当日DIF下穿DEA（前一日DIF>DEA且当日DIF>DEA）';

-- 5. 验证
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'stock_daily_snapshot'
  AND column_name IN ('ma60', 'is_macd_golden_cross', 'is_macd_dead_cross')
ORDER BY ordinal_position;
