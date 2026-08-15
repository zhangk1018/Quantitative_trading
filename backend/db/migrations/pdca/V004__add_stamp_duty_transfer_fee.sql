-- ============================================================
-- V004: 追加印花税(stamp_duty)和过户费(transfer_fee)列
--
-- 背景：交易台账成本计算需包含完整A股费用结构
--   买入：券商佣金 + 过户费
--   卖出：券商佣金 + 印花税 + 过户费
-- ============================================================

BEGIN;

-- 1. trading_exit_slip 表：单笔卖出记录的印花税、过户费
ALTER TABLE pdca.trading_exit_slip ADD COLUMN IF NOT EXISTS stamp_duty NUMERIC(12,4) DEFAULT 0;
ALTER TABLE pdca.trading_exit_slip ADD COLUMN IF NOT EXISTS transfer_fee NUMERIC(12,4) DEFAULT 0;

-- 2. trading_record 表：汇总印花税和过户费（展示/查询用，应用层写入）
ALTER TABLE pdca.trading_record ADD COLUMN IF NOT EXISTS stamp_duty NUMERIC(12,4) DEFAULT 0;
ALTER TABLE pdca.trading_record ADD COLUMN IF NOT EXISTS transfer_fee NUMERIC(12,4) DEFAULT 0;

COMMIT;