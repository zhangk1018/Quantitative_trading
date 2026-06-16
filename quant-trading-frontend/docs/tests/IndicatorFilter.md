# IndicatorFilter.test.tsx

> **测试代码**：[`quant-trading-frontend/tests/components/IndicatorFilter.test.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/IndicatorFilter.test.tsx)
> **被测源码**：[`src/features/stock-picker/components/IndicatorFilter.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/IndicatorFilter.tsx)
> **用例数**：**16** | **覆盖率**：100% / 82.75% / 100%

---

## 模块职责

行情指标筛选组件，提供：
- 折叠面板（默认折叠）
- 9 个行情指标按钮（`market_cap`/`price`/`change_pct`/`pe_static`/`pe_ttm`/`pb`/`volume_ratio`/`amount`/`volume`/`turnover`）
- 多选 + 每个指标独立 min/max 范围输入
- badge 计数（"X/9"）
- 清除按钮（min 或 max 非空时显示）

---

## 测试用例清单

### 1. 基础渲染（3 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 渲染 header 文本和 badge | "行情指标" + badge 初始 0 |
| 2 | 默认折叠状态下不渲染指标按钮 | `queryByTestId('indicator-btn-*')` 全部为 null |
| 3 | 默认折叠状态下显示空状态提示 | "点击上方按钮添加筛选条件" |

### 2. 折叠面板交互（2 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 点击 header 展开面板，显示所有指标按钮 | 9 个按钮全可见 |
| 2 | 展开后看到空状态提示（未选中任何指标） | "点击上方按钮添加筛选条件" |

### 3. 指标按钮交互（3 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 点击按钮切换为选中（data-selected=true） | `data-selected` 切换 |
| 2 | 再次点击取消选中 | 再次点击 toggle 关闭 |
| 3 | 同时选中多个指标时，badge 显示总数 | `badge.textContent === '3'` |

### 4. 范围输入（4 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 选中指标后显示该指标的 min/max 输入框 | 展开后 `data-testid="indicator-min-{id}"` 出现 |
| 2 | 同时选中多个指标时各自 range 区独立 | 2 个 range 区块互不干扰 |
| 3 | 输入 min 值后，state 同步变化 | `inspector.textContent` 包含 min 值 |
| 4 | 输入 min 和 max 后，state 完整同步 | min + max 同时写入 |

### 5. 清除按钮（3 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 初始状态下清除按钮不显示（min 和 max 都为空） | |
| 2 | 只输入 min 后清除按钮显示 | |
| 3 | 点击清除按钮后 min/max 重置为空 | min + max 都置 `''` |

### 6. disabled 状态（1 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | disabled 指标按钮不可点击 | `disabled === true` |

---

## 关键 mock / helper

- **`renderFilter()`**（顶层）：`render(<ScreenerProvider><IndicatorFilter /><StateInspector /></ScreenerProvider>)`
- **`expandPanel(user)`**：点击 `data-testid="indicator-filter-header"`
- **`StateInspector`**：`<div>{JSON.stringify(state)}</div>`，暴露 state 用于断言
- **顶层 `beforeEach`**：清理 `MARKET_INDICATORS` 残留 `disabled` 字段，防止 describe 块间污染

---

## 维护要点

- Antd InputNumber + `fireEvent.change` 兼容性：用 `fireEvent.change(input, { target: { value: '100' }})` 触发
- 单位换算：行情指标中"亿元/万元"等单位在 `StockPickerView.test.tsx` 集成层验证，本组件**不验证**单位换算
- `MARKET_INDICATORS` 数组是**模块级常量**，vitest 默认 module isolation 保证跨 test file 不污染

---

## 变更记录

- 2026-06-15：初始版本（16 用例），K 一次性 review 通过
- 2026-06-15：[6.4-INDICATOR-FILTER-20260615] CLOSED 后归档
