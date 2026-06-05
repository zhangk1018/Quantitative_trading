-- 清理数据库垃圾表
-- 包含：10 个 0 行占位表 + 1 个测试表 + 1 个 10GB 旧快照

BEGIN;

-- 0 行占位表（stock_indicators）
DROP TABLE IF EXISTS stock_indicators_2025;
DROP TABLE IF EXISTS stock_indicators_2027;
DROP TABLE IF EXISTS stock_indicators_2028;
DROP TABLE IF EXISTS stock_indicators_2029;
DROP TABLE IF EXISTS stock_indicators_2030;

-- 0 行占位表（stock_quotes）
DROP TABLE IF EXISTS stock_quotes_2027;
DROP TABLE IF EXISTS stock_quotes_2028;
DROP TABLE IF EXISTS stock_quotes_2029;
DROP TABLE IF EXISTS stock_quotes_2030;

-- 测试残留
DROP TABLE IF EXISTS test_table;

-- 10GB 旧快照（官方迁移脚本已标记 DROP）
DROP TABLE IF EXISTS stock_daily_snapshot_old;

COMMIT;

-- 验证：确认以上表都已不存在
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'test_table',
    'stock_indicators_2025','stock_indicators_2027','stock_indicators_2028','stock_indicators_2029','stock_indicators_2030',
    'stock_quotes_2027','stock_quotes_2028','stock_quotes_2029','stock_quotes_2030',
    'stock_daily_snapshot_old'
  );
-- 期望：返回 0 行

-- 检查释放后的总空间
SELECT pg_size_pretty(SUM(pg_total_relation_size(c.oid))) AS total_size
FROM pg_class c
WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace;
