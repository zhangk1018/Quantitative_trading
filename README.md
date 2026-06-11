# 量化交易系统

**Quantitative Trading System** — 沪深 A 股数据采集、清洗、回测与策略研发一体化平台

---

## 📋 目录

- [架构总览](#一架构总览)
- [目录结构](#二目录结构)
- [数据流](#三数据流)
- [快速开始](#四快速开始)
- [文档导航](#五文档导航)
- [变更记录](#六变更记录)

---

## 一、架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    shared/   共享数据契约                      │
│              Pydantic schemas · 常量 · 工具函数                 │
└────────────────────┬───────────────────┬─────────────────────┘
                     │                   │
        ┌────────────▼──────┐    ┌───────▼─────────┐
        │      backend/     │    │    frontend/    │
        │   数据采集与清洗    │    │  策略研发与展示   │
        │                   │    │                 │
        │ • collector 数据源│    │ • strategies    │
        │ • imputer 补全/复权│    │ • backtester    │
        │ • clean 清洗      │    │ • analyzer      │
        │ • core/api REST  │◄───┤ • dashboard     │
        │   (FastAPI)       │    │   (Streamlit)   │
        └───────────────────┘    └─────────────────┘
```

### 核心设计原则

| 原则 | 落地方式 |
|------|----------|
| **数据契约统一** | 前后端共用 `shared/`，避免字段/类型不一致 |
| **防未来函数** | `imputer/` 严格禁止 `bfill`，策略基类禁 `shift(-N)` |
| **复权标准** | `Adjuster` 统一前/后复权入口，K线 API 支持 `adj` 参数 |
| **可观测性** | `health_monitor.py` 守护进程，每分钟输出心跳 |
| **增量优先** | 数据下载、宽表同步均支持增量运行 |

---

## 二、目录结构

```
Quantitative_trading/
├── shared/                        # 【新】前后端共享契约
│   ├── schemas.py                 #   Pydantic 数据模型
│   ├── constants.py               #   枚举/字段白名单
│   └── utils.py                   #   公共工具函数
│
├── backend/                       # 数据后台
│   ├── collector/                 #   数据采集
│   │   ├── datasource/            #     Tushare / Baostock / AkShare
│   │   ├── etl/                   #     ETL 流程（含 health_monitor）
│   │   ├── scheduler/             #     智能调度（断路器、熔断）
│   │   └── storage/               #     PostgreSQL / SQLite
│   ├── imputer/                   # 【新】数据补全与复权
│   │   ├── missing_handler.py     #   缺失值（ffill/interpolate，禁 bfill）
│   │   ├── incomplete_handler.py  #   缺口检测与补全
│   │   └── adjuster.py            #   前/后复权
│   ├── clean/                     # 数据清洗（已部分迁移到 imputer/）
│   ├── core/
│   │   ├── api/                   #   FastAPI REST 服务
│   │   │   ├── router/            #     kline / stocks / signals
│   │   │   └── models/            #     兼容层（re-export shared）
│   │   └── service/               #   业务服务层
│   ├── utils/                     # 工具（logger / config / error_classifier）
│   ├── tests/                     # 正式测试
│   ├── temp/                      # 临时测试（.gitignore）
│   ├── main.py                    # 后台入口
│   └── PROJECT_RULES.md           # 后台开发规范
│
├── frontend/                      # 前端工作区
│   ├── src/                       #   React + TS 主应用
│   ├── backtester/                # 【新】回测引擎（纯 Python）
│   ├── strategies/                # 【新】策略基类 + 示例
│   ├── analyzer/                  # 【新】绩效分析
│   ├── dashboard/                 # 【新】Streamlit 看板
│   ├── utils/                     # 【新】API 客户端
│   ├── README.md                  #   前端工作区说明
│   ├── PROJECT_DESIGN.md          #   前端设计文档
│   ├── RUNNING_GUIDE.md           #   前端运行指南
│   └── CODING_STANDARDS.md        #   前端编码规范
│
├── .trae/                         # IDE 配置 + 工作规则
├── .env                           # 环境变量（PG / Tushare Token）
└── README.md                      # 本文档
```

---

## 三、数据流

### 3.1 盘后自动流程（crontab）

```
┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Tushare /   │───▶│ import_daily_    │───▶│   stock_quotes   │
│  Baostock    │    │ data.py --incremental│  (PostgreSQL)    │
└──────────────┘    └──────────────────┘    └────────┬─────────┘
                                                     │
                                            ┌────────▼─────────┐
                                            │ sync_quotes_to_  │
                                            │ snapshot.py      │──▶ stock_daily_snapshot
                                            └──────────────────┘    (宽表)
                                                     │
                                            ┌────────▼─────────┐
                                            │ run_data_complete│──▶ 缺口/缺失补全
                                            └──────────────────┘
```

- **16:05** `import_daily_data.py --incremental`（默认并行：沪→Tushare，深→Baostock）
- **16:30** `sync_quotes_to_snapshot.py --latest`（从 stock_quotes 计算指标并同步宽表）

### 3.2 心跳守护

```bash
python backend/collector/etl/health_monitor.py --daemon
# 每分钟输出: 18:29:18, 下载, 正常, 58/4876(1%), 处理到 SZ.000066
```

### 3.3 API 服务

```bash
cd backend && python -m uvicorn core.api.main:app --reload
# 默认 http://localhost:8000/docs
```

主要路由：
- `GET /api/stocks` — 股票筛选（按行情/估值/技术指标）
- `GET /api/kline/{code}?adj=forward` — K线 + 复权参数
- `GET /api/signals/{code}` — 买卖信号
- `GET /api/meta` — 元信息（交易日历、复权因子等）

### 3.4 策略回测

```python
from frontend.strategies import DoubleMAStrategy
from frontend.backtester import BacktestEngine

engine = BacktestEngine(strategy=DoubleMAStrategy(fast=5, slow=20))
result = engine.run(kline_df, stock_code='000001.SZ')
print(result.metrics.sharpe_ratio, result.metrics.max_drawdown)
```

---

## 四、快速开始

### 4.1 环境准备

```bash
# Python 3.11+
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
pip install -r backend/requirements_api.txt
```

### 4.2 配置

复制并编辑 `.env`：
```env
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=quant_trading
PG_USER=quant_user
PG_PASSWORD=xxx
TUSHARE_TOKEN=your_token_here
```

### 4.3 启动

```bash
# 1) 手动执行一次今日增量
python backend/collector/etl/import_daily_data.py --incremental

# 2) 同步宽表
python sync_quotes_to_snapshot.py --latest

# 3) 启动 API
cd backend && python -m uvicorn core.api.main:app --reload --port 8000

# 4) 启动 Streamlit 看板
streamlit run frontend/dashboard/app.py

# 5) 启动心跳守护
python backend/collector/etl/health_monitor.py --daemon
```

---

## 五、文档导航

### 5.1 项目级文档（`docs/`）

| 文档 | 说明 |
|------|------|
| [docs/project_README.md](./docs/project_README.md) | 项目概述与功能特性 |
| [docs/PROJECT_PLAN.md](./docs/PROJECT_PLAN.md) | 项目总体计划 |
| [docs/DATA_COLLECTION_DESIGN.md](./docs/DATA_COLLECTION_DESIGN.md) | 数据采集与定时任务设计 |
| [docs/DATA_SCHEMA.md](./docs/DATA_SCHEMA.md) | 数据库 Schema 说明 |
| [docs/AI_COLLABORATION.md](./docs/AI_COLLABORATION.md) | AI 协作记录 |
| [docs/AI_Agent_Workflow_Config.md](./docs/AI_Agent_Workflow_Config.md) | AI 角色与工作流配置 |
| [docs/CODE_QUALITY_GUIDE.md](./docs/CODE_QUALITY_GUIDE.md) | 代码质量规范 |
| [docs/DEPLOYMENT_CHECKLIST.md](./docs/DEPLOYMENT_CHECKLIST.md) | 部署检查清单 |
| [docs/DAILY_REPORT_POLICY.md](./docs/DAILY_REPORT_POLICY.md) | 日报规范 |
| [docs/SCHEDULER_GUIDE.md](./docs/SCHEDULER_GUIDE.md) | 调度器指南 |

### 5.2 模块级文档

| 模块 | 文档 |
|------|------|
| 共享契约（新） | [shared/README.md](./shared/README.md) |
| 数据补全/复权（新） | [backend/imputer/README.md](./backend/imputer/README.md) |
| 后台 ETL | [backend/collector/etl/README.md](./backend/collector/etl/README.md) |
| 后台开发规范 | [backend/PROJECT_RULES.md](./backend/PROJECT_RULES.md) |
| 前端工作区 | [frontend/README.md](./frontend/README.md) |
| 前端设计 | [frontend/PROJECT_DESIGN.md](./frontend/PROJECT_DESIGN.md) |
| 前端运行 | [frontend/RUNNING_GUIDE.md](./frontend/RUNNING_GUIDE.md) |
| 前端编码规范 | [frontend/CODING_STANDARDS.md](./frontend/CODING_STANDARDS.md) |

### 5.3 调研资料（`docs/research/`）

前端图表库调研：klinecharts / lightweight-charts / echarts / highcharts-stock / chartjs / d3js / lightningchart / streamlit-grafana

### 5.4 参考资料（`docs/reference/`）

- Tushare / AkShare / Baostock 接口参考
- PostgreSQL 常用命令
- 量化交易 AI 助手提示词

---

## 六、变更记录

### v0.6.0 (2026-06-06) — 架构重构
- ✅ 新增 `shared/` 目录统一前后端数据契约
- ✅ 新增 `backend/imputer/` 整合补全与复权
- ✅ 新增 `frontend/{backtester,strategies,analyzer,dashboard}/`
- ✅ K线 API 新增 `adj` 参数（none/forward/backward）
- ✅ 缺失值填充严格禁止 `bfill`，消除未来函数风险
- ✅ FastAPI Settings `extra="ignore"`，兼容多源环境变量

### v0.5.0 (2026-05-31)
- 完成并行下载（沪市Tushare / 深市Baostock）
- 修复 crontab 缺少下载任务的故障

### v0.4.0
- 同步宽表从 `stock_indicators` 改为从 `stock_quotes` 计算指标
