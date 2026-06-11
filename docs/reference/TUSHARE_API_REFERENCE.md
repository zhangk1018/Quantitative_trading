# Tushare 行情接口参考文档

本文档整理了 Tushare 行情数据接口的关键信息，包括分钟行情、日线行情、周线行情、月线行情、复权行情、复权因子、停复牌信息、每日行情指标和通用行情接口。

---

## 1. 通用行情接口 (pro_bar)

**接口名称**: `pro_bar`  
**描述**: 集成开发接口，整合了股票、指数、ETF基金、期货、期权等的行情数据，支持复权和分钟数据。  
**注意**: 此接口为 SDK 层逻辑，暂不支持 HTTP 方式调用。

### 输入参数

| 名称 | 类型 | 必选 | 描述 |
|---|---|---|---|
| ts_code | str | Y | 证券代码，不支持多值输入 |
| start_date | str | N | 开始日期<br>(日线: YYYYMMDD, 分钟: 2019-09-01 09:00:00) |
| end_date | str | N | 结束日期 (YYYYMMDD) |
| asset | str | N | 资产类别: E股票 I沪深指数 FT期货 FD基金 O期权 CB可转债, 默认E |
| adj | str | N | 复权类型: None未复权 qfq前复权 hfq后复权, 默认None<br>**只支持日线复权** |
| freq | str | N | 数据频度: 1/5/15/30/60min / D日线 / W周 / M月, 默认D |
| ma | list | N | 均线 (e.g. [5,10,20]) |
| factors | list | N | 因子: tor换手率 vr量比 |
| adjfactor | str | N | 是否返回复权因子, 默认False |

### 接口示例

```python
# 000001 前复权行情
df = ts.pro_bar(ts_code='000001.SZ', adj='qfq', 
                start_date='20180101', end_date='20181011')

# 上证指数行情
df = ts.pro_bar(ts_code='000001.SH', asset='I',
                start_date='20180101', end_date='20181011')

# 均线
df = ts.pro_bar(ts_code='000001.SZ', ma=[5,20,50],
                start_date='20180101', end_date='20181011')
```

---

## 2. A股日线行情 (daily)

**接口**: `daily`  
**更新时间**: 交易日 15:00-16:00  
**说明**: 未复权行情，停牌期间无数据

### 输入参数

| 名称 | 类型 | 必选 | 描述 |
|---|---|---|---|
| ts_code | str | N | 股票代码（支持多个，逗号分隔） |
| trade_date | str | N | 交易日期 (YYYYMMDD) |
| start_date | str | N | 开始日期 (YYYYMMDD) |
| end_date | str | N | 结束日期 (YYYYMMDD) |

### 输出参数

| 字段 | 类型 | 描述 |
|---|---|---|
| ts_code | str | 股票代码 |
| trade_date | str | 交易日期 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| pre_close | float | 昨收价（除权价） |
| change | float | 涨跌额 |
| pct_chg | float | 涨跌幅（%，基于除权昨收） |
| vol | float | 成交量（手） |
| amount | float | 成交额（千元） |

### 示例

```python
# 单个股票
df = pro.daily(ts_code='000001.SZ', 
               start_date='20180701', end_date='20180718')

# 多个股票
df = pro.daily(ts_code='000001.SZ,600000.SH',
               start_date='20180701', end_date='20180718')

# 单日全部股票
df = pro.daily(trade_date='20180810')
```

### 数据样例

```
 ts_code trade_date open  high   low  close pre_close change pct_chg        vol       amount
0 000001.SZ 20180718 8.75  8.85  8.69   8.70    8.72 -0.02   -0.23  525152.77  460697.377
1 000001.SZ 20180717 8.74  8.75  8.66   8.72    8.73 -0.01   -0.11  375356.33  326396.994
...
```

---

## 3. 分钟行情 (stk_mins)

**接口**: `stk_mins`  
**描述**: A股分钟数据，支持 HTTP RESTful API 和 Python SDK 两种方式调用  
**频度**: 1min / 5min / 15min / 30min / 60min  
**限量**: 单次最大 8000 行数据  
**历史**: 可提供超过 10 年历史分钟数据

### 输入参数

| 名称 | 类型 | 必选 | 描述 |
|---|---|---|---|
| ts_code | str | Y | 股票代码, e.g. 600000.SH |
| freq | str | Y | 分钟频度: 1min/5min/15min/30min/60min |
| start_date | datetime | N | 开始日期 (格式: YYYY-MM-DD HH:MM:SS) |
| end_date | datetime | N | 结束时间 (格式: YYYY-MM-DD HH:MM:SS) |

### 输出参数

| 字段 | 类型 | 描述 |
|---|---|---|
| ts_code | str | 股票代码 |
| trade_time | str | 交易时间 |
| open | float | 开盘价 |
| close | float | 收盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| vol | int | 成交量 (股) |
| amount | float | 成交金额 (元) |

### 示例

```python
# 获取浦发银行 600000.SH 的历史分钟数据
df = pro.stk_mins(
    ts_code='600000.SH', 
    freq='1min', 
    start_date='2023-08-25 09:00:00', 
    end_date='2023-08-25 19:00:00'
)
```

### 数据样例

```
 ts_code    trade_time         close  open  high   low       vol      amount
0 600000.SH 2023-08-25 15:00:00   7.05  7.05  7.05  7.05   235500.0   1660275.0
1 600000.SH 2023-08-25 14:59:00   7.05  7.05  7.05  7.05        0.0         0.0
...
240 600000.SH 2023-08-25 09:30:00  6.99  6.99  6.99  6.99   103700.0    724863.0
```

---

## 4. 周线行情 (weekly)

**接口**: `weekly`  
**更新时间**: 每周最后一个交易日  
**积分要求**: 至少 2000 积分

### 输入参数

| 名称 | 类型 | 必选 | 描述 |
|---|---|---|---|
| ts_code | str | N | TS代码 |
| trade_date | str | N | 交易日期（每周最后一个交易日，YYYYMMDD） |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

### 输出参数

| 字段 | 类型 | 描述 |
|---|---|---|
| ts_code | str | 股票代码 |
| trade_date | str | 交易日期 |
| close | float | 周收盘价 |
| open | float | 周开盘价 |
| high | float | 周最高价 |
| low | float | 周最低价 |
| pre_close | float | 上一周收盘价 |
| change | float | 周涨跌额 |
| pct_chg | float | 周涨跌（未复权，如需复权用pro_bar） |
| vol | float | 周成交量 |
| amount | float | 周成交额 |

### 示例

```python
df = pro.weekly(ts_code='000001.SZ', 
                start_date='20180101', end_date='20181101')
```

---

## 5. 月线行情 (monthly)

**接口**: `monthly`  
**更新时间**: 每月最后一个交易日  
**积分要求**: 至少 2000 积分

### 输入参数

| 名称 | 类型 | 必选 | 描述 |
|---|---|---|---|
| ts_code | str | N | TS代码 |
| trade_date | str | N | 交易日期（每月最后一个交易日，YYYYMMDD） |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

### 输出参数

| 字段 | 类型 | 描述 |
|---|---|---|
| ts_code | str | 股票代码 |
| trade_date | str | 交易日期 |
| close | float | 月收盘价 |
| open | float | 月开盘价 |
| high | float | 月最高价 |
| low | float | 月最低价 |
| pre_close | float | 上月收盘价 |
| change | float | 月涨跌额 |
| pct_chg | float | 月涨跌（未复权，如需复权用pro_bar） |
| vol | float | 月成交量 |
| amount | float | 月成交额 |

### 示例

```python
df = pro.monthly(ts_code='000001.SZ', 
                 start_date='20180101', end_date='20181101')
```

---

## 6. 复权行情 (pro_bar + adj)

**接口**: `pro_bar` (通用行情接口)  
**说明**: 复权行情基于复权因子动态计算，只支持日线复权  
**Python SDK要求**: >= 1.2.26

### 复权类型

| 类型 | 算法 | 参数标识 |
|---|---|---|
| 不复权 | 无 | 空或None |
| 前复权 | 当日收盘价 × 当日复权因子 / 最新复权因子 | qfq |
| 后复权 | 当日收盘价 × 当日复权因子 | hfq |

**注意**: Tushare 复权以 `end_date` 参数为基准向前复权，采用"分红再投"模式。

### 示例

```python
# 日线前复权
df = ts.pro_bar(ts_code='000001.SZ', adj='qfq',
                start_date='20180101', end_date='20181011')

# 日线后复权
df = ts.pro_bar(ts_code='000001.SZ', adj='hfq',
                start_date='20180101', end_date='20181011')

# 周线复权
df = ts.pro_bar(ts_code='000001.SZ', freq='W', adj='qfq',
                start_date='20180101', end_date='20181011')

# 月线复权
df = ts.pro_bar(ts_code='000001.SZ', freq='M', adj='hfq',
                start_date='20180101', end_date='20181011')
```

---

## 7. 复权因子 (adj_factor)

**接口**: `adj_factor`  
**更新时间**: 盘前 9:15-9:20 完成当日因子入库  
**积分要求**: 2000 积分起

### 输入参数

| 名称 | 类型 | 必选 | 描述 |
|---|---|---|---|
| ts_code | str | N | 股票代码 |
| trade_date | str | N | 交易日期 (YYYYMMDD) |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

### 输出参数

| 字段 | 类型 | 描述 |
|---|---|---|
| ts_code | str | 股票代码 |
| trade_date | str | 交易日期 |
| adj_factor | float | 复权因子 |

### 示例

```python
# 单只股票全部复权因子
df = pro.adj_factor(ts_code='000001.SZ')

# 单日全部股票复权因子
df = pro.adj_factor(trade_date='20180718')
```

---

## 8. 停复牌信息

**注**: 原文档链接返回 404，请访问 Tushare 官网查找最新接口或使用通用行情接口结合停牌状态字段。

---

## 9. 每日行情指标 (daily_basic)

**接口**: `daily_basic`  
**更新时间**: 交易日 15:00-17:00  
**积分要求**: 至少 2000 积分，5000 积分无总量限制  
**说明**: 获取每日重要基本面指标，用于选股分析等

### 输入参数

| 名称 | 类型 | 必选 | 描述 |
|---|---|---|---|
| ts_code | str | Y | 股票代码 (ts_code/trade_date 二选一) |
| trade_date | str | N | 交易日期 (二选一) |
| start_date | str | N | 开始日期 (YYYYMMDD) |
| end_date | str | N | 结束日期 (YYYYMMDD) |

### 输出参数

| 字段 | 类型 | 描述 |
|---|---|---|
| ts_code | str | TS股票代码 |
| trade_date | str | 交易日期 |
| close | float | 当日收盘价 |
| turnover_rate | float | 换手率（%） |
| turnover_rate_f | float | 换手率（自由流通股） |
| volume_ratio | float | 量比 |
| pe | float | 市盈率（总市值/净利润，亏损为空） |
| pe_ttm | float | 市盈率（TTM，亏损为空） |
| pb | float | 市净率（总市值/净资产） |
| ps | float | 市销率 |
| ps_ttm | float | 市销率（TTM） |
| dv_ratio | float | 股息率（%） |
| dv_ttm | float | 股息率（TTM）（%） |
| total_share | float | 总股本（万股） |
| float_share | float | 流通股本（万股） |
| free_share | float | 自由流通股本（万） |
| total_mv | float | 总市值（万元） |
| circ_mv | float | 流通市值（万元） |

### 示例

```python
df = pro.daily_basic(ts_code='', trade_date='20180726',
                     fields='ts_code,trade_date,turnover_rate,volume_ratio,pe,pb')
```

---

## 附录: 常用接口速查表

| 功能 | 接口 | 积分要求 | 复权支持 | HTTP支持 |
|---|---|---|---|---|
| 日线行情 | `daily` | 基础积分 | ❌ | ✅ |
| 分钟行情 | `stk_mins` | 需单独开权限 | ❌ | ✅ |
| 周线行情 | `weekly` | 2000+ | ❌ | ✅ |
| 月线行情 | `monthly` | 2000+ | ❌ | ✅ |
| 分钟行情 | `pro_bar` | 600+ | ❌ | ❌ |
| 复权行情 | `pro_bar` | 基础积分 | ✅ | ❌ |
| 复权因子 | `adj_factor` | 2000+ | N/A | ✅ |
| 每日指标 | `daily_basic` | 2000+ | N/A | ✅ |

---

**文档来源**: Tushare Pro 官方文档 (https://tushare.pro)
