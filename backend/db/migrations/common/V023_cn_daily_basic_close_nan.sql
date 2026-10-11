-- ============================================================
-- V023: 清理 cn `stock_daily_basic.close` 的 NaN 脏值
-- ============================================================
-- 现象：`stock_daily_basic.close` 存在 **NaN**（PG 的 numeric NaN ≠ NULL，会污染比较/聚合/前端展示）。
--   实测 2026-10-11：cn **66,499 行**为 NaN（2025-06-24 ~ 2026-06-19），hk/us 为 0；
--   与 48.0 的 cn `total_mv` 「元」问题是**同一时期、同一批老基本面数据**（2026-07 起新管道无 NaN）。
--
-- 处理（两步，均可空列已确认 `is_nullable=YES`）：
--   1) **能救的救**：同日同码在 `stock_quotes`（cycle=1d）有 qfq `close` 的 → 回填（实测 **61,679 / 66,499** 可恢复）；
--   2) 其余（4,820 行，源端确无当日行情）→ 置 **NULL**（严禁留 NaN）。
--
-- 破坏性：是（数值改写）。备份：`stock_daily_basic_cn_close_nan_bak_20261011`（仅 NaN 行）。
-- 回滚：按 (code, trade_date) 从备份表回写 `close`（NaN 亦在其中，可用于还原）。
-- 幂等：migration_flags['V023_cn_daily_basic_close_nan']
-- 执行：按 `-- STEP` 分段（同 V021/V022：避免大事务整体回滚）。
-- ============================================================

-- STEP 1｜回填可恢复的 close（从 stock_quotes 的 qfq 收盘）
UPDATE stock_daily_basic b
   SET close = q.close
  FROM stock_quotes q
 WHERE b.close::text = 'NaN'
   AND q.market = b.market AND q.code = b.code AND q.cycle = '1d'
   AND q.trade_date = b.trade_date AND q.close IS NOT NULL;

-- STEP 2｜其余 NaN → NULL
UPDATE stock_daily_basic
   SET close = NULL
 WHERE close::text = 'NaN';

-- STEP 3｜标记（幂等）
INSERT INTO migration_flags (flag_name, executed_at)
VALUES ('V023_cn_daily_basic_close_nan', NOW())
ON CONFLICT (flag_name) DO NOTHING;
