# backend/collector/etl/ — ETL 流程

## 目的

盘后数据流转：**下载 → 清洗（指标）→ 补全**，以及对应的监控与守护。

## 文件清单

| 文件 | 职责 |
|------|------|
| `import_daily_data.py` | 日线数据下载（支持增量 + 并行：沪市 Tushare / 深市 Baostock） |
| `daily_snapshot_sync.py` | 宽表同步（**已废弃**，请用根目录 `sync_quotes_to_snapshot.py`） |
| `sync_quotes_to_snapshot.py` | 宽表同步（**当前方案**，从 stock_quotes 计算技术指标） |
| `run_data_complete.py` | 数据完整性检查 + 补全（基于 `imputer/`） |
| `pipeline_health_check.py` | 任务执行前的**前置条件检查**（DB / 数据源 / 磁盘） |
| `health_monitor.py` | **心跳守护进程**（监控下载/清洗/补全状态） |
| `crontab_config.sh` | crontab 配置模板 |
| `bulk_download.py` / `fast_download.py` | 历史数据全量下载（一次性） |
| `data_complementer.py` | 旧版补全器（已迁移到 imputer/incomplete_handler） |
| `add_partitions.py` / `partition_scheduler.py` | PostgreSQL 分区管理 |
| `monitor_download.py` / `monitor_import.py` | 临时监控脚本（建议改用 health_monitor） |

## 盘后流程

### 定时任务（crontab）

```cron
# 16:05 盘后下载当日数据（增量，并行）
5 16 * * 1-5  cd $PROJECT_DIR && python $PROJECT_DIR/backend/collector/etl/import_daily_data.py --incremental > $LOG_DIR/daily_import.log 2>&1

# 16:30 同步宽表
30 16 * * 1-5 cd $PROJECT_DIR && python $PROJECT_DIR/sync_quotes_to_snapshot.py --latest > $LOG_DIR/daily_sync.log 2>&1

# 17:00 补全（依赖前两步完成）
0 17 * * 1-5  cd $PROJECT_DIR && python $PROJECT_DIR/backend/collector/etl/run_data_complete.py > $LOG_DIR/data_complementer.log 2>&1
```

### 手动触发

```bash
# 增量下载（仅下载未到最新交易日的部分）
python backend/collector/etl/import_daily_data.py --incremental

# 全量补全（首次部署或大盘点）
python backend/collector/etl/import_daily_data.py --full

# 宽表同步
python sync_quotes_to_snapshot.py --latest

# 数据补全
python backend/collector/etl/run_data_complete.py
```

## 心跳守护

```bash
# 启动（推荐后台运行）
nohup python backend/collector/etl/health_monitor.py --daemon > /dev/null 2>&1 &

# 单次检查
python backend/collector/etl/health_monitor.py --once
```

输出示例：
```
18:29:18, 下载, 正常, 58/4876(1%), 处理到 SZ.000066
18:29:18, 清洗, 空闲, -, -
18:29:18, 补全, 空闲, -, -
18:29:18, DB, q:06-05(42)|06-04(4543) sn:06-04(4543)|06-03(4543)
```

监控目标（见 `MONITORED_TASKS`）：
- **下载** — `import_daily_data.py`
- **清洗** — `sync_quotes_to_snapshot.py`
- **补全** — `run_data_complete.py`

## 前置条件检查

每次 ETL 任务执行前，建议先跑 `pipeline_health_check.py`：

```bash
python backend/collector/etl/pipeline_health_check.py
```

会检查：
1. PostgreSQL 连接
2. 数据源（Tushare / Baostock）连通性
3. 磁盘空间
4. 关键表（stock_quotes / stock_basic）是否存在
5. 上一交易日数据完整性

只有全部通过才执行 ETL，避免在错误环境下浪费时间。

## 并行下载原理

`import_daily_data.py` 默认启用并行：

```
                    ┌─ 沪市 SH (Tushare) ─┐
所有股票代码 ──────▶│                       │──▶ stock_quotes
                    └─ 深市 SZ (Baostock) ─┘
```

- **SH 沪市** → Tushare（数据全、字段多）
- **SZ 深市** → Baostock（无频率限制，绕过 Tushare 200 次/分钟限制）

两个线程独立下载，约 4500 只股票 10 分钟内完成。

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 16:30 后 stock_quotes 还没更新 | 16:05 任务没跑 | 手动跑 `import_daily_data.py --incremental` |
| 宽表技术指标全空 | 旧 `daily_snapshot_sync.py` 依赖 `stock_indicators` 表 | 改用 `sync_quotes_to_snapshot.py` |
| 复权后 close 价格跳空 | 复权因子表缺失 | 跑 `python -m backend.imputer.scripts.build_adj_factor` 补齐 |
| health_monitor 一直报"空闲" | 任务进程没启动 / 被杀 | 查 `pgrep -f import_daily_data` |
