-- 为 stock_indicators 表添加 BOLL 指标列
-- 用于方案 A：在指标计算阶段存储 BOLL 原始值，供宽表同步和 K 线 API 使用

ALTER TABLE stock_indicators
    ADD COLUMN IF NOT EXISTS boll_upper NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS boll_mid   NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS boll_lower NUMERIC(10, 2);

COMMENT ON COLUMN stock_indicators.boll_upper IS '布林带上轨 (20日中轨+2*标准差)';
COMMENT ON COLUMN stock_indicators.boll_mid   IS '布林带中轨 (20日移动平均)';
COMMENT ON COLUMN stock_indicators.boll_lower IS '布林带下轨 (20日中轨-2*标准差)';
