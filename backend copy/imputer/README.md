# backend/imputer/ — 数据补全与复权

## 目的

数据采集过程中会出现两类问题，本模块专门处理：

1. **数据缺口** — 某些交易日完全没下载到（如停牌、节假日漏拉）
2. **数据缺失** — 单条记录某些字段为空（如停牌日的 close 为空、成交额缺失）
3. **复权不一致** — 分红派息 / 拆股导致 K 线跳空，影响回测

## 文件清单

| 文件 | 职责 |
|------|------|
| `missing_handler.py` | 缺失值填充（ffill / interpolate） |
| `incomplete_handler.py` | 缺口检测与补全（从数据源重新拉取） |
| `adjuster.py` | 复权因子加载与应用 |

## 关键约束

### ⚠️ 严禁 `bfill`（防未来函数）

```python
from backend.imputer import fill_missing_prices

# ✅ 正确：前向填充
fill_missing_prices(df, method='ffill')

# ❌ 错误：后向填充会导致前视偏差
fill_missing_prices(df, method='bfill')
# → ValueError: bfill is forbidden to prevent look-ahead bias
```

**白名单**（仅以下方法可用）：
- `ffill` — 前向填充
- `interpolate` — 线性插值
- `none` / `drop` — 不处理

**黑名单**：`bfill` / `backfill` / `pad` / `mean` / `median` / `zero`（价格在分位中位会引入未来信息）。

### 复权规则

| 方式 | 基准 | 用途 |
|------|------|------|
| `none` | 原始价格 | 看真实历史价格 |
| `forward` 前复权 | 最新价格为基准 | **回测推荐**，避免 K 线跳空 |
| `backward` 后复权 | 最早价格为基准 | 观察历史真实收益 |

复权 **只影响 OHLC**，**不影响 volume / amount**。

## 使用示例

### 1. 填充缺失值

```python
import pandas as pd
from backend.imputer import fill_missing_prices, fill_missing_volume

df = pd.DataFrame({...})  # 含 close/volume 的 K 线
df = fill_missing_prices(df, method='ffill')   # 价格用前向填充
df = fill_missing_volume(df, method='zero')    # 成交量填 0
```

### 2. 检测与补全缺口

```python
from backend.imputer import DataGapDetector, DataGapFiller

detector = DataGapDetector(expected_freq='B')  # B = 工作日
gaps = detector.detect(df, stock_code='000001.SZ')

filler = DataGapFiller(data_source='tushare')
filler.fill(gaps)
```

### 3. 复权

```python
from backend.imputer import Adjuster
from shared.constants import AdjMethod

adjuster = Adjuster(storage)  # 注入 PG 存储
df_adj = adjuster.adjust(df, stock_code='000001.SZ', method=AdjMethod.FORWARD)
# → 新增 adj_open/adj_high/adj_low/adj_close 列，原始列保留
```

或通过 K线 API（推荐）：
```bash
curl 'http://localhost:8000/api/kline/000001.SZ?adj=forward&start_date=2024-01-01'
```

## 复权因子表

`Adjuster.load_adj_factors(stock_code)` 从 `adj_factor` 表读取：

```sql
CREATE TABLE adj_factor (
    ts_code    VARCHAR(20),
    trade_date DATE,
    adj_factor NUMERIC(20, 6),  -- 复权因子
    PRIMARY KEY (ts_code, trade_date)
);
```

**如果该表无数据**，`Adjuster.adjust()` 会跳过复权并打 warning，但不会让调用方崩溃。

## 迁移历史

| 日期 | 迁移内容 |
|------|----------|
| 2026-06-06 | 从 `backend/clean/processor/data_gap_handler.py` 迁移到 `incomplete_handler.py`，原文件保留兼容层 |
| 2026-06-06 | 新增 `adjuster.py` 和 `missing_handler.py` |
| 2026-06-06 | 缺失值填充加入 `bfill` 黑名单（防未来函数） |
