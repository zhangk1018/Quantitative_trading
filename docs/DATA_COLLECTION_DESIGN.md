# 数据采集与校验设计文档

**创建日期**：2026-06-04  
**最后更新**：2026-06-04

---

## 一、定时任务调度方案

### 推荐方案：系统级调度（crontab）

**理由**：
- 独立进程，不占用主服务资源
- 系统级守护，崩溃可自动重启
- 成熟的日志轮转机制
- 运维友好，符合 Linux 最佳实践

### 任务清单

| 任务名称 | 执行时间 | cron 表达式 | 说明 |
|----------|----------|-------------|------|
| 收盘作业 | 16:00（周一至周五） | `0 16 * * 1-5` | 下载当日交易数据 |
| 每日数据更新 | 20:10 | `10 20 * * *` | 更新行情和技术指标 |
| 股票列表更新 | 17:30 | `30 17 * * *` | 更新股票基本信息 |
| 数据完整性检查 | 03:00 | `0 3 * * *` | 检查数据完整性和一致性 |
| 数据库维护 | 周六 02:00 | `0 2 * * 6` | 清理和优化 |

### crontab 配置示例

```bash
# 收盘作业
0 16 * * 1-5 /path/to/venv/bin/python /opt/quant/scripts/closing_job.py >> /var/log/quant/closing.log 2>&1

# 每日数据更新
10 20 * * * /path/to/venv/bin/python /opt/quant/scripts/daily_update.py >> /var/log/quant/daily_update.log 2>&1

# 股票列表更新
30 17 * * * /path/to/venv/bin/python /opt/quant/scripts/update_stock_list.py >> /var/log/quant/stock_list.log 2>&1

# 数据完整性检查
0 22 * * * /path/to/venv/bin/python /opt/quant/scripts/integrity_check.py >> /var/log/quant/integrity.log 2>&1

# 数据库维护（周六）
0 2 * * 6 /path/to/venv/bin/python /opt/quant/scripts/weekly_maintenance.py >> /var/log/quant/maintenance.log 2>&1
```

---

## 二、数据校验流程

### 校验流程

```
原始数据
    │
    ▼
┌──────────────┐
│  格式校验    │ → 字段完整性、数据类型
└──────┬───────┘
       │通过
       ▼
┌──────────────┐
│  业务规则校验 │ → 价格逻辑、涨跌幅、成交量
└──────┬───────┘
       │通过
       ▼
┌──────────────┐
│  跨数据源校验 │ → 自动从备用数据源交叉验证
└──────┬───────┘
       │通过
       ▼
    入库存储
       │
       ▼
  更新水位线

  任一环节失败 → 写入脏数据表 → 自动修复或标记异常
```

### 跨数据源校验规则

| 校验项 | 逻辑 | 允许差异 | 处理方式 |
|--------|------|---------|---------|
| 收盘价 | 多源收盘价比对 | < 0.5% | 取加权平均值 |
| 成交量 | 多源成交量比对 | < 5% | 取最大值 |
| 涨跌停标记 | 验证价格是否触及涨跌停 | - | 以备用源为准 |

**自动修复策略**：
1. 差异在允许范围内 → 自动采用校验后的数据
2. 差异超限 → 写入脏数据表，标记为 `cross_validate_failed`
3. 备用数据源不可用 → 保留原始数据，标记警告

---

## 三、数据校验规则明细

### 3.1 格式校验

| 规则 | 校验内容 | 错误类型 |
|------|---------|---------|
| 字段完整性 | code, trade_date, open, high, low, close, volume | `missing_field` |
| 数据类型 | 价格为数值型、日期为 YYYY-MM-DD | `type_error` |

### 3.2 业务规则校验

| 规则 | 校验逻辑 | 错误类型 |
|------|---------|---------|
| 价格关系 | `high >= low`, `low <= open <= high`, `low <= close <= high` | `price_range_error` |
| 涨跌幅计算 | `abs(pct_change - (close - pre_close) / pre_close * 100) < 0.01` | `pct_change_error` |
| 成交量 | `volume >= 0` | `volume_error` |
| 成交额 | `amount >= 0` | `amount_error` |
| 换手率 | `0 <= turnover_rate <= 100` | `turnover_error` |
| 日期合法性 | trade_date 在交易日历中且 is_open=1 | `date_error` |

### 3.3 脏数据处理

**规则**：
- 校验失败的数据自动写入 `stock_quotes_dirty` 表
- 自动尝试从备用数据源获取正确数据
- 备用源数据校验通过后，自动覆盖原数据
- 备用源也失败的数据，标记为需人工处理

---

## 四、执行计划

### 今日（2026-06-04）

| 任务 | 负责人 | 说明 |
|------|--------|------|
| 数据校验逻辑实现 | 量量 | 实现格式校验和业务规则校验 |
| crontab 部署 | 量量 | 配置定时任务 |

### 明日（2026-06-05）

| 任务 | 负责人 | 说明 |
|------|--------|------|
| 跨数据源校验实现 | 量量 | 实现自动交叉验证逻辑 |
| 脏数据表完善 | 量量 | 确保自动修复流程闭环 |

### 本周内

| 任务 | 负责人 | 说明 |
|------|--------|------|
| 完整性检查脚本 | 量量 | 定时检查数据完整性 |
| 告警机制 | 量量 | 校验失败告警 |
| 测试验证 | K | 功能验收 |

---

## 五、相关文件

| 文件 | 说明 |
|------|------|
| `collector/etl/import_daily_data.py` | 数据导入主脚本 |
| `clean/processor/data_validator.py` | 数据校验器 |
| `collector/scheduler/` | 调度相关代码 |
| `storage/postgresql_storage.py` | 数据库存储 |
