# ScreenerContext.test.tsx

> **测试代码**：[`quant-trading-frontend/tests/context/ScreenerContext.test.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/context/ScreenerContext.test.tsx)
> **被测源码**：[`src/features/stock-picker/context/ScreenerContext.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/context/ScreenerContext.tsx)
> **用例数**：**16** | **覆盖率**：88.48% / 88.88% / 100%

---

## 模块职责

ScreenerContext 是整个 StockPicker 视图的状态中心。通过 `useReducer` 管理：
- `selectedMarket`：当前市场（`cn`/`hk`/`us`）
- `selectedBoards`：选中的板块
- `selectedMarketIndicators`：行情指标 + 范围（`Record<id, { min, max }>`）
- `selectedFinancialIndicators`：财务指标
- `selectedTechnicalIndicators`：技术指标（`Record<id, optionValue>`）
- `openTechnicalModal`：当前打开的技术指标 Modal id
- `collapsedPanels`：折叠面板状态
- `factorWeights`：因子权重

提供 actions：`TOGGLE_MARKET_INDICATOR` / `SET_MARKET_INDICATOR_RANGE` / `SET_FINANCIAL_INDICATOR` / `TOGGLE_FINANCIAL_INDICATOR` / `OPEN_TECHNICAL_MODAL` / `CLOSE_TECHNICAL_MODAL` / `SET_TECHNICAL_INDICATOR_OPTION` / `CLEAR_TECHNICAL_INDICATOR_OPTION` / `SET_MARKET` / `TOGGLE_PANEL` / `RESET_ALL`

---

## 测试用例清单

### 1. screenerReducer（11 用例）

#### TOGGLE_MARKET_INDICATOR（3 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 添加指标时同时初始化 range = { min: "", max: "" } | state 中含 `range: { min: '', max: '' }` |
| 2 | 再次点击同 id 移除指标并删除对应 range | 指标 + range 都从 state 删除 |
| 3 | 已存在 range 时保留旧值（不重置） | 覆盖 action 不重置 range |

#### SET_MARKET_INDICATOR_RANGE（2 用例）
| # | it 标题 |
|---|--------|
| 1 | 更新范围 |
| 2 | 覆盖已有 range（不合并） |

#### SET_MARKET（4 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 从 cn 切换到 cn：selectedBoards 重置为 ["all"]，所有指标清空 | |
| 2 | 切换到 hk（disabled 市场）：selectedBoards = []，所有指标清空 | |
| 3 | 切换到 us（disabled 市场）：selectedBoards = []，所有指标清空 | |
| 4 | 切换市场时保留 factorWeights | **重要** — factorWeights 不被清空 |

#### TOGGLE_PANEL（2 用例）
| # | it 标题 |
|---|--------|
| 1 | 切换后状态取反 |
| 2 | 只影响目标面板，不影响其他面板 |

#### RESET_ALL（1 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 重置所有状态到 initialState | |

#### Unknown action（1 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 返回原 state（不抛错） | reducer 兜底分支 |

### 2. ScreenerProvider / useScreener（5 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 在 Provider 外调用 useScreener 抛出明确错误 | 错误信息含 "useScreener must be used within a ScreenerProvider" |
| 2 | 在 Provider 内可正常获取 state 和 dispatch | `state.selectedMarket === 'cn'` |
| 3 | dispatch TOGGLE_MARKET_INDICATOR 后 state 变更 | 验证 dispatch 通路 |
| 4 | SET_MARKET 联动重置 selectedBoards/所有指标 | 集成验证 |
| 5 | RESET_ALL 恢复 initialState | |

---

## 关键 mock / helper

- **`renderHook`** + **`Wrapper`**：用 `renderHook` 测试 reducer 纯函数
- **`act`**：包裹 dispatch 调用
- **`vi.spyOn(console, 'error')`**：抑制 Provider 外调用 useScreener 时 React 的错误日志
- **无外部 mock**：纯 reducer 逻辑 + Provider 渲染

---

## 维护要点

- 新增 reducer action 时必须补一个 describe 块（即使是空用例也保留占位）
- `SET_MARKET` 联动逻辑（如 `selectedTechnicalIndicators` / `openTechnicalModal` 清空）必须**显式测试**，避免回归
- `SET_MARKET` 保留 `factorWeights` 的行为由 K 2026-06-04 决策，**不得修改**
- 88.48% 行覆盖率：未覆盖的是 `getInitialState` 在 module 加载时的静态字段初始化（无需测）

---

## 变更记录

- 2026-06-15：随 [6.4-INDICATOR-FILTER-20260615] 增加 `selectedTechnicalIndicators` 字段，配套更新 SET_MARKET 联动测试
- 2026-06-16：因 K 决定技术指标改"按钮+弹窗"模式，`SET_MARKET` 联动清空项增加 `openTechnicalModal: null`
