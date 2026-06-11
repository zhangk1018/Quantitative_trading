# 定时任务调度系统使用指南

## 概述

量化交易系统提供两套调度机制，可配合使用：

| 调度方式 | 用途 | 复杂度 | 当前状态 |
|----------|------|--------|----------|
| **cron 定时任务** | 简单、可靠的固定时间执行（盘后同步/质量检查） | 低 | ✅ 生产使用 |
| **APScheduler 调度器** | 程序内带重试、优先级、告警的复杂任务编排 | 中 | ⚡ 备选方案 |
| **智能调度系统** | 多数据源轮换、熔断、动态权重的高级调度 | 高 | 📦 可用组件 |

---

## 一、cron 定时任务（当前主力）

### 1.1 配置方式

配置文件位于 `backend/collector/etl/crontab_config.sh`，执行后可生成 crontab。

```bash
# 生成 crontab 配置
cd /Users/zhangk/workspace/Quantitative_trading
bash backend/collector/etl/crontab_config.sh

# 启用定时任务
crontab /tmp/quant_crontab

# 查看当前 crontab
crontab -l
```

### 1.2 定时任务清单

| 时间 | 频率 | 任务 | 脚本路径 | 说明 |
|------|------|------|----------|------|
| 16:00 | 周一至周五 | 盘后数据同步 | `backend/collector/etl/daily_snapshot_sync.py` | 下载当日交易数据并入库 |
| 21:00 | 每日 | 复权因子同步 | `backend/collector/etl/sync_adj_factor.py --incremental` | 增量同步复权因子 |
| 22:00 | 每日 | 数据完整性检查 | `backend/clean/quality/check_data_quality.py` | 检查数据完整性和一致性 |
| 周日 02:00 | 每周 | 全量数据校验 | `backend/collector/etl/daily_snapshot_sync.py` | 同步过去7天数据用于校验 |
| 01:00 | 每日 | 日志清理 | `find ... -mtime +5 -delete` | 清理5天前的日志文件 |

### 1.3 查看执行状态

```bash
# 日志位置
# cron 输出日志：
tail -f logs/etl/daily_sync.log
tail -f logs/etl/weekly_sync.log
tail -f logs/etl/integrity_check.log

# 查看今日同步记录
grep "$(date +%Y-%m-%d)" logs/etl/daily_sync.log

# 数据库校验
# 查看最新交易日期
psql -h localhost -U quant_user -d quant_trading -c "SELECT MAX(trade_date) FROM stock_quotes;"

# 查看今日新增记录数
psql -h localhost -U quant_user -d quant_trading -c "
    SELECT COUNT(*) FROM stock_quotes WHERE trade_date = CURRENT_DATE;
"

# 查看失败的任务
psql -h localhost -U quant_user -d quant_trading -c "
    SELECT id, task_name, status, message, created_at
    FROM task_progress
    WHERE status = 'failed'
    ORDER BY created_at DESC LIMIT 10;
"
```

### 1.4 手动执行

```bash
# 手动盘后同步
cd /Users/zhangk/workspace/Quantitative_trading
source venv/bin/activate
python backend/collector/etl/daily_snapshot_sync.py --latest

# 手动指定日期范围同步
python backend/collector/etl/daily_snapshot_sync.py --start-date 2026-06-01 --end-date 2026-06-04

# 手动复权因子同步（全量）
python backend/collector/etl/sync_adj_factor.py

# 手动复权因子同步（增量）
python backend/collector/etl/sync_adj_factor.py --incremental

# 手动行业数据补全
python backend/collector/etl/fill_industry.py

# 手动数据完整性检查
python backend/clean/quality/check_data_quality.py
```

### 1.5 配置参数

定时任务的核心参数在 `backend/pipeline.yaml` 中配置：

```yaml
scheduler:
  daily_update_time: "20:10"         # 每日行情更新时间
  closing_time: "15:10"              # 收盘作业时间
  daily_stock_list_update_time: "17:30"
  weekly_maintenance_day: 6          # 0=周一, 6=周日
  weekly_maintenance_time: "02:00"
  integrity_check_time: "03:00"      # 完整性检查时间（cron 实际使用 22:00）
  max_download_threads: 2
  max_retries: 3
  retry_delay: 60
```

---

## 二、APScheduler 任务调度器（备选）

### 2.1 概述

`backend/task_scheduler.py` 基于 APScheduler，提供轻量级应用内调度，支持：
- 任务优先级（高/中/低）
- 自动重试（可配置次数和延迟）
- 错误分类（可重试 vs 不可重试）
- 任务进度记录到 `task_progress` 表

### 2.2 启动方式

```bash
cd /Users/zhangk/workspace/Quantitative_trading/backend
python task_scheduler.py
```

### 2.3 查看日志

```bash
# 调度器日志
tail -f backend/logs/task_scheduler.log

# 查看任务完成记录
grep "任务完成" backend/logs/task_scheduler.log

# 查看任务失败记录
grep "任务失败" backend/logs/task_scheduler.log
```

### 2.4 配置加载

调度器从 `pipeline.yaml` 加载定时配置，可在配置中调整各任务的执行时间。

### 2.5 重试机制

| 参数 | 值 | 说明 |
|------|-----|------|
| 最大重试次数 | 3次 | 超过后标记为失败 |
| 初始重试延迟 | 60秒 | 首次重试等待 |
| 指数退避 | 是 | 重试间隔逐渐增加 |

---

## 三、智能调度系统（可选组件）

### 3.1 概述

智能调度系统位于 `backend/collector/scheduler/`，提供高级调度能力，适用于需要多数据源轮换、熔断保护、告警通知的场景。

### 3.2 核心组件

| 组件 | 路径 | 用途 |
|------|------|------|
| SmartScheduler | `collector/scheduler/smart_scheduler.py` | 主调度器，按配置定时执行数据采集 |
| SmartDataSourceManager | `collector/scheduler/smart_dsm.py` | 智能数据源管理器，多数据源轮换、动态权重 |
| CircuitBreaker | `collector/scheduler/circuit_breaker.py` | 熔断器，保护系统免受故障数据源影响 |
| AlertManager | `collector/scheduler/alert.py` | 多渠道告警（控制台/钉钉/邮件） |
| ScheduleConfig | `collector/scheduler/config.py` | 灵活调度配置（日期规则/采集间隔） |

### 3.3 系统架构

```
SmartScheduler
    ├── SmartDataSourceManager
    │   ├── CircuitBreaker (熔断器)
    │   ├── DataSourceMetrics (性能指标)
    │   └── DynamicWeightStrategy (权重策略)
    ├── FlexibleScheduleConfig (调度配置)
    ├── AlertManager (告警管理器)
    └── PostgreSQLStorage (数据存储)
```

### 3.4 数据源管理

#### 熔断器状态

| 状态 | 说明 |
|------|------|
| `closed` | 正常状态，允许请求通过 |
| `open` | 熔断状态，拒绝请求 |
| `half-open` | 半开状态，允许少量请求测试恢复 |

**熔断时间（指数退避）**：
- 第1次：60秒 → 第2次：120秒 → 第3次：240秒 → ... → 第N次：60×2^(N-1)秒

#### 动态权重调整

数据源的权重根据性能指标动态调整，影响因子：
- 成功率
- 平均响应时间
- 最大响应时间
- 请求总数

### 3.5 启动智能调度

```python
from collector.scheduler.smart_scheduler import SmartScheduler
from collector.scheduler.config import ScheduleConfig
from collector.scheduler.smart_dsm import SmartDataSourceManager
from storage.postgresql_storage import PostgreSQLStorage

# 初始化组件
storage = PostgreSQLStorage()
config = ScheduleConfig.default_config()
dsm = SmartDataSourceManager()

# 创建并启动调度器
scheduler = SmartScheduler(config, dsm, storage)
scheduler.setup_schedule()
scheduler.start()

try:
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    scheduler.shutdown()
```

### 3.6 告警配置

在 `.env` 中配置告警通道：

```env
# 钉钉告警（可选）
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=...

# 邮件告警（可选）
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USER=your@email.com
EMAIL_PASSWORD=your_password
```

### 3.7 常用操作

```bash
# 暂停调度器
scheduler.pause()
# 恢复
scheduler.resume()

# 手动重置熔断器
cb = dsm.circuit_breakers['BaoStock']
cb.reset()

# 查看数据源性能指标
metrics = dsm.metrics['BaoStock']
print(f"成功率: {metrics.success_rate}")
print(f"平均响应时间: {metrics.avg_response_time}")
```

---

## 四、常见问题

### Q1: 任务没有执行？

```bash
# 检查 cron 服务状态
sudo crontab -l

# 检查 cron 日志
grep -i "quant" /var/log/cron.log 2>/dev/null || echo "无 cron 日志"

# 确认系统时间
date

# 手动执行测试
bash backend/collector/etl/crontab_config.sh
```

### Q2: 任务执行失败？

```bash
# 查看失败原因
grep "ERROR\|失败\|异常" logs/etl/daily_sync.log | tail -20

# 或者查看数据库任务记录
psql -h localhost -U quant_user -d quant_trading -c "
    SELECT * FROM task_progress
    WHERE status = 'failed'
    ORDER BY created_at DESC LIMIT 5;
"
```

### Q3: 如何切换调度方式？

- **简单定时任务**：使用 cron（当前默认）
- **需要重试和告警**：使用 `task_scheduler.py`
- **需要多数据源轮换**：使用 `collector/scheduler/smart_scheduler.py`

### Q4: 如何自定义调度时间？

编辑 `backend/collector/etl/crontab_config.sh` 中的 cron 表达式，然后重新执行 `crontab /tmp/quant_crontab`。

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 2.0 | 2026-06-04 | 合并原 TASK_SCHEDULER_GUIDE 和 SMART_SCHEDULER_GUIDE；更新路径与实际一致；明确 cron 为主力调度 |
| 1.0 | 2026-06-01 | 初始版本 |

---

**文档版本**: 2.0  
**最后更新**: 2026-06-04  
**位置**: `docs/SCHEDULER_GUIDE.md`