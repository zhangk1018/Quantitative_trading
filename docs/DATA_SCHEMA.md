# 量化交易系统数据架构文档

## 概述

本文档详细描述量化交易系统的数据架构，包括数据文件组织、数据库表结构、字段定义、主键约束、索引设计、数据校验规则和工程化流水线。

### 设计变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v4.0 | 2026-06-04 | 合并 DATA_DIRECTORY_PLAN 文档，更新目录结构与实际保持一致；补充 trade_signals 表；同步当前项目路径 |
| v3.2 | 2026-06-02 | 核心修正：补充跨周期时间范围扫描专用索引（ACTION-4）；修复PG 11+环境下子分区触发器重复执行问题（ACTION-2）；修复水位线断层伪推进问题（ACTION-1）；优化数据转换性能（ACTION-3） |
| v3.1 | 2026-06-02 | 修复分区维护脚本触发器绑定逻辑 |
| v3.0 | 2026-06-02 | 重大更新：统一时间字段为 trade_datetime、月度分区、数据类型优化、新增脏数据表和水位线表 |
| v2.2 | 2026-05-30 | 基础版本 |

> **升级指引**：从 v3.0 / v3.1 升级到 v3.2，请执行迁移脚本 [`backend/collector/db/sql/migrate_v3_to_v3.2.sql`](../backend/collector/db/sql/migrate_v3_to_v3.2.sql)。全新部署请使用 [`backend/collector/db/sql/init_db.sql`](../backend/collector/db/sql/init_db.sql)。

---

## 一、数据目录结构

### 1.1 项目目录布局

```
Quantitative_trading/
│
├── .env                        # 环境变量配置（数据库密码等敏感信息）
├── .gitignore
├── requirements.txt            # Python 依赖（仅根级公共依赖）
│
├── backend/                    # 后端代码主目录
│   ├── main.py                 # FastAPI 主入口
│   ├── pipeline.yaml           # 核心配置文件（数据源/存储/定时任务/缓存）
│   ├── requirements.txt        # 后端 Python 依赖
│   ├── requirements_api.txt    # API 服务 Python 依赖
│   ├── task_scheduler.py       # 定时任务调度器（APScheduler）
│   ├── test_scheduler.py       # 调度器测试
│   ├── test_service.py         # 服务测试
│   │
│   ├── collector/              # 数据采集模块
│   │   ├── datasource/         # 多数据源（baostock/akshare/sina/tencent）
│   │   ├── db/                 # 数据库操作（models/loader/meta/repository）
│   │   │   └── sql/            # SQL 脚本（建表/分区/迁移/索引）
│   │   ├── etl/                # ETL 流程（导入/同步/分区/监控）
│   │   ├── scheduler/          # 智能调度系统（SmartScheduler/熔断/告警）
│   │   ├── storage/            # 存储层（PostgreSQL/SQLite）
│   │   └── check_programs.py   # 程序健康检查
│   │
│   ├── clean/                  # 数据清洗与补全模块
│   │   ├── enrich/             # 数据补全（基本面/行业/技术指标/新高突破）
│   │   ├── processor/          # 核心处理（导入器/缺口处理/质量检查/技术指标）
│   │   ├── quality/            # 数据质量检查（完整性/重复/模式校验）
│   │   └── tools/              # 工具脚本（信号预计算/数据管道/清理/对比）
│   │
│   ├── core/                   # 核心服务层
│   │   ├── api/                # FastAPI 路由
│   │   │   ├── main.py         # FastAPI 应用入口
│   │   │   ├── config.py       # API 配置
│   │   │   ├── dependencies.py # 依赖注入
│   │   │   ├── models/         # Pydantic 模型（schemas.py）
│   │   │   └── router/         # 路由（kline/signals/stocks/meta）
│   │   └── service/            # 业务服务（kline/signal/screener/data_service）
│   │
│   ├── utils/                  # 工具模块（配置/日志/监控/错误分类/存储工厂）
│   └── logs/                   # 日志目录
│       ├── daily_import.log    # 日线导入日志
│       ├── minute_import.log   # 分钟线导入日志
│       ├── base_importer.log   # 导入器日志
│       ├── data_quality_checker.log  # 数据质量检查日志
│       ├── technical_indicator.log   # 技术指标计算日志
│       ├── datasource_manager.log    # 数据源管理日志
│       └── *.log               # 其它模块日志
│
├── data/                       # 数据目录
│   ├── metadata/               # 元数据文件
│   │   └── stock_list.parquet  # 股票列表缓存
│   └── price/                  # 价格数据
│       └── daily/              # 日线数据 Parquet
│           └── latest_quotes.parquet  # 最新行情快照（Parquet格式）
│
├── logs/                       # 根级日志目录（少量程序使用）
│   └── etl/                    # ETL 定时任务日志
│       ├── daily_sync.log
│       └── weekly_sync.log
│
└── docs/                       # 项目文档
    ├── AI_COLLABORATION.md     # AI 协作待办清单
    ├── DATA_SCHEMA.md          # 数据架构文档（本文档）
    ├── SCHEDULER_GUIDE.md      # 调度系统使用指南
    └── PROJECT_PLAN.md         # 项目规划
```

### 1.2 目录用途说明

| 目录 | 用途 | 文件格式 | 更新频率 |
|------|------|----------|----------|
| `backend/` | 后端所有源代码（采集/清洗/核心API） | Python | - |
| `backend/collector/` | 数据采集：多数据源适配、ETL流程、数据库操作 | Python | - |
| `backend/clean/` | 数据清洗与补全：字段计算、质量检查、技术指标 | Python | 每日 |
| `backend/core/` | 核心服务：FastAPI 路由、业务逻辑、Pydantic 模型 | Python | - |
| `backend/logs/` | 各模块运行日志 | Text | 实时 |
| `data/metadata/` | 元数据缓存 | Parquet | 按需 |
| `data/price/daily/` | 行情快照 | Parquet | 每日 |
| `docs/` | 项目文档 | Markdown | 按需 |

### 1.3 原始数据目录说明 (`data/raw/`)

**设计目的**:
1. **审计溯源**: 保留原始数据供合规审计使用
2. **清洗规则升级**: 当清洗规则变更时，可重新运行原始数据
3. **多数据源交叉验证**: 支持多个数据源的数据比对

**目录结构**:
```
data/raw/
├── baostock/           # Baostock 数据源
│   ├── daily/          # 日线数据
│   │   └── {date}_quotes.parquet
│   └── minute/         # 分钟线数据
│       └── {date}_min5.parquet
├── akshare/            # Akshare 数据源
│   └── daily/
│       └── {date}_quotes.csv
└── backup/             # 原始数据备份
    └── {date}_raw.tar.gz
```

---

## 二、数据库表结构

### 2.1 数据库配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| 数据库类型 | PostgreSQL | 生产环境数据库 |
| 数据库名 | `quant_trading` | 数据库名称 |
| 用户名 | `quant_user` | 数据库用户 |
| 端口 | `5432` | 默认 PostgreSQL 端口 |

### 2.2 表结构总览

| 表名 | 用途 | 记录数（预计） | 存储类型 |
|------|------|---------------|----------|
| `stock_basic` | 股票基本信息 | ~5,000 | 热数据 |
| `stock_quotes` | 行情数据（多周期统一存储） | ~150,000,000 | 热数据（分区表） |
| `stock_indicators` | 技术指标 | ~150,000,000 | 热数据（分区表） |
| `trade_signals` | 交易信号（MACD金叉/死叉） | ~500,000 | 热数据 |
| `stock_fundamental_pit` | 财务PIT数据（二期） | ~200,000 | 热数据 |
| `trade_calendar` | 交易日历 | ~10,000 | 元数据 |
| `task_progress` | 任务进度（断点续传） | 动态 | 临时数据 |
| `task_metrics` | 任务执行指标 | ~365 | 统计数据 |
| `data_dict` | 数据字典 | ~100 | 元数据 |
| `data_error_log` | 数据错误日志 | 动态 | 日志数据 |
| `data_audit_log` | 操作审计日志 | 动态 | 审计数据 |
| `stock_quotes_dirty` | 脏数据死信表 | 动态 | 日志数据 |
| `sync_checkpoints` | 同步水位线表 | ~35,000 | 热数据 |

---

## 三、表结构详细说明

### 3.1 stock_basic（股票基本信息表）

**用途**: 存储股票基本信息，包括代码、名称、行业分类等

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `code` | VARCHAR(10) | PRIMARY KEY | 股票代码（如 sh.600000） |
| `name` | VARCHAR(50) | NOT NULL | 股票名称 |
| `industry` | VARCHAR(50) | | 行业分类 |
| `sw_industry` | VARCHAR(50) | | 申万行业分类 |
| `list_date` | DATE | | 上市日期 |
| `delist_date` | DATE | | 退市日期（NULL表示正常交易） |
| `status` | VARCHAR(20) | DEFAULT 'normal' | 状态（normal/delist/suspended） |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间（带时区） |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间（带时区） |

**索引**:
- `PRIMARY KEY (code)`
- `idx_basic_status` - 按状态查询
- `idx_basic_industry` - 按行业查询

**表注释**:
```sql
COMMENT ON TABLE stock_basic IS '股票基本信息表';
COMMENT ON COLUMN stock_basic.code IS '股票代码（如 sh.600000）';
COMMENT ON COLUMN stock_basic.status IS '股票状态：normal-正常交易，delist-已退市，suspended-暂停上市';
```

---

### 3.2 stock_quotes（行情数据表）

**用途**: 存储股票多周期行情数据（统一存储 5m/15m/30m/60m/1d/1w/1m）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | BIGSERIAL | | 自增ID（非主键） |
| `code` | VARCHAR(10) | NOT NULL | 股票代码 |
| `cycle` | VARCHAR(10) | NOT NULL | 周期（5m/15m/30m/60m/1d/1w/1m） |
| `trade_datetime` | TIMESTAMP WITH TIME ZONE | NOT NULL | 交易时间（日线/周线/月线统一为当天 15:00:00+08:00） |
| `open` | REAL | | 开盘价 |
| `high` | REAL | | 最高价 |
| `low` | REAL | | 最低价 |
| `close` | REAL | | 收盘价 |
| `volume` | BIGINT | | 成交量（股） |
| `amount` | DOUBLE PRECISION | | 成交额（元） |
| `pct_chg` | REAL | | 涨跌幅（%） |
| `turnover_rate` | REAL | | 换手率（%） |
| `adjust_type` | VARCHAR(10) | DEFAULT 'qfq' | 复权类型（qfq/hfq/none） |
| `update_time` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间（带时区） |

**约束**:
- `PRIMARY KEY(id, trade_datetime)`（分区表主键必须包含分区键）
- `UNIQUE(code, cycle, trade_datetime)`（唯一性约束，防止重复数据）
- `CHECK(cycle IN ('5m', '15m', '30m', '60m', '1d', '1w', '1m'))`
- `CHECK(adjust_type IN ('qfq', 'hfq', 'none'))`

**索引**:
| 索引名 | 字段 | 用途 |
|--------|------|------|
| `idx_quotes_code_cycle_time_desc` | `code, cycle, trade_datetime DESC` | 单股票某周期最新N条K线查询（关键优化） |
| `idx_quotes_code_cycle_time` | `code, cycle, trade_datetime` | 单股票某周期特定时间范围查询 |
| `idx_quotes_code_time` | `code, trade_datetime` | 单股票跨周期时间范围扫描（ACTION-4：支撑高频时序查询） |
| `idx_quotes_cycle_time` | `cycle, trade_datetime` | 某日/时段全市场查询 |
| `idx_quotes_cycle_time_pctchg_desc` | `cycle, trade_datetime, pct_chg DESC` | 涨跌幅排名查询 |

**表注释**:
```sql
COMMENT ON TABLE stock_quotes IS '行情数据表（多周期统一存储，分区表）';
COMMENT ON COLUMN stock_quotes.trade_datetime IS '交易时间（日线/周线/月线统一为该周期结束当天 15:00:00+08:00）';
COMMENT ON COLUMN stock_quotes.pct_chg IS '涨跌幅（%），基于不复权原始价格计算，不受 adjust_type 影响';
COMMENT ON COLUMN stock_quotes.adjust_type IS '复权类型：qfq-前复权，hfq-后复权，none-不复权';
```

> ⚠️ **数据类型优化说明**:
> 1. 价格字段使用 `REAL`（单精度浮点）替代 `NUMERIC`，提升量化回测计算性能，精度足够金融场景使用
> 2. 成交额使用 `DOUBLE PRECISION` 避免溢出
> 3. 时间字段统一为 `trade_datetime`，支持分钟线精确时间

> ⚠️ **生产规范提醒**:
> 1. **分区约束红线**: PostgreSQL 分区表的 `UNIQUE` 和 `PRIMARY KEY` 约束 **必须包含分区键** `trade_datetime`。当前设计完全合规
> 2. **JSON/Parquet 时区对齐**: 所有导出文件的时间字段建议统一使用 ISO 8601 格式（如 `2024-01-15T15:00:00+08:00` 或 UTC `Z` 结尾）
> 3. **索引优化关键**: `idx_quotes_code_cycle_time_desc` 包含 `DESC` 排序，优化获取最新N条K线的查询性能

---

### 3.3 stock_indicators（技术指标表）

**用途**: 存储计算后的技术指标数据（多周期统一存储）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | BIGSERIAL | | 自增ID（非主键） |
| `code` | VARCHAR(10) | NOT NULL | 股票代码 |
| `cycle` | VARCHAR(10) | NOT NULL | 周期（5m/15m/30m/60m/1d/1w/1m） |
| `trade_datetime` | TIMESTAMP WITH TIME ZONE | NOT NULL | 交易时间（与 stock_quotes 统一） |
| `ma5` | REAL | | 5日均线 |
| `ma10` | REAL | | 10日均线 |
| `ma20` | REAL | | 20日均线 |
| `ma60` | REAL | | 60日均线 |
| `macd` | REAL | | MACD值（DIF-DEA差值） |
| `dif` | REAL | | MACD快线（DIF） |
| `dea` | REAL | | MACD慢线（DEA） |
| `rsi6` | REAL | | 6日RSI |
| `rsi12` | REAL | | 12日RSI |
| `rsi24` | REAL | | 24日RSI |
| `kdj_k` | REAL | | KDJ-K值 |
| `kdj_d` | REAL | | KDJ-D值 |
| `kdj_j` | REAL | | KDJ-J值 |
| `boll_upper` | REAL | | 布林带上轨 |
| `boll_middle` | REAL | | 布林带中轨 |
| `boll_lower` | REAL | | 布林带下轨 |
| `calc_version` | VARCHAR(10) | | 指标计算版本（用于幂等重算） |
| `update_time` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间（带时区） |

**约束**:
- `PRIMARY KEY(id, trade_datetime)`（分区表主键必须包含分区键）
- `UNIQUE(code, cycle, trade_datetime)`（唯一性约束）
- `CHECK(cycle IN ('5m', '15m', '30m', '60m', '1d', '1w', '1m'))`

**索引**:
| 索引名 | 字段 | 用途 |
|--------|------|------|
| `idx_indicators_code_cycle_time_desc` | `code, cycle, trade_datetime DESC` | 单股票某周期最新指标查询 |
| `idx_indicators_code_cycle_time` | `code, cycle, trade_datetime` | 单股票某周期指标查询 |
| `idx_indicators_code_time` | `code, trade_datetime` | 单股票跨周期时间范围扫描（ACTION-4：支撑高频时序查询） |

**表注释**:
```sql
COMMENT ON TABLE stock_indicators IS '技术指标表（多周期统一存储，分区表）';
COMMENT ON COLUMN stock_indicators.calc_version IS '指标计算版本（用于幂等重算）';
```

> ⚠️ **与 stock_quotes 统一**: `trade_datetime` 字段与 stock_quotes 完全一致，便于 JOIN 查询

---

### 3.4 stock_fundamental_pit（财务PIT表）

**用途**: 存储股票财务数据的时点快照（Point-in-Time），确保回测时使用当时可见的数据

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | SERIAL | PRIMARY KEY | 自增主键 |
| `code` | VARCHAR(10) | NOT NULL | 股票代码 |
| `report_date` | DATE | NOT NULL | 财务报告期 |
| `announce_date` | DATE | NOT NULL | 公告发布日期 |
| `net_profit` | NUMERIC(18, 2) | | 净利润（元） |
| `revenue` | NUMERIC(18, 2) | | 营业收入（元） |
| `pe_ttm` | NUMERIC(10, 2) | | 滚动市盈率 |
| `pb` | NUMERIC(10, 2) | | 市净率 |
| `eps` | NUMERIC(10, 4) | | 每股收益 |
| `roe` | NUMERIC(10, 2) | | 净资产收益率（%） |
| `data_version` | VARCHAR(10) | DEFAULT 'v1' | 数据版本（支持修正追溯） |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 入库时间（带时区） |

**约束**:
- `UNIQUE(code, report_date, announce_date)`

**索引**:
| 索引名 | 字段 | 用途 |
|--------|------|------|
| `idx_fundamental_code_report` | `code, report_date` | 按股票+报告期查询 |
| `idx_fundamental_announce` | `announce_date` | 按公告日期查询 |

**表注释**:
```sql
COMMENT ON TABLE stock_fundamental_pit IS '财务PIT表（时点快照）';
COMMENT ON COLUMN stock_fundamental_pit.data_version IS '数据版本（支持财报修正追溯）';
```

---

### 3.5 trade_calendar（交易日历表）

**用途**: 存储交易日历信息，标记哪些日期是交易日

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `cal_date` | DATE | PRIMARY KEY | 日期 |
| `is_open` | INTEGER | NOT NULL | 是否交易（1=是，0=否） |
| `holiday_name` | VARCHAR(100) | | 节假日名称（非交易日时） |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间（带时区） |

**索引**:
- `PRIMARY KEY (cal_date)`

**表注释**:
```sql
COMMENT ON TABLE trade_calendar IS '交易日历表';
COMMENT ON COLUMN trade_calendar.is_open IS '是否交易：1-是，0-否';
```

---

### 3.6 task_progress（任务进度表）

**用途**: 记录数据同步任务的进度，支持断点续传

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | SERIAL | PRIMARY KEY | 自增主键 |
| `task_name` | VARCHAR(100) | NOT NULL | 任务名称 |
| `status` | VARCHAR(20) | DEFAULT 'pending' | 状态（pending/running/success/failed） |
| `progress` | NUMERIC(5, 2) | DEFAULT 0 | 进度（0-100） |
| `message` | TEXT | | 任务消息 |
| `last_sync_date` | DATE | | 最后同步日期（断点续传用） |
| `failed_code_list` | TEXT[] | | 失败的股票代码列表 |
| `shard_id` | INTEGER | | 分片ID（支持分片任务） |
| `timeout` | TIMESTAMP WITH TIME ZONE | | 任务超时时间 |
| `dependencies` | TEXT[] | | 依赖任务列表 |
| `parent_task_id` | INTEGER | | 父任务ID |
| `start_time` | TIMESTAMP WITH TIME ZONE | | 任务开始时间（带时区） |
| `end_time` | TIMESTAMP WITH TIME ZONE | | 任务结束时间（带时区） |
| `retry_count` | INTEGER | DEFAULT 0 | 重试次数 |
| `error_msg` | TEXT | | 错误信息（详细） |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间（带时区） |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间（带时区） |

**索引**:
- `idx_task_name` - 按任务名查询
- `idx_task_status` - 按状态查询

**表注释**:
```sql
COMMENT ON TABLE task_progress IS '任务进度表（断点续传）';
COMMENT ON COLUMN task_progress.shard_id IS '分片ID（支持全市场股票按代码分片）';
COMMENT ON COLUMN task_progress.timeout IS '任务超时时间';
COMMENT ON COLUMN task_progress.dependencies IS '依赖任务列表';
```

---

### 3.7 task_metrics（任务执行指标表）

**用途**: 记录每日数据同步任务的执行指标

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | SERIAL | PRIMARY KEY | 自增主键 |
| `task` | VARCHAR(50) | NOT NULL | 任务名称 |
| `date` | DATE | NOT NULL | 日期 |
| `total_count` | INTEGER | DEFAULT 0 | 总数 |
| `success_count` | INTEGER | DEFAULT 0 | 成功数 |
| `failed_count` | INTEGER | DEFAULT 0 | 失败数 |
| `duration_seconds` | NUMERIC(10, 2) | | 耗时（秒） |
| `avg_time_per_stock` | NUMERIC(10, 4) | | 单股票平均耗时（秒） |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间（带时区） |

**约束**:
- `UNIQUE(task, date)`

**表注释**:
```sql
COMMENT ON TABLE task_metrics IS '任务执行指标表';
COMMENT ON COLUMN task_metrics.duration_seconds IS '任务执行耗时（秒）';
COMMENT ON COLUMN task_metrics.avg_time_per_stock IS '单股票平均处理时间（秒）';
```

---

### 3.8 data_dict（数据字典表）

**用途**: 记录所有表/字段的元数据信息，支持数据治理和团队协作

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | SERIAL | PRIMARY KEY | 自增主键 |
| `table_name` | VARCHAR(50) | NOT NULL | 表名 |
| `column_name` | VARCHAR(50) | | 字段名 |
| `column_type` | VARCHAR(50) | | 字段类型 |
| `description` | TEXT | | 字段描述 |
| `constraint` | VARCHAR(100) | | 约束条件 |
| `default_value` | TEXT | | 默认值 |
| `is_required` | BOOLEAN | DEFAULT FALSE | 是否必填 |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间（带时区） |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间（带时区） |

**索引**:
- `idx_dict_table` - 按表名查询
- `idx_dict_column` - 按字段名查询

**表注释**:
```sql
COMMENT ON TABLE data_dict IS '数据字典表';
COMMENT ON COLUMN data_dict.table_name IS '表名';
COMMENT ON COLUMN data_dict.column_name IS '字段名';
COMMENT ON COLUMN data_dict.description IS '字段描述';
```

---

### 3.9 data_error_log（数据错误日志表）

**用途**: 记录数据校验失败的错误日志，便于问题排查和数据追溯

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | SERIAL | PRIMARY KEY | 自增主键 |
| `code` | VARCHAR(10) | | 股票代码 |
| `trade_date` | DATE | | 交易日期 |
| `error_type` | VARCHAR(50) | NOT NULL | 错误类型 |
| `error_message` | TEXT | | 错误详情 |
| `raw_data` | JSONB | | 原始数据（用于追溯） |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**表注释**:
```sql
COMMENT ON TABLE data_error_log IS '数据错误日志表';
COMMENT ON COLUMN data_error_log.error_type IS '错误类型（如 high_low_error, pct_change_error）';
COMMENT ON COLUMN data_error_log.raw_data IS '原始数据（JSON格式，用于问题追溯）';
```

---

### 3.10 data_audit_log（操作审计日志表）

**用途**: 记录数据写入/更新/删除操作，满足合规审计要求

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | SERIAL | PRIMARY KEY | 自增主键 |
| `operator` | VARCHAR(50) | NOT NULL | 操作人 |
| `operation_type` | VARCHAR(20) | NOT NULL | 操作类型（INSERT/UPDATE/DELETE） |
| `table_name` | VARCHAR(50) | NOT NULL | 操作表名 |
| `data_range` | JSONB | | 数据范围 |
| `record_count` | INTEGER | | 影响记录数 |
| `operation_time` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 操作时间 |
| `description` | TEXT | | 操作描述 |

**表注释**:
```sql
COMMENT ON TABLE data_audit_log IS '数据操作审计日志表';
COMMENT ON COLUMN data_audit_log.operator IS '操作人';
COMMENT ON COLUMN data_audit_log.data_range IS '数据范围（JSON格式）';
```

---

### 3.11 stock_quotes_dirty（脏数据死信表）

**用途**: 存储数据校验失败的原始数据，避免数据悄悄丢失，便于追溯和修复

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | BIGSERIAL | PRIMARY KEY | 自增主键 |
| `code` | VARCHAR(10) | | 股票代码 |
| `cycle` | VARCHAR(10) | | 周期 |
| `trade_datetime` | TIMESTAMP WITH TIME ZONE | | 交易时间 |
| `raw_data` | JSONB | NOT NULL | 完整原始数据 |
| `error_type` | VARCHAR(50) | NOT NULL | 错误类型（如 price_missing, high_low_invalid） |
| `error_message` | TEXT | NOT NULL | 错误详情 |
| `source` | VARCHAR(50) | | 数据源（baostock/akshare/...） |
| `fetch_time` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 获取时间 |
| `status` | VARCHAR(20) | DEFAULT 'pending' | 状态（pending/resolved/ignored） |
| `resolve_time` | TIMESTAMP WITH TIME ZONE | | 解决时间 |
| `resolve_note` | TEXT | | 解决说明 |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**索引**:
| 索引名 | 字段 | 用途 |
|--------|------|------|
| `idx_dirty_code_cycle` | `code, cycle` | 按股票和周期查询脏数据 |
| `idx_dirty_error_type` | `error_type` | 按错误类型查询 |
| `idx_dirty_status` | `status` | 按状态查询 |
| `idx_dirty_fetch_time` | `fetch_time DESC` | 按获取时间排序查询 |

**表注释**:
```sql
COMMENT ON TABLE stock_quotes_dirty IS '脏数据死信表（存储校验失败的原始数据）';
COMMENT ON COLUMN stock_quotes_dirty.status IS '脏数据处理状态：pending-待处理，resolved-已解决，ignored-已忽略';
```

---

### 3.12 trade_signals（交易信号表）

**用途**: 存储预计算的交易信号（MACD 金叉/死叉），由 `backend/clean/tools/precompute_signals.py` 写入，供 API 查询

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | SERIAL | PRIMARY KEY | 自增主键 |
| `code` | VARCHAR(32) | NOT NULL | 股票代码 |
| `trade_date` | DATE | NOT NULL | 交易日期 |
| `signal_type` | VARCHAR(32) | NOT NULL | 信号类型（golden_cross=金叉, death_cross=死叉） |
| `price` | NUMERIC(12, 4) | | 信号发生时的收盘价 |
| `macd` | NUMERIC(12, 4) | | MACD 值 |
| `macd_signal` | NUMERIC(12, 4) | | 信号线值 |
| `macd_hist` | NUMERIC(12, 4) | | 柱状图值（MACD - 信号线） |
| `created_at` | TIMESTAMP | DEFAULT NOW() | 创建时间 |

**索引**:
| 索引名 | 字段 | 用途 |
|--------|------|------|
| `idx_trade_signals_code_date` | `code, trade_date DESC` | 按股票和日期查询信号 |
| `idx_trade_signals_type` | `signal_type, trade_date DESC` | 按信号类型查询 |

**表注释**:
```sql
COMMENT ON TABLE trade_signals IS '交易信号表（MACD 金叉/死叉预计算结果）';
COMMENT ON COLUMN trade_signals.signal_type IS '信号类型：golden_cross-金叉，death_cross-死叉';
COMMENT ON COLUMN trade_signals.price IS '信号发生时的收盘价';
```

---

### 3.13 sync_checkpoints（同步水位线表）

**用途**: 记录每只股票每个周期的最新成功同步时间，实现精准断点续传

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | BIGSERIAL | PRIMARY KEY | 自增主键 |
| `code` | VARCHAR(10) | NOT NULL | 股票代码 |
| `cycle` | VARCHAR(10) | NOT NULL | 周期 |
| `last_sync_datetime` | TIMESTAMP WITH TIME ZONE | NOT NULL | 最后成功同步时间（ACTION-1：断层时保持原值，防止伪推进） |
| `last_continuous_sync_datetime` | TIMESTAMP WITH TIME ZONE | | 最后连续同步时间（ACTION-1：记录无断层的最远同步点） |
| `is_continuous` | BOOLEAN | DEFAULT TRUE | 是否连续（ACTION-1：标记当前同步是否存在数据断层） |
| `sync_status` | VARCHAR(20) | DEFAULT 'success' | 同步状态（pending/in_progress/success/failed） |
| `sync_count` | INTEGER | DEFAULT 0 | 本次同步记录数 |
| `fail_reason` | TEXT | | 失败原因 |
| `task_id` | VARCHAR(50) | | 任务ID |
| `source` | VARCHAR(50) | | 数据源 |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**约束**:
- `UNIQUE(code, cycle)`（每只股票每个周期仅一条记录）

**索引**:
| 索引名 | 字段 | 用途 |
|--------|------|------|
| `idx_checkpoint_code_cycle` | `code, cycle` | 按股票和周期查询水位线（主键已覆盖） |
| `idx_checkpoint_status` | `sync_status` | 按状态查询 |
| `idx_checkpoint_task` | `task_id` | 按任务ID查询 |

**表注释**:
```sql
COMMENT ON TABLE sync_checkpoints IS '同步水位线表（断点续传使用）';
COMMENT ON COLUMN sync_checkpoints.last_sync_datetime IS '最后成功同步时间，下次同步从该时间之后开始（ACTION-1：断层时不推进）';
COMMENT ON COLUMN sync_checkpoints.last_continuous_sync_datetime IS '最后连续同步时间，记录无数据断层的最远同步点';
COMMENT ON COLUMN sync_checkpoints.is_continuous IS '是否连续：TRUE表示数据连续，FALSE表示存在断层';
COMMENT ON COLUMN sync_checkpoints.sync_status IS '同步状态：pending-待同步，in_progress-同步中，success-成功，failed-失败';
```

---

## 四、数据流转架构

### 4.1 数据流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据源层                                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐    │
│  │  Baostock   │    │   Akshare   │    │  Sina/Tencent   │    │
│  └──────┬──────┘    └──────┬──────┘    └────────┬────────┘    │
└─────────┼──────────────────┼─────────────────────┼─────────────┘
          │                  │                     │
          ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                     采集层 (backend/collector/)                 │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────┐    │
│  │  datasource  │    │  etl/导入脚本 │    │  storage/存储  │    │
│  │  (源适配器)  │───→│  (ETL流程)   │───→│  (PostgreSQL)  │    │
│  └──────────────┘    └──────────────┘    └────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     清洗与补全层 (backend/clean/)                │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────┐    │
│  │ processor/   │    │  enrich/     │    │  quality/      │    │
│  │ 导入/校验    │───→│ 补全/指标计算 │───→│ 质量检查       │    │
│  └──────────────┘    └──────────────┘    └────────────────┘    │
│                              │                                   │
│  ┌──────────────┐    ┌──────────────┐                           │
│  │ tools/       │    │  tools/      │                           │
│  │ 数据管道     │    │ 信号预计算   │──→ trade_signals 表        │
│  └──────────────┘    └──────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      数据库存储层                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐        │
│  │ stock_quotes │ │stock_indicators│ │  trade_signals  │        │
│  │  (分区表)    │ │  (分区表)    │ │  (信号预计算)    │        │
│  └──────────────┘ └──────────────┘ └──────────────────┘        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐        │
│  │ stock_basic  │ │trade_calendar│ │  task_progress   │        │
│  │  (元数据)    │ │  (元数据)    │ │  (断点续传)      │        │
│  └──────────────┘ └──────────────┘ └──────────────────┘        │
│  ┌──────────────┐ ┌──────────────────┐                         │
│  │ dummy_quotes │ │ snapshot 相关表  │                         │
│  │  (快照)      │ │ (daily_snapshot) │                         │
│  └──────────────┘ └──────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API 服务层 (backend/core/)                  │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────┐    │
│  │  K线接口     │    │  信号接口    │    │  股票筛选接口  │    │
│  │  /kline      │    │  /signals    │    │  /stocks       │    │
│  └──────────────┘    └──────────────┘    └────────────────┘    │
│  ┌──────────────┐    ┌──────────────┐                          │
│  │  元数据接口  │    │  业务服务    │                          │
│  │  /meta       │    │  (kline/signal                          │
│  └──────────────┘    │   /screener) │                          │
│                      └──────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     定时任务 (cron + APScheduler)                │
│  ┌────────────────────┐   ┌──────────────────────────┐          │
│  │ 16:00 盘后同步     │   │ 22:00 数据完整性检查     │          │
│  │ (crontab)          │   │ (crontab)                │          │
│  └────────────────────┘   └──────────────────────────┘          │
│  ┌────────────────────┐   ┌──────────────────────────┐          │
│  │ 周日02:00 全量校验  │   │ 盘后技术指标计算         │          │
│  │ (crontab)          │   │ (task_scheduler.py)      │          │
│  └────────────────────┘   └──────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 冷热数据分离策略

**推荐方案：PostgreSQL 声明式分区**

| 方案 | 描述 | 优势 | 适用场景 |
|------|------|------|----------|
| **分区表** | 按 `trade_date` 进行范围分区 | 管理简单、查询自动路由、支持冷热分离 | 推荐生产环境 |
| **双表架构** | 热数据+归档表手动迁移 | 实现简单 | 小规模数据 |

**分区表创建示例**:
```sql
-- 创建分区表（替代原双表架构）
CREATE TABLE stock_quotes (
    id SERIAL,
    code VARCHAR(10) NOT NULL,
    cycle VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    pre_close NUMERIC(10, 2),
    open NUMERIC(10, 2),
    high NUMERIC(10, 2),
    low NUMERIC(10, 2),
    close NUMERIC(10, 2),
    pct_change NUMERIC(8, 2),
    volume BIGINT,
    amount NUMERIC(18, 2),
    turnover_rate NUMERIC(8, 2),
    adjust_type VARCHAR(10) DEFAULT 'qfq',
    suspended BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (trade_date);

-- 创建年度分区（热数据，近3年）
CREATE TABLE stock_quotes_2024 PARTITION OF stock_quotes
FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

-- 创建归档分区（冷数据，3年前）
CREATE TABLE stock_quotes_archive PARTITION OF stock_quotes
FOR VALUES FROM ('1990-01-01') TO ('2023-01-01');
```

> **说明**: `stock_quotes_archive` 仅为历史分区的一个命名示例，实际可按年份创建多个分区（如 `stock_quotes_2022`、`stock_quotes_2023`）。超过3年的分区可以通过 `ALTER TABLE stock_quotes DETACH PARTITION stock_quotes_20xx;` 分离到冷存储，实现冷热数据物理分离。

---

## 五、索引设计策略

### 5.1 索引总览

| 表名 | 索引名 | 字段 | 用途 |
|------|--------|------|------|
| `stock_basic` | PRIMARY KEY | `code` | 主键查询 |
| `stock_basic` | `idx_basic_status` | `status` | 状态筛选 |
| `stock_basic` | `idx_basic_industry` | `sw_industry` | 行业筛选 |
| `stock_quotes` | UNIQUE | `code, cycle, trade_date` | 唯一性约束，防止重复数据 |
| `stock_quotes` | `idx_quotes_code_date` | `code, trade_date` | 单股票历史查询 |
| `stock_quotes` | `idx_quotes_date` | `trade_date` | 单日全市场查询 |
| `stock_indicators` | UNIQUE | `code, trade_date, cycle` | 唯一性约束，防止重复数据 |
| `stock_indicators` | `idx_indicator_code_date_cycle` | `code, trade_date, cycle` | 单股票指标查询（与唯一约束字段顺序一致，避免回表） |
| `stock_fundamental_pit` | `idx_fundamental_code_report` | `code, report_date` | 财务数据查询 |
| `task_progress` | `idx_task_name` | `task_name` | 任务状态查询 |

### 5.2 索引设计原则

1. **主键索引**: 所有表必须有主键
2. **唯一性约束**: 业务唯一字段必须加 UNIQUE 约束
3. **复合索引**: 经常一起查询的字段建立复合索引
4. **避免过度索引**: 写入密集表控制索引数量
5. **BRIN 索引**: 时序数据（如 trade_date）可使用 BRIN 索引

### 5.3 索引优化建议

```sql
-- 为时序数据创建 BRIN 索引（空间效率高）
CREATE INDEX idx_quotes_date_brin ON stock_quotes USING BRIN (trade_date);

-- 定期检查索引使用情况
SELECT 
    idx.relname AS index_name,
    pg_stat_user_indexes.idx_scan AS scan_count
FROM pg_stat_user_indexes
JOIN pg_class idx ON pg_stat_user_indexes.indexrelid = idx.oid
WHERE pg_stat_user_indexes.schemaname = 'public'
ORDER BY idx_scan ASC;
```

---

## 六、数据文件格式

### 6.1 快照文件格式（JSON）

**文件路径**: `data/snapshot/latest/{ts_code}.json`

**格式示例**:
```json
{
    "code": "sh.600000",
    "name": "浦发银行",
    "trade_date": "2024-01-15",
    "open": 8.50,
    "close": 8.62,
    "high": 8.70,
    "low": 8.45,
    "volume": 12500000,
    "amount": 107750000.00,
    "pct_change": 1.41,
    "update_time": "2024-01-15 15:00:00"
}
```

### 6.2 元数据文件格式（Parquet）

**文件路径**: `data/metadata/stock_list.parquet`

**字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | STRING | 股票代码 |
| `name` | STRING | 股票名称 |
| `list_date` | DATE | 上市日期 |
| `status` | STRING | 状态 |

---

## 七、数据质量保障

### 7.1 数据完整性约束

| 表名 | 约束 | 说明 |
|------|------|------|
| `stock_quotes` | `UNIQUE(code, cycle, trade_date)` | 同一股票同一周期同一日期仅一条记录 |
| `stock_indicators` | `UNIQUE(code, trade_date, cycle)` | 同一股票同一日期同一周期仅一条指标记录 |
| `trade_calendar` | `PRIMARY KEY (cal_date)` | 日期唯一 |
| `task_metrics` | `UNIQUE(task, date)` | 同一任务同一日期仅一条记录 |

### 7.2 入库校验规则

对 `stock_quotes` 的业务校验：

| 校验规则 | 说明 | 处理方式 |
|---------|------|---------|
| `high >= low` | 最高价 ≥ 最低价 | 写入 error_log |
| `ABS(pct_change - (close - pre_close) / NULLIF(pre_close, 0) * 100) < 0.01` | 涨跌幅一致性（允许 0.01% 相对误差） | 自动修正或标记异常 |
| `volume >= 0` | 成交量非负 | 写入 error_log |
| `amount >= 0` | 成交额非负 | 写入 error_log |
| `trade_date` 在 `trade_calendar` 中且 `is_open=1` | 交易日期合法性 | 自动过滤 |

### 7.2.1 推荐写入模式：幂等 Upsert

**问题**: 使用 `DELETE + INSERT` 模式会导致索引碎片、MVCC 膨胀及短事务锁表。

**推荐方案**: 使用 `ON CONFLICT DO UPDATE` 幂等写入：

```sql
-- 推荐：幂等写入（Upsert），无锁表风险，自动处理覆盖
INSERT INTO stock_quotes (code, cycle, trade_date, pre_close, open, high, low, close, pct_change, volume, amount, turnover_rate, adjust_type, suspended)
VALUES 
  ('sh.600000', 'daily', '2024-01-02', 8.45, 8.50, 8.65, 8.45, 8.60, 1.78, 12500000, 107500000.00, 0.45, 'qfq', FALSE)
ON CONFLICT (code, cycle, trade_date) 
DO UPDATE SET 
  pre_close = EXCLUDED.pre_close, open = EXCLUDED.open, high = EXCLUDED.high, 
  low = EXCLUDED.low, close = EXCLUDED.close, pct_change = EXCLUDED.pct_change,
  volume = EXCLUDED.volume, amount = EXCLUDED.amount, turnover_rate = EXCLUDED.turnover_rate,
  updated_at = NOW();
```

**优势**:
- 无需 `DELETE` 操作，避免索引碎片和 MVCC 膨胀
- 原子性保证，冲突时自动更新
- 适合量化数据每日增量更新场景

### 7.3 数据血缘与版本控制

**schema_version.json 元数据文件**:
```json
{
    "version": "1.0.0",
    "updated_at": "2024-01-15T10:30:00+08:00",
    "adjust_method": "qfq",
    "indicator_calc_lib": "ta-lib 0.4.24",
    "data_source": "baostock",
    "data_range": {
        "start_date": "2020-01-01",
        "end_date": "2024-01-15"
    },
    "schema_hash": "abc123def456",
    "changelog": [
        {"date": "2024-01-15", "change": "新增 stock_fundamental_pit 表"},
        {"date": "2024-01-10", "change": "时间字段统一为 TIMESTAMP WITH TIME ZONE"}
    ]
}
```

---

## 八、备份与容灾策略

### 8.1 分层备份策略

| 数据类型 | 备份策略 | 保留周期 |
|---------|---------|---------|
| **热数据**（stock_quotes/stock_indicators） | 每日增量备份 + 每周全量备份 | 增量7天，全量4周 |
| **冷数据**（归档分区） | 每月全量备份 | 6个月 |
| **元数据**（stock_basic/trade_calendar） | 实时同步到备用库 | 实时 |

### 8.2 备份验证

- **频率**: 每月一次
- **流程**: 从备份恢复到测试环境 → 验证数据完整性 → 执行查询验证
- **验证指标**: 记录数匹配、关键数据校验、查询性能达标

### 8.3 多副本存储

- 将 `data/raw/` 目录同步到对象存储（如 AWS S3、阿里云 OSS）
- 同步频率：每日
- 保留策略：与本地一致

### 8.4 原始数据校验

在 `data/raw/` 目录下新增校验文件（如 `{date}_checksum.md5`）：
```
# 2024-01-15_checksum.md5
baostock/daily/20240115_quotes.parquet: md5sum=abc123def456
akshare/daily/20240115_quotes.csv: md5sum=789ghi012jkl
```

---

## 九、监控与可维护性

### 9.1 数据完整性监控

| 指标 | 监控内容 | 告警阈值 |
|------|---------|---------|
| 每日新增记录数 | stock_quotes 每日新增记录数 | 低于预期 80% |
| 缺失股票数量 | 预期同步但未同步的股票数 | > 100 |
| 错误率 | data_error_log 记录数 / 总入库数 | > 1% |

### 9.2 性能监控

| 指标 | 监控内容 | 告警阈值 |
|------|---------|---------|
| 慢查询 | 单次查询超过 5 秒的 SQL | 出现即告警 |
| 索引使用率 | 未使用的索引比例 | > 20% |
| 表膨胀率 | 表的 dead tuple 比例 | > 30% |

**定期维护**:
```sql
-- 每周执行 VACUUM ANALYZE
VACUUM ANALYZE stock_quotes;
VACUUM ANALYZE stock_indicators;
```

### 9.3 任务监控

| 指标 | 监控内容 | 告警阈值 |
|------|---------|---------|
| 任务失败率 | 失败股票数 / 总数 | > 5% |
| 任务耗时 | 任务执行时间 | > 预期时间 2 倍 |
| 重试次数 | 任务重试次数 | > 3 |

### 9.4 数据字典自动化

**自动同步脚本**:
```python
def sync_data_dict():
    """从 information_schema 同步表/字段信息到 data_dict"""
    tables = get_tables_from_information_schema()
    for table in tables:
        columns = get_columns_from_information_schema(table)
        for column in columns:
            upsert_data_dict(table, column)
```

**字段变更日志表**（data_dict_change_log）:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | SERIAL | 主键 |
| `table_name` | VARCHAR(50) | 表名 |
| `column_name` | VARCHAR(50) | 字段名 |
| `change_type` | VARCHAR(20) | 变更类型（ADD/MODIFY/DELETE） |
| `old_value` | TEXT | 变更前值 |
| `new_value` | TEXT | 变更后值 |
| `operator` | VARCHAR(50) | 操作人 |
| `change_time` | TIMESTAMP WITH TIME ZONE | 变更时间 |
| `description` | TEXT | 变更说明 |

---

## 十、分区表配置

### 10.1 分区表概述

| 表名 | 分区类型 | 分区键 | 分区范围 |
|------|---------|--------|---------|
| `stock_quotes` | RANGE | `trade_datetime` | 2015-01-01 ~ 2031-01-01（月度分区） |
| `stock_indicators` | RANGE | `trade_datetime` | 2015-01-01 ~ 2031-01-01（月度分区） |

**设计说明**: 从年度分区改为月度分区，原因是分钟线数据量巨大，月度分区可以更好地平衡查询性能和管理成本。

### 10.2 分区表结构

**stock_quotes 分区结构示例（2024年）**:
```
stock_quotes (父表)
├── stock_quotes_y2024m01 (2024-01-01 00:00:00+08 ~ 2024-02-01 00:00:00+08)
├── stock_quotes_y2024m02 (2024-02-01 00:00:00+08 ~ 2024-03-01 00:00:00+08)
├── stock_quotes_y2024m03 (2024-03-01 00:00:00+08 ~ 2024-04-01 00:00:00+08)
├── ...
├── stock_quotes_y2026m06 (2026-06-01 00:00:00+08 ~ 2026-07-01 00:00:00+08)
└── ...
```

### 10.3 冷热数据分离策略

| 数据类型 | 时间范围 | 分区示例 | 推荐存储 |
|---------|---------|---------|---------|
| 热数据 | 近3个月 | `stock_quotes_y2026m04` ~ `stock_quotes_y2026m06` | SSD (hot_storage) |
| 温数据 | 3个月~1年 | `stock_quotes_y2025m06` ~ `stock_quotes_y2026m03` | HDD (warm_storage) |
| 冷数据 | 1年以上 | `stock_quotes_y2015m01` ~ `stock_quotes_y2025m05` | HDD (cold_storage) |

### 10.4 分区维护工具

**分区维护脚本位置**: `backend/collector/db/sql/partition_maintenance.sql`

| 存储过程/函数 | 用途 |
|--------------|------|
| `add_month_partition(table, year, month)` | 幂等添加单个月度分区 |
| `add_month_partitions(table, start_year, start_month, end_year, end_month)` | 批量添加连续月度分区 |
| `drop_month_partition(table, year, month)` | 幂等删除月度分区 |
| `get_partition_status(table)` | 查看分区状态 |

**使用示例**:
```sql
-- 添加单个月度分区
CALL add_month_partition('stock_quotes', 2026, 7);

-- 批量添加多个月度分区（2026年7月~12月）
CALL add_month_partitions('stock_indicators', 2026, 7, 2026, 12);

-- 查看分区状态
SELECT * FROM get_partition_status('stock_quotes');
```

### 10.5 生产部署注意事项

⚠️ **重要提示**:
1. `init_db.sql` 为首次初始化脚本，不支持重复执行（PostgreSQL 分区表 `CREATE TABLE ... PARTITION OF` 不支持 `IF NOT EXISTS`）
2. 后续月度分区维护请使用 `partition_maintenance.sql`
3. 冷热分离需要提前在 OS 层创建目录：
   ```bash
   sudo mkdir -p /data/cold /data/warm /data/hot
   sudo chown postgres:postgres /data/cold /data/warm /data/hot
   sudo chmod 700 /data/cold /data/warm /data/hot
   ```

---

## 十一、回测/实盘一致性保障

### 11.1 读取路径统一

**统一 DataLoader，通过 mode 参数切换**:
```python
class DataLoader:
    def load(self, codes: list, dates: list, mode: str = 'backtest'):
        """
        统一数据加载接口
        :param codes: 股票代码列表
        :param dates: 日期列表
        :param mode: backtest / live
        """
        if mode == 'backtest':
            return self._query_historical(codes, dates)
        else:
            return self._query_live_plus_history(codes, dates)
```

### 11.2 指标计算幂等

**方案**: 在 `stock_indicators` 增加版本字段，ETL 对比版本号触发重算

**重算触发逻辑**:
```sql
SELECT * 
FROM stock_quotes q
LEFT JOIN stock_indicators i ON q.code = i.code AND q.trade_date = i.trade_date
WHERE i.quotes_version != q.version  -- 行情版本变更
   OR i.calc_version IS NULL;        -- 未计算过
```

### 11.3 前视偏差代码级防护

**强制封装**:
```python
class BacktestEngine:
    def get_data(self, trade_date: str):
        """
        回测引擎强制封装的数据获取接口
        内部自动注入 WHERE trade_date <= :current_date 过滤
        """
        pass
```

**强制规则**:
- 回测时禁止策略直接执行 SQL
- 所有数据查询必须通过 `get_data(trade_date)` 接口
- 内部自动添加 `WHERE trade_date <= :current_date` 约束

---

### 11.4 幸存者偏差防护

**问题**: 回测中如果不考虑退市股票，会引入幸存者偏差，导致策略回测结果过于乐观

**强制规则**: 回测中构建股票池必须使用以下条件：

```sql
SELECT code, name
FROM stock_basic
WHERE list_date <= :current_date 
  AND (delist_date IS NULL OR delist_date > :current_date)
  AND status = 'normal';
```

**说明**:
- `list_date <= current_date`: 确保股票已上市
- `delist_date IS NULL OR delist_date > current_date`: 确保股票在当前日期未退市
- `status = 'normal'`: 确保股票状态正常

---

### 12.1 扩展规划

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| 一期 | 基础行情数据同步、指标计算、回测引擎 | 已完成 |
| 二期 | 财务PIT表、多数据源支持、实盘接口 | 高 |
| 三期 | 分钟线数据、因子库、机器学习框架集成 | 中 |

### 12.2 风险点与应对策略

| 风险点 | 描述 | 应对策略 |
|--------|------|---------|
| **复权类型冲突** | 前复权/后复权混用导致回测结果失真。当前设计仅存储一种复权类型（默认前复权），如需切换需全量重算 | 统一使用前复权，记录复权类型。二期可考虑迁移到「原始价格 + 复权因子」模式，支持动态复权切换 |
| **涨跌幅声明** | 原始数据中涨跌幅字段的定义不一致 | 入库时重新计算涨跌幅，注释明确声明「基于不复权原始价格计算」 |
| **幸存者偏差** | 回测时未考虑退市股票 | 使用强制过滤条件筛选股票池，保留退市记录 |
| **停牌处理** | 当前仅记录 `suspended` 布尔标记，无法获取停牌起止区间。复杂策略（如停牌期间不允许卖出）需精确时间范围 | 基于连续 `suspended=TRUE` 的天数推断停牌状态。二期扩展 `stock_suspend` 表记录精确停牌起止日期 |
| **数据一致性** | 多数据源同步导致数据不一致 | 引入分布式锁和幂等设计 |
| **前视偏差** | 策略使用未来数据 | 强制封装数据获取接口，自动注入时间约束 |

### 12.3 工程微调建议

1. **索引优化**: stock_indicators 考虑使用 BRIN 索引
2. **精度调整**: 价格字段精度调整为 NUMERIC(10, 2) 足够
3. **多数据源处理**: 建立数据源优先级和冲突解决机制
4. **回测接口**: 统一 DataLoader，区分回测和实盘模式

---

## 附录：常用查询示例

### 场景 A：获取某股票最新 N 条 5 分钟 K 线
```sql
-- 索引命中：idx_quotes_code_cycle_time_desc
SELECT * 
FROM stock_quotes
WHERE code = 'sh.600000'
  AND cycle = '5m'
ORDER BY trade_datetime DESC
LIMIT 60;
```

### 场景 B：获取某股票某日期范围的日线 K 线
```sql
-- 索引命中：idx_quotes_code_cycle_time
SELECT * 
FROM stock_quotes
WHERE code = 'sh.600000'
  AND cycle = '1d'
  AND trade_datetime >= '2024-05-01 15:00:00+08'
  AND trade_datetime < '2024-06-01 15:00:00+08'
ORDER BY trade_datetime;
```

### 场景 C：获取某日涨跌幅排名前 10 的股票（日线）
```sql
-- 索引命中：idx_quotes_cycle_time_pctchg_desc
SELECT code, close, pct_chg
FROM stock_quotes
WHERE cycle = '1d'
  AND trade_datetime = '2024-05-01 15:00:00+08'
  AND pct_chg IS NOT NULL
ORDER BY pct_chg DESC
LIMIT 10;
```

### 场景 D：获取单股票近一年行情 + 指标（JOIN）
```sql
SELECT q.*, i.ma5, i.ma10, i.macd, i.rsi6
FROM stock_quotes q
JOIN stock_indicators i ON q.code = i.code AND q.cycle = i.cycle AND q.trade_datetime = i.trade_datetime
WHERE q.code = 'sh.600000'
  AND q.cycle = '1d'
  AND q.trade_datetime >= CURRENT_TIMESTAMP - INTERVAL '1 year'
ORDER BY q.trade_datetime;
```

### 场景 E：查询待处理的脏数据
```sql
SELECT * 
FROM stock_quotes_dirty
WHERE status = 'pending'
ORDER BY fetch_time DESC
LIMIT 100;
```

### 场景 F：查询同步失败的股票
```sql
SELECT code, cycle, last_sync_datetime, fail_reason
FROM sync_checkpoints
WHERE sync_status = 'failed'
ORDER BY updated_at DESC;
```

---

## 十二、数据同步容错机制

### 12.1 幂等 Upsert（推荐）

**使用场景**: 数据同步时可能重复拉取同一时间段数据，使用 `ON CONFLICT` 实现安全更新

```sql
-- 方案 1：使用 execute_values 批量插入（推荐）
INSERT INTO stock_quotes (
    code, cycle, trade_datetime, open, high, low, close,
    volume, amount, pct_chg, turnover_rate, adjust_type, update_time
)
VALUES %s
ON CONFLICT (code, cycle, trade_datetime)
DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume,
    amount = EXCLUDED.amount,
    pct_chg = EXCLUDED.pct_chg,
    turnover_rate = EXCLUDED.turnover_rate,
    adjust_type = EXCLUDED.adjust_type,
    update_time = CURRENT_TIMESTAMP
RETURNING code, cycle, trade_datetime, CASE WHEN xmax = 0 THEN 'insert' ELSE 'update' END AS operation;
```

**方案 2：使用 COPY（性能最优，适合超大规模数据）**

### 12.2 脏数据过滤规则

| 错误类型 | 检查规则 |
|---------|---------|
| `price_missing` | open, high, low, close 任一为 NULL |
| `high_low_invalid` | high < low |
| `volume_error` | volume < 0 |
| `non_trading_time` | trade_datetime 不在交易时间内（根据 trade_calendar 判断） |

### 12.3 水位线断点续传流程

```
开始同步
  ↓
查询 sync_checkpoints 获取 last_sync_datetime
  ↓
将 sync_status 设置为 in_progress
  ↓
从 last_sync_datetime 之后开始拉取数据
  ↓
数据校验 → 有效数据批量 Upsert
         → 无效数据写入 stock_quotes_dirty
  ↓
更新 sync_checkpoints（last_sync_datetime, sync_status, sync_count）
  ↓
提交事务
```

### 12.4 接口限流退避策略

**指数退避 + 随机抖动**:
- 重试间隔: `min(base_delay * 2^(retry-1), max_delay) + random_jitter`
- 推荐参数: `base_delay=1s`, `max_delay=30s`, `max_retries=5`

---

**文档版本**: 3.0  
**最后更新**: 2026-06-02  
**适用版本**: 量化交易系统 v2.0