# 量化交易系统

**Quantitative Trading System** — 沪深 A 股数据采集、清洗、选股与回测一体化平台

---

## 架构

```
┌──────────────────────────────────────────────────────┐
│                    backend/                           │
│  ┌──────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │  collector/  │  │  clean/  │  │   core/api/   │  │
│  │  数据采集     │─▶│  清洗计算 │─▶│  FastAPI REST │  │
│  │  ETL 管道    │  │  指标/形态│  │  (端口 8000)  │  │
│  └──────────────┘  └──────────┘  └───────┬───────┘  │
│  ┌──────────────────────────────────────┐ │          │
│  │  shared/  数据模型 + 常量 (Pydantic) │◀┘          │
│  └──────────────────────────────────────┘            │
└──────────────────────────────────────────────────────┘
                         │
┌────────────────────────┼────────────────────────────┐
│                  frontend/                            │
│  React + TypeScript + Vite + Ant Design              │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │ stock-picker│  │  backtest    │  │ strategy-   │  │
│  │ 选股器      │  │  回测分析     │  │ backtest    │  │
│  │            │  │             │  │ 策略回测     │  │
│  └────────────┘  └──────────────┘  └─────────────┘  │
│  ┌────────────┐  ┌──────────────┐                   │
│  │ watchlist  │  │ stock-detail │                   │
│  │ 自选股      │  │  个股详情     │                   │
│  └────────────┘  └──────────────┘                   │
└──────────────────────────────────────────────────────┘
```

---

## 目录结构

```
Quantitative_trading/
├── backend/
│   ├── collector/                 # 数据采集
│   │   ├── datasource/            #   Baostock / Tushare
│   │   ├── etl/                   #   ETL 脚本（导入/同步/快照/补全）
│   │   ├── db/                    #   数据库模型与迁移
│   │   ├── config/                #   数据源配置
│   │   └── storage/               #   PostgreSQL 存储
│   ├── clean/
│   │   ├── etl/                   #   指标计算 / 形态识别 / 信号生成
│   │   ├── enrich/                #   数据增强 / Parquet 导出
│   │   └── processor/             #   数据导入基类 / 技术指标 / 数据清洗
│   ├── core/
│   │   ├── api/                   #   FastAPI 路由 + 模型
│   │   └── service/               #   业务服务层
│   ├── cron/                      #   定时任务 (daily_job_runner.py)
│   ├── monitoring/                #   系统监控
│   ├── shared/                    #   前后端共享 Pydantic 模型
│   ├── utils/                     #   日志 / 配置 / 重试 / 错误分类
│   └── tests/                     #   后端测试
├── frontend/
│   ├── src/
│   │   ├── features/              #   选股 / 回测 / 自选股 / 个股详情
│   │   ├── lib/indicators/        #   前端指标计算 + K线适配
│   │   └── shared/contexts/       #   全局设置上下文
│   ├── tests/                     #   单元测试 + E2E 测试
│   ├── public/pyodide/            #   Pyodide 运行时（自编指标执行）
│   ├── docs/                      #   前端设计文档
│   ├── vite.config.ts             #   Vite 构建配置
│   ├── tsconfig.json              #   TypeScript 配置
│   └── package.json               #   依赖与脚本
├── scripts/                       #   启停 / 部署 / Git 推送
├── docker/                        #   PostgreSQL 初始化脚本
├── data/                          #   Parquet 导出数据
├── docs/                          #   项目文档 + 日报
├── tests/                         #   根级测试与调试脚本
├── .env.production.example        #   生产环境变量模板
├── docker-compose.yml             #   生产环境编排
├── Dockerfile.backend             #   后端镜像
├── Dockerfile.frontend            #   前端镜像 (含 Nginx)
├── nginx.conf                     #   Nginx 反向代理配置
├── start_prod.sh                  #   生产环境启动
└── verify_prod.sh                 #   生产健康检查
```

---

## 快速开始

### 开发环境

```bash
# 安装依赖
./scripts/start.sh install

# 启动前后端
./scripts/start.sh dev start

# 查看状态
./scripts/start.sh dev status
```

### 生产环境

```bash
# 配置环境变量
cp .env.production.example .env.production
# 编辑 .env.production 替换密码

# 部署
./start_prod.sh start
./verify_prod.sh
```

### 数据管道

```bash
# 一键执行全流程（3 阶段）
PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/cron/daily_job_runner.py

# 阶段 1: 健康检查 + 股票列表同步
PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/cron/daily_job_runner.py --stage 1

# 阶段 2: 日线行情导入
PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/cron/daily_job_runner.py --stage 2

# 阶段 3: 复权因子 → 补全 → 基本面 → 指标 → 形态 → 信号 → 宽表 → Parquet
PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/cron/daily_job_runner.py --stage 3
```

完整 ETL 流程见 [.trae/rules/ETL_PIPELINE.md](.trae/rules/ETL_PIPELINE.md)。

---

## API

| 端点 | 说明 |
|------|------|
| `GET /api/meta/` | 元信息（行业/板块/筛选条件） |
| `GET /api/stocks/` | 股票筛选（行情/财务/技术指标/形态） |
| `GET /api/snapshot/` | 全量快照（宽表数据） |
| `GET /api/kline/{code}` | K线数据（日/周/月，支持复权） |
| `GET /api/signals/{code}` | 交易信号 |
| `GET /api/watchlist/` | 自选股管理 |
| `GET /api/monitor/` | 数据监控（管道状态/数据质量） |
| `GET /admin` | 系统监控看板 |
| `GET /health` | 健康检查 |
| `GET /docs` | Swagger API 文档 |

---

## 文档

| 文档 | 说明 |
|------|------|
| [ETL_PIPELINE.md](.trae/rules/ETL_PIPELINE.md) | 数据管道完整流程 |
| [量化交易.md](.trae/rules/量化交易.md) | 项目技术规范 |
| [frontend/docs/项目规划文档.md](frontend/docs/项目规划文档.md) | 前端架构设计 |
| [frontend/docs/项目使用手册.md](frontend/docs/项目使用手册.md) | 前端使用指南 |
| [frontend/docs/策略回测方案设计-v4.md](frontend/docs/策略回测方案设计-v4.md) | 策略回测方案设计 |
| [frontend/docs/自编指标开发规范.md](frontend/docs/自编指标开发规范.md) | 自编指标开发规范 |