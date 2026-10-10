-- V018: stock_quotes 增加 adj_share（复权股本因子 a），支撑港股仿射复权口径
--
-- 背景（协作单 45.0）：新浪港股 `adjust='hfq'` 是**仿射**口径 `hfq = a*raw + b`
--   （a = 累计股本因子，送股/拆股；b = 累计加性调整，现金分红等），
--   并非「raw × 单一复权倍率」的乘性口径。实测：碧桂园 02007 a≈1、b≈5.2415；
--   腾讯 00700 a=5.0000、b≈278.93；汇丰 00005 a=4.2501、b≈375.31。
--
-- 由此带来两个问题，本列用于解决第 2 个（第 1 个已在 detect_factor_dates 修复）：
--   1. 除权日检测按该比值变化 >1% 判定 → 比值随行情逐日漂移 → 几乎天天误标（已修）；
--   2. 复权 O/H/L 按 `raw_x × (adj_close/close)` 折算 → 日内波幅被放大
--      `(a + b/close)/a` 倍（碧桂园 ~30 倍）→ 本列存下 a，使其按 `a*raw_x + b` 正确折算。
--
-- 语义：该行所处复权区间的股本因子 a（未除权日恒定；送股/拆股日跳变）。
--   adj_x = adj_share * raw_x + (adj_close - adj_share * raw_close)
-- 消费方：
--   - import_hk_daily.clean_and_split → 逐只路径写入；
--   - import_hk_daily._snapshot_quotes_df → 增量批量快照路径读取上一行 a 做仿射换算；
--   - split_raw_adj → 由数据源透传的 Adj Share 写入（缺失时退化为乘性倍率）。
-- 兼容性：仅港股/美股写（A 股该列保持 NULL）；旧数据为 NULL 时下游自动退化为原乘性口径。
--
-- 风险：仅新增可空列、无默认值、不改现有列类型 → PostgreSQL 11+ 为元数据操作，
--   不重写分区数据、不阻塞读写。可回滚（DROP COLUMN），无数据破坏性。
--
-- 数据库: PostgreSQL 18.6（stock_quotes 按年分区，共 69 个分区）

ALTER TABLE stock_quotes ADD COLUMN IF NOT EXISTS adj_share NUMERIC(12, 6);

COMMENT ON COLUMN stock_quotes.adj_share IS
  '复权股本因子 a（仿射口径 adj = a*raw + b 的斜率）；港股/美股写入，A 股为 NULL（V018）';

-- 校验：列已存在
SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_name = 'stock_quotes' AND column_name = 'adj_share';
