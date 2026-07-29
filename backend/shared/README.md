# shared/ — 共享数据契约

## 目的

`shared/` 是**前后端共用的唯一数据契约来源**，任何被 frontend/ 和 backend/ 同时使用的
定义都必须放在这里。这是为了：

1. **字段一致** — 前端 `BackendClient` 与后端 `KLineResponse` 共享同一份 Pydantic schema
2. **约束统一** — 排序白名单、复权方式、字段枚举都有唯一来源
3. **修改可控** — 改动只发生在一处，不会出现前后端字段不同步

## 文件清单

| 文件 | 作用 | 谁会引用 |
|------|------|----------|
| `schemas.py` | Pydantic v2 数据模型（K线、股票、信号、响应） | 后端路由 + 前端 API 客户端 |
| `constants.py` | 枚举 / 字段白名单 / 硬约束 | 后端路由参数校验 + 前端下拉选项 |
| `utils.py` | 工具函数（股票代码规范化、日期解析） | 前后端都需要 |

## 当前契约

### 数据模型（schemas.py）

- `KLineItem` — 单根 K 线（含 OHLC、volume、技术指标）
- `KLineResponse` — K线响应（含 `adj_method` 字段）
- `StockResponse` — 单只股票（行情 + 估值 + 技术指标）
- `StockListResponse` — 股票列表
- `SignalItem` / `SignalResponse` — 买卖信号

### 枚举（constants.py）

- `ListedBoard` — 主板/创业板/科创板/北交所
- `AdjMethod` — 复权方式 `none` / `forward` / `backward`
- `KlinePeriod` — 日/周/月线
- `DataSourceType` — tushare / baostock / akshare

### 白名单

- `ALLOWED_SORT_FIELDS` — `/api/stocks` 排序字段白名单
- `ALLOWED_FILTER_FIELDS` — 过滤字段白名单
- `ALLOWED_ADJ_METHODS` — 复权方式白名单

## 兼容层

后端 `backend/core/api/models/schemas.py` **re-export** `shared/`，保留旧代码兼容：

```python
# 旧代码仍可工作
from backend.core.api.models.schemas import StockResponse

# 新代码统一用 shared
from shared.schemas import StockResponse
```

> ⚠️ 兼容层不会长期保留，建议新代码直接 import `shared`。

## 迁移原则

| 应该放 shared/ | 不应该放 shared/ |
|---------------|-----------------|
| 前后端都要用的 Pydantic 模型 | 仅后端使用的 ORM 模型 |
| 字段白名单、枚举 | 仅前端使用的 UI 常量 |
| 公共工具（代码规范化、日期） | 仅后端使用的数据库工具 |

## 改动流程

修改 `shared/` 任何文件后：
1. 同步更新 frontend 调用方
2. 同步更新 backend 调用方
3. 跑 `python smoke_test.py`（如存在）验证未破坏
4. 提交时单独 commit，并在 message 注明 `[shared]`

## 反例

```python
# ❌ 错误：直接在前端定义 Pydantic 模型
# frontend/types.py
class StockItem(BaseModel):  # 字段迟早会和后端不同
    ...

# ✅ 正确：前端从 shared 导入
from shared.schemas import StockResponse as StockItem
```
