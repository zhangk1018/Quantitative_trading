-- ============================================================
-- V022: 纠正 hk/us `stock_daily_basic.total_mv/circ_mv` 被二次缩小（亿元 → 万元）
-- ============================================================
-- 现象（2026-10-11 06:45 核验发现）：
--   V020 已把 hk/us 的 `total_mv` 由「元」÷1e4 折算为「万元」并验证通过
--   （0700.HK=386,253,900 万元、AAPL=491,368,924 万元）。
--   但随后 DB 内该值又变成 **÷1e4 之后的值**：
--     0700.HK 2026-10-09 = 38,625.39（= 3.86 万亿 ÷ 1e8 = 百度原始「亿元」值）
--     AAPL    2026-10-09 = 49,136.89（同理，原始「亿元」值）
--   即：hk/us 落库值 = **亿元原值**（既非「元」也非正确的「万元」，比正确值小 1e4 倍）。
--   仓库内 ETL 因子（`sync_hk_basic._MV_YI_FACTOR=1e4`、`sync_us_basic` factor=`1e4/1e-4`）
--   已正确并已提交（d8cca5a），故本次异常来自**仓库之外的一次写入/转换**（待 K 确认来源）。
--
-- 修复：hk/us 两表 ×1e4 还原为「万元」（当前值口径统一为「亿元」，可安全整体乘回）。
-- 破坏性：是（数值改写）。备份：`stock_daily_basic_hkus_bak_20261011` /
--   `stock_daily_snapshot_hkus_bak_20261011`。
-- 幂等：migration_flags['V022_hk_us_market_cap_yi_to_wan']
-- 执行：按 `-- STEP` 分段（见 run_v021.py 的通用分段逻辑）。
-- ============================================================

-- STEP 1｜stock_daily_basic：hk/us ×1e4（亿元 → 万元）
UPDATE stock_daily_basic
   SET total_mv = ROUND(total_mv * 10000, 2),
       circ_mv  = ROUND(circ_mv  * 10000, 2)
 WHERE market IN ('hk', 'us')
   AND (total_mv IS NOT NULL OR circ_mv IS NOT NULL);

-- STEP 2｜stock_daily_snapshot：按修正后的 basic 同步 hk/us（只写真正变化的行）
UPDATE stock_daily_snapshot s SET
    market_cap = b.total_mv,
    circ_mv    = b.circ_mv
  FROM stock_daily_basic b
 WHERE s.market IN ('hk', 'us') AND b.market = s.market
   AND b.code = s.code AND b.trade_date = s.trade_date
   AND (s.market_cap IS DISTINCT FROM b.total_mv
        OR s.circ_mv IS DISTINCT FROM b.circ_mv);

-- STEP 3｜标记（幂等）
INSERT INTO migration_flags (flag_name, executed_at)
VALUES ('V022_hk_us_market_cap_yi_to_wan', NOW())
ON CONFLICT (flag_name) DO NOTHING;
