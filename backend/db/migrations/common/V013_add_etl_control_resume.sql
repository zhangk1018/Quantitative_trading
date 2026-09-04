-- =====================================================================
-- V013: 港股/美股下载 断点续传 —— etl_control 增加 last_processed_code 游标列
-- 依赖方: 协作单 30.0 港股/美股下载强化（限流 + 断点续传）
-- =====================================================================
-- 功能: 下载中断后，重启时从上次已处理的标的（游标）继续，而非从 0 重拉全部标的。
-- 幂等性: ADD COLUMN IF NOT EXISTS，可重复执行。
-- 数据库: PostgreSQL 18.6
-- =====================================================================
ALTER TABLE etl_control
    ADD COLUMN IF NOT EXISTS last_processed_code VARCHAR(40);

COMMENT ON COLUMN etl_control.last_processed_code IS
    '断点续传游标：记录本轮增量/全量下载已处理到的最后一个 code（如 0700.HK / AAPL）；整批跑完后置 NULL';