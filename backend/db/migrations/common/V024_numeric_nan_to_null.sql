-- ============================================================
-- V024: 清理 stock_daily_basic / stock_daily_snapshot 的数值列 NaN 脏值
-- ============================================================
-- 背景（承接 V023 / 协作单 48.0）：
--   V023 已清 `stock_daily_basic.close` 的 NaN；全表扫描发现**两表各有 10 个 numeric 列仍含 NaN**
--   （PG 的 numeric NaN ≠ NULL，会污染比较/聚合/前端展示）。实测（2026-10-11）：
--     stock_daily_basic   : turnover_rate 68,389 / volume_ratio 68,397 / pe 76,913 / pe_ttm 9,087 /
--                           pb 68,602 / dv_ratio 475,497 / dv_ttm 452,600 / ps 8 / ps_ttm 68,793 /
--                           float_share 68,330
--     stock_daily_snapshot: turnover_rate 63,493 / volume_ratio 63,498 / pe 69,101 / pe_ttm 5,940 /
--                           pb 63,674 / dv_ratio 457,658 / dv_ttm 437,173 / ps 8 / ps_ttm 63,658 /
--                           float_share 63,492
--   （`market_cap`/`circ_mv` 已于 V021 处理、无 NaN；价格/指标列无 NaN）
--
-- 处理：上述列 **NaN → NULL**（nullif 写法，非 NaN 列原值不变；`WHERE` 仅命中含 NaN 的行）。
-- 破坏性：是（NaN 值改写为 NULL，语义更正确）。备份：
--   `stock_daily_basic_nan_bak_20261011` / `stock_daily_snapshot_nan_bak_20261011`（仅受影响行 × 上述 10 列）。
-- 回滚：按 (code, trade_date) 从备份表回写对应列。
-- 幂等：migration_flags['V024_numeric_nan_to_null']
-- 执行：按 `-- STEP` 分段（同 V021~V023）。
-- ============================================================

-- STEP 1｜stock_daily_basic：10 列 NaN → NULL（仅写含 NaN 的行）
UPDATE stock_daily_basic SET
    turnover_rate = NULLIF(turnover_rate::text, 'NaN')::numeric,
    volume_ratio  = NULLIF(volume_ratio::text,  'NaN')::numeric,
    pe            = NULLIF(pe::text,            'NaN')::numeric,
    pe_ttm        = NULLIF(pe_ttm::text,        'NaN')::numeric,
    pb            = NULLIF(pb::text,            'NaN')::numeric,
    dv_ratio      = NULLIF(dv_ratio::text,      'NaN')::numeric,
    dv_ttm        = NULLIF(dv_ttm::text,        'NaN')::numeric,
    ps            = NULLIF(ps::text,            'NaN')::numeric,
    ps_ttm        = NULLIF(ps_ttm::text,        'NaN')::numeric,
    float_share   = NULLIF(float_share::text,   'NaN')::numeric
 WHERE turnover_rate::text = 'NaN' OR volume_ratio::text = 'NaN' OR pe::text = 'NaN'
    OR pe_ttm::text = 'NaN' OR pb::text = 'NaN' OR dv_ratio::text = 'NaN'
    OR dv_ttm::text = 'NaN' OR ps::text = 'NaN' OR ps_ttm::text = 'NaN'
    OR float_share::text = 'NaN';

-- STEP 2｜stock_daily_snapshot：同样 10 列（宽表从 basic 复制，同带 NaN）
UPDATE stock_daily_snapshot SET
    turnover_rate = NULLIF(turnover_rate::text, 'NaN')::numeric,
    volume_ratio  = NULLIF(volume_ratio::text,  'NaN')::numeric,
    pe            = NULLIF(pe::text,            'NaN')::numeric,
    pe_ttm        = NULLIF(pe_ttm::text,        'NaN')::numeric,
    pb            = NULLIF(pb::text,            'NaN')::numeric,
    dv_ratio      = NULLIF(dv_ratio::text,      'NaN')::numeric,
    dv_ttm        = NULLIF(dv_ttm::text,        'NaN')::numeric,
    ps            = NULLIF(ps::text,            'NaN')::numeric,
    ps_ttm        = NULLIF(ps_ttm::text,        'NaN')::numeric,
    float_share   = NULLIF(float_share::text,   'NaN')::numeric
 WHERE turnover_rate::text = 'NaN' OR volume_ratio::text = 'NaN' OR pe::text = 'NaN'
    OR pe_ttm::text = 'NaN' OR pb::text = 'NaN' OR dv_ratio::text = 'NaN'
    OR dv_ttm::text = 'NaN' OR ps::text = 'NaN' OR ps_ttm::text = 'NaN'
    OR float_share::text = 'NaN';

-- STEP 3｜标记（幂等）
INSERT INTO migration_flags (flag_name, executed_at)
VALUES ('V024_numeric_nan_to_null', NOW())
ON CONFLICT (flag_name) DO NOTHING;
