# 项目规则文档

## 1. 测试用例管理规则

### 1.1 测试目录结构
```
backend/
├── tests/                    # 正式测试用例目录（永久保存）
│   ├── test_cycle_synthesis.py   # 周线/月线合成测试
│   ├── test_kline_service.py     # K线服务测试
│   ├── test_datasource.py        # 数据源测试
│   └── conftest.py               # pytest配置
├── temp/                     # 临时测试目录（定期清理）
│   ├── test_script_xxx.py        # 临时测试脚本
│   ├── debug_data.csv            # 临时调试数据
│   └── .gitignore                # 忽略所有文件
```

### 1.2 测试用例规范
- **位置**：正式测试用例必须放在 `tests/` 目录下
- **命名**：文件名以 `test_` 开头，类名以 `Test` 开头，方法名以 `test_` 开头
- **内容**：测试用例应覆盖核心业务逻辑，确保修改后功能符合预期
- **运行**：使用 `pytest tests/` 运行所有测试

### 1.3 临时文件规范
- **位置**：临时测试脚本、调试数据放在 `temp/` 目录下
- **清理**：周末定时清理 `temp/` 目录（可通过 cron 或 CI 脚本执行）
- **提交**：`temp/` 目录下的文件不应提交到版本控制（已添加到 .gitignore）

---

## 2. 数据合成规则

### 2.1 周线合成规则
```
周线 = {
    trade_date: 当周最后一个交易日（通常为周五）
    open: 当周第一个交易日开盘价
    high: 当周最高价
    low: 当周最低价
    close: 当周最后一个交易日收盘价
    volume: 当周成交量总和
    amount: 当周成交额总和
    is_weekend: 是否为周五（dayofweek == 4）
}
```

### 2.2 月线合成规则
```
月线 = {
    trade_date: 当月最后一个交易日
    open: 当月第一个交易日开盘价
    high: 当月最高价
    low: 当月最低价
    close: 当月最后一个交易日收盘价
    volume: 当月成交量总和
    amount: 当月成交额总和
    is_month_end: 是否为自然月末
}
```

### 2.3 数据源限流规则
| 接口 | 频率限制 | 说明 |
|------|---------|------|
| daily | 200次/分钟 | Tushare日线接口 |
| weekly | 1次/分钟 | Tushare周线接口 |
| monthly | 1次/小时 | Tushare月线接口 |
| min5/min15/min30/min60 | 30次/分钟 | Tushare分钟线接口 |

---

## 3. 代码规范

### 3.1 命名规范
- 文件名：全小写，用下划线分隔（如 `cycle_synthesis.py`）
- 类名：大驼峰命名（如 `CycleSynthesizer`）
- 方法名：小写，用下划线分隔（如 `synthesize_weekly`）
- 变量名：小写，用下划线分隔（如 `trade_date`）

### 3.2 日志规范
- 使用 `logging` 模块，设置合适的日志级别
- 关键操作记录 INFO 级别日志
- 调试信息记录 DEBUG 级别日志
- 错误信息记录 ERROR 级别日志

### 3.3 异常处理
- 所有外部调用（API、数据库）必须有 try-except 包裹
- 异常信息应包含上下文（如股票代码、时间范围）
- 避免静默失败，至少记录错误日志

---

## 4. 数据库规范

### 4.1 表结构规范
```sql
stock_quotes (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) NOT NULL,      -- 股票代码
    cycle VARCHAR(10) NOT NULL,     -- 周期：1d/1w/1m
    trade_date DATE NOT NULL,       -- 交易日期
    open DECIMAL(10,2),             -- 开盘价
    high DECIMAL(10,2),             -- 最高价
    low DECIMAL(10,2),              -- 最低价
    close DECIMAL(10,2),            -- 收盘价
    pre_close DECIMAL(10,2),        -- 前收盘价
    volume BIGINT,                  -- 成交量（股）
    amount DECIMAL(18,2),           -- 成交额（元）
    adjust_type VARCHAR(10),        -- 复权类型
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)

-- 索引
CREATE INDEX idx_stock_quotes_code_cycle ON stock_quotes(code, cycle);
CREATE INDEX idx_stock_quotes_trade_date ON stock_quotes(trade_date);
```

### 4.2 数据导入规范
- 导入前验证数据格式正确性
- 导入过程记录详细日志
- 导入完成后输出总结报告
- 失败时记录失败原因，支持断点续传

---

## 5. API 规范

### 5.1 接口命名规范
- 使用 RESTful 风格
- 路径使用小写，用连字符分隔（如 `/api/kline/{stock_code}`）
- 参数使用 snake_case（如 `trade_date`）

### 5.2 响应格式规范
```json
{
    "stock_code": "000001",
    "data": [...],
    "count": 100,
    "status": "success"
}
```

### 5.3 错误响应规范
```json
{
    "error": "Stock not found",
    "code": 404,
    "message": "股票代码不存在"
}
```

---

## 6. 定时任务规则

### 6.1 数据更新任务
- **日线更新**：每天收盘后执行（约 15:30）
- **周线合成**：每周五收盘后执行
- **月线合成**：每月最后一个交易日收盘后执行
- **临时文件清理**：每周日凌晨执行

### 6.2 日志归档任务
- 日志按日期归档
- 保留最近 30 天的日志
- 过期日志自动压缩备份

---

## 7. 版本控制规则

### 7.1 分支策略
- `main`：主分支，稳定版本
- `develop`：开发分支，功能开发
- `feature/*`：特性分支，单个功能开发
- `hotfix/*`：热修复分支，紧急修复

### 7.2 提交规范
- 使用 Conventional Commits 格式
- 提交信息清晰描述变更内容
- 每个提交只包含一个逻辑变更

示例：
```
feat: 添加周线/月线合成功能
fix: 修复周期参数传递错误
docs: 更新项目规则文档
test: 添加周线合成测试用例
```
