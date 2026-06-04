# 量化交易系统

一个基于 Python 的量化交易数据展示与分析平台。

## 📋 项目概述

本项目旨在构建一个完整的量化交易数据展示系统，提供股票数据的实时展示、市场分类筛选、以及数据统计功能。

## ✨ 功能特性

### 已实现功能

1. **股票数据展示**
   - 实时展示股票最新价、涨跌幅、涨跌额等数据
   - 支持 45+ 字段展示：代码、名称、行业、涨跌幅、收盘价、PE、PB、总市值、成交额、换手率、量比、净流入、开盘、最高、最低、昨收、涨跌额、成交量、PE-TTM、PS、PS-TTM、股息率、股息率TTM、流通市值、流通股、资金流向（小单/中单/大单/特大单）、20日新高、60日新高、连涨天数、5日量比、5日均量、MA5/MA10/MA20、RSI6、MACD、布林带等
   - 涨跌颜色区分（红色上涨、绿色下跌）

2. **多维度筛选**
   - 全部股票
   - 上市板块：上海主板、深圳主板、创业板、科创板、中小板
   - 行业分类筛选
   - **地区筛选**：31个省市自治区

3. **表格交互**
   - 表头固定，不随内容滚动
   - 支持列排序（点击表头）
   - 分页浏览
   - 点击"查看更多字段"展开完整字段

4. **数据统计**
   - API调用次数统计
   - 快照文件数量统计
   - 日线文件数量统计
   - 系统运行时间统计

5. **界面优化**
   - 统一的深色主题配色
   - 表格与按钮区块无缝连接
   - 页面加载时默认显示全部股票
   - 股票代码可点击跳转至同花顺详情页

## 🛠 技术栈

| 分类 | 技术 | 版本 |
|------|------|------|
| 后端框架 | FastAPI | 0.100+ |
| 前端框架 | React + TypeScript | 18+ |
| 前端构建 | Vite | 5+ |
| 数据存储 | PostgreSQL | 15+ |
| 数据格式 | Parquet | - |
| 数据源 | Akshare / Tushare | - |

## 📁 项目结构

```
Quantitative_trading/
├── .env                     # 环境变量配置
├── requirements.txt         # Python 依赖
├── start_service.sh         # 服务管理脚本（start/stop/restart/status）
├── README.md                # 项目主文档
├── IMPROVEMENTS.md          # 改进文档
├── AKSHARE_README.md        # Akshare 使用说明
├── postgresql_migration_plan.md  # PostgreSQL 迁移方案
├── data_preparation_plan.md # 数据准备计划
├── config/
│   └── pipeline.yaml        # 配置文件
├── data/
│   ├── price/
│   │   └── daily/           # 日线数据（Parquet格式）
│   ├── snapshot/
│   │   └── latest/          # 实时快照数据（JSON格式）
│   ├── backup/              # 数据库备份目录
│   └── metadata/            # 元数据（股票列表等）
├── logs/                    # 日志目录
├── scripts/
│   ├── data_pipeline.py     # 数据处理管道主入口
│   ├── etl/                 # ETL核心脚本
│   │   ├── daily_snapshot_sync.py
│   │   ├── tushare_fetcher.py
│   │   └── ...
│   ├── quality/             # 数据质量检查
│   │   ├── check_table_schema.py
│   │   ├── check_data_quality.py
│   │   └── ...
│   ├── enrichment/          # 数据补全/增强
│   │   ├── update_from_parquet.py
│   │   ├── update_indicators_from_parquet.py
│   │   ├── calculate_highs.py
│   │   └── ...
│   └── utils/               # 工具脚本
├── src/
│   ├── backend/             # FastAPI 后端
│   │   ├── main.py          # API入口
│   │   ├── models.py        # SQLAlchemy模型
│   │   ├── repository.py    # 数据访问层
│   │   └── database.py      # 数据库连接
│   └── frontend/            # React前端
│       ├── src/
│       │   ├── App.tsx      # 主应用组件
│       │   ├── components/  # UI组件
│       │   └── api.ts       # API调用封装
│       └── dist/            # 构建产物
├── tests/                   # 测试目录
└── venv/                    # 虚拟环境
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- PostgreSQL 15+

### 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装前端依赖
cd src/frontend
npm install
```

### 启动服务

```bash
# 使用统一脚本启动（推荐）
./start_service.sh start

# 或手动启动
# 后端：cd src/backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
# 前端：cd src/frontend && npm run dev
```

### 服务管理

```bash
# 启动服务
./start_service.sh start

# 停止服务
./start_service.sh stop

# 重启服务
./start_service.sh restart

# 查看状态
./start_service.sh status
```

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端页面 | http://localhost:5173 |
| 后端API | http://localhost:8000/api |
| API文档 | http://localhost:8000/docs |

## 🔧 数据处理

### 数据处理管道

```bash
# 完整流程（检查 + 补全）
python scripts/data_pipeline.py full --date 2026-06-01

# 仅执行数据质量检查
python scripts/data_pipeline.py check

# 仅执行数据补全
python scripts/data_pipeline.py enrich
```

### 定时任务

本系统使用 Crontab 实现定时任务调度：

| 任务名称 | 执行时间 | 说明 |
|---------|---------|------|
| 每日股票列表更新 | 17:30 | 更新股票列表信息 |
| **收盘作业** | **15:10 (周一至周五)** | 收盘后下载当日最终交易数据，写入数据库 |
| **每日行情更新** | **20:10** | 增量更新日线数据 |
| 每周数据库维护 | 周六 02:00 | VACUUM + ANALYZE + 备份 |
| 每日数据完整性检查 | 03:00 | 检查数据完整性 |

### 数据质量检查

```bash
# 检查表结构一致性
python scripts/quality/check_table_schema.py

# 检查数据完整性
python scripts/quality/check_data_quality.py

# 检查重复数据
python scripts/quality/check_duplicates.py
```

### 数据补全

```bash
# 从Parquet更新基础字段
python scripts/enrichment/update_from_parquet.py

# 更新技术指标
python scripts/enrichment/update_indicators_from_parquet.py

# 更新特殊标志（ST/新股/涨跌停）
python scripts/enrichment/update_special_flags.py

# 计算20日新高和60日新高
python scripts/enrichment/calculate_highs.py --date 2026-06-01
```

## 📊 API 接口

### 获取股票列表

```
GET /api/stocks
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| as_of_date | string | 查询日期（YYYY-MM-DD） |
| listed_board | string | 上市板块筛选 |
| industry | string | 行业筛选（逗号分隔） |
| area | string | 地区筛选（逗号分隔） |
| sort_by | string | 排序字段 |
| sort_asc | boolean | 是否升序 |
| offset | int | 分页偏移量 |
| limit | int | 每页数量（1-500） |

**返回示例**:
```json
{
    "code": 200,
    "message": "success",
    "data": {
        "total": 300,
        "items": [
            {
                "stock_code": "000001",
                "stock_name": "平安银行",
                "industry": "银行",
                "change_pct": 2.35,
                "close": 12.58,
                "pe": 8.56,
                "pb": 0.92,
                "market_cap": 2560.00,
                "amount": 15.20,
                "turnover_rate": 1.85,
                "volume_ratio": 1.23,
                "net_mf_amount": 5200.00
            }
        ]
    }
}
```

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
*最后更新：2026-06-02*
