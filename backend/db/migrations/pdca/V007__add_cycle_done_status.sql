-- ============================================================
-- V007: 新增周期终态「已闭环」(DONE)
-- 需求：协作单 [26.0-PDCA-CYCLE-TERMINAL-STATUS] 需求①
-- 取消 ACT→PLAN 自动续期，旧周期 ACT 结束后进入终态 DONE（仅查看/统计）。
-- 新周期由用户手动 POST /api/pdca/cycles 创建，后端不再自动 INSERT。
-- ============================================================

-- 枚举新增终态值（幂等）。注意：此语句不可与后续使用 'DONE' 的
-- UPDATE 处于同一事务（PostgreSQL 限制：新枚举值不能在 ADD VALUE 同事务使用）。
ALTER TYPE pdca.cycle_status ADD VALUE IF NOT EXISTS 'DONE';