# FinancialFilter.test.tsx

> **测试代码**：[`quant-trading-frontend/tests/components/FinancialFilter.test.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/FinancialFilter.test.tsx)
> **被测源码**：[`src/features/stock-picker/components/FinancialFilter.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/FinancialFilter.tsx)
> **用例数**：**29** | **覆盖率**：100% / 91.17% / 100%

---

## 模块职责

财务指标筛选组件，提供：
- 折叠面板（默认折叠）
- 3 个财务指标按钮（`net_profit`/`revenue`/`roe`）
- 多选 + 每个指标独立 min/max 范围输入
- 范围条件区标签渲染（"指标名(单位)"）
- 负数输入支持（财务指标可为负数，如净利润亏损）
- `min > max` 时**前端不校验**，仅传参
- badge 计数
- disabled 状态 + `disabledReason` Tooltip 提示
- 与 ScreenerContext 市场切换联动（清空）

---

## 测试用例清单

### 1. 基础渲染（3 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 渲染 header 文本和 badge | "财务指标" + badge 初始 0 |
| 2 | 默认折叠状态下不渲染指标按钮 | |
| 3 | 默认折叠状态下不显示空状态提示 | 与 IndicatorFilter 行为不同 |

### 2. 折叠面板交互（2 用例）

| # | it 标题 |
|---|--------|
| 1 | 点击 header 展开面板，显示所有指标按钮 |
| 2 | 展开后看到空状态提示（未选中任何指标） |

### 3. 指标按钮交互（4 用例）

| # | it 标题 |
|---|--------|
| 1 | 点击按钮切换为选中（data-selected=true） |
| 2 | 再次点击取消选中 |
| 3 | 同时选中多个指标时，badge 显示总数 |
| 4 | 选中指标后空状态提示消失，范围条件区显示 |

### 4. 范围条件区标签渲染（1 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 选中指标后范围区显示 "指标名(单位)" 标签 | 例如 "净利润(元)" |

### 5. 范围输入（7 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 选中指标后显示该指标的 min/max 输入框 | |
| 2 | 同时选中多个指标时各自 range 区独立 | |
| 3 | 输入 min 值后，state 同步变化 | |
| 4 | 输入 min 和 max 后，state 完整同步 | |
| 5 | 取消选中指标后 range 状态被清空 | 取消 → range 同步从 state 删除 |
| 6 | 支持负数输入（财务指标可负，如净利润亏损） | 输入 `-1000000` 不报错 |
| 7 | min > max 时不自动纠正，前端只负责传参不校验 | 故意 `min=10, max=5` 验证不纠正 |

### 6. 清除按钮（5 用例）

| # | it 标题 |
|---|--------|
| 1 | 初始状态下清除按钮不显示（min 和 max 都为空） |
| 2 | 只输入 min 后清除按钮显示 |
| 3 | 只输入 max 后清除按钮也显示 |
| 4 | 同时输入 min 和 max 时清除按钮存在 |
| 5 | 点击清除按钮后 min/max 重置为空 |

### 7. disabled 状态（4 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | disabled 指标按钮不可点击 | `disabled === true` |
| 2 | disabled 指标不打开 range 区 | 选不中 → 不渲染 range |
| 3 | disabled 指标显示 Tooltip disabledReason | 鼠标悬停显示原因 |
| 4 | 切换市场后 disabled 状态保留 | market switch 不清 disabled |

### 8. 与 ScreenerContext 市场切换联动（2 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 切换市场后已选财务指标全部清空 | state.financialIndicators = {} |
| 2 | 切换市场后 badge 重置为 0 | |

---

## 关键 mock / helper

- **`renderFilter({ stateInspectorId })`**：渲染整个组件，StateInspector 只跟踪指定 id 的财务指标
- **`MarketSwitcher`**（helper 组件）：dispatch `SET_MARKET` action 触发市场切换
- **`selectIndicatorAndWaitForRange(user, id)`**：选指标后 waitFor range 区出现
- **顶层 `beforeEach`**：清理 `FINANCIAL_INDICATORS` 残留 `disabled/disabledReason` 字段

---

## 维护要点

- 财务指标**可负数**这一特性必须保留（净利润亏损场景）
- `min > max` 不纠正 — 故意保留给后端校验，前端职责单一（只负责传参）
- Tooltip 包装 disabled 按钮：使用 Antd `Tooltip` + `disabled` button pattern，注意 Tooltip target 是 button
- `disabled` 数组修改在 vitest module isolation 下不会跨 test file 污染，但仍需 `beforeEach` 兜底

---

## 变更记录

- 2026-06-15：初始版本（17 用例）
- 2026-06-15：K 1st review（8 条建议）→ 24 用例
- 2026-06-15：K 2nd review（5 条建议）→ 29 用例
  - 重点补：负数输入、min>max 不纠正、清除按钮 4 子用例、disabled + Tooltip 测试、市场切换联动 2 用例
- 2026-06-15：[6.4-INDICATOR-FILTER-20260615] 中被 K 视为"指标筛选"范本
