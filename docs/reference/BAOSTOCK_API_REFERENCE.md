# BaoStock Python API 摘要

> **重要参考文档**: https://www.baostock.com/mainContent?file=pythonAPI.md
>
> **创建日期**: 2026-05-30

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
| `fields` | 返回字段 | 多指标用逗号分隔 |
| `start_date` | 开始日期 | `YYYY-MM-DD`，空则取2015-01-01 |
| `end_date` | 结束日期 | `YYYY-MM-DD`，空则取最近交易日 |
| `frequency` | K线周期 | `d`(日线), `w`(周线), `m`(月线), `5`(5分钟), `15`, `30`, `60` |
| `adjustflag` | 复权类型 | `3`(不复权), `2`(前复权), `1`(后复权) |

### 2.2 字段规范（日线 vs 分钟线）

**日线字段**（含停牌证券）：
```
date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST
```

**分钟线字段**（不包含指数）：
```
date,time,code,open,high,low,close,volume,amount,adjustflag
```

### 2.3 分钟线时间格式

分钟线返回的 `time` 字段格式为：`YYYYMMDDHHMMSSsss`
- 示例：`20260506093500000` 表示 `2026-05-06 09:35:00.000`

### 2.4 使用示例

**日线获取**：
```python
rs = bs.query_history_k_data_plus(
    code="sh.600000",
    fields="date,code,open,high,low,close,volume,amount,adjustflag",
    start_date='2024-07-01',
    end_date='2024-12-31',
    frequency="d",
    adjustflag="3"
)
```

**分钟线获取**：
```python
rs = bs.query_history_k_data_plus(
    code="sh.600000",
    fields="date,time,code,open,high,low,close,volume,amount,adjustflag",
    start_date='2024-07-01',
    end_date='2024-12-31',
    frequency="5",  # 5分钟; 15/30/60同理
    adjustflag="3"
)
```

### 2.5 注意事项

1. **指数没有分钟线数据**
2. **停牌日处理**：日线中停牌日 open/high/low/close 相同且等于前一交易日收盘价，volume/amount 为 0
3. **复权说明**：使用"涨跌幅复权算法"，与其他系统可能不一致
4. **周/月线**：仅在每周/每月最后一个交易日可获取

---

## 3. 股票基本资料 (query_stock_basic)

```python
rs = bs.query_stock_basic(code="sh.600000")
```

返回字段：code, code_name, ipoDate, outDate, stock_id, type, status

---

## 4. 交易日查询 (query_trade_dates)

```python
rs = bs.query_trade_dates(start_date='2024-01-01', end_date='2024-12-31')
```

返回字段：calendarDate, isOpen, exchange

---

## 5. 全部股票查询 (query_all_stock)

```python
rs = bs.query_all_stock(day='2024-12-31')
```

返回字段：code, code_name, changeDate, status

---

## 6. 除权除息信息 (query_dividend_data)

```python
rs = bs.query_dividend_data(code="sh.600000", year="2024", yearType="report")
```

参数：
- `year`: 年份
- `yearType`: `report`(报告期) 或 `random`(预案公告日期)

---

## 7. 复权因子 (query_adjust_factor)

```python
rs = bs.query_adjust_factor(code="sh.600000", start_date='2024-01-01', end_date='2024-12-31')
```

---

## 8. 季度财务数据

| 方法 | 说明 |
|------|------|
| `query_profit_data()` | 季频盈利能力 |
| `query_operation_data()` | 季频营运能力 |
| `query_growth_data()` | 季频成长能力 |
| `query_balance_data()` | 季频偿债能力 |
| `query_cash_flow_data()` | 季频现金流量 |
| `query_dupont_data()` | 季频杜邦指数 |

---

## 9. 板块数据

| 方法 | 说明 |
|------|------|
| `query_stock_industry()` | 行业分类 |
| `query_sz50_stocks()` | 上证50成分股 |
| `query_hs300_stocks()` | 沪深300成分股 |
| `query_zz500_stocks()` | 中证500成分股 |

---

## 10. 数据质量注意事项

1. **重复索引问题**：`rs.get_data()` 可能返回带重复索引的 DataFrame，务必在操作前调用 `reset_index(drop=True)`
2. **空值处理**：停牌日或无数据时字段可能为空字符串，需用 `pd.to_numeric(x, errors='coerce')` 转换
3. **换手率转换**：`result["turn"] = [0 if x == "" else float(x) for x in result["turn"]]`
4. **连接维护**：频繁调用时需定期检查连接状态，断开时自动重连

---

## 11. 代码模板

### 获取分钟线数据（标准写法）

```python
import baostock as bs
import pandas as pd

def get_minute_data(code, frequency='5', start_date=None, end_date=None):
    """获取分钟线数据"""
    lg = bs.login()
    if lg.error_code != '0':
        raise RuntimeError(f"登录失败: {lg.error_msg}")

    try:
        rs = bs.query_history_k_data_plus(
            code=code,  # 格式: sh.600000 或 sz.000001
            fields="date,time,code,open,high,low,close,volume,amount,adjustflag",
            start_date=start_date or '2015-01-01',
            end_date=end_date or bs.query_trade_dates().get_data().iloc[-1]['calendarDate'],
            frequency=frequency,  # '5', '15', '30', '60'
            adjustflag="3"  # 不复权
        )

        if rs.error_code != '0':
            raise RuntimeError(f"查询失败: {rs.error_msg}")

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())
        result = pd.DataFrame(data_list, columns=rs.fields)

        # 关键：重置索引避免重复标签问题
        result = result.reset_index(drop=True)

        return result

    finally:
        bs.logout()
```

---

## 12. 周期映射表

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

## 13. 错误代码参考

| error_code | 说明 |
|------------|------|
| `0` | 成功 |
| `1000` | 用户未登录/登录失效 |
| 其他 | 详见 error_msg |

---

**最后更新**: 2026-05-30
