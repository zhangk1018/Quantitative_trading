# BaoStock Python API 摘要

> **重要参考文档**:
> - https://www.baostock.com/mainContent?file=pythonAPI.md
> - https://www.baostock.com/mainContent?file=stockKData.md (A股K线数据)
> - https://www.baostock.com/mainContent?file=factorInfo.md (复权因子信息)
> - https://www.baostock.com/mainContent?file=DailyUpdates.md (每日更新)
>
> **创建日期**: 2026-05-30
> **最后更新**: 2026-07-21

---

## 1. 核心概念

### 1.1 登录/登出

```python
import baostock as bs

# 登录
lg = bs.login()
print('error_code:', lg.error_code)  # '0' 表示成功
print('error_msg:', lg.error_msg)

# 登出
bs.logout()
```

### 1.2 数据获取模式

BaoStock 使用**游标迭代模式**获取数据：

```python
rs = bs.query_history_k_data_plus(...)
data_list = []
while (rs.error_code == '0') & rs.next():
    data_list.append(rs.get_row_data())
result = pd.DataFrame(data_list, columns=rs.fields)
```

**重要**: `rs.get_data()` 返回的 DataFrame 可能存在**重复索引**，操作前需要调用 `reset_index(drop=True)`

---

## 2. 历史K线数据 (query_history_k_data_plus)

### 2.1 核心参数

| 参数 | 说明 | 可选值/格式 |
|------|------|------------|
| `code` | 股票代码 | `sh.600000`, `sz.000001`（6位数字） |
| `fields` | 返回字段 | 多指标用半角逗号分隔，详见 2.2 |
| `start_date` | 开始日期（包含） | `YYYY-MM-DD`，空则取2015-01-01 |
| `end_date` | 结束日期（包含） | `YYYY-MM-DD`，空则取最近交易日 |
| `frequency` | K线周期 | `d`=日线, `w`=周线, `m`=月线, `5`=5分钟, `15`, `30`, `60` |
| `adjustflag` | 复权类型 | **默认 `3`（不复权）**；`2`=前复权；`1`=后复权。已支持日线/周线/月线/分钟线 |

**注意**: 数据范围支持 1990-12-19 至当前时间。

### 2.2 字段规范

#### 日线字段（含停牌证券）

```
date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST
```

日线完整字段说明：

| 参数名称 | 参数描述 | 精度/单位 |
|----------|----------|-----------|
| `date` | 交易所行情日期 | `YYYY-MM-DD` |
| `code` | 证券代码 | 如 `sh.600000` |
| `open` | 今开盘价 | 小数点后4位；人民币元 |
| `high` | 最高价 | 小数点后4位；人民币元 |
| `low` | 最低价 | 小数点后4位；人民币元 |
| `close` | 今收盘价 | 小数点后4位；人民币元 |
| `preclose` | 前收盘价 | 小数点后4位；人民币元。除权除息日由交易所计算，见 2.4 |
| `volume` | 成交数量 | **单位：股** |
| `amount` | 成交金额 | **单位：人民币元** |
| `adjustflag` | 复权状态 | `1`=后复权, `2`=前复权, `3`=不复权 |
| `turn` | 换手率 | 小数点后6位；单位 `%`。停牌日为空字符串 |
| `tradestatus` | 交易状态 | `1`=正常交易, `0`=停牌 |
| `pctChg` | 涨跌幅 | 小数点后6位；百分比 |
| `peTTM` | 滚动市盈率 | 小数点后6位 |
| `pbMRQ` | 市净率 | 小数点后6位 |
| `psTTM` | 滚动市销率 | 小数点后6位 |
| `pcfNcfTTM` | 滚动市现率 | 小数点后6位 |
| `isST` | 是否ST股 | `1`=是, `0`=否 |

#### 分钟线字段（不包含指数）

```
date,time,code,open,high,low,close,volume,amount,adjustflag
```

分钟线字段说明：

| 参数名称 | 参数描述 | 精度/单位 |
|----------|----------|-----------|
| `date` | 交易所行情日期 | `YYYY-MM-DD` |
| `time` | 交易所行情时间 | `YYYYMMDDHHMMSSsss`，如 `20260506093500000` |
| `code` | 证券代码 | 如 `sh.600000` |
| `open` | 开盘价 | 小数点后4位；人民币元 |
| `high` | 最高价 | 小数点后4位；人民币元 |
| `low` | 最低价 | 小数点后4位；人民币元 |
| `close` | 收盘价 | 小数点后4位；人民币元 |
| `volume` | 成交数量 | **单位：股**；时间范围内累计成交量 |
| `amount` | 成交金额 | **单位：人民币元**；时间范围内累计成交金额 |
| `adjustflag` | 复权状态 | `1`=后复权, `2`=前复权, `3`=不复权 |

#### 周/月线字段

```
date,code,open,high,low,close,volume,amount,adjustflag,turn,pctChg
```

### 2.3 使用示例

**日线获取（前复权）**：

```python
rs = bs.query_history_k_data_plus(
    code="sh.600000",
    fields="date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
    start_date='2024-07-01',
    end_date='2024-12-31',
    frequency="d",
    adjustflag="2"  # 前复权
)
```

**分钟线获取**：

```python
rs = bs.query_history_k_data_plus(
    code="sh.600000",
    fields="date,time,code,open,high,low,close,volume,amount,adjustflag",
    start_date='2024-07-01',
    end_date='2024-12-31',
    frequency="5",
    adjustflag="3"  # 不复权
)
```

### 2.4 前收盘价 (preclose) 说明

证券在指定交易日的"前收盘价"，当日发生除权除息时不是前一天的实际收盘价，而是交易所根据股权登记日收盘价与分红、送股、配股等计算出的参考价。

计算方法：

1. **除息价** = 股息登记日收盘价 - 每股所分红利现金额
2. **送红股除权价** = 股权登记日收盘价 / (1 + 每股送红股数)
3. **配股除权价** = (股权登记日收盘价 + 配股价 × 每股配股数) / (1 + 每股配股数)
4. **除权除息价** = (股权登记日收盘价 - 每股所分红利现金额 + 配股价 × 每股配股数) / (1 + 每股送红股数 + 每股配股数)

首发日的"前收盘价"等于"首发价格"。

### 2.5 注意事项

1. **指数没有分钟线数据**
2. **停牌日处理**：日线中停牌日 `open/high/low/close` 相同且等于前一交易日收盘价，`volume/amount` 为 0，`turn` 为空字符串
3. **复权说明**：使用"涨跌幅复权算法"，与同花顺、通达信等系统可能存在差异
4. **周/月线**：仅在每周/每月最后一个交易日可获取
5. **换手率转换**：`result["turn"] = [0 if x == "" else float(x) for x in result["turn"]]`

---

## 3. 复权因子 (query_adjust_factor)

### 3.1 方法说明

通过 API 获取复权因子信息数据。BaoStock 提供的是**涨跌幅复权算法**复权因子。

```python
rs = bs.query_adjust_factor(
    code="sh.600000",
    start_date='2015-01-01',
    end_date='2017-12-31'
)
```

### 3.2 参数

| 参数 | 说明 |
|------|------|
| `code` | 股票代码，如 `sh.600000`，不可为空 |
| `start_date` | 开始日期，为空默认 `2015-01-01` |
| `end_date` | 结束日期，为空默认当前日期 |

### 3.3 返回字段

| 参数名称 | 参数描述 | 算法说明 |
|----------|----------|----------|
| `code` | 证券代码 | |
| `dividOperateDate` | 除权除息日期 | |
| `foreAdjustFactor` | **向前复权因子** | 除权除息日前一个交易日的收盘价 / 除权除息日最近的一个交易日的前收盘价 |
| `backAdjustFactor` | **向后复权因子** | 除权除息日最近的一个交易日的前收盘价 / 除权除息日前一个交易日的收盘价 |
| `adjustFactor` | 本次复权因子 | |

### 3.4 本地复权计算

基于 BaoStock 复权因子与本地 BaoStock 日 K 线数据可生成复权行情，参考：
https://www.baostock.com/mainContent?file=localdatafactorInfo.md

---

## 4. 每日更新批量接口 (DailyUpdates)

适合每日增量更新，**单次请求返回指定日期全市场数据**。

### 4.1 获取某日所有A股日K线：query_daily_history_k_AStock()

```python
rs = bs.query_daily_history_k_AStock(date='2026-02-05')
```

**参数**:
- `date`: 获取日期，格式 `YYYY-MM-DD`，为空时取当前自然日

**返回字段**：
```
date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST
```

单次返回全市场所有 A 股在指定日期的数据，覆盖约 5000+ 只股票。

### 4.2 获取某日所有ETF日K线：query_daily_history_k_ETF()

```python
rs = bs.query_daily_history_k_ETF(date='2026-02-05')
```

参数与返回字段同 A 股接口，仅返回 ETF。

### 4.3 获取某日复权因子：query_daily_adjust_factor()

```python
rs = bs.query_daily_adjust_factor(date='2026-02-05')
```

**返回字段**：
```
code,dividOperateDate,foreAdjustFactor,backAdjustFactor,adjustFactor
```

单次返回指定日期全市场复权因子。

### 4.4 批量接口使用建议

- **日线增量更新**：使用 `query_daily_history_k_AStock(date)` 替代循环单只股票请求，可大幅减少 API 调用次数
- **复权因子增量更新**：使用 `query_daily_adjust_factor(date)` 替代循环单只股票请求
- **全量历史回填**：仍可按日期逐日调用批量接口，约 2500 个交易日请求即可覆盖 2015 年至今全市场

---

## 5. 股票基本资料 (query_stock_basic)

```python
rs = bs.query_stock_basic(code="sh.600000")
```

返回字段：`code, code_name, ipoDate, outDate, stock_id, type, status`

---

## 6. 交易日查询 (query_trade_dates)

```python
rs = bs.query_trade_dates(start_date='2024-01-01', end_date='2024-12-31')
```

返回字段：`calendarDate, isOpen, exchange`

---

## 7. 全部股票查询 (query_all_stock)

```python
rs = bs.query_all_stock(day='2024-12-31')
```

返回字段：`code, code_name, changeDate, status`

---

## 8. 除权除息信息 (query_dividend_data)

```python
rs = bs.query_dividend_data(code="sh.600000", year="2024", yearType="report")
```

参数：
- `year`: 年份
- `yearType`: `report`(报告期) 或 `random`(预案公告日期)

---

## 9. 季度财务数据

| 方法 | 说明 |
|------|------|
| `query_profit_data()` | 季频盈利能力 |
| `query_operation_data()` | 季频营运能力 |
| `query_growth_data()` | 季频成长能力 |
| `query_balance_data()` | 季频偿债能力 |
| `query_cash_flow_data()` | 季频现金流量 |
| `query_dupont_data()` | 季频杜邦指数 |

---

## 10. 板块数据

| 方法 | 说明 |
|------|------|
| `query_stock_industry()` | 行业分类 |
| `query_sz50_stocks()` | 上证50成分股 |
| `query_hs300_stocks()` | 沪深300成分股 |
| `query_zz500_stocks()` | 中证500成分股 |

---

## 11. 数据质量注意事项

1. **重复索引问题**：`rs.get_data()` 可能返回带重复索引的 DataFrame，务必在操作前调用 `reset_index(drop=True)`
2. **空值处理**：停牌日或无数据时字段可能为空字符串，需用 `pd.to_numeric(x, errors='coerce')` 转换
3. **换手率转换**：`result["turn"] = [0 if x == "" else float(x) for x in result["turn"]]`
4. **连接维护**：频繁调用时需定期检查连接状态，断开时自动重连
5. **成交量/成交额单位**：`volume` 单位为**股**，`amount` 单位为**人民币元**，无需再做手/千元转换
6. **复权标志**：`query_history_k_data_plus` 默认 `adjustflag="3"`（不复权）；若需前复权行情，必须显式指定 `adjustflag="2"`

---

## 12. 代码模板

### 获取日线数据（前复权，标准写法）

```python
import baostock as bs
import pandas as pd

def get_daily_qfq(code, start_date=None, end_date=None):
    """获取前复权日线数据"""
    lg = bs.login()
    if lg.error_code != '0':
        raise RuntimeError(f"登录失败: {lg.error_msg}")

    try:
        rs = bs.query_history_k_data_plus(
            code=code,
            fields="date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
            start_date=start_date or '2015-01-01',
            end_date=end_date,
            frequency="d",
            adjustflag="2"  # 前复权
        )

        if rs.error_code != '0':
            raise RuntimeError(f"查询失败: {rs.error_msg}")

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())
        result = pd.DataFrame(data_list, columns=rs.fields)

        # 关键：重置索引避免重复标签问题
        result = result.reset_index(drop=True)

        # 数值转换
        for col in ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'turn', 'pctChg']:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors='coerce')

        return result

    finally:
        bs.logout()
```

### 获取某日全市场A股数据（批量接口）

```python
import baostock as bs
import pandas as pd

def get_all_a_stock_daily(trade_date):
    """获取指定日期全市场 A 股日线数据"""
    lg = bs.login()
    if lg.error_code != '0':
        raise RuntimeError(f"登录失败: {lg.error_msg}")

    try:
        rs = bs.query_daily_history_k_AStock(date=trade_date)
        if rs.error_code != '0':
            raise RuntimeError(f"查询失败: {rs.error_msg}")

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())
        result = pd.DataFrame(data_list, columns=rs.fields)
        return result.reset_index(drop=True)

    finally:
        bs.logout()
```

---

## 13. 周期映射表

| 内部标识 | BaoStock frequency | 说明 |
|---------|-------------------|------|
| `1d` | `d` | 日线 |
| `1w` | `w` | 周线 |
| `1m` | `m` | 月线 |
| `5m` | `5` | 5分钟线 |
| `15m` | `15` | 15分钟线 |
| `30m` | `30` | 30分钟线 |
| `60m` | `60` | 60分钟线（1小时） |

---

## 14. 错误代码参考

| error_code | 说明 |
|------------|------|
| `0` | 成功 |
| `1000` | 用户未登录/登录失效 |
| 其他 | 详见 `error_msg` |

---

## 15. 数据更新时间（官方）

> 来源: <https://baostock.com/mainContent?file=home.md>
> 用于校准自动任务调度时间。

### 15.1 每日最新数据更新时间

| 数据类型 | 入库时间 | 说明 |
|----------|----------|------|
| 日K线数据 | 当前交易日 **17:30** | 日线行情数据完成入库 |
| 复权因子数据 | 当前交易日 **18:00** | 复权因子数据完成入库 |
| 分钟K线数据 | 第二自然日 **11:00** | 5/15/30/60 分钟线数据完成入库 |
| 其它财务报告数据 | 第二自然日 **1:30** | 前一交易日的财务报告类数据完成入库 |
| 周线数据 | 周六 **17:30** | 周线数据完成入库 |

### 15.2 每周数据更新时间

| 数据类型 | 入库时间 | 说明 |
|----------|----------|------|
| 指数成份股信息 | 每周一下午 | 上证50、沪深300、中证500 成份股信息完成入库 |

### 15.3 自动任务调度建议

基于上述更新时间，ETL 自动任务可参考以下调度：

- **日线数据下载**: 当前交易日 **18:00 之后**启动，确保日K线与复权因子均已入库。
- **复权因子同步**: 当前交易日 **18:30 之后**启动，避免 18:00 入库完成前的空跑。
- **分钟线数据**: 第二自然日 **11:30 之后**启动。
- **周线数据**: 周六 **18:00 之后**启动。
- **指数成份股**: 每周一下午 **15:00 之后**启动。

> 实际调度应结合 `trade_calendar` 表中的 `is_open` 字段判断是否为交易日，避免非交易日空跑。
