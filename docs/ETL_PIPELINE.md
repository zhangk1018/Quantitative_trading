# 数据管道完整流程说明

## 概述

本文档描述从数据下载到生成 parquet 文件的完整流程，包括每个步骤的验证方法和常见问题修复。

**执行顺序**（每日收盘后，由 `daily_job_runner.py` 自动按序执行）：
```
1. 健康检查 → 2. 股票列表同步 → 3. 日线数据下载 → 4. 复权因子同步 → 
5. 基本面数据同步 → 6. 缺失数据补全 → 7. 技术指标计算 → 
8. 宽表同步 → 9. Parquet 导出
```

**数据源优先级链**（Failover 模式，按 priority 自动降级）：
```
Baostock (主, 前复权) → Tushare (备1, 不复权→自动转换) → pytdx(通达信) (备2, 不复权→自动转换)
```

> **说明**：已移除 Akshare / Tencent / Sina / PyWenCai 数据源，保持数据源层仅保留 Baostock / Tushare / pytdx 三个。

---

## 统一调度入口

**脚本**：`backend/cron/daily_job_runner.py`

**功能**：
- 统一调度入口，按顺序自动执行所有 ETL 管道步骤
- 每一步执行状态记录到 `task_run_log` 表（含开始时间、结束时间、状态、错误信息）
- 内置自动重试机制，单步失败后自动重试 3 次
- 完整的日志输出，便于排查问题

**执行**：
```bash
PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/cron/daily_job_runner.py
```

**验证**：
```sql
-- 检查最近一次执行状态
SELECT step_name, status, started_at, finished_at, error_message
FROM task_run_log
WHERE run_date = CURRENT_DATE
ORDER BY step_name;
```

> **注意**：以下各阶段脚本均可独立手动执行，用于调试或补跑。日常运行推荐直接使用 `daily_job_runner.py` 一键完成全流程。

---

## 阶段 1：前置检查

### 1.1 管道健康检查

**脚本**：`backend/collector/etl/pipeline_health_check.py`

**功能**：
- 检查数据库连接
- 验证 stock_basic 表是否有数据
- 检查数据库分区是否覆盖目标日期
- 验证数据源（tushare/baostock）可用性
- 检查必需目录是否存在

**执行**：
```bash
./venv/bin/python backend/collector/etl/pipeline_health_check.py --pre-import
```

**验证**：
- 退出码 0 = 全部通过
- 退出码 1 = 有错误（必须修复）
- 退出码 2 = 有警告（建议修复）

**常见问题**：
- **数据库连接失败**：检查 `.env` 中的 `PG_HOST/PG_PORT/PG_DATABASE/PG_USER/PG_PASSWORD`
- **stock_basic 为空**：先执行 1.2 股票列表同步
- **分区未覆盖**：执行 `ALTER TABLE stock_quotes ATTACH PARTITION ...`

---

## 阶段 2：数据下载

### 2.1 股票列表同步

**脚本**：`backend/collector/etl/sync_stock_list_baostock.py`

**功能**：
- 从 Baostock 获取完整股票列表
- 更新 stock_basic 表（股票代码、名称、上市日期等）
- 标记退市股票

**执行**：
```bash
./venv/bin/python backend/collector/etl/sync_stock_list_baostock.py
```

**验证**：
```sql
-- 检查股票总数
SELECT COUNT(*) FROM stock_basic;
-- 预期：5000+ 只

-- 检查最新更新日期
SELECT MAX(updated_at) FROM stock_basic;
-- 预期：今天、
```

**常见问题**：
- **Baostock 连接失败**：检查网络连接，Baostock 服务偶尔不稳定
- **股票数量为 0**：检查 Baostock API 是否可用

---

### 2.2 日线数据下载

**脚本**：`backend/collector/etl/import_daily_data.py`

**功能**：
- 从 Baostock 下载日线 K 线数据
- 写入 stock_quotes 表
- 支持全量导入和增量导入

**执行**：
```bash
# 增量导入（推荐，每日使用）
./venv/bin/python backend/collector/etl/import_daily_data.py --incremental

# 增量Tushare下载（推荐每日使用）
./venv/bin/python backend/collector/etl/import_daily_data.py --data-source tushare --incremental

# 全量导入（首次使用）
./venv/bin/python backend/collector/etl/import_daily_data.py

# 单只股票
./venv/bin/python backend/collector/etl/import_daily_data.py --code 000001
```

**验证**：
```sql
-- 检查最新交易日期
SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d';
-- 预期：最新交易日（如 2026-06-15）

-- 检查股票数量
SELECT COUNT(DISTINCT code) FROM stock_quotes 
WHERE trade_date = (SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d') 
AND cycle = '1d';
-- 预期：5000+ 只

-- 检查数据完整性（随机抽样）
SELECT code, COUNT(*) as days 
FROM stock_quotes 
WHERE cycle = '1d' 
GROUP BY code 
ORDER BY days DESC 
LIMIT 10;
-- 预期：老股票应有 1000+ 天数据
```

**常见问题**：
- **下载中断**：重新执行 `--incremental`，脚本会跳过已下载的股票
- **某些股票数据为空**：可能是新股或停牌，执行 2.5 缺失数据补全
- **Baostock 超时**：脚本内置超时控制，可重试
- **Tushare 限速**：每天 5 次配额，超限后跳过

#### 2.2.1 pytdx（通达信）日线数据下载（备用数据源）

**脚本**：`backend/collector/etl/import_tdx_daily.py`

**功能**：
- 从 pytdx（通达信协议）下载日线 K 线数据
- 免费、无需 Token、无配额限制
- 作为 Tushare/Baostock 之后的第三级兜底数据源
- 不支持北交所（自动跳过 8 开头代码）

**执行**：
```bash
# 全量下载（约 30-40 分钟，5000+ 只股票）
PYTHONPATH=backend ./venv/bin/python backend/collector/etl/import_tdx_daily.py

# 增量下载（最近 30 天）
PYTHONPATH=backend ./venv/bin/python backend/collector/etl/import_tdx_daily.py --incremental

# 单只股票
PYTHONPATH=backend ./venv/bin/python backend/collector/etl/import_tdx_daily.py --code 000001

# 指定日期范围
PYTHONPATH=backend ./venv/bin/python backend/collector/etl/import_tdx_daily.py --start 2026-01-01 --end 2026-07-17
```

**验证**：
```sql
-- 同 2.2 日线数据下载验证
SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d';
SELECT COUNT(DISTINCT code) FROM stock_quotes 
WHERE trade_date = (SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d') AND cycle = '1d';
```

**常见问题**：
- **连接失败**：通达信主机 IP 可能变更，更新 `backend/collector/config/tdx_hosts.yaml` 中的主机列表
- **下载速度慢**：约 2-3 只/秒，全量需 30-40 分钟；可通过 `--incremental` 只下载最近数据
- **成交量单位**：pytdx 返回"手"（百股），脚本自动 ×100 转为"股"

---

### 2.3 复权因子同步

**脚本**：`backend/collector/etl/sync_adj_factor.py`

**功能**：
- 从 Baostock 获取复权因子
- 更新 stock_adj_factor 表
- 用于计算前复权/后复权价格

**执行**：
```bash
# 增量同步（最近 30 天）
./venv/bin/python backend/collector/etl/sync_adj_factor.py --incremental

# 全量同步（首次使用）
./venv/bin/python backend/collector/etl/sync_adj_factor.py
```

**验证**：
```sql
-- 检查最新日期
SELECT MAX(trade_date) FROM stock_adj_factor;
-- 预期：最新交易日

-- 检查覆盖率
SELECT COUNT(DISTINCT code) FROM stock_adj_factor 
WHERE trade_date = (SELECT MAX(trade_date) FROM stock_adj_factor);
-- 预期：5000+ 只
```

**常见问题**：
- **复权因子缺失**：重新执行全量同步
- **价格异常**：检查复权因子是否正确应用

---

### 2.4 基本面数据同步

**脚本**：`backend/collector/etl/sync_daily_basic.py`

**功能**：
- 同步日频基本面数据（PE/PB/换手率/市值等）
- 数据源优先级：Baostock（主，PE/PB/换手率）→ Tushare Pro（备，全量字段）
- 写入 stock_daily_basic 表

**执行**：
```bash
# 同步最新交易日
./venv/bin/python backend/collector/etl/sync_daily_basic.py --latest

# 同步指定日期
./venv/bin/python backend/collector/etl/sync_daily_basic.py --date 2026-06-15
```

**验证**：
```sql
-- 检查最新日期
SELECT MAX(trade_date) FROM stock_daily_basic;
-- 预期：最新交易日

-- 检查关键字段
SELECT COUNT(*) as total,
       SUM(CASE WHEN pe IS NOT NULL THEN 1 ELSE 0 END) as pe_cnt,
       SUM(CASE WHEN pb IS NOT NULL THEN 1 ELSE 0 END) as pb_cnt,
       SUM(CASE WHEN turnover_rate IS NOT NULL THEN 1 ELSE 0 END) as tr_cnt
FROM stock_daily_basic
WHERE trade_date = (SELECT MAX(trade_date) FROM stock_daily_basic);
-- 预期：pe/pb/turnover_rate 覆盖率 > 95%
```

**常见问题**：
- **Baostock 请求失败**：自动降级到 Tushare Pro；若 Tushare 未配置 TOKEN，则跳过
- **Tushare 限速**：daily_basic 接口 5次/天配额，超限后跳过
- **dv_ratio/ps_ttm 等字段为空**：Baostock 不提供这些字段，需通过 `sync_tushare_daily_basic.py` 用 Tushare Pro 补充
- **pe_ttm 覆盖率低（~72%）**：Tushare/Baostock 不提供亏损股的 pe_ttm（负值），导致约 1500 只亏损股 pe_ttm 缺失。需通过东方财富 API 补全亏损股 pe_ttm（负值），见下方 pe_ttm 补全脚本

**补充脚本**：`backend/collector/etl/sync_tushare_daily_basic.py`
```bash
# 补充 dv_ratio/dv_ttm/float_share/ps/ps_ttm
./venv/bin/python backend/collector/etl/sync_tushare_daily_basic.py
```

**pe_ttm 补全脚本**（亏损股 pe_ttm 兜底）：
```bash
# 用东方财富 API 补全 Tushare/Baostock 未提供的亏损股 pe_ttm（负值）
./venv/bin/python backend/collector/etl/fill_pe_ttm_eastmoney.py
```
> **说明**：Tushare 和 Baostock 均不提供亏损股的 pe_ttm（负值），导致约 1500 只股票 pe_ttm 缺失，覆盖率仅 ~72%。此脚本调用东方财富 API 逐个查询亏损股 pe_ttm 并写入 `stock_daily_basic` 表，将覆盖率提升至 100%。执行后需重跑宽表同步和 Parquet 导出。

---

### 2.5 缺失数据补全

**脚本**：`backend/collector/etl/fill_missing_data.py`

**功能**：
- 补全数据不足的股票（如科创板新股）
- 使用 Baostock 下载全量历史数据

**执行**：
```bash
# 补全所有数据不足的股票
./venv/bin/python backend/collector/etl/fill_missing_data.py

# 仅科创板
./venv/bin/python backend/collector/etl/fill_missing_data.py --market kcb

# 单只股票
./venv/bin/python backend/collector/etl/fill_missing_data.py --code 688001
```

**验证**：
```sql
-- 检查数据不足的股票
SELECT code, COUNT(*) as days 
FROM stock_quotes 
WHERE cycle = '1d' 
GROUP BY code 
HAVING COUNT(*) < 60
ORDER BY days;
-- 预期：只剩最近上市的新股
```

**常见问题**：
- **新股数据不足**：正常现象，上市不足 60 天的股票无法计算长期指标

---

## 阶段 3：数据计算

### 3.1 技术指标计算

**脚本**：`backend/clean/etl/compute_indicators_daily.py`

**功能**：
- 从 stock_quotes 读取价格数据
- 计算技术指标（MA/EMA/MACD/RSI/BOLL/KDJ/ATR/量比/换手率）
- 写入 stock_indicators 表

**执行**：
```bash
# 全市场计算（推荐）
./venv/bin/python backend/clean/etl/compute_indicators_daily.py

# 单只股票
./venv/bin/python backend/clean/etl/compute_indicators_daily.py --code 000001
```

**验证**：
```sql
-- 检查最新日期
SELECT MAX(trade_date) FROM stock_indicators WHERE cycle = '1d';
-- 预期：最新交易日

-- 检查关键字段
SELECT COUNT(*) as total,
       SUM(CASE WHEN dif IS NOT NULL AND dif != 0 THEN 1 ELSE 0 END) as dif_cnt,
       SUM(CASE WHEN dea IS NOT NULL AND dea != 0 THEN 1 ELSE 0 END) as dea_cnt,
       SUM(CASE WHEN macd IS NOT NULL AND macd != 0 THEN 1 ELSE 0 END) as macd_cnt,
       SUM(CASE WHEN rsi6 IS NOT NULL AND rsi6 != 0 THEN 1 ELSE 0 END) as rsi6_cnt,
       SUM(CASE WHEN rsi12 IS NOT NULL AND rsi12 != 0 THEN 1 ELSE 0 END) as rsi12_cnt,
       SUM(CASE WHEN rsi24 IS NOT NULL AND rsi24 != 0 THEN 1 ELSE 0 END) as rsi24_cnt
FROM stock_indicators 
WHERE trade_date = (SELECT MAX(trade_date) FROM stock_indicators WHERE cycle='1d') 
AND cycle = '1d';
-- 预期：所有字段覆盖率 > 95%
```

**常见问题**：
- **字段为 NULL**：检查字段映射是否正确（MACD→dif, MACD_SIGNAL→dea, MACD_HIST→macd）
- **RSI 字段缺失**：确认计算了 6/12/24 三个窗口
- **计算中断**：重新执行，脚本会跳过已计算的股票

---

### 3.2 宽表同步

**脚本**：`backend/collector/etl/daily_snapshot_sync.py`

**功能**：
- 合并 stock_quotes、stock_basic、stock_indicators、stock_daily_basic 四表数据
- 计算 MA/BOLL 等技术指标（基于 70 天窗口）
- 计算 14 个技术指标 pattern（MA/MACD/BOLL/RSI 筛选信号）
- 写入 stock_daily_snapshot 宽表

**执行**：
```bash
# 增量同步最新日期（推荐，每日使用）
./venv/bin/python backend/collector/etl/daily_snapshot_sync.py --latest

# 同步指定日期
./venv/bin/python backend/collector/etl/daily_snapshot_sync.py --date 2026-06-15

# 按日期范围同步（用于历史数据回补）
./venv/bin/python backend/collector/etl/daily_snapshot_sync.py --start-date 2025-01-01 --end-date 2026-07-22
```

**验证**：
```sql
-- 检查最新日期
SELECT MAX(trade_date) FROM stock_daily_snapshot;
-- 预期：最新交易日

-- 检查记录数
SELECT COUNT(*) FROM stock_daily_snapshot 
WHERE trade_date = (SELECT MAX(trade_date) FROM stock_daily_snapshot);
-- 预期：5000+ 条

-- 检查 pattern 字段（关键！）
SELECT 
  SUM(CASE WHEN ma_long_align THEN 1 ELSE 0 END) as ma_long,
  SUM(CASE WHEN macd_low_golden_cross THEN 1 ELSE 0 END) as macd_golden,
  SUM(CASE WHEN macd_bottom_divergence THEN 1 ELSE 0 END) as macd_bottom,
  SUM(CASE WHEN boll_break_upper THEN 1 ELSE 0 END) as boll_upper,
  SUM(CASE WHEN rsi_low_golden_cross THEN 1 ELSE 0 END) as rsi_golden
FROM stock_daily_snapshot 
WHERE trade_date = (SELECT MAX(trade_date) FROM stock_daily_snapshot);
-- 预期：所有字段 > 0（如果全为 0，说明计算失败）
```

**常见问题**：
- **pattern 全为 0**：检查 stock_indicators 表中 dif/dea/rsi12/rsi24 是否为 NULL
- **self 未定义错误**：确认 `_update_tech_patterns` 是独立函数，不是类方法
- **SQL 执行超时**：拆分为多个 UPDATE 语句，避免单次查询过于复杂

---
### 3.3 交易信号生成
**脚本**：`backend/clean/etl/signal_precompute.py`  
**功能**：  
- 基于 `stock_indicators` 表中的技术指标（如 MACD、RSI、BOLL）  
- 计算交易信号（如 MACD 金叉/死叉、RSI 超买超卖、BOLL 突破）  
- 将结果写入 `trade_signals` 表  

**执行**：
```bash
# 全市场批量计算（推荐）
./venv/bin/python backend/clean/etl/signal_precompute.py

# 强制全量重算（覆盖所有历史数据）
./venv/bin/python backend/clean/etl/signal_precompute.py --force-full

# 手工补某天（如2024-03-15）
export END_DATE=2024-03-15 && ./venv/bin/python backend/clean/etl/signal_precompute.py
```

**验证**：
```sql
-- 检查最新信号日期
SELECT MAX(trade_date) FROM trade_signals;

-- 检查关键信号类型
SELECT signal_type, COUNT(*) 
FROM trade_signals 
WHERE trade_date = (SELECT MAX(trade_date) FROM trade_signals)
GROUP BY signal_type;
-- 预期：至少包含 macd_cross、rsi_oversold、rsi_overbought、bollinger_breakout 四种类型

-- 验证单只股票信号
SELECT * FROM trade_signals 
WHERE code = '000001' 
ORDER BY trade_date DESC 
LIMIT 10;
```

**常见问题**：
- **`stock_indicators` 字段缺失**：  
  检查 `compute_indicators_daily.py` 是否成功运行，确保 `dif`/`dea`/`rsi6` 等字段存在
- **信号未生成**：  
  确认输入数据满足条件（如 MACD 金叉需 `DIF > DEA` 且前一日 `DIF ≤ DEA`）
- **内存不足**：  
  调整 `precompute_all_signals_batch` 的 `chunk_batch_size` 参数（默认 200）


---


## 阶段 4：数据导出

### 4.1 导出 Parquet

**脚本**：`backend/clean/enrich/export_parquet.py`

**功能**：
- 从 stock_daily_snapshot 导出最新日期数据
- 保存为 `data/price/daily/latest_quotes.parquet`
- 包含所有字段（76 列，含 14 个 pattern 列 + dif/dea/rsi_12/rsi_24）

**执行**：
```bash
./venv/bin/python backend/clean/enrich/export_parquet.py
```

**验证**：
```bash
# 检查文件是否存在
ls -lh data/price/daily/latest_quotes.parquet

# 检查文件大小
du -h data/price/daily/latest_quotes.parquet
# 预期：50-100 MB

# 使用 Python 验证
./venv/bin/python -c "
import pandas as pd
df = pd.read_parquet('data/price/daily/latest_quotes.parquet')
print(f'记录数: {len(df)}')
print(f'列数: {len(df.columns)}')
print(f'交易日期: {df.trade_date.iloc[0]}')
print(f'Pattern 列: {[c for c in df.columns if 'macd_' in c or 'rsi_' in c or 'boll_' in c or 'ma_' in c]}')
"
# 预期：5000+ 条，76 列，pattern 列存在
```

**常见问题**：
- **文件为空**：检查 stock_daily_snapshot 是否有数据
- **字段缺失**：确认 models.py 中定义了所有字段
- **dif/dea/rsi_12/rsi_24 为 NULL**：
  - 检查 stock_daily_snapshot 表是否有这 4 个列（`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`）
  - 检查 daily_snapshot_sync.py 的 INSERT/SELECT 语句是否包含这 4 个字段
  - 重新导出 parquet：`./venv/bin/python backend/clean/enrich/export_parquet.py`
- **后端服务未更新**：重启后端服务，让 DataLoader 重新加载 parquet

---

## 阶段 5：后端服务

### 5.1 重启后端服务

**执行**：
```bash
# 停止服务
./scripts/start.sh dev stop &
# 启动服务
./scripts/start.sh dev start &
```

**验证**：
```bash
# 检查 API 是否可用
curl http://localhost:8000/api/meta/

# 检查 pattern 筛选
curl "http://localhost:8000/api/stocks/?tech_macd=low_golden_cross&limit=10"
# 预期：返回 MACD 低位金叉的股票
```

---

## 每日执行脚本（推荐顺序）

```bash
#!/bin/bash
# daily_etl.sh - 每日 ETL 流程

set -e  # 遇到错误立即退出

echo "=== 1. 健康检查 ==="
./venv/bin/python backend/collector/etl/pipeline_health_check.py --pre-import

echo "=== 2. 股票列表同步 ==="
./venv/bin/python backend/collector/etl/sync_stock_list_baostock.py

echo "=== 3. 日线数据下载 ==="
./venv/bin/python backend/collector/etl/import_daily_data.py --incremental

echo "=== 4. 复权因子同步 ==="
./venv/bin/python backend/collector/etl/sync_adj_factor.py --incremental

echo "=== 5. 基本面数据同步 ==="
./venv/bin/python backend/collector/etl/sync_daily_basic.py --latest

echo "=== 6. 缺失数据补全（可选）==="
# ./venv/bin/python backend/collector/etl/fill_missing_data.py

echo "=== 7. 技术指标计算 ==="
./venv/bin/python backend/clean/etl/compute_indicators_daily.py

echo "=== 8. 生成交易信号 ==="
./venv/bin/python backend/clean/etl/signal_precompute.py

# 调整宽表同步顺序（需等待信号生成完成）
echo "=== 9. 宽表同步 ==="
./venv/bin/python backend/collector/etl/daily_snapshot_sync.py --latest

echo "=== 10. 导出 Parquet ==="
./venv/bin/python backend/clean/enrich/export_parquet.py

echo "=== 11. 重启后端服务 ==="
./scripts/start.sh dev restart &

echo "✅ ETL 流程完成"
```

---

## 常见问题速查表

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| 如何查看 daily_job_runner 执行状态 | 查询 task_run_log 表 | `SELECT * FROM task_run_log WHERE run_date = CURRENT_DATE ORDER BY step_name;` |
| stock_basic 为空 | 未执行股票列表同步 | 执行 `sync_stock_list_baostock.py` |
| stock_quotes 数据为空 | 未下载日线数据 | 执行 `import_daily_data.py --incremental` |
| dif/dea/rsi12/rsi24 为 NULL | MACD/RSI 字段映射错误 | 检查 `compute_indicators_daily.py` 字段映射 |
| pattern 全为 0 | stock_indicators 字段缺失 | 重新执行 `compute_indicators_daily.py` |
| self 未定义错误 | `_update_tech_patterns` 是类方法 | 改为独立函数 |
| parquet 文件未更新 | 未执行导出脚本 | 执行 `export_parquet.py` |
| API 返回旧数据 | 后端服务未重启 | 重启 uvicorn 服务 |
| Baostock 连接失败 | 网络问题 | 等待重试，自动降级到 Tushare/pytdx |
| Tushare 限速 | 超过每日 5 次配额 | 等待次日或跳过 |

---

## 数据流向图

```
数据源（Baostock/Tushare/pytdx(通达信)）
    ↓
stock_basic（股票列表）
stock_quotes（日线 K 线）
stock_adj_factor（复权因子）
stock_daily_basic（基本面）
    ↓
stock_indicators（技术指标）← compute_indicators_daily.py
    ↓
stock_daily_snapshot（宽表）← daily_snapshot_sync.py
    ↓
latest_quotes.parquet ← export_parquet.py
    ↓
后端 API（/api/stocks/）← loader.py 加载 parquet
```

---

## 附录：关键表说明

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| stock_basic | 股票基础信息 | code, name, listed_date |
| stock_quotes | 日线 K 线 | code, trade_date, open/high/low/close, volume |
| stock_adj_factor | 复权因子 | code, trade_date, adj_factor |
| stock_daily_basic | 基本面数据 | code, trade_date, pe, pb, total_mv |
| stock_indicators | 技术指标 | code, trade_date, dif, dea, macd, rsi6/12/24, ema5/10/20/60, atr, vol_ratio, turnover_rate, kdj_k/d/j |
| stock_daily_snapshot | 宽表（最终输出） | 包含所有字段 + 14 个 pattern 列 |

---

**文档版本**：v1.1  
**最后更新**：2026-07-18  
**维护者**：量量
