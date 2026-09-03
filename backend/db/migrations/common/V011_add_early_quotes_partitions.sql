-- =====================================================================
-- V011: 港股/美股改造 —— stock_quotes 补齐美股早期年份分区
-- 依赖方: 协作单 30.0 V3（M3 美股 ETL）
-- =====================================================================
-- 背景：stock_quotes 年度分区原只覆盖 1990~2028（A 股最早 1990 年上市）。
--   但美股标普500 成分股大量在 1960~1989 年上市（如 AEP 1962、ADSK 1985、
--   JNJ 于纽交所 1944/1960s、MSFT 1986），引入美股后 `--init` 拉 max 全量
--   会落入无分区年份，报 `no partition of relation stock_quotes found`。
--   本迁移补齐 1960~1989 早期分区（美股最早的标普500 成分约 1960s 上市）。
--   若后续需更早（如美股最长上市早于 1960），可再补，但当前核心池最老 ~1962。
-- 幂等性：CREATE TABLE IF NOT EXISTS + PARTITION OF，可重复执行。
-- 数据库：PostgreSQL 18.6
-- =====================================================================

DO $$
DECLARE
    y INTEGER;
BEGIN
    FOR y IN 1960..1989 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS stock_quotes_%s PARTITION OF stock_quotes '
            'FOR VALUES FROM (%L) TO (%L)',
            y,
            make_date(y, 1, 1),
            make_date(y + 1, 1, 1)
        );
    END LOOP;
END;
$$;

-- =====================================================================
-- 校验：确认 stock_quotes 分区覆盖 1960~2028
-- =====================================================================
SELECT substring(relname FROM 'stock_quotes_([0-9]{4})') AS yr
FROM pg_class
WHERE relname ~ '^stock_quotes_[0-9]{4}$'
ORDER BY yr DESC
LIMIT 5;