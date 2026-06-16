# indicatorConfig.test.ts

> **测试代码**：[`quant-trading-frontend/tests/config/indicatorConfig.test.ts`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/config/indicatorConfig.test.ts)
> **被测源码**：[`src/features/stock-picker/config/indicatorConfig.ts`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/config/indicatorConfig.ts)
> **用例数**：**17** | **覆盖率**：100% / 100% / 100%

---

## 模块职责

锁定 4 个核心配置表（`MARKET_INDICATORS` / `FINANCIAL_INDICATORS` / `TECHNICAL_INDICATORS` / `FACTOR_CONFIG`）的硬约束，防止后续修改破坏结构。

- `MARKET_INDICATORS`：行情指标（`market_cap`/`price`/`change_pct`/`pe`/`pe_ttm`/`pb`/`volume_ratio`/`amount`/`volume`/`market_cap`）
- `FINANCIAL_INDICATORS`：财务指标（`revenue`/`net_profit`/`roe`）
- `TECHNICAL_INDICATORS`：技术指标（4 个**配置型**指标 `ma`/`macd`/`boll`/`rsi`，含 `options[]` 数组）
- `FACTOR_CONFIG`：因子权重（3 个因子权重和=100）

---

## 测试用例清单

### 1. MARKET_INDICATORS（5 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 包含行情指标基础字段 | `length > 0` + 5 字段齐备（id/label/field/unit?/disabled?） |
| 2 | id 唯一 | `new Set(ids).size === ids.length` |
| 3 | label 唯一 | 同上 |
| 4 | field 不为空（行情指标都映射到后端字段） | `field !== null` |
| 5 | 必含核心指标：市值/价格/换手率 | `ids.includes('market_cap'/'price'/'turnover')` |

### 2. FINANCIAL_INDICATORS（3 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 包含财务指标基础字段 | `length > 0` + 字段齐备 |
| 2 | id 唯一 | |
| 3 | label 唯一 | |

### 3. TECHNICAL_INDICATORS（2 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 包含技术指标基础字段 | `length > 0` |
| 2 | field 为 null（技术指标由配置面板单独管理，无单一后端字段） | `field === null` |
| 3 | id 唯一 | |

### 4. FACTOR_CONFIG（5 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 权重和为 100 | `reduce((s, f) => s + f.defaultWeight) === 100` |
| 2 | 每个因子有 id/label/defaultWeight/color 字段 | `hasProperty` |
| 3 | color 是有效的 6 位 hex 值 | `/^#[0-9A-Fa-f]{6}$/` |
| 4 | id 唯一 | |
| 5 | defaultWeight 在 0-100 之间 | `0 ≤ w ≤ 100` |

### 5. IndicatorItem 接口（1 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | disabled 字段可选（默认 undefined） | 遍历全表，disabled 可不存在 |

---

## 关键 mock / helper

- **无 mock / 无 helper**：纯静态配置校验，0 依赖
- 直接 `import { MARKET_INDICATORS, ... } from '@/features/stock-picker/config/indicatorConfig'` 后断言

---

## 维护要点

- 任何新指标加入 `TECHNICAL_INDICATORS` 数组，需在 [TechnicalFilter.md](./TechnicalFilter.md) "新增指标" 章节同步
- 任何修改 `FACTOR_CONFIG` 权重总和，必须保证 `defaultWeight` 之和=100，否则**测试 1 失败**
- `disabled` 字段是**可选**的，不要移除该字段定义

---

## 变更记录

- 2026-06-16：因 K 调整技术指标配置结构（取消"自定义"，改用 `options[]` 固定 Radio），更新 `TECHNICAL_INDICATORS` 注释（"field 为 null" 含义变更为"由配置面板单独管理"）
