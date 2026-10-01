-- =====================================================================
-- V016: stock_quotes 增加覆盖索引 —— 支撑 monitor「近 2 年活跃股票数」聚合
-- 依赖方: /api/monitor/data-summary/ 慢查询治理（A+C 方案，2026-09-29）
-- =====================================================================
-- 背景: data-summary?market=cn 冷启动 48~65s、缓冲热 15s，其中单条
--       "SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle='1d'
--        AND market=? AND trade_date >= now()-730d" 独占 8.8s(cn)/5.0s(hk)，
--       导致端点耗时远超其 60s 缓存 TTL，前端每次轮询（同为 60s）必然缓存失效，
--       长请求占满浏览器同源并发（上限 6）→ 其余接口 Failed to fetch、导航 ERR_ABORTED。
--
-- 现状: 已有 idx_quotes_market_code_date (market, code, trade_date)。该列序恰好
--       匹配 COUNT(DISTINCT code) 的「按 code 有序输入」（GroupAggregate/Merge Append），
--       但缺 cycle 列 → 必须回表取 cycle 再过滤，实测 2025 分区回表 1.16s。
--
-- 方案: 保持列序不变、把 cycle 追加为载荷列 → (market, code, trade_date, cycle)，
--       使上述查询转为 Index Only Scan，无需回表。
--       ⚠️ 列序不可改为 (market, cycle, trade_date, code)：实测该列序会破坏
--          code 有序性，规划器改走显式排序，退化为原计划且索引不被选用。
--
-- 实测收益（2025 分区，EXPLAIN ANALYZE BUFFERS）:
--       2025 分区 Index Scan 1159ms → Index Only Scan 656ms
--       整条 COUNT(DISTINCT) 4760ms → 3100ms（该项含尚未加索引的 2024/2026 分区）
--
-- 建法: 沿用 V008 先例，父表普通 CREATE INDEX（分区表 CONCURRENTLY 不支持）；
--       幂等 IF NOT EXISTS，可重复执行。执行期间 stock_quotes 有 1~2 分钟
--       ACCESS EXCLUSIVE 锁窗口，须避开 ETL 写入时段（16:30~19:00）执行。
--
-- 遗留: 新索引 (market, code, trade_date, cycle) 以旧索引 (market, code, trade_date)
--       为前缀，旧索引此后冗余；已由 V017 删除（2026-09-29），本文件保留历史记录。
--
-- 数据库: PostgreSQL 18.6（stock_quotes 按年分区，共 69 个分区）
-- =====================================================================
CREATE INDEX IF NOT EXISTS idx_quotes_market_code_date_cycle
    ON stock_quotes(market, code, trade_date, cycle);

COMMENT ON INDEX idx_quotes_market_code_date_cycle IS
    '覆盖索引：支撑 monitor data-summary 的「近 N 年活跃股票数」COUNT(DISTINCT code) 聚合，'
    '使 (market, code, trade_date) 访问路径转为 Index Only Scan；cycle 仅作载荷列，列序不可前置';