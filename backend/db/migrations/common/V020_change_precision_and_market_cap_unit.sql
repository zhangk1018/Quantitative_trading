-- ============================================================
-- V020: ① 扩 stock_daily_snapshot.change 精度 (10,2) → (12,4)
--       ② 港股/美股 market_cap 单位订正「元 → 万元」（契约统一）
-- ============================================================
-- 一、change 精度（协作单 46.0 验收发现）
--   港股仙股日内涨跌额很小 —— 碧桂园 2007.HK 最新日 close=0.1830、pre_close=0.1790，
--   真实涨跌额 = 0.0040，但前端「涨跌额」恒显示 +0.00。根因两处叠加：
--     1) 本列原为 NUMERIC(10,2)，0.0040 写入时即被四舍五入为 0.00；
--     2) 快照同步 SQL `daily_snapshot_sync.py` 的 `ROUND(q.close - q.pre_close, 2) AS change`
--        也显式量化到 2 位（该处已同步改为 ROUND(..., 4)）。
--   V019 扩精度时只覆盖 open/high/low/close/pre_close，漏了 change。
--
-- 二、market_cap / circ_mv 单位（K 决策 A：hk/us 统一为**万元**，与 A 股 tushare 一致）
--   契约（models.py / schemas.py / screener_service）本就声明为「万元」，但 hk/us 实存「元」：
--     - hk：`sync_hk_basic._MV_YI_FACTOR` 由 1e8(亿元→元) 改为 1e4(亿元→万元)（已改代码）；
--     - us：`sync_us_basic` factor 由 1.0(元) 改为 1e-4（元→万元）（已改代码）。
--   前端选股表/详情弹窗按「万元 ÷1e4 → 亿」渲染，此前港美股被放大 1e4 倍
--   （碧桂园 857,400.00亿 → 真值 85.74亿）。
--
-- 破坏性：否（① 仅放宽精度并恢复被量化丢失的日内涨跌额；② 数值单位换算，语义对齐契约）。
-- 说明：两表均为普通表（非分区），rewrite 秒级；仍建议避开 ETL 时段执行。
-- 回滚：① ALTER ... TYPE NUMERIC(10,2)（会再次量化，无法还原）；② ×1e4 乘回。
-- ============================================================

-- ---------- ① change 精度 ----------
ALTER TABLE stock_daily_snapshot
    ALTER COLUMN change TYPE NUMERIC(12, 4);

UPDATE stock_daily_snapshot
   SET change = ROUND(close - pre_close, 4)
 WHERE close IS NOT NULL
   AND pre_close IS NOT NULL
   AND close - pre_close IS DISTINCT FROM change;

-- ---------- ② hk/us market_cap 单位 «元 → 万元»（幂等：以 migration_flags 标记防重复折算） ----------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM migration_flags WHERE flag_name = 'V020_hk_us_market_cap_yuan_to_wan') THEN
        UPDATE stock_daily_basic
           SET total_mv = ROUND(total_mv / 10000, 2),
               circ_mv  = ROUND(circ_mv  / 10000, 2)
         WHERE market IN ('hk', 'us')
           AND (total_mv IS NOT NULL OR circ_mv IS NOT NULL);

        UPDATE stock_daily_snapshot
           SET market_cap = ROUND(market_cap / 10000, 2),
               circ_mv    = ROUND(circ_mv    / 10000, 2)
         WHERE market IN ('hk', 'us')
           AND (market_cap IS NOT NULL OR circ_mv IS NOT NULL);

        INSERT INTO migration_flags (flag_name, executed_at) VALUES
            ('V020_hk_us_market_cap_yuan_to_wan', NOW());
        RAISE NOTICE 'V020: hk/us market_cap 元→万元 折算完成';
    ELSE
        RAISE NOTICE 'V020: hk/us market_cap 折算已执行过，跳过';
    END IF;
END $$;
