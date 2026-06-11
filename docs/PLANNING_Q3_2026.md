# 量化研究平台 Q3 项目规划

**编制日期**：2026-06-10
**编制人**：量量（后台 + 架构） / 方舟（前台 + 回测引擎）
**适用周期**：2026-06-10 ~ 2026-09-30

---

## 一、建设目标

构建面向 **选股研究 + 指标验证 + 股票回测** 的轻量级量化研究平台，架构示意：

```
┌─────────────────────────────────────────────────────────┐
│                   Docker Host A（后端容器）                  │
│  ┌──────────┐   ┌──────────────────────┐   ┌─────────┐  │
│  │ PostgreSQL│   │     FastAPI 后端      │   │  定时   │  │
│  │   数据库   │◄──│  (数据API + 回测接口) │◄──│  任务   │  │
│  └──────────┘   └──────────────────────┘   └─────────┘  │
└────────────────────────────┬──────────────────────────────┘
                             │ HTTP / WebSocket
┌────────────────────────────▼──────────────────────────────┐
│                   Docker Host B（前端容器）                  │
│  ┌──────────────┐   ┌─────────────────┐   ┌──────────┐  │
│  │  React 前端   │   │   回测引擎       │   │  选股器   │  │
│  │  (K线+看板)  │   │  (Baostock/CSV) │   │ (条件筛选)│  │
│  └──────────────┘   └─────────────────┘   └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 1.1 Q3 核心交付

| 阶段 | 目标 | 关键交付物 |
|------|------|-----------|
| **Phase 1**（6月底） | 数据管道稳定运行 | 日线数据自动采集、清洗、同步，Docker 化部署 |
| **Phase 2**（7月） | 选股器上线 | 条件组合筛选、多因子打分、前端展示 |
| **Phase 3**（8月） | 回测引擎对接 | 策略编辑 + 一键回测 + 绩效展示 |
| **Phase 4**（9月） | 指标体系完善 | 自定义指标、指标验证工具 |

### 1.2 不在 Q3 范围

- 实盘交易对接
- 金融衍生品（期权/期货）数据
- 多账号管理
- 高频/ Tick 数据

---

## 二、系统架构

### 2.1 部署架构

```
┌─ Docker Host A ────────────────────────────────────────┐
│  后端 + 数据库（docker-compose）                          │
│  ├── backend_api      (FastAPI on :8000)               │
│  ├── backend_worker   (定时任务：Celery 或原生 cron)     │
│  └── postgres         (PostgreSQL on :5432)            │
│                                                      │
│  暴露端口: 8000 (API)                                 │
└───────────────────────────────────────────────────────-┘

┌─ Docker Host B ────────────────────────────────────────┐
│  前端（docker-compose 或 nginx 单容器）                  │
│  ├── frontend        (React/Vite on :80)              │
│  └── 回测引擎        (Python 子进程或独立服务)            │
│                                                      │
│  暴露端口: 80 (HTTP)                                  │
└───────────────────────────────────────────────────────-┘
```

### 2.2 数据流

```
Tushare/Baostock ──▶ import_daily_data.py ──▶ stock_quotes
                                                  │
                                                  ▼
                                     sync_quotes_to_snapshot.py
                                                  │
                                                  ▼
                                    stock_daily_snapshot（宽表）
                                                  │
                    ┌─────────────────────────────┼
                    ▼                             ▼
              FastAPI GET                  前端选股器/回测
              /api/kline                   通过 API 消费数据
              /api/stocks
              /api/signals
```

---

## 三、现有系统盘点

### 3.1 已就绪（直接复用）

| 模块 | 路径 | 状态 |
|------|------|------|
| 数据采集（日线） | `backend/collector/etl/import_daily_data.py` | ✅ 并行采集，FAILOVER |
| 数据清洗/宽表同步 | `sync_quotes_to_snapshot.py`（根目录） | ✅ 从 stock_quotes 计算技术指标 |
| 技术指标计算 | `backend/clean/processor/technical_indicator.py` | ✅ MA/MACD/RSI/BOLL/KDJ |
| 周月线合成 | `backend/collector/etl/synthesize_cycle_data.py` | ✅ |
| 数据补全（缺失值） | `backend/imputer/missing_handler.py` | ✅ ffill/interpolate |
| 前置检查 | `backend/collector/etl/pipeline_health_check.py` | ✅ |
| FastAPI 路由 | `backend/core/api/router/` | ✅ kline/stocks/signals/meta |
| 数据契约 | `shared/schemas.py` | ✅ Pydantic 模型 |
| Dockerfile | `Dockerfile` | ✅ 需验证 |
| docker-compose | `docker-compose.yml` | ✅ 需适配前后端分离 |

### 3.2 需修复/补充

| 模块 | 问题 | 修复方案 |
|------|------|---------|
| `stock_daily_basic` dv/ps 等字段 | Tushare daily_basic 限速 5次/天，历史数据未同步 | 制定每日同步计划，分批补全历史 |
| `stock_adj_factor` 表 | 缺失，复权功能空跑 | 新建表，接入 sync_adj_factor.py |
| 北交所数据 | 干扰数据质量 | 已排除，后续保持 |
| Docker 部署 | 当前为单体，需改为前后端分离 | 重写 docker-compose，分离 Host A/B |
| 选股器前端 | 仅有 mock，真实功能未实现 | 方舟负责 |
| 回测引擎 | 未实现 | 方舟负责 |
| 指标验证工具 | 未实现 | Q3 Phase 4 |

---

## 四、Q3 分阶段计划

### Phase 1：数据管道稳定化（6/10 ~ 6/30）

**目标**：数据管道 Docker 化，字段完整性 > 99%

| 任务 | 负责人 | 交付物 | 截止 |
|------|--------|--------|------|
| Docker 化部署文档 | 量量 | `docs/DEPLOYMENT.md` 更新 | 6/15 |
| 后端 + DB 容器化 | 量量 | `docker-compose.backend.yml` | 6/15 |
| 前端容器化 | 方舟 | `docker-compose.frontend.yml` | 6/15 |
| 前置检查接入定时任务 | 量量 | 任务失败自动告警 | 6/20 |
| dv/ps/float_share 历史数据补全 | 量量 | stock_daily_basic 填充率 > 95% | 6/30 |
| stock_adj_factor 表 + 同步 | 量量 | 复权因子表 + 定时同步 | 6/30 |
| 数据管道端到端验证 | 量量 | 每日快照字段完整性报告 | 6/30 |

**验收标准**：stock_daily_snapshot 空值率 < 1%（技术指标字段）

### Phase 2：选股器（7/1 ~ 7/31）

**目标**：前端条件筛选 + 多因子打分上线

| 任务 | 负责人 | 交付物 |
|------|--------|--------|
| 选股条件 API 扩展 | 量量 | `/api/stocks/filter` 支持多条件组合 |
| 多因子打分接口 | 量量 | `/api/stocks/score` |
| 选股器前端页面 | 方舟 | 条件面板 + 结果表格 |
| 股票详情页完善 | 方舟 | K线 + 技术指标 + 基本面 |

**验收标准**：能按行业/市值/估值/技术指标组合筛选，返回结果可导出

### Phase 3：回测引擎对接（8/1 ~ 8/31）

**目标**：策略编辑 + 回测 + 绩效展示

| 任务 | 负责人 | 交付物 |
|------|--------|--------|
| 回测 API 接口设计 | 量量 | `/api/backtest` POST/GET |
| 策略参数存储 | 量量 | `/api/strategies` CRUD |
| 策略编辑前端 | 方舟 | 代码编辑器 + 参数配置 |
| 回测结果展示 | 方舟 | 收益曲线/回撤/夏普比率 |
| 一键回测入口 | 方舟 | 从选股结果直接发起回测 |

**验收标准**：完整回测流程（选股 → 编辑策略 → 回测 → 查看绩效）

### Phase 4：指标体系完善（9/1 ~ 9/30）

**目标**：自定义指标 + 验证工具

| 任务 | 负责人 | 交付物 |
|------|--------|--------|
| 自定义指标 DSL 设计 | 量量 | 指标表达式解析器 |
| 指标验证工具 | 量量 | `/api/indicators/validate` |
| 指标历史对比 | 方舟 | 指标截面分析页面 |
| 文档更新 | 量量 | `docs/USER_GUIDE.md` |

---

## 五、技术规范

### 5.1 后端 API 清单（Q3 新增/修复）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/stocks/filter` | POST | 多条件选股 |
| `/api/stocks/score` | POST | 多因子打分 |
| `/api/backtest` | POST | 创建回测任务 |
| `/api/backtest/{id}` | GET | 回测结果 |
| `/api/strategies` | GET/POST/DELETE | 策略管理 |
| `/api/indicators/validate` | POST | 指标表达式验证 |
| `/api/snapshot/fields` | GET | 宽表字段说明 |

### 5.2 数据库（Q3 涉及）

| 表 | 用途 |
|---|---|
| `stock_basic` | 股票基础信息 |
| `stock_quotes` | 日线行情（主数据） |
| `stock_daily_snapshot` | 宽表（含技术指标） |
| `stock_daily_basic` | 每日基本面（dv/pe/pb/ps等） |
| `stock_adj_factor` | 复权因子 |
| `trade_signals` | 信号预计算结果 |
| `trade_calendar` | 交易日历 |
| `backtest_results` | 回测结果（新建） |
| `user_strategies` | 用户策略（新建） |

### 5.3 Docker 配置

```
# Host A: docker-compose.backend.yml
services:
  postgres:
    image: postgres:16
    # ...
  backend_api:
    build: ./backend
    # ...
  backend_worker:
    build: ./backend
    command: python -m cron_runner
    # ...

# Host B: docker-compose.frontend.yml  
services:
  frontend:
    build: ./frontend
    # ...
  backtest_engine:
    build: ./frontend
    # ...
```

---

## 六、风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Tushare daily_basic 限速 | 历史数据补全慢 | 制定分批计划，每天5次配额用于增量 |
| 前端选股器复杂度 | 回测引擎依赖选股结果 | Phase 2/3 顺序不可颠倒 |
| Docker 网络互通 | Host A/B 通信 | 统一使用 docker network，通过 HTTP |
| 数据质量历史问题 | 北交所/缺失数据污染 | Phase 1 彻底清理后再推进 |

---

## 七、文档清单

| 文档 | 状态 | 说明 |
|------|------|------|
| `docs/PLANNING_Q3_2026.md` | 本文档 | 项目总体规划 |
| `docs/DEPLOYMENT.md` | 待更新 | Docker 部署指南（Phase 1 输出） |
| `docs/API_REFERENCE.md` | 待更新 | API 接口文档 |
| `docs/DATA_SCHEMA.md` | 已存在 | 数据库 Schema |
| `docs/USER_GUIDE.md` | Phase 4 | 用户操作指南 |
