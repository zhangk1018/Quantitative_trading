-- =====================================================================
-- V012: 自选股表增加市场维度列 (market) + 代码列扩容 + 唯一键纳入 market
-- 依赖方: 港股/美股改造 V5 (M5)  工单见协作单
-- 幂等性: ADD COLUMN IF NOT EXISTS / DO 条件判断 / DROP...IF EXISTS，可重复执行。
-- 数据库: PostgreSQL 18.6
-- 兼容性: 旧自选股无 market 列，迁移后默认 'cn'，A股行为完全不变。
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. user_watchlist 增加 market 列（旧数据默认 cn，保持向后兼容）
-- ---------------------------------------------------------------------
ALTER TABLE user_watchlist ADD COLUMN IF NOT EXISTS market VARCHAR(8) DEFAULT 'cn';

-- ---------------------------------------------------------------------
-- 2. code 列扩容：A股6位 / 港股 `0001.HK`(7) / 美股 `AAPL`(4)，统一放宽到 10
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF (SELECT character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'user_watchlist'
          AND column_name  = 'code') < 10 THEN
        ALTER TABLE user_watchlist ALTER COLUMN code TYPE VARCHAR(10);
    END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- 3. 唯一键纳入 market
--    - 旧多分组唯一索引 (user_id, code, group_name) → 重建为 (user_id, code, group_name, market)
--    - 保留旧冲突去重约束 user_watchlist_user_id_code_key：(user_id, code) 维度的去重语义
--      不迁移到 market（该约束不冲突：A股6位 / 港股带 .HK / 美股字母，语法互斥）
-- ---------------------------------------------------------------------
DROP INDEX IF EXISTS uq_user_watchlist_user_code_group;
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_watchlist_user_code_group_market
    ON user_watchlist(user_id, code, group_name, market);

-- =====================================================================
-- 校验：确认 market 列与 code 宽度
-- =====================================================================
SELECT c.column_name, c.data_type, c.character_maximum_length
FROM information_schema.columns c
WHERE c.table_schema = 'public'
  AND c.table_name = 'user_watchlist'
  AND c.column_name IN ('code', 'market')
ORDER BY c.column_name;