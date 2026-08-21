-- ============================================================
-- V003: 清理台账旧数据，重置为"1买多卖"新模型
-- 
-- 说明：
-- - 删除所有旧交易记录（trading_record + trading_exit_slip）
-- - 关联表（behavior_log / trading_diary / trade_experience）中
--   引用这些记录的字段会被 SET NULL（由外键约束自动处理）
-- - exit_date / exit_price 列保留，供未来展示聚合数据使用
-- ============================================================

BEGIN;

-- 1. 删除所有卖出子单（先删子表）
DELETE FROM pdca.trading_exit_slip;

-- 2. 删除所有交易记录（主表）
--    behavior_log.trading_record_id → SET NULL（自动）
--    trading_diary.trading_record_id → SET NULL（自动）
--    trade_experience.trading_record_id → SET NULL（自动）
DELETE FROM pdca.trading_record;

-- 3. 重置序列（可选，保持 ID 从头开始）
ALTER SEQUENCE pdca.trading_record_id_seq RESTART WITH 1;
ALTER SEQUENCE pdca.trading_exit_slip_id_seq RESTART WITH 1;

COMMIT;