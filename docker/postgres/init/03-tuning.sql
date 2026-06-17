-- ==========================================
-- docker/postgres/init/03-tuning.sql
-- PostgreSQL 生产参数调优（SSD 通用配置）
-- 执行时机：表结构创建之后，首次启动时运行一次
-- 注意：ALTER SYSTEM 修改 postgresql.auto.conf，需重启生效
-- ==========================================

-- ---- 内存配置（基于容器 2G 内存限制）----
-- shared_buffers：建议 25% 物理内存，此处设为 512MB
ALTER SYSTEM SET shared_buffers = '512MB';
-- effective_cache_size：建议 75% 物理内存
ALTER SYSTEM SET effective_cache_size = '1GB';
-- work_mem：排序/Hash 操作内存上限（避免频繁磁盘溢出）
ALTER SYSTEM SET work_mem = '16MB';
-- maintenance_work_mem：VACUUM/ANALYZE/建索引 内存
ALTER SYSTEM SET maintenance_work_mem = '256MB';
-- temp_buffers：临时表上限
ALTER SYSTEM SET temp_buffers = '8MB';

-- ---- 连接配置 ----
-- 最大连接数（uvicorn 多 worker 场景，每个 worker 占用 1 个连接）
-- 4 workers × 2（健康预留）+ 20 并发 = ~28，建议设 50 留余量
ALTER SYSTEM SET max_connections = '100';

-- ---- 写入/Checkpoint 配置 ----
-- checkpoint_completion_target：平滑写入，降低 I/O 峰值
ALTER SYSTEM SET checkpoint_completion_target = '0.9';
-- wal_buffers：预写日志缓冲区
ALTER SYSTEM SET wal_buffers = '32MB';
-- 批量写入优化：增大提交间隔（单次事务提交可写更多）
ALTER SYSTEM SET commit_siblings = '5';

-- ---- 异步 I/O 与 SSD 优化 ----
-- random_page_cost：SSD 随机读与顺序读几乎等速（设为 1.1）
ALTER SYSTEM SET random_page_cost = '1.1';
-- effective_io_concurrency：并发 I/O 线程数（SSD 建议 200）
ALTER SYSTEM SET effective_io_concurrency = '200';

-- ---- 统计信息采样 ----
-- 提升统计信息采样率，减少糟糕执行计划
ALTER SYSTEM SET default_statistics_target = '200';

-- ---- 日志配置 ----
-- 记录慢查询（超过 1 秒的查询）
ALTER SYSTEM SET log_min_duration_statement = '1000';
-- 记录连接/断开
ALTER SYSTEM SET log_connections = 'off';
ALTER SYSTEM SET log_disconnections = 'off';

-- ---- 查询计划器稳定性 ----
-- 增大 planner 成本常数，降低选择非索引路径的倾向
ALTER SYSTEM SET seq_page_cost = '1.0';

\echo '[INIT] 03-tuning.sql 完成：PG 参数已写入 postgresql.auto.conf'
\echo '[INIT] 提示：执行 SELECT pg_reload_conf(); 或重启容器使参数生效'
