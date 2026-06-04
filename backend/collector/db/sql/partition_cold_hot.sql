-- ==========================================
-- 冷热数据分离策略 - 生产部署版
-- PostgreSQL 表空间分离方案
-- ==========================================

-- ⚠️ 生产部署前置条件（必须执行）
-- 在 OS 层面创建表空间目录并授权：
-- sudo mkdir -p /data/cold /data/hot
-- sudo chown postgres:postgres /data/cold /data/hot
-- sudo chmod 700 /data/cold /data/hot

-- ==========================================
-- 1. 创建表空间（需要超级用户权限）
-- ==========================================
-- 冷数据表空间（HDD/大容量存储，用于历史数据归档）
-- CREATE TABLESPACE IF NOT EXISTS cold_storage 
--     LOCATION '/data/cold' 
--     WITH (seq_page_cost = 2.0, random_page_cost = 4.0);

-- 热数据表空间（SSD/高速存储，用于近1年活跃数据）
-- CREATE TABLESPACE IF NOT EXISTS hot_storage 
--     LOCATION '/data/hot' 
--     WITH (seq_page_cost = 1.0, random_page_cost = 1.0);

-- ==========================================
-- 2. 冷热数据分离策略
-- ==========================================
-- 热数据（近1年）：2025, 2026 分区 -> hot_storage
-- 温数据（1-3年）：2022, 2023, 2024 分区 -> cold_storage  
-- 冷数据（3年以上）：2015-2021 分区 -> cold_storage (归档)

-- ==========================================
-- 3. 迁移冷数据到冷存储表空间
-- ==========================================
-- 迁移 stock_quotes 冷数据分区（2015-2024）
-- ALTER TABLE stock_quotes_2015 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_quotes_2016 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_quotes_2017 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_quotes_2018 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_quotes_2019 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_quotes_2020 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_quotes_2021 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_quotes_2022 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_quotes_2023 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_quotes_2024 SET TABLESPACE cold_storage;

-- 迁移 stock_indicators 冷数据分区（2015-2024）
-- ALTER TABLE stock_indicators_2015 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_indicators_2016 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_indicators_2017 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_indicators_2018 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_indicators_2019 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_indicators_2020 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_indicators_2021 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_indicators_2022 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_indicators_2023 SET TABLESPACE cold_storage;
-- ALTER TABLE stock_indicators_2024 SET TABLESPACE cold_storage;

-- ==========================================
-- 4. 迁移热数据到热存储表空间（近1年）
-- ==========================================
-- ALTER TABLE stock_quotes_2025 SET TABLESPACE hot_storage;
-- ALTER TABLE stock_quotes_2026 SET TABLESPACE hot_storage;
-- ALTER TABLE stock_indicators_2025 SET TABLESPACE hot_storage;
-- ALTER TABLE stock_indicators_2026 SET TABLESPACE hot_storage;

-- ==========================================
-- 5. 索引冷热分离（可选）
-- ==========================================
-- 将冷数据的索引也迁移到冷存储（减少热存储占用）
-- ALTER INDEX idx_quotes_code_cycle_date SET TABLESPACE cold_storage;

-- ==========================================
-- 6. 自动归档策略建议
-- ==========================================
-- 推荐使用 pg_partman 工具进行自动分区管理：
-- 1. 安装 pg_partman 扩展
-- 2. 配置父表使用自动分区
-- 3. 设置 cron 任务定期维护分区
-- 
-- 手动归档示例（每年执行）：
-- 1. 将上一年数据迁移到冷存储
-- 2. 创建新年度分区（如需）
-- 3. 监控分区大小和查询性能

-- ==========================================
-- 7. 当前环境状态检查
-- ==========================================
-- 检查表空间状态
-- SELECT spcname, spclocation FROM pg_tablespace;

-- 检查分区所在表空间
-- SELECT 
--     c.relname AS partition_name,
--     ts.spcname AS tablespace_name
-- FROM pg_class c
-- LEFT JOIN pg_tablespace ts ON c.reltablespace = ts.oid
-- WHERE c.relname LIKE 'stock_quotes_%' OR c.relname LIKE 'stock_indicators_%'
-- ORDER BY c.relname;