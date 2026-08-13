-- ============================================================
-- V002: 新增 trading_exit_slip 表（一买多卖分批卖出子单）
-- 需求：一笔买入后分多笔卖出（分批止盈/止损/加仓后部分减仓）
-- ============================================================

-- 1. 新建卖出子单表
CREATE TABLE pdca.trading_exit_slip (
    id                SERIAL PRIMARY KEY,
    record_id         INTEGER NOT NULL REFERENCES pdca.trading_record(id) ON DELETE CASCADE,
    exit_date         DATE NOT NULL,
    exit_price        NUMERIC(12,4) NOT NULL,
    quantity          INTEGER NOT NULL CHECK (quantity > 0),
    commission        NUMERIC(12,4) DEFAULT 0,
    exit_reason        VARCHAR(32),
    exit_score        NUMERIC(5,2),
    actual_stop_loss  NUMERIC(12,4),
    slip_point        NUMERIC(12,4) DEFAULT 0,
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at        TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_exit_slip_record_id ON pdca.trading_exit_slip(record_id);

-- 2. 在 trading_record 新增 remain_qty 字段（剩余持仓量）
ALTER TABLE pdca.trading_record ADD COLUMN IF NOT EXISTS remain_qty INTEGER;

-- 3. 存量数据迁移：为已有 exit_date 的记录生成一条子单
--    保持向后兼容：原有 exit_* 字段暂不删除，待所有数据迁移后再考虑废弃
INSERT INTO pdca.trading_exit_slip (record_id, exit_date, exit_price, quantity, commission, exit_reason, exit_score, actual_stop_loss, slip_point)
SELECT id, exit_date, exit_price, quantity, COALESCE(commission_exit, 0), exit_reason, exit_score, actual_stop_loss, COALESCE(slip_point, 0)
FROM pdca.trading_record
WHERE exit_date IS NOT NULL AND exit_price IS NOT NULL AND deleted_at IS NULL;

-- 4. 更新 remain_qty = quantity - sum(卖出子单数量)
UPDATE pdca.trading_record SET remain_qty = quantity - COALESCE(
    (SELECT SUM(quantity) FROM pdca.trading_exit_slip WHERE record_id = trading_record.id AND deleted_at IS NULL),
    0
);

-- 5. 无子单的记录 remain_qty = quantity（全仓持有）
UPDATE pdca.trading_record SET remain_qty = quantity WHERE remain_qty IS NULL;
