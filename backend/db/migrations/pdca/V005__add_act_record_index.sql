-- V005: 添加 pdca_act_record.pdca_cycle_id 索引
-- 复盘理由：pdca_cycle_id 是高频查询字段（按周期查询所有改进记录），需索引加速
CREATE INDEX IF NOT EXISTS idx_act_record_pdca_cycle_id
    ON pdca.pdca_act_record(pdca_cycle_id);