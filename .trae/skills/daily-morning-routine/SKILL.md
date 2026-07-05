---
name: "daily-morning-routine"
description: "每日数据管道晨检：检查 stock_quotes 数据下载、stock_daily_snapshot 清洗同步、补全状态，以及协作单待办任务。每天第一件事调用。"
---

# 每日数据管道晨检

在开始当天任务前执行此晨检流程。目标是确认数据管道各环节是否正常，及时发现异常。

## 检查流程

### 1. 加载 .env 配置

先从 `.env` 获取数据库密码等敏感配置，设置到环境变量：

```bash
export $(grep -v '^#' /Users/zhangk/workspace/Quantitative_trading/.env | xargs)
```

数据库连接参数（目前）：
- host: `localhost`
- port: `5432`
- database: `quant_trading`
- user: `quant_user`
- password: `${PG_PASSWORD}`
- Python venv: `/Users/zhangk/workspace/Quantitative_trading/venv/bin/python`

### 2. 检查数据下载（stock_quotes）

编写并运行临时 Python 脚本检查以下指标：

#### a. 最新交易日期数据量

```sql
SELECT trade_date, COUNT(*) 
FROM stock_quotes 
WHERE cycle='1d' AND trade_date >= CURRENT_DATE - INTERVAL '3 days'
GROUP BY trade_date 
ORDER BY trade_date DESC;
```

**健康标准**：
- 今天如果是交易日，应有 ~4500+ 条记录
- 对比最近几个交易日的数据量，不应有明显下降（下降超过 10% 需告警）
- 最新交易日距离今天不应超过 2 个自然日（周末除外，周末可接受 2-3 天）

#### b. 一致性与缺失检查

```sql
-- 去重股票数
SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle='1d';
-- 今日未更新的股票数
SELECT COUNT(*) FROM (
  SELECT DISTINCT code FROM stock_quotes WHERE cycle='1d'
  EXCEPT
  SELECT code FROM stock_quotes WHERE cycle='1d' AND trade_date='<最新交易日>'
) t;
```

#### c. 判断标准

| 指标 | 健康 | 需关注 | 异常 |
|------|------|--------|------|
| 最新交易日数据量 | ≥4500 | 3000-4500 | <3000 |
| 缺失股票数 | ≤100 | 100-500 | >500 |
| 距离今天天数 | ≤2天(工作日) | 3-5天 | >5天 |

### 3. 检查数据清洗/宽表同步（stock_daily_snapshot）

```sql
SELECT trade_date, COUNT(*) 
FROM stock_daily_snapshot 
WHERE trade_date >= CURRENT_DATE - INTERVAL '3 days'
GROUP BY trade_date 
ORDER BY trade_date DESC;
```

**健康标准**：宽表的日期覆盖范围应与 stock_quotes 保持一致。

### 4. 检查数据补全

检查宽表的字段完整性：

```sql
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN pe_ttm IS NOT NULL THEN 1 ELSE 0 END) as pe_ttm_count,
    SUM(CASE WHEN ma5 IS NOT NULL THEN 1 ELSE 0 END) as ma5_count,
    SUM(CASE WHEN macd IS NOT NULL THEN 1 ELSE 0 END) as macd_count,
    SUM(CASE WHEN rsi_6 IS NOT NULL THEN 1 ELSE 0 END) as rsi6_count,
    SUM(CASE WHEN boll_mid IS NOT NULL THEN 1 ELSE 0 END) as boll_count
FROM stock_daily_snapshot 
WHERE trade_date = '<最新交易日>';
```

关键字段合规阈值：
- **pe_ttm**：≥72% 正常（Tushare 数据源天然覆盖限制，ST/退市股无估值）
- **ma5, macd, rsi_6, boll_mid**：≥80% 正常（技术指标，大部分股票有数据）
- 所有字段 ≥95% 时仅显示绿色，不展示详细报错

### 5. 检查任务日志

查看日志中的错误信息：

```bash
# 检查最近错误
grep -c "ERROR\|失败\|❌" /Users/zhangk/workspace/Quantitative_trading/logs/daily_import.log 2>/dev/null
grep -c "ERROR\|失败\|❌" /Users/zhangk/workspace/Quantitative_trading/logs/clean_data_*.log 2>/dev/null

# 获取最近一次导入结果
tail -5 /Users/zhangk/workspace/Quantitative_trading/logs/daily_import.log 2>/dev/null | grep "增量导入完成"
```

### 6. 检查协作单待办

查看以下两个文件的待办任务：

1. **[docs/协作单.md](file:///Users/zhangk/workspace/Quantitative_trading/docs/协作单.md)** — 活动工单区：
   - 查找状态为 `NEW`（待认领）或 `REOPENED`（需重新处理）的工单
   - 优先认领属于量量职责范围（backend）的 `NEW` 工单
   - 优先跟进自己上次处理的 `REOPENED` 工单
   - 关注 P0（紧急）任务

2. **[.trae/topics.md](file:///Users/zhangk/workspace/Quantitative_trading/.trae/topics.md)** — 跨会话通知：
   - 读取最新通知，确认是否有新的状态变更需要响应
   - 特别关注 `→量量` 标记的通知（明确由量量接单）

## 报告格式

向用户输出以下格式的晨检报告：

```markdown
## 每日数据管道晨检报告 (YYYY-MM-DD)

### 数据下载
- 最新交易日: 2026-06-XX, 共 XXXX 条
- 缺失股票数: XX 只
- 状态: ✅ 正常 / ⚠️ 需关注 / 🚨 异常
- 说明: ...

### 宽表同步
- 最新交易日: 2026-06-XX, 共 XXXX 条
- 状态: ✅ 正常 / ⚠️ 需关注 / 🚨 异常

### 数据补全
- 字段完整率: XX%
- 状态: ✅ 正常 / ⚠️ 需关注

### 待办任务
- 协作单活动工单: X 个（NEW: X, REOPENED: X, VERIFY: X）
- P0 任务: X 个 | P1 任务: X 个
- topics.md 新通知: X 条需响应
- 新/变化的重要事项: ...
```

## 异常处理

当发现异常时：
1. **数据下载异常（数据缺失）**：如果最新交易日是工作日且数据缺失，尝试手动触发增量导入：
   ```bash
   cd /Users/zhangk/workspace/Quantitative_trading && \
   PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/collector/etl/import_daily_data.py --incremental
   ```
2. **宽表同步异常**：尝试手动触发宽表同步：
   ```bash
   cd /Users/zhangk/workspace/Quantitative_trading && \
   PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/collector/etl/daily_snapshot_sync.py --latest
   ```
3. **待办任务阻塞**：协作单中有 P0 未处理时，优先处理或提醒用户

## 注意

- 所有数据库查询使用临时 Python 脚本执行，脚本存放在 `/tmp/` 目录，用完不需要清理
- 查询时需避免长时间占用的查询，使用索引友好的查询条件（按日期过滤）
- stock_quotes 是分区表（~1600 万行），避免全表扫描