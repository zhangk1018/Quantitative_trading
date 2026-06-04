# 代码质量指南

本文档总结了项目开发过程中的最佳实践和经验规则，旨在提升代码质量、稳定性和可维护性。

---

## 一、数据处理规范

### 1.1 数据校验（三重校验机制）

项目采用三重校验机制确保数据质量，参考 `src/processor/data_quality_checker.py`：

| 校验阶段 | 执行时机 | 校验内容 | 实现位置 |
|----------|----------|----------|----------|
| **第一重：采集后校验** | 数据拉取后立即执行 | 数据源连通性、字段完整性、数据非空 | `DataQualityChecker.check_data_source_connectivity()` |
| **第二重：入库前校验** | 数据写入数据库前 | OHLC合理性、成交量非负、价格范围、重复数据 | `DataQualityChecker.check_before_insert()` |
| **第三重：入库后校验** | 数据写入数据库后 | 数据完整性、一致性、统计指标 | `DataQualityChecker.check_after_insert()` |

**校验规则（参考 config.py validation 配置）：**

```yaml
validation:
  price_min: 0.01              # 价格最小值
  price_max: 999999.99         # 价格最大值
  volume_min: 0                # 成交量最小值
  volume_negative_action: drop # 成交量为负时的处理方式
  ohlc_check: true             # 开启 OHLC 校验（high >= max(open,close), low <= min(open,close))
  volume_check: true           # 开启成交量校验
  price_range_check: true      # 开启价格范围校验
  duplicate_check: true        # 开启重复数据校验
```

**使用示例：**

```python
from processor.data_quality_checker import DataQualityChecker

checker = DataQualityChecker()

# 第一重校验：采集后
result = checker.check_data_source_connectivity(df, 'baostock')
if result['status'] == 'error':
    logger.error(f"数据源校验失败: {result['message']}")
    return None

# 第二重校验：入库前
result = checker.check_before_insert(df)
if result['status'] == 'error':
    logger.error(f"入库前校验失败: {result['message']}")
    df = checker.clean_data(df)  # 自动清洗数据

# 第三重校验：入库后
result = checker.check_after_insert(code, cycle, start_date, end_date)
if result['status'] == 'warning':
    logger.warning(f"入库后校验警告: {result['message']}")
```

### 1.2 时间处理规范

**问题：分钟线时间精度丢失**

常见错误：
```python
# ❌ 错误：仅解析日期，丢失时分秒
result['trade_time'] = pd.to_datetime(df['trade_date'])

# ❌ 错误：NaN 转为 "nan" 导致解析失败
time_str = df['time'].astype(str)  # NaN 变成 "nan"
```

正确做法：
```python
# ✅ 正确：安全组合 date 与 time 列
if 'time' in df.columns and 'date' in df.columns:
    date_str = df['date'].astype(str).replace('nan', pd.NaT)
    time_str = df['time'].astype(str).replace('nan', pd.NaT)
    result['trade_time'] = pd.to_datetime(date_str + ' ' + time_str, errors='coerce')

# ✅ 正确：过滤解析失败的脏数据
result = result.dropna(subset=['trade_time'])
```

### 1.3 空值处理规范

**原则：提前过滤，减少内存复制**

```python
# ❌ 错误：先复制全量数据再过滤，浪费内存
result = df.copy()
result = result.dropna(subset=['close'])

# ✅ 正确：提前过滤，减少内存占用
df = df.dropna(subset=['close']).copy()
if df.empty:
    return df
result = df
```

---

## 二、数据库操作规范

### 2.1 批量写入规范

**问题：SQL 模板与列数不匹配**

常见错误：
```python
# ❌ 错误：自定义 template 导致列数不一致
write_cols = ['code', 'cycle', ..., 'adjust_type']  # 12列
sql = "INSERT INTO ... (..., created_at) VALUES %s"  # 13列
execute_values(cur, sql, values, template="%s, CURRENT_TIMESTAMP")  # 危险！
```

正确做法：
```python
# ✅ 正确：列数严格对齐，使用默认模板
write_cols = ['code', 'cycle', ..., 'adjust_type', 'created_at']  # 13列
sql = f"INSERT INTO {table} ({', '.join(write_cols)}) VALUES %s"  # 13列
execute_values(cur, sql, batch, page_size=1000)  # 使用默认模板 "(%s, %s, ...)"
```

**空值处理：**
```python
# ✅ 正确：向量化替换 NaN/Inf -> None
df_write = df[write_cols].copy()
df_write = df_write.replace({np.nan: None, np.inf: None, -np.inf: None, pd.NaT: None})
values = df_write.values.tolist()
```

### 2.2 连接管理规范

**原则：使用上下文管理器，自动关闭连接**

```python
# ❌ 错误：手动获取 cursor，可能忘记关闭
cursor = self.storage.conn.cursor()
cursor.execute(...)
row = cursor.fetchone()
return row[0] if row and row[0] else None

# ✅ 正确：使用 with 自动关闭
with self.storage.conn.cursor() as cursor:
    cursor.execute(...)
    row = cursor.fetchone()
return row[0] if row and row[0] else None
```

### 2.3 唯一索引依赖

**重要：ON CONFLICT 依赖唯一索引**

执行批量写入前，必须确认唯一索引存在：
```sql
-- sql/create_indexes.sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_quotes_minute_unique 
ON stock_quotes_minute (code, cycle, trade_date, trade_time);

CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_indicators_unique 
ON stock_indicators (code, cycle, trade_date, trade_time);
```

---

## 三、异常处理规范

### 3.1 错误分类机制

项目使用 `ErrorClassifier` 区分可重试与不可重试错误：

| 错误类型 | 分类 | 处理策略 |
|----------|------|----------|
| 网络超时、连接拒绝 | 可重试 | 自动重试（最多3次） |
| 限流（429）、服务端忙（503） | 可重试 | 增加延迟后重试 |
| 服务端错误（5xx） | 可重试 | 等待后重试 |
| 数据格式错误、参数错误 | 不可重试 | 记录日志，跳过 |
| 股票代码不存在 | 不可重试 | 记录日志，跳过 |

**使用示例：**

```python
from utils.error_classifier import ErrorClassifier, ErrorType

classifier = ErrorClassifier()

try:
    df = datasource.get_kline(...)
except Exception as e:
    error_type, should_retry = classifier.classify(e)
    
    if error_type == ErrorType.RETRYABLE and retry_count < max_retries:
        logger.warning(f"可重试错误: {e}, 第 {retry_count + 1} 次重试")
        time.sleep(retry_delay)
        retry_count += 1
        continue  # 重试
    else:
        logger.error(f"不可重试错误: {e}, 跳过该股票")
        failed_stocks.append({'code': code, 'error': str(e), 'type': error_type})
        break  # 跳过
```

### 3.2 重试机制规范

**配置参数（config.py）：**

```yaml
data_source:
  max_retries: 3      # 最大重试次数
  timeout_sec: 30     # 超时时间
  delay_sec: 0.3      # 默认延迟
```

**实现原则：**
1. 网络超时：立即重试
2. 限流错误：延迟加倍（0.3s → 0.6s → 1.2s）
3. 服务端错误：固定延迟（1s）
4. 重试失败：记录详细上下文（股票代码、周期、日期、错误栈）

---

## 四、增量导入规范

### 4.1 时间精度优化

**问题：增量导入重复拉取当天数据**

常见错误：
```python
# ❌ 错误：仅使用日期作为起点，重复拉取当天数据
last_time = get_last_trade_time(code, cycle)  # 2026-01-15 14:30:00
actual_start_date = last_time.strftime('%Y-%m-%d')  # 2026-01-15
# 会拉取 2026-01-15 全天数据，重复 14:30 之前的数据
```

正确做法：
```python
# ✅ 正确：使用 last_time + 1分钟 作为起点
last_time = get_last_trade_time(code, cycle)  # 2026-01-15 14:30:00
actual_start_datetime = last_time + timedelta(minutes=1)  # 2026-01-15 14:31:00
actual_start_date = actual_start_datetime.strftime('%Y-%m-%d')  # 2026-01-15
# 拉取后过滤：df = df[df['trade_time'] > last_time]
```

### 4.2 数据库层面过滤（优化方向）

**当前：拉取后过滤（内存浪费）**
```python
df = fetch_minute_data(code, cycle, start_date, end_date)
df = df[df['trade_time'] > last_time]  # 内存中过滤
```

**优化：数据库层面过滤**
```python
# TODO: 改为数据库层面过滤
df = fetch_minute_data_with_filter(code, cycle, last_time, end_date)
# SQL: WHERE trade_time > %s AND trade_time <= %s
```

---

## 五、配置管理规范

### 5.1 配置外置化

**原则：所有硬编码参数统一放到配置文件**

```yaml
# config/pipeline.yaml
minute_data:
  batch_days: 10           # 分批拉取天数
  max_batch_size: 5000     # 批量写入批次大小
  default_cycles: ['5m', '15m', '30m', '60m']
  api_delay: 0.3           # API 调用延迟

indicators:
  ma_windows: [5, 10, 20, 60]
  rsi_windows: [6, 12, 24]
  macd_span: [12, 26, 9]
  max_batch_size: 5000
```

**代码中从配置读取：**
```python
from utils.config import config

batch_days = config.minute_data.get('batch_days', 10)
ma_windows = config.indicators.get('ma_windows', [5, 10, 20, 60])
```

### 5.2 环境区分（扩展方向）

**建议：支持多环境配置**

```yaml
# config/pipeline.dev.yaml   # 开发环境
# config/pipeline.prod.yaml  # 生产环境

# 加载逻辑：
env = os.environ.get('APP_ENV', 'dev')
config_path = f"config/pipeline.{env}.yaml"
config = load_config(config_path)
```

---

## 六、代码复用规范

### 6.1 基类设计

**原则：公共逻辑抽离到基类**

`BaseDataImporter` 基类提供：
- 数据库连接管理（惰性初始化、上下文管理器）
- 任务进度管理（create_task、update_task_progress）
- 股票代码校验（validate_stock_code、_format_code）
- 日期校验（validate_date、validate_date_range）
- 周期校验（validate_cycles）
- 批量写入（batch_write_to_db）

**子类只需实现业务逻辑：**
```python
class MinuteDataImporter(BaseDataImporter):
    def import_stock_data(self, code: str, start_date: str, end_date: str) -> int:
        # 实现具体导入逻辑
        pass
```

### 6.2 DRY原则（Don't Repeat Yourself）

**避免重复代码：**
```python
# ❌ 错误：两个脚本重复实现批量写入
def write_to_db_batch(self, df):
    # 100+ 行重复代码

# ✅ 正确：使用基类方法
inserted = self.batch_write_to_db(df, 'stock_quotes_minute', write_cols, update_cols)
```

---

## 七、日志规范

### 7.1 日志分级

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| **DEBUG** | 调试信息、批次详情 | `分批拉取: {code} {cycle} {batch_start}~{batch_end}` |
| **INFO** | 流程节点、完成状态 | `导入完成: {code} {cycle} - {inserted} 条` |
| **WARNING** | 可恢复异常、数据质量警告 | `过滤无效股票代码: {invalid_codes}` |
| **ERROR** | 不可恢复异常、失败记录 | `导入失败: {code} - {e}` |

### 7.2 日志内容规范

**关键步骤记录入参和出参：**
```python
logger.info(f"开始导入: {len(codes)} 只股票, 周期: {cycles}, 日期: {start_date}~{end_date}")
logger.info(f"导入完成: 成功 {success_count}, 失败 {fail_count}, 总记录 {total_records}")
```

**失败日志包含唯一标识：**
```python
logger.error(f"导入失败: {code} {cycle} {start_date}~{end_date} - {e}")
failed_stocks.append({
    'code': code,
    'cycle': cycle,
    'date': start_date,
    'error': str(e),
    'stack_trace': traceback.format_exc()
})
```

---

## 八、性能优化规范

### 8.1 向量化操作

**原则：优先使用 Pandas 向量化操作，避免循环**

```python
# ❌ 错误：逐行处理
for i in range(len(df)):
    df.loc[i, 'vwap'] = df.loc[i, 'amount'] / df.loc[i, 'volume']

# ✅ 正确：向量化操作
mask = df['volume'] > 0
df['vwap'] = np.nan
df.loc[mask, 'vwap'] = (df.loc[mask, 'amount'] / df.loc[mask, 'volume']).round(4)
```

### 8.2 RSI 极值处理

**问题：使用 .loc 赋值触发 Pandas 警告**

```python
# ❌ 错误：触发 SettingWithCopyWarning
rsi.loc[avg_loss == 0] = 100

# ✅ 正确：使用 .where() 向量化赋值
rsi = rsi.where(avg_loss > 0, 100.0)
rsi = rsi.where(avg_gain > 0, 0.0)
```

---

## 九、测试与监控规范

### 9.1 可测试性设计

**原则：关键函数设计为纯函数**

```python
# ✅ 正确：纯函数，便于单元测试
def calculate_rsi_wilder(series: pd.Series, window: int) -> pd.Series:
    """计算 RSI（Wilder算法）
    
    Args:
        series: 收盘价序列
        window: 窗口大小
        
    Returns:
        RSI 序列（0-100）
    """
    # 无副作用，输入输出明确
    ...

# ❌ 错误：有副作用，难以测试
def calculate_indicators(self, df):
    self.storage.conn.execute(...)  # 数据库操作
    ...
```

### 9.2 边界测试场景

必须覆盖以下极端场景：
- 空数据（df is None 或 df.empty）
- 日期跨月/跨年
- 股票代码格式异常
- 数据长度不足（如 MA60 需要 60 条数据）
- 价格/成交量为负
- 时间解析失败

---

## 十、命令行参数规范

### 10.1 参数校验

**所有输入参数必须校验：**

```python
# 日期格式校验
if args.start:
    try:
        BaseDataImporter.validate_date(args.start)
    except ValueError as e:
        logger.error(f"参数错误: {e}")
        return

# 日期范围校验
if args.start and args.end:
    try:
        BaseDataImporter.validate_date_range(args.start, args.end)
    except ValueError as e:
        logger.error(f"参数错误: {e}")
        return

# 数值校验
if args.delay is not None and args.delay < 0:
    logger.error(f"参数错误: delay 不能为负数: {args.delay}")
    return
```

### 10.2 帮助信息规范

**动态显示默认值：**
```python
parser.add_argument('--cycle', type=str, 
                   help=f'周期（逗号分隔，默认 {",".join(config.minute_data.default_cycles)}）')
```

---

## 附录：快速参考

### A. 常见错误与修复

| 错误类型 | 错误示例 | 正确做法 |
|----------|----------|----------|
| 时间精度丢失 | `pd.to_datetime(df['trade_date'])` | 组合 date + time 列 |
| SQL列数不匹配 | 自定义 template | 列数严格对齐，默认模板 |
| 连接泄漏 | 手动 cursor | 使用 with 上下文管理器 |
| 内存浪费 | 先 copy 再过滤 | 提前过滤再 copy |
| RSI警告 | `.loc[]` 赋值 | 使用 `.where()` |
| 增量重复 | 仅用日期起点 | last_time + 1分钟 |

### B. 配置文件模板

```yaml
# config/pipeline.yaml
data_source:
  name: baostock
  delay_sec: 0.3
  max_retries: 3
  timeout_sec: 30

minute_data:
  batch_days: 10
  max_batch_size: 5000
  default_cycles: ['5m', '15m', '30m', '60m']
  api_delay: 0.3

indicators:
  ma_windows: [5, 10, 20, 60]
  rsi_windows: [6, 12, 24]
  macd_span: [12, 26, 9]
  max_batch_size: 5000

validation:
  price_min: 0.01
  price_max: 999999.99
  volume_min: 0
  ohlc_check: true
  volume_check: true
  price_range_check: true
  duplicate_check: true

logging:
  level: INFO
  format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
```

### C. 代码审查 Checklist

每次代码提交前，检查以下维度：

| 维度 | 审查内容 |
|------|----------|
| **逻辑正确性** | 算法实现、边界条件、信号时机、数据计算公式 |
| **安全性** | SQL注入、路径遍历、敏感信息暴露、权限控制 |
| **性能** | 批量操作、索引使用、循环优化、缓存策略 |
| **健壮性** | 异常处理、空值处理、类型转换、超时控制 |
| **可维护性** | 注释完备性、命名规范性、代码重复度、模块耦合度 |
| **合规性** | 表结构一致、API调用限制、数据范围规定 |

---

**文档版本：v1.0**  
**更新日期：2026-05-31**  
**维护者：Quantitative Trading Team**