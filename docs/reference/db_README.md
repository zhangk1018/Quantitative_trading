# 量化选股系统后端 API

**项目位置**：`Quantitative_trading/src/backend`  
**技术栈**：FastAPI + Pandas + SQLAlchemy + PostgreSQL  
**数据源**：PostgreSQL 数据库（quant_trading）

---

## 📁 项目结构

```
src/backend/
├── main.py              # FastAPI 主应用（109行）
├── db_loader.py         # 数据库数据加载器（245行）
├── database.py          # 数据库连接管理（113行）
├── loader.py            # Parquet 数据加载器（56行，备用）
├── meta.py              # 元数据管理（207行）
├── requirements.txt     # Python 依赖
├── .env                 # 环境变量配置（需自行创建）
├── .env.example         # 环境变量模板
├── test_api.py          # API 接口测试（96行）
├── test_loader.py       # 数据加载测试（27行）
└── test_meta.py         # 元数据测试（43行）
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
cd /Users/zhangk/workspace/Quantitative_trading/src/backend
pip install -r requirements.txt
```

**新增依赖说明**：
- `psycopg2-binary` - PostgreSQL 数据库驱动
- `sqlalchemy` - ORM 框架，提供连接池管理

### 2. 配置数据库

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：
```ini
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=quant_trading
PG_USER=quant_user
PG_PASSWORD=your_password_here
```

### 3. 验证数据库连接

```bash
python database.py
```

预期输出：
```
🔍 测试数据库连接...
✅ 数据库连接成功！
📊 数据库: quant_trading
🏠 主机: localhost:5432

📋 数据库中的表 (10 个):
   - stock_basic
   - stock_quotes
   - stock_indicators
   ...
```

### 4. 启动服务

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

启动时会看到：
```
🔍 检查数据库连接...
✅ 数据库连接正常
📊 加载股票数据...
📊 从 PostgreSQL 数据库加载数据...
📅 交易日期: 20260420
✅ 数据加载成功: 5484 行 × 89 列
```

### 5. 访问 API

- **API 文档**：http://localhost:8000/docs
- **元数据接口**：http://localhost:8000/api/meta
- **股票列表接口**：http://localhost:8000/api/stocks

---

## 📊 API 接口

### GET /api/meta

获取元数据（交易日期、筛选条件、行业选项、地区选项）

**响应示例**：
```json
{
  "trade_date": "20260420",
  "total": 5484,
  "groups": [...],
  "industry_options": ["银行", "地产", ...],
  "area_options": ["北京", "上海", ...]
}
```

### GET /api/stocks

获取股票列表（支持筛选、排序、分页）

**请求参数**：
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| filters | string | "" | 筛选条件（逗号分隔） |
| industry | string | "" | 行业（逗号分隔） |
| area | string | "" | 地区（逗号分隔） |
| sort_by | string | "pct_chg" | 排序字段 |
| sort_asc | boolean | false | 是否升序 |
| offset | int | 0 | 分页偏移 |
| limit | int | 100 | 每页数量（1-500） |

**响应示例**：
```json
{
  "total": 5484,
  "offset": 0,
  "limit": 100,
  "rows": [...]
}
```

---

## 🔧 配置说明

### 数据文件路径

默认从以下位置读取数据：
```
Quantitative_trading/data/price/daily/latest_quotes.parquet
```

如需自定义路径，可通过环境变量设置：

```bash
# 方法1：创建 .env 文件
cp .env.example .env
# 编辑 .env，设置 PARQUET_PATH

# 方法2：命令行设置
PARQUET_PATH=/custom/path/data.parquet uvicorn main:app --reload
```

---

## 🧪 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest test_api.py
pytest test_loader.py
pytest test_meta.py

# 详细输出
pytest -v
```

---

## 📝 开发指南

### 代码架构

```
main.py (FastAPI 应用)
    ↓ 导入
loader.py (数据加载层)
    ↓ 读取
Parquet 文件 (2.5MB, 5484行 × 205列)
    ↓ 提供
DataFrame 全局变量
    ↓ 使用
meta.py (元数据管理)
    ↓ 返回
JSON API 响应
```

### 关键模块

#### loader.py
- 负责加载 Parquet 文件到内存
- 提供全局变量：`df`, `trade_date`, `field_counts`
- 应用启动时调用一次 `load()`

#### meta.py
- 定义筛选条件分组（127个K线形态 + 动量因子）
- 动态过滤不存在的字段
- 提供行业和地区选项

#### main.py
- FastAPI 应用入口
- 定义 API 路由
- CORS 配置
- 静态文件服务（生产环境）

---

## ⚠️ 注意事项

### 1. 数据文件依赖

后端启动时必须存在 Parquet 数据文件，否则会抛出异常。

**解决方案**：
- 确保 `data/price/daily/latest_quotes.parquet` 存在
- 或设置 `PARQUET_PATH` 环境变量

### 2. 内存占用

当前数据量（5,484行 × 205列）约占用 50MB 内存。

如果数据量增长到 10万+ 行，建议：
- 迁移到 PostgreSQL 数据库
- 或使用 PyArrow 直接查询（无需加载到 Pandas）

### 3. 并发安全

当前实现为单进程模式，不适合高并发场景。

**生产环境建议**：
- 使用 Gunicorn + Uvicorn workers
- 或迁移到数据库方案

---

## 🔗 相关文档

- [PROJECT_DESIGN.md](../frontend/PROJECT_DESIGN.md) - 前端项目设计文档
- [MIGRATION_NOTES.md](../../data/MIGRATION_NOTES.md) - 数据源迁移说明
- [DATA_SCHEMA.md](../../data/DATA_SCHEMA.md) - 完整数据架构文档

---

## 📈 性能指标

| 指标 | 数值 |
|------|------|
| **启动时间** | ~200ms |
| **内存占用** | ~50MB |
| **API 响应** | <50ms |
| **数据加载** | 一次性加载，后续查询内存操作 |

---

**最后更新**：2026-05-31  
**维护者**：灵码前端工程师（Lingma-FE）
