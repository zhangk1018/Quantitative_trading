-- 2026-06-17 stock_indicators 修复 SOP
-- 背景: 准备 K 线形态 ETL 前, 发现 stock_indicators_2026 有 cycle != '1d' 的 76 行残留
--        (5m/15m/30m/60m 各 19 行, 测试时统一塞入)
-- 业务: 项目只有日线数据, 不需要其他 cycle
-- 此脚本一次性, 已执行 (2026-06-17 19:00 by 方舟), 留作运维 SOP 备查

BEGIN;

-- 1. 删除非 1d 残留 (76 行)
DELETE FROM stock_indicators_2026 WHERE cycle != '1d';

-- 2. 加 CHECK 约束防再发 (父表, 未来所有分区继承)
ALTER TABLE stock_indicators
ADD CONSTRAINT ck_stock_indicators_cycle
CHECK (cycle = '1d');

-- 3. ALTER TABLE 加 5 个 K 线形态列 (TA-Lib 输出 -100/-80/0/80/100, DEFAULT 0)
ALTER TABLE stock_indicators ADD COLUMN IF NOT EXISTS pattern_morning_star     INTEGER DEFAULT 0;
ALTER TABLE stock_indicators ADD COLUMN IF NOT EXISTS pattern_evening_star     INTEGER DEFAULT 0;
ALTER TABLE stock_indicators ADD COLUMN IF NOT EXISTS pattern_bullish_engulfing INTEGER DEFAULT 0;
ALTER TABLE stock_indicators ADD COLUMN IF NOT EXISTS pattern_bearish_engulfing INTEGER DEFAULT 0;
ALTER TABLE stock_indicators ADD COLUMN IF NOT EXISTS pattern_hammer           INTEGER DEFAULT 0;

-- 4. 验证
-- SELECT cycle, COUNT(*) FROM stock_indicators_2026 GROUP BY cycle;
-- 期望: 仅 cycle='1d' 一行
-- SELECT conname FROM pg_constraint WHERE conrelid='stock_indicators'::regclass AND conname='ck_stock_indicators_cycle';
-- 期望: 1 行
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name='stock_indicators' AND column_name LIKE 'pattern_%';
-- 期望: 5 行

COMMIT;
