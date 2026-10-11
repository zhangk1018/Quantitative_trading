-- ============================================================
-- V021: 回填 cn `stock_daily_basic.total_mv/circ_mv` 历史行「元 → 万元」
-- ============================================================
-- 背景（协作单 48.0）：
--   cn 的 `total_mv` 口径在 **2026-07-01** 由「元」改为「万元」（对齐 tushare 与
--   `models.py` / `schemas.py` / `screener_service` 的契约），但**只改了写入代码、未回填历史行**：
--     2026-07-01 前 cn 共 1,315,453 行 → 1,204,220 行（91.5%）仍是「元」、68,330 行为 `NaN`（应为 NULL）。
--   `stock_daily_snapshot.market_cap` 逐行复制 `total_mv`（daily_snapshot_sync.py:233），
--   故宽表 cn 历史行（2025-01 ~ 2026-06）市值同样虚高 1e4 倍。
--
-- 判别方法（协作单 48.0）：与该股「2026-07 之后的**万元**中位数」比值落在 [1e3, 1e5] → 判为「元」（÷1e4）。
--   比「≥1e10」阈值更准 —— 后者会漏判小盘股（50 亿市值存成 5e9 看似正常、实为元）。
--   无 2026-07 后参考的行 → 置 NULL（宁可无数据，也不写错单位）。
--
-- 破坏性：**是**（改写历史数值，语义由「元」纠正为「万元」）。已备份：
--   `stock_daily_basic_cn_bak_20261011` / `stock_daily_snapshot_cn_bak_20261011`。
-- 回滚：按 (code, trade_date) 从上述备份表回写两列。
--
-- 执行方式：**按 `-- STEP` 分段、逐段提交**（每段幂等，重跑安全；避免大事务整体回滚）。
--   本文件由 `backend/scripts/run_v021.py` 逐段执行；也可手工按段粘贴。
-- ============================================================

-- STEP 1｜NaN → NULL（PG 的 numeric NaN 不等于 NULL，会污染比较/聚合）
UPDATE stock_daily_basic SET total_mv = NULL WHERE market = 'cn' AND total_mv::text = 'NaN';
-- STEP 1b
UPDATE stock_daily_basic SET circ_mv = NULL WHERE market = 'cn' AND circ_mv::text = 'NaN';

-- STEP 2｜「元」→「万元」（比值判据；无参考 → NULL）；仅 2026-07-01 之前
--   幂等：首轮折算后 ratio≈1，不再命中 [1e3,1e5]，重跑无副作用
WITH ref AS (
    SELECT code,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY total_mv) AS mv_t,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY circ_mv)  AS mv_c
      FROM stock_daily_basic
     WHERE market = 'cn' AND trade_date >= DATE '2026-07-01' AND total_mv > 0
     GROUP BY code
)
UPDATE stock_daily_basic b SET
    total_mv = CASE
        WHEN r.mv_t IS NULL THEN NULL
        WHEN b.total_mv > 0 AND b.total_mv / r.mv_t BETWEEN 1000 AND 100000
            THEN ROUND(b.total_mv / 10000, 2)
        ELSE b.total_mv END,
    circ_mv = CASE
        WHEN r.mv_c IS NULL THEN NULL
        WHEN b.circ_mv > 0 AND b.circ_mv / r.mv_c BETWEEN 1000 AND 100000
            THEN ROUND(b.circ_mv / 10000, 2)
        ELSE b.circ_mv END
  FROM ref r
 WHERE b.market = 'cn' AND b.trade_date < DATE '2026-07-01' AND r.code = b.code;

-- STEP 3｜宽表 cn 历史行同步（定向，不跑全量 daily_snapshot_sync）；只写真正变化的行
UPDATE stock_daily_snapshot s SET
    market_cap = b.total_mv,
    circ_mv    = b.circ_mv
  FROM stock_daily_basic b
 WHERE s.market = 'cn' AND s.trade_date < DATE '2026-07-01'
   AND b.market = 'cn' AND b.code = s.code AND b.trade_date = s.trade_date
   AND (s.market_cap IS DISTINCT FROM b.total_mv
        OR s.circ_mv IS DISTINCT FROM b.circ_mv);

-- STEP 4｜标记（幂等）
INSERT INTO migration_flags (flag_name, executed_at)
VALUES ('V021_cn_total_mv_yuan_to_wan', NOW())
ON CONFLICT (flag_name) DO NOTHING;
