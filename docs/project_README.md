# 量化交易系统

一个基于 Python 的量化交易数据采集、清洗、分析与展示平台。

## 📋 项目概述

本项目构建了一套完整的量化交易数据流水线，涵盖数据采集（多数据源）、清洗校验、技术指标计算、信号生成，并提供 RESTful API 和监控看板。

## ✨ 功能特性

### 已实现功能

1. **多数据源管理**
   - Baostock 主力数据源（免费、稳定、无Token）
   - Tushare 备用数据源（免费版，仅限日线）
   - DataSourceManager 自动故障切换（FAILOVER 策略）
   - 令牌桶限流器，避免触发 API 频率限制

2. **数据采集与清洗**
   - 日线数据全量/增量同步
   - 复权因子同步（Baostock query_adjust_factor）
   - 行业数据补全（Baostock query_stock_industry）
   - 数据格式校验、业务规则校验、跨数据源交叉验证
   - 脏数据自动修复与死信表

3. **技术指标计算**
   - 移动平均线（MA5/MA10/MA20/MA60）
   - MACD 指标（DIF/DEA/MACD）
   - RSI 指标（6/12/24）
   - KDJ 指标（K/D/J）
   - 布林带（上轨/中轨/下轨）

4. **交易信号**
   - MACD 金叉/死叉预计算
   - 信号持久化到 trade_signals 表

5. **股票数据展示**
   - 实时展示股票最新价、涨跌幅、涨跌额等 45+ 字段
   - 涨跌颜色区分（红色上涨、绿色下跌）

6. **多维度筛选**
   - 全部股票
   - 上市板块：上海主板、深圳主板、创业板、科创板、中小板
   - 行业分类筛选
   - 地区筛选：31个省市自治区

7. **表格交互**
   - 表头固定，不随内容滚动
   - 支持列排序（点击表头）
   - 分页浏览
   - 点击"查看更多字段"展开完整字段

8. **数据监控看板** `/admin`
   - 数据完整性总览（覆盖率、最新日期、缺失股票）
   - 覆盖率趋势图表
   - 管道执行状态（各 ETL 任务进度）
   - 当前下载进度
   - 数据质量统计（脏数据、同步失败）
   - 系统健康状态（数据库/数据源/分区校验）

9. **数据统计**
   - API调用次数统计
   - 快照文件数量统计
   - 日线文件数量统计
   - 系统运行时间统计

## 🛠 技术栈

| 分类 | 技术 | 版本 |
|------|------|------|
| 后端框架 | FastAPI | 0.100+ |
| 前端框架 | React + TypeScript | 18+ |
| 前端构建 | Vite | 5+ |
| 数据存储 | PostgreSQL | 15+ |
| 数据格式 | Parquet | - |
| 数据源 | Baostock（主力） / Tushare（备用） | - |
| 调度系统 | crontab（主力） / APScheduler（备选） | - |

## 📁 项目结构

```
Quantitative_trading/
├── .env                     # 环境变量配置
├── requirements.txt         # Python 依赖（根级公共依赖）
├── start_service.sh         # 服务管理脚本（start/stop/restart/status/all）
├── README.md                # 项目主文档
├── backend/                 # 后端代码主目录
│   ├── main.py              # FastAPI 主入口
│   ├── pipeline.yaml        # 核心配置文件
│   ├── task_scheduler.py    # APScheduler 调度器
│   ├── collector/           # 数据采集
│   │   ├── datasource/      # 多数据源（base/tushare/baostock/akshare）
│   │   ├── db/              # 数据库操作（models/loader/meta/repository）
│   │   │   └── sql/         # SQL 脚本（建表/分区/迁移）
│   │   ├── etl/             # ETL 流程（import/sync_adj_factor/fill_industry/分区维护）
│   │   ├── scheduler/       # 智能调度系统
│   │   └── storage/         # 存储层（PostgreSQL/SQLite）
│   ├── clean/               # 数据清洗与补全
│   │   ├── enrich/          # 数据补全（基本面/行业/技术指标/新高突破）
│   │   ├── processor/       # 核心处理（导入器/缺口处理/质量检查/技术指标）
│   │   ├── quality/         # 数据质量检查
│   │   └── tools/           # 工具脚本（信号预计算/数据管道/清理/对比）
│   ├── core/                # 核心服务
│   │   └── api/             # FastAPI 路由（main/config/dependencies/models/router/）
│   ├── monitoring/          # 系统监控（system_monitor）
│   ├── static/              # 静态文件（monitor.html 监控看板）
│   ├── utils/               # 工具模块（配置/日志/错误分类/存储工厂/股票代码工具）
│   └── logs/                # 运行日志
├── data/                    # 数据目录
│   ├── metadata/            # 元数据缓存（stock_list.parquet）
│   └── price/daily/         # 日线快照（latest_quotes.parquet）
├── logs/                    # 根级日志
│   └── etl/                 # ETL 定时任务日志
└── docs/                    # 项目文档
    ├── DATA_SCHEMA.md       # 数据架构
    ├── DATA_COLLECTION_DESIGN.md  # 数据采集设计
    ├── SCHEDULER_GUIDE.md   # 调度系统指南
    ├── project_README.md    # 本文档
    └── ...                  # 其他设计文档
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- PostgreSQL 15+

### 环境变量配置

创建 `.env` 文件（在项目根目录）：

```env
# 数据库配置
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=quant_trading
PG_USER=quant_user
PG_PASSWORD=your_password

# Tushare Token（可选，仅备用数据源需要）
TUSHARE_TOKEN=your_token_here
```

### 安装依赖

```bash
# 安装 Python 依赖（后端）
pip install -r requirements.txt
pip install -r backend/requirements.txt

# 安装前端依赖
cd src/frontend
npm install
```

### 初始化数据库

```bash
# 执行建表脚本
psql -h localhost -U quant_user -d quant_trading -f backend/collector/db/sql/init_db.sql
```

### 启动服务

```bash
# 启动所有服务（后端 + 前端 + 监控看板）
./start_service.sh all

# 或分别启动
./start_service.sh start    # 仅后端 + 前端
./start_service.sh admin    # 仅监控看板
```

### 服务管理

```bash
./start_service.sh start      # 启动服务
./start_service.sh stop       # 停止服务
./start_service.sh restart    # 重启服务
./start_service.sh status     # 查看状态
./start_service.sh all        # 启动全部（含监控看板）
```

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端页面 | http://localhost:5173 |
| 后端API | http://localhost:8000/api |
| API文档 | http://localhost:8000/docs |
| 系统看板 | http://localhost:8000/admin |

## 🔧 数据处理

### 数据采集 ETL

```bash
# 日线数据导入
cd /Users/zhangk/workspace/Quantitative_trading/backend
python collector/etl/import_daily_data.py --start-date 2026-06-01 --end-date 2026-06-05

# 复权因子同步（全量）
python collector/etl/sync_adj_factor.py

# 复权因子同步（增量）
python collector/etl/sync_adj_factor.py --incremental

# 行业数据补全
python collector/etl/fill_industry.py
```

### 数据清洗与补全

```bash
# 技术指标计算
python clean/processor/calculate_technical_indicators.py

# 信号预计算（MACD 金叉/死叉）
python clean/tools/precompute_signals.py

# 新高突破计算
python clean/enrich/calculate_highs.py --date 2026-06-01
```

### 数据质量检查

```bash
# 检查表结构一致性
python clean/quality/check_table_schema.py

# 检查数据完整性
python clean/quality/check_data_quality.py

# 检查重复数据
python clean/quality/check_duplicates.py
```

### 定时任务

本系统使用 Crontab 实现定时任务调度：

| 任务名称 | 执行时间 | 脚本路径 | 说明 |
|---------|---------|----------|------|
| 收盘作业 | 16:00（周一至周五） | `collector/etl/daily_snapshot_sync.py` | 下载当日交易数据 |
| 每日行情更新 | 20:10 | `collector/etl/daily_snapshot_sync.py` | 增量更新日线数据 |
| 复权因子同步 | 21:00 | `collector/etl/sync_adj_factor.py` | 增量同步复权因子 |
| 每日数据完整性检查 | 22:00 | `clean/quality/check_data_quality.py` | 检查数据完整性 |
| 每周数据库维护 | 周六 02:00 | `collector/etl/weekly_maintenance.py` | VACUUM + ANALYZE + 备份 |

## 📊 API 接口

### 股票相关

```
GET /api/stocks                     # 获取股票列表
GET /api/stocks/query               # 按代码/名称搜索
GET /api/meta                       # 获取元数据（行业/地区/板块）
GET /api/kline/{code}               # 获取K线数据
GET /api/signals/{code}             # 获取交易信号
```

### 监控相关

```
GET /api/monitor/data-summary/      # 数据完整性总览
GET /api/monitor/coverage-trend/    # 覆盖率趋势
GET /api/monitor/pipeline-status/   # 管道执行状态
GET /api/monitor/download-progress/ # 当前下载进度
GET /api/monitor/data-quality/      # 数据质量统计
GET /api/monitor/sync-checkpoints/  # 同步水位线异常
GET /api/monitor/health-check/      # 系统健康状态
GET /api/monitor/pipeline-history/  # 管道历史趋势
```

监控看板访问地址：`http://localhost:8000/admin`

### 获取元数据

```
GET /api/meta
```

**返回示例**:
```json
{
    "code": 200,
    "message": "success",
    "data": {
        "trade_date": "20260601",
        "total": 300,
        "industry_options": ["银行", "证券", "保险", ...],
        "area_options": ["北京", "上海", "广东", ...],
        "groups": [...]
    }
}
```

## 📝 开发日志

### 2026-06-08
- ✅ 重构 Tushare 数据源，仅保留日线数据下载功能
- ✅ 新增 Baostock 复权因子获取（get_adj_factor）
- ✅ 新增 Baostock 行业数据获取（get_stock_industry）
- ✅ 实现 DataSourceManager 故障切换策略
- ✅ 新增复权因子同步脚本 sync_adj_factor.py
- ✅ 新增行业数据补全脚本 fill_industry.py
- ✅ 新增系统监控看板（/admin）
- ✅ 修复 .env 配置文件加载路径
- ✅ 修正监控看板分区检查逻辑（年度分区）

### 2026-06-04
- ✅ 数据采集设计文档完成
- ✅ 合并调度系统指南文档
- ✅ 数据架构文档 v4.0 更新

### 2026-06-02
- ✅ 整理代码结构：新增 quality/、enrichment/ 目录
- ✅ 创建数据处理管道主入口 data_pipeline.py
- ✅ 实现20日新高和60日新高计算
- ✅ 添加45+数据字段展示
- ✅ 实现地区筛选功能（31个地区）
- ✅ 移除ST、新股、涨停、跌停字段展示

### 2026-06-01
- ✅ 添加量比、净流入字段
- ✅ 添加PE-TTM、PS、PS-TTM、股息率等估值指标
- ✅ 添加资金流向字段（小单/中单/大单/特大单）
- ✅ 添加连涨天数、5日量比字段
- ✅ 修复前端布尔值渲染问题
- ✅ 实现净流入红涨绿跌着色

### 2026-05-31
- ✅ 创建服务管理脚本 start_service.sh
- ✅ 完成全量数据同步（15,933,246条记录）
- ✅ 前端构建测试通过
- ✅ API性能测试（毫秒级响应）
- ✅ 配置Crontab定时任务

### 2026-05-30
- ✅ 修复宽表JOIN问题（股票代码前缀格式不一致）
- ✅ 更新行业、PE、PB、市值、换手率等字段
- ✅ 添加技术指标（MA5/MA10/MA20、RSI6、MACD、布林带）
- ✅ 修复ST、新股、涨停、跌停标志显示

### 2026-05-29
- ✅ 新增 15:10 收盘作业定时任务
- ✅ 收盘后自动下载当日交易数据写入数据库
- ✅ 修复交易时段快照更新配置

### 2026-05-28
- ✅ 实现表头固定功能
- ✅ 修复表头与表体横向滚动同步
- ✅ 实现列宽度自动对齐
- ✅ 添加系统统计 API

### 2026-05-27
- ✅ 修复市场筛选逻辑
- ✅ 统一页面色块样式
- ✅ 表格与按钮区块无缝连接

### 2026-05-26
- ✅ 集成 Akshare 数据源
- ✅ 实现股票数据展示界面
- ✅ 实现市场分类筛选功能

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

*项目名称：量化交易系统*
*最后更新：2026-06-08*
