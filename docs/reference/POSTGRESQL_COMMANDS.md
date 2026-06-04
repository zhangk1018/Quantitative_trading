# PostgreSQL 数据库操作命令手册

## 一、数据库连接

### 连接到数据库
```bash
# 连接到量化交易数据库
psql -h localhost -p 5432 -d quant_trading -U quant_user

# 如果密码在环境变量中
PGPASSWORD=your_password psql -h localhost -p 5432 -d quant_trading -U quant_user
```

### 常用连接参数
| 参数 | 说明 | 示例值 |
|------|------|--------|
| -h | 主机地址 | localhost |
| -p | 端口号 | 5432 |
| -d | 数据库名 | quant_trading |
| -U | 用户名 | quant_user |

---

## 二、数据库结构

### 查看所有表
```sql
-- 查看数据库中所有表
\dt

-- 查看表详细信息
\d stock_basic
\d stock_quotes
```

### 表结构概览

#### 1. stock_basic（股票基本信息表）
| 字段 | 类型 | 说明 |
|------|------|------|
| code | VARCHAR(10) | 股票代码（主键） |
| name | VARCHAR(50) | 股票名称 |
| exchange | VARCHAR(20) | 交易所 |
| industry | VARCHAR(100) | 行业 |
| list_date | DATE | 上市日期 |
| delist_date | DATE | 退市日期 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### 2. stock_quotes（行情数据表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL | 主键 |
| code | VARCHAR(10) | 股票代码 |
| cycle | VARCHAR(10) | 周期（1d/daily/min5等） |
| trade_date | DATE | 交易日期 |
| open | NUMERIC(10,2) | 开盘价 |
| high | NUMERIC(10,2) | 最高价 |
| low | NUMERIC(10,2) | 最低价 |
| close | NUMERIC(10,2) | 收盘价 |
| pre_close | NUMERIC(10,2) | 昨收盘价 |
| volume | BIGINT | 成交量 |
| amount | NUMERIC(18,2) | 成交额 |
| adjust_type | VARCHAR(10) | 复权类型 |
| created_at | TIMESTAMP | 创建时间 |

# 查看某只股票（如 000001）的最新10条记录
psql -h localhost -U quant_user -d quant_trading -c "SELECT * FROM stock_quotes WHERE code = '000001' ORDER BY trade_date DESC LIMIT 10;"
---

## 三、数据查询

### 股票基本信息查询

```sql
-- 查询所有股票数量
SELECT COUNT(*) FROM stock_basic;

-- 查询前10只股票
SELECT code, name, industry, list_date FROM stock_basic LIMIT 10;

-- 查询特定行业的股票
SELECT code, name FROM stock_basic WHERE industry = '金融';

-- 查询上市日期范围
SELECT code, name, list_date 
FROM stock_basic 
WHERE list_date BETWEEN '2020-01-01' AND '2021-01-01';
```

### 行情数据查询

```sql
-- 查询某只股票的日线数据
SELECT trade_date, open, high, low, close, pre_close, volume 
FROM stock_quotes 
WHERE code = '600000' AND cycle = '1d' 
ORDER BY trade_date DESC LIMIT 20;

-- 查询多只股票的最新行情
SELECT code, trade_date, close, pre_close, 
       ROUND((close - pre_close)/pre_close * 100, 2) AS pct_change
FROM stock_quotes 
WHERE cycle = '1d' 
AND trade_date = (SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d')
ORDER BY pct_change DESC;

-- 查询成交量排行
SELECT code, SUM(volume) AS total_volume
FROM stock_quotes 
WHERE cycle = '1d' 
AND trade_date >= '2024-01-01'
GROUP BY code
ORDER BY total_volume DESC LIMIT 10;
```

### 技术指标查询

```sql
-- 查询股票的技术指标
SELECT trade_date, ma5, ma10, ma20, macd, rsi6, rsi12
FROM stock_indicators 
WHERE code = '600000' AND cycle = '1d'
ORDER BY trade_date DESC LIMIT 20;
```

---

## 四、数据统计与分析

### 统计分析

```sql
-- 统计各行业股票数量
SELECT industry, COUNT(*) AS count
FROM stock_basic 
GROUP BY industry 
ORDER BY count DESC;

-- 计算平均每日成交量
SELECT AVG(volume) AS avg_volume, 
       MAX(volume) AS max_volume, 
       MIN(volume) AS min_volume
FROM stock_quotes 
WHERE code = '600000' AND cycle = '1d';

-- 计算涨跌幅统计
WITH daily_changes AS (
    SELECT code, trade_date,
           ROUND((close - pre_close)/pre_close * 100, 2) AS pct_change
    FROM stock_quotes 
    WHERE cycle = '1d' AND pre_close > 0
)
SELECT code,
       AVG(pct_change) AS avg_change,
       MAX(pct_change) AS max_up,
       MIN(pct_change) AS max_down,
       COUNT(*) AS trading_days
FROM daily_changes
GROUP BY code
ORDER BY avg_change DESC LIMIT 10;
```

---

## 五、数据导入与导出

### 导出数据

```sql
-- 导出股票列表到CSV
COPY (SELECT * FROM stock_basic) 
TO '/path/to/stock_basic.csv' 
WITH (FORMAT csv, HEADER, ENCODING 'UTF8');

-- 导出某只股票的行情数据
COPY (
    SELECT trade_date, open, high, low, close, volume
    FROM stock_quotes 
    WHERE code = '600000' AND cycle = '1d'
    ORDER BY trade_date
) TO '/path/to/600000_quotes.csv' 
WITH (FORMAT csv, HEADER, ENCODING 'UTF8');
```

### 导入数据

```sql
-- 从CSV导入股票基本信息
COPY stock_basic(code, name, exchange, industry, list_date)
FROM '/path/to/stock_basic.csv' 
WITH (FORMAT csv, HEADER, ENCODING 'UTF8');
```

---

## 六、索引管理

### 查看索引
```sql
-- 查看表的索引
\d stock_quotes

-- 查看所有索引
SELECT tablename, indexname FROM pg_indexes WHERE tablename = 'stock_quotes';
```

### 创建索引
```sql
-- 创建行情表的复合索引
CREATE INDEX IF NOT EXISTS idx_stock_quotes_code_cycle ON stock_quotes(code, cycle);
CREATE INDEX IF NOT EXISTS idx_stock_quotes_trade_date ON stock_quotes(trade_date);
```

---

## 七、常用管理命令

### 数据库状态
```sql
-- 查看数据库大小
SELECT pg_size_pretty(pg_database_size('quant_trading'));

-- 查看表大小
SELECT pg_size_pretty(pg_total_relation_size('stock_quotes'));
```

### 事务操作
```sql
-- 开始事务
BEGIN;

-- 执行操作
UPDATE stock_basic SET industry = '金融' WHERE code = '600000';

-- 提交事务
COMMIT;

-- 回滚事务
ROLLBACK;
```

### 备份与恢复

```bash
# 备份数据库
pg_dump -h localhost -p 5432 -U quant_user -d quant_trading > backup.sql

# 恢复数据库
psql -h localhost -p 5432 -U quant_user -d quant_trading < backup.sql

# 压缩备份
pg_dump -h localhost -p 5432 -U quant_user -d quant_trading | gzip > backup.sql.gz

# 恢复压缩备份
gunzip -c backup.sql.gz | psql -h localhost -p 5432 -U quant_user -d quant_trading
```

---

## 八、实用查询示例

### 示例1：查询涨停股票
```sql
SELECT code, name, close, pre_close,
       ROUND((close - pre_close)/pre_close * 100, 2) AS pct_change
FROM stock_quotes sq
JOIN stock_basic sb ON sq.code = sb.code
WHERE cycle = '1d'
  AND trade_date = (SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d')
  AND close >= pre_close * 1.1
ORDER BY pct_change DESC;
```

### 示例2：查询连续上涨股票
```sql
WITH daily_data AS (
    SELECT code, trade_date, close,
           LAG(close) OVER (PARTITION BY code ORDER BY trade_date) AS prev_close
    FROM stock_quotes 
    WHERE cycle = '1d'
),
up_days AS (
    SELECT code, trade_date,
           CASE WHEN close > prev_close THEN 1 ELSE 0 END AS is_up,
           SUM(CASE WHEN close > prev_close THEN 1 ELSE 0 END) 
               OVER (PARTITION BY code ORDER BY trade_date 
                     ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS consecutive_up
    FROM daily_data
)
SELECT DISTINCT code 
FROM up_days 
WHERE consecutive_up = 5
  AND trade_date >= '2024-01-01';
```

---

## 九、注意事项

1. **时区设置**：确保数据库时区与应用一致
   ```sql
   SHOW timezone;
   SET timezone = 'Asia/Shanghai';
   ```

2. **数据类型**：注意 NUMERIC 类型的精度设置，避免数据溢出

3. **性能优化**：
   - 对常用查询字段创建索引
   - 使用 LIMIT 限制返回数据量
   - 避免在大表上执行全表扫描

4. **数据一致性**：
   - stock_basic 和 stock_quotes 的 code 字段格式需保持一致
   - 使用事务确保数据完整性
