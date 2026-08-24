-- V006: 冻结经验落库 - trade_experience 增加来源 act_record 关联
-- 背景：Act 模块「冻结经验」开关目前仅保存 is_freeze_experience 标记，
--       需将经验自动落库到 pdca.trade_experience（经验知识库）。
-- 幂等：source_act_record_id 唯一索引保证一条改进记录最多对应一条经验条目
--       （PostgreSQL 唯一索引允许多个 NULL，不影响历史无来源记录）
ALTER TABLE pdca.trade_experience
    ADD COLUMN IF NOT EXISTS source_act_record_id INT;

-- 唯一索引同时作为 ON CONFLICT (source_act_record_id) 的幂等键
CREATE UNIQUE INDEX IF NOT EXISTS uq_exp_source_act_record
    ON pdca.trade_experience(source_act_record_id);
