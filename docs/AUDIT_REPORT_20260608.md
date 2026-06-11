# 代码审查报告 — PLANNING_REVIEW_2026Q2 vs 当前实现

**审查日期**：2026-06-08  
**审查范围**：全量（数据采集 / 清洗 / 补全 / API / 数据契约）  
**审查基线**：`docs/PLANNING_REVIEW_2026Q2.md`  
**代码版本**：当前工作区代码

---

## 📊 总体一致性评估

**评分：6.5 / 10**

当前代码实现了设计文档中约 70% 的核心功能，数据管道（采集→清洗→快照→API）基本贯通，但存在多处关键偏差：`create_dsm()` 工厂函数的数据源优先级与设计相反，`import_by_trade_date` 批量导入路径绕过了限流和容灾机制，复权因子表尚未创建导致 Adjuster 完全失效。已修复的 `AUDIT-001` 7 项问题已闭环，但新增偏差表明代码走查和设计同步仍需加强。

---

## ✅ 完美契合的部分

| 模块 | 亮点说明 |
|------|----------|
| **Tushare 数据源限流** | `tushare.py` 的 `RateLimiter`（令牌桶）实现正确，各 API 类型独立限流，配置合理 |
| **DataSourceManager 容灾模式** | `base.py` 的 failover/round-robin/weighted 三种策略实现完整，健康检查 + 自动恢复机制到位 |
| **信号预计算** | `signal_precompute.py` 逻辑清晰（金叉死叉/RSI超买超卖/BOLL突破），字段匹配 `trade_signals` 表 |
| **日线导入（单线程路径）** | `import_daily_data.py` 使用 DataSourceManager（Tushare 主 → Baostock 备），增量断点续传逻辑完善 |
| **K线 API 路由** | `kline.py` 参数校验完备（日期/股票代码/周期），接口返回格式与 `KLineResponse` schema 对齐 |
| **宽表同步（PE 修复后）** | `daily_snapshot_sync.py` 和 `batch_sync.py` 均已添加 `stock_daily_basic` JOIN，PE/PB 字段填充正确 |
| **前端 K线买卖点标注** | 自定义 `tradeMarker` 覆盖物 + Tooltip + 副图切换，按设计交付 |
| **数据契约 `shared/`** | `schemas.py` / `constants.py` 与 `backend` 兼容层稳定，字段一致性检查通过 |

---

## ⚠️ 偏差与缺失项

### 🔴 高严重度

| 模块/功能 | 设计要求 | 当前代码实现 | 偏差类型 | 严重程度 |
|-----------|----------|--------------|----------|----------|
| `create_dsm()` 工厂函数 — 数据源优先级 | Tushare 为主数据源（priority=0），Baostock 为备用（priority=1） | `base.py:599-604` 将 Baostock 设为主（priority=0），Tushare 不在列表内 | **不一致** | **高** |
| `import_by_trade_date()` — 限流与容灾 | 所有 Tushare API 调用须经 `RateLimiter` 和 `DataSourceManager` 统一管理 | `import_daily_data.py:52-58` 直接 `TushareDataSource()` → `tushare._pro.daily()`，绕过 `_wait_for_rate_limit()` 和 failover | **遗漏/不一致** | **高** |
| `stock_adj_factor` 复权因子表 | 表已设计，需从 Tushare 拉取全市场复权因子 | **表不存在** → `Adjuster.load_adj_factors()`（`imputer/adjuster.py:60`）查询会抛异常，复权功能完全不可用 | **遗漏** | **高** |
| 复权处理端到端 | 前端 adj 参数 `forward/backward` 应正常工作 | `kline_service.py:115-121` 调用 Adjuster → 因无表总是失败 → 降级为 `warning: 复权处理失败`，但用户仍选 forward 时实际返回的是原始价格 | **遗漏** | **高** |

### 🟡 中严重度

| 模块/功能 | 设计要求 | 当前代码实现 | 偏差类型 | 严重程度 |
|-----------|----------|--------------|----------|----------|
| `daily_snapshot_sync.py` — 日志规范 | 统一使用 `logger` 模块记录日志 | 多处使用 `print()`（如 `print(f"✅ {target_date} 宽表同步完成")`），违背日志规范 | **不一致** | **中** |
| `batch_sync.py` — 日志规范 | 同上 | 同上，使用 `print()` | **不一致** | **中** |
| `kline_service.py` — Mock 代码 | K线服务应从 `stock_quotes` 读真实数据，不应保留 Mock | `_generate_mock_kline()` 仍存在于 `kline_service.py:51-73`，作为 DB 空时的兜底 | **过度设计** | **中** |
| `stock_basic.industry` 补齐 | industry 覆盖率应 ≥ 95%（设计 A-2 任务） | 当前 `41.77% NULL`（设计文档 1.1 节已记录，但无修复代码） | **遗漏** | **中** |
| `sync_checkpoints` 表 | 同步水位线表应有记录 | 设计文档显示记录数为 0，未启用水位线管理 | **遗漏** | **中** |
| `data_error_log` 表 | 采集失败应落库记录 | 记录数为 0，采集失败未落库 | **遗漏** | **中** |

### 🟢 低严重度

| 模块/功能 | 设计要求 | 当前代码实现 | 偏差类型 | 严重程度 |
|-----------|----------|--------------|----------|----------|
| `frontend/src/mocks/` | 开发期 Mock 数据应在联调后清理 | `meta.ts`、`stocks.ts`、`index.ts` 仍存在 | **过度设计** | **低** |
| `imputer/missing_handler.py` — `interpolate` 使用 | 实盘应警惕使用 `interpolate`（设计 1.3 节） | 仍有 `interpolate` 调用点 | **不一致** | **低** |
| `miss_fill_volume_gaps()` — 停牌日填充 | 停牌日应为"无成交"，不应填 0 | 设计 1.3 节指出写死 0 填充的问题 | **不一致** | **低** |

---

## 💡 改进与修复建议

### 🔴 高优先级修复

#### 1. `base.py:create_dsm()` 数据源优先级修正

**修改**：[`/Users/zhangk/workspace/Quantitative_trading/backend/collector/datasource/base.py`](file:///Users/zhangk/workspace/Quantitative_trading/backend/collector/datasource/base.py#L593-L604)

将 Tushare 设为主数据源（priority=0），Baostock 降为备用：

```python
def create_dsm(...) -> DataSourceManager:
    from collector.datasource.tushare import TushareDataSource
    from collector.datasource.baostock import BaostockDataSource
    from collector.datasource.akshare import AkshareDataSource
    from collector.datasource.sina import SinaDataSource
    from collector.datasource.tencent import TencentDataSource
    
    sources = [
        {'source': TushareDataSource(), 'weight': 3, 'priority': 0},    # 主: Tushare
        {'source': BaostockDataSource(), 'weight': 2, 'priority': 1},    # 备用1: Baostock
        {'source': AkshareDataSource(), 'weight': 1, 'priority': 2},     # 备用2: Akshare
        {'source': TencentDataSource(), 'weight': 1, 'priority': 3},     # 备用3
        {'source': SinaDataSource(), 'weight': 1, 'priority': 4}         # 备用4
    ]
    ...
```

#### 2. `import_by_trade_date()` 增加限流和容灾

**修改**：[`/Users/zhangk/workspace/Quantitative_trading/backend/collector/etl/import_daily_data.py`](file:///Users/zhangk/workspace/Quantitative_trading/backend/collector/etl/import_daily_data.py#L39-L86)

弃用 `tushare._pro.daily()` 直接调用模式，改用 `DataSourceManager` 统一管理：

```python
def import_by_trade_date(self, trade_date: str):
    # 使用 DataSourceManager（已有 Tushare primary + Baostock backup + rate limit）
    try:
        df = self.datasource_manager.get_kline(
            code='',  # 空代码表示全市场
            cycle='daily',
            start_date=trade_date,
            end_date=trade_date
        )
    except Exception as e:
        logger.error(f"批量导入失败: {e}")
        return 0, 1, 0
```

或保持当前路径但在 `TushareDataSource` 中增加一个 `batch_get_daily(trade_date)` 方法，内部调用 `_wait_for_rate_limit()`：

```python
def batch_get_daily(self, trade_date: str) -> pd.DataFrame:
    """批量获取指定日期全市场日线数据（带限流）"""
    self._wait_for_rate_limit('daily')
    ts_date = trade_date.replace('-', '')
    df = self._pro.daily(
        trade_date=ts_date,
        fields='ts_code,trade_date,open,high,low,close,pre_close,vol,amount'
    )
    return df
```

#### 3. 创建 `stock_adj_factor` 表 + 数据填充

这是 Phase C 的前置条件。参考 `sync_daily_basic.py` 的模式，新增 [`sync_adj_factor.py`](file:///Users/zhangk/workspace/Quantitative_trading/backend/collector/etl/sync_adj_factor.py)（已存在但可能有配置文件问题，之前已修复 `user`→`username`）。

**DDL**：
```sql
CREATE TABLE IF NOT EXISTS stock_adj_factor (
    stock_code VARCHAR(32) NOT NULL,
    trade_date DATE NOT NULL,
    adj_factor NUMERIC(16, 4) NOT NULL DEFAULT 1.0,
    PRIMARY KEY (stock_code, trade_date)
);
```

按日期遍历策略（Tushare `adj_factor` 限频 1次/分钟，按日期批量获取全市场），每天仅需 1 次 API 调用。

### 🟡 中优先级修复

#### 4. 替换 `print()` → `logger.info()`

涉及文件：
- [`daily_snapshot_sync.py`](file:///Users/zhangk/workspace/Quantitative_trading/backend/collector/etl/daily_snapshot_sync.py) — 所有 `print()` 替换
- [`batch_sync.py`](file:///Users/zhangk/workspace/Quantitative_trading/backend/collector/etl/batch_sync.py) — 所有 `print()` 替换

#### 5. Industry 补齐任务（Phase A-2）

新增脚本或用 SQL 从 Tushare `stock_basic` 表更新：
```sql
UPDATE stock_basic b
SET industry = t.industry
FROM tushare_stock_basic t
WHERE b.code = t.code AND b.industry IS NULL;
```

#### 6. 水位线管理启用

- `sync_checkpoints` 表已有设计但未使用
- 建议在每次 ETL 成功后在 `sync_checkpoints` 插入水位线记录

#### 7. Mock 数据清理

- 联调确认前后端已对接后，清理 `frontend/src/mocks/` 目录
- 或加环境变量控制（`USE_MOCK=true/false`）

---

## 🚨 潜在风险预警

| 风险 | 触发条件 | 可能后果 | 建议缓解 |
|------|----------|----------|----------|
| **Tushare API 限频触发 429** | `import_by_trade_date()` 批量导入时高频调用 `_pro.daily()`（无限流） | API 被封 IP 或 token，当天数据采集失败→QoS 降级 | 立即修复限流失控路径，切换到 `get_kline()` 路径 |
| **复权功能静默错误** | 用户请求 `adj=forward` 时，Adjuster 因无 `stock_adj_factor` 表抛异常→catch 后返回原始价格 | 前端展示未复权 K 线，回测结果偏差大，用户无感知 | 在 API 层面校验 `stock_adj_factor` 表是否存在，不存在则返回 400 错误（"复权因子未就绪"） |
| **`create_dsm()` 被意外调用** | 新增模块调用 `create_dsm()` 而非直接用 `import_daily_data.py` 中的正确配置 | Baostock 成为主数据源，Tushare 备用（违背设计） | 修复 `create_dsm()` 优先级，同时标记为 `@deprecated`，推荐使用带参构造 |
| **Mock 数据泄漏到生产** | 后端 DB 连接失败→`_generate_mock_kline()` 返回伪造数据 | 前端展示虚假 K 线，交易决策基于假数据 | 生产环境应直接报错而非降级到 mock |
| **行业数据长期为 NULL** | 前端选股器按行业筛选时 | 行业筛选功能不完整，用户体验差 | 安排 Phase A-2 任务，设定完工期限 |
| **采集失败无告警日志** | `data_error_log` 表为空 | 运维无法发现采集链路问题，问题积累到用户投诉 | 采集失败时写入 `data_error_log`，配合 `health_monitor.py` 触发告警 |

---

## 总结

> 当前代码已实现设计文档中约 70% 的功能，但存在 **3 项高严重度偏差**（数据源优先级、限流路径绕过、复权表缺失），后两项直接违反用户明确指定的"Tushare 优先 + 限频"要求。已修复的 AUDIT-001 7 项问题验证通过。建议立即处理 3 项高优先级修复，随后按 Phase A→B→C 顺序推进剩余任务。