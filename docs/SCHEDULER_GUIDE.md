# 定时任务调度系统使用指南

## 概述

量化交易系统提供两套调度机制，可配合使用：

| 调度方式 | 用途 | 复杂度 | 当前状态 |
|----------|------|--------|----------|
| **cron 定时任务** | 简单、可靠的固定时间执行（盘后同步/质量检查） | 低 | ❌ 已废弃 (由 daily_job_runner.py 替代) |
| **daily_job_runner** | 统一任务链调度，带断点续跑、重试、日志记录 | 低 | ✅ 生产使用 |
| **APScheduler 调度器** | 程序内带重试、优先级、告警的复杂任务编排 | 中 | ⚡ 备选方案 |
| **智能调度系统** | 多数据源轮换、熔断、动态权重的高级调度 | 高 | 📦 可用组件 |

---

## 一、cron 定时任务（已废弃）

⚠️ 已废弃：cron 定时任务已被 `daily_job_runner.py` 替代。保留此节仅作历史参考。

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

### 1.5 配置参数（已废弃）

⚠️ `pipeline.yaml` 不再用于调度配置。当前调度逻辑由 `daily_job_runner.py` 内部硬编码的任务链控制。

历史参考：cron 定时任务的核心参数曾在 `backend/pipeline.yaml` 中配置：

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

## 五、daily_job_runner 统一调度（当前主力）

### 5.1 概述

`daily_job_runner.py` 位于 `backend/cron/daily_job_runner.py`，是当前生产环境使用的统一任务链调度器。它替代了旧的 cron 定时任务，提供以下核心能力：

- **线性任务链**：按依赖顺序依次执行任务，前序失败则中断后续
- **断点续跑（Resume from Breakpoint）**：通过 `task_run_log` 表记录状态，已成功的任务自动跳过
- **自动重试**：最多 3 次重试，间隔 15 分钟，不可重试错误（语法错误、导入错误等）立即终止
- **僵尸进程清理**：运行超过 2 小时的任务自动标记为失败并重新执行
- **文件锁**：防止同一时刻多个实例同时运行
- **dry-run 模式**：预览今日计划执行的任务，不实际执行

### 5.2 任务链执行顺序

任务分为两个阶段执行：

**阶段 1（15:30）**：
1. **健康检查** (`pipeline_health_check.py --pre-import`) — 检查数据库连接、磁盘空间等前置条件
2. **股票列表同步** (`sync_stock_list_baostock.py`) — 同步最新股票列表

**阶段 2（16:30）**：
3. **行情数据导入** (`import_daily_data.py --incremental`) — 增量导入当日行情数据
4. **缺失数据补全** (`fill_missing_data.py`，可选) — 补全历史缺失数据
5. **复权因子同步** (`sync_adj_factor.py --incremental`) — 增量同步复权因子
6. **基本面数据同步** (`sync_daily_basic.py --latest`) — 同步最新基本面数据
7. **指标计算** (`compute_indicators_daily.py`) — 计算技术指标
8. **信号预计算** (`signal_precompute.py`) — 预计算交易信号
9. **宽表同步** (`daily_snapshot_sync.py --latest`) — 同步每日快照宽表
10. **Parquet 导出** (`export_parquet.py`) — 导出 Parquet 格式数据

### 5.3 task_run_log 表跟踪

所有任务执行记录写入 `task_run_log` 表，包含以下字段：

| 字段 | 说明 |
|------|------|
| `id` | 自增主键 |
| `task_name` | 任务名称 |
| `stage` | 阶段编号（1/2） |
| `batch_id` | 批次号（格式：`YYYYMMDD-xxxxxxxx`） |
| `data_date` | 数据日期 |
| `start_time` | 开始时间 |
| `end_time` | 结束时间 |
| `status` | 状态：`running` / `success` / `failed` / `pending` |
| `exit_code` | 退出码 |
| `error_message` | 错误信息 |
| `rows_affected` | 影响行数 |
| `extra_metrics` | 额外指标（JSON 格式） |

### 5.4 batch_id 断点续跑机制

每次运行生成唯一 `batch_id`（格式：`YYYYMMDD-xxxxxxxx`），用于：

- **断点续跑**：重启时查询 `task_run_log` 表中各任务的最新状态，已成功的任务自动跳过
- **状态隔离**：按 `stage` 过滤，避免跨阶段干扰
- **僵尸检测**：`running` 状态超过 2 小时的任务视为僵尸进程，自动清理后重新执行

### 5.5 文件锁机制

启动时在 `logs/cron/.daily_job_runner.lock` 创建文件锁，防止调度器重复执行。锁文件包含 PID 和启动时间信息。

### 5.6 手动执行

```bash
# 全量执行（阶段 1 + 阶段 2）
cd /Users/zhangk/workspace/Quantitative_trading
PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/cron/daily_job_runner.py

# 仅执行阶段 1（健康检查 + 股票列表）
PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/cron/daily_job_runner.py --stage 1

# 仅执行阶段 2（数据导入 + 计算 + 导出）
PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/cron/daily_job_runner.py --stage 2

# 执行阶段 2 并包含缺失数据补全
PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/cron/daily_job_runner.py --stage 2 --fill-missing

# 试运行模式（预览任务，不实际执行）
PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/cron/daily_job_runner.py --dry-run
```

### 5.7 查看执行状态

```bash
# 查看今日所有任务执行状态
psql -h localhost -U quant_user -d quant_trading -c "
    SELECT task_name, stage, status, batch_id,
           to_char(start_time, 'HH24:MI:SS') AS start,
           to_char(end_time, 'HH24:MI:SS') AS end,
           rows_affected, error_message
    FROM task_run_log
    WHERE data_date = CURRENT_DATE
    ORDER BY id;
"

# 查看今日失败的 task
psql -h localhost -U quant_user -d quant_trading -c "
    SELECT id, task_name, stage, batch_id, error_message, start_time, end_time
    FROM task_run_log
    WHERE data_date = CURRENT_DATE AND status = 'failed'
    ORDER BY id;
"

# 查看最近批次的执行概况
psql -h localhost -U quant_user -d quant_trading -c "
    SELECT batch_id, task_name, status, rows_affected,
           to_char(start_time, 'MM-DD HH24:MI:SS') AS start
    FROM task_run_log
    WHERE batch_id = (
        SELECT batch_id FROM task_run_log
        WHERE task_name = 'etl_pipeline'
        ORDER BY id DESC LIMIT 1
    )
    ORDER BY id;
"

# 查看各任务日志
tail -f logs/cron/stock_list_sync_$(date +%Y%m%d).log
tail -f logs/cron/daily_import_$(date +%Y%m%d).log
tail -f logs/cron/indicators_compute_$(date +%Y%m%d).log
```

### 5.8 日志位置

每个任务独立日志文件，位于 `logs/cron/` 目录下，按任务名和日期命名，自动轮转（最大 10MB，保留 5 个备份）：

- `logs/cron/pipeline_health_check_YYYYMMDD.log`
- `logs/cron/stock_list_sync_YYYYMMDD.log`
- `logs/cron/daily_import_YYYYMMDD.log`
- `logs/cron/adj_factor_sync_YYYYMMDD.log`
- `logs/cron/daily_basic_sync_YYYYMMDD.log`
- `logs/cron/indicators_compute_YYYYMMDD.log`
- `logs/cron/signal_precompute_YYYYMMDD.log`
- `logs/cron/daily_sync_YYYYMMDD.log`
- `logs/cron/parquet_export_YYYYMMDD.log`

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 3.0 | 2026-07-09 | 废弃 cron 调度，迁移至 daily_job_runner.py 统一任务链调度；新增 task_run_log 表跟踪、batch_id 断点续跑机制 |
| 2.0 | 2026-06-04 | 合并原 TASK_SCHEDULER_GUIDE 和 SMART_SCHEDULER_GUIDE；更新路径与实际一致；明确 cron 为主力调度 |
| 1.0 | 2026-06-01 | 初始版本 |

---

**文档版本**: 3.0  
**最后更新**: 2026-07-09  
**位置**: `docs/SCHEDULER_GUIDE.md`