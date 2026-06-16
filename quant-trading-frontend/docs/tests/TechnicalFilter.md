# TechnicalFilter.test.tsx

> **测试代码**：[`quant-trading-frontend/tests/components/TechnicalFilter.test.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/TechnicalFilter.test.tsx)
> **被测源码**：
> - [`src/features/stock-picker/components/TechnicalFilter.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/TechnicalFilter.tsx)
> - [`src/features/stock-picker/components/TechnicalIndicatorModal.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/TechnicalIndicatorModal.tsx)
> **用例数**：**27** | **覆盖率**：100% / 95% / 100%

---

## 模块职责

技术指标筛选组件（K 2026-06-16 决定风格：**按钮 + 弹窗 + Radio**，取消"自定义"选项），提供：
- 折叠面板（默认折叠）
- 4 个技术指标按钮（`ma`/`macd`/`boll`/`rsi`）
- **点击按钮 → 打开弹窗**（非 toggle）
- 弹窗内 14 个固定 Radio option（K 决定取消"自定义"）
- 弹窗"取消" / "确定" / "清除已选"三按钮
- "确定"按钮在未选 Radio 时 disabled
- 弹窗回显已选 option
- 切换市场时关闭打开中的弹窗
- 紧凑风格：Modal width=400（<520，整面积缩小 50%+）

---

## 测试用例清单

### 1. TechnicalFilter 主体（24 用例）

#### 1.1 基础渲染（2 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 渲染 header 文本和 badge（初始 0） | "技术指标" + badge=0 |
| 2 | 默认折叠状态下不渲染指标按钮 | 4 个 btn 全部不存在 |

#### 1.2 折叠面板交互（1 用例）
| # | it 标题 |
|---|--------|
| 1 | 点击 header 展开后，4 个指标按钮（MA/MACD/BOLL/RSI）都可见 |

#### 1.3 指标按钮交互（点击打开弹窗）（4 用例）
| # | it 标题 |
|---|--------|
| 1 | 点击 ma 按钮打开 "MA·日K" 弹窗 |
| 2 | 点击 macd 按钮打开 "MACD·日K" 弹窗 |
| 3 | 点击 boll 按钮打开 "BOLL·日K" 弹窗 |
| 4 | 点击 rsi 按钮打开 "RSI·日K" 弹窗 |

> 4 个测试用 `it.each` 模板生成，data-testid: `technical-btn-{id}`

#### 1.4 弹窗 → 选 Radio → 确定 → 写入 state（4 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | ma 弹窗选 long_align（多头排列）并确定后，state 写入对应 option | `readState() === { ma: 'long_align' }` |
| 2 | macd 弹窗选 bottom_divergence（底背离）并确定后，state 写入 | |
| 3 | boll 弹窗选 break_upper（升穿上轨）并确定后，state 写入 | |
| 4 | rsi 弹窗选 low_golden_cross（低位金叉）并确定后，state 写入 | |

#### 1.5 弹窗 → 取消场景（2 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 选 Radio 后点取消，state 保持空 | 取消不写入 |
| 2 | **打开弹窗后直接取消（无任何选择）state 保持空** | 中 5 边界 |

#### 1.6 再次打开弹窗回显（2 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 已选 MA 后再次打开弹窗，Radio 回显已选项 | `input[value=long_align].checked === true` |
| 2 | **BOLL 已选 break_middle_up 后再次打开，显示"当前已选：升穿中轨"** | 高 4 — BOLL 特有意图文本 |

#### 1.7 清除已选（2 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 已选后再次打开点击"清除已选"，state 清空，弹窗保持打开 | 弹窗不关闭 |
| 2 | **清除已选后，确定按钮重新 disabled** | 高 3 — tempOption 跟随 currentOption 同步 |

#### 1.8 更改已有选项（1 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | **MA 已选多头排列后改为空头排列，state 从 long_align 变为 short_align，badge 仍为 1** | 高 2 + 中 8 合并 |

#### 1.9 同时选中多个技术指标（1 用例）
| # | it 标题 |
|---|--------|
| 1 | MA + RSI 各选一个，state 含 2 个条目，badge=2 |

#### 1.10 切换市场（2 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 切换市场后已选技术指标全部清空 | |
| 2 | **切换市场时关闭打开中的弹窗** | 中 7 |

#### 1.11 确定按钮启用/禁用（2 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 弹窗刚打开时"确定"按钮 disabled | |
| 2 | **点击 radio 后"确定"按钮变为 enabled** | 中 6 |

#### 1.12 禁用指标（1 用例）
| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | **disabled 指标按钮不可点击，且不打开弹窗** | 低 12 — `button.disabled === true` |

### 2. TechnicalIndicatorModal 单独测试（3 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | **未传 onClear 时，已选 option 的弹窗不显示"清除已选"按钮** | 高 1 修正 |
| 2 | 未传 onClear 时，无 currentOption 的弹窗不显示"当前已选"区域 | onClear 缺省联动 |
| 3 | 传 onClear 时，点击"清除已选"调用 onClear 回调 | `vi.fn()` 验证回调触发 |

---

## 关键 mock / helper

### 测试 helper（顶层）

- **`StateInspector`**：`<div data-testid="state-technical">{JSON.stringify(state.selectedTechnicalIndicators)}</div>`
- **`readState()`**：`JSON.parse(inspector.textContent || '{}')` — 低 13 严格 JSON 解析避免子串误匹配
- **`renderFilter()`**：`render(<ScreenerProvider><TechnicalFilter /><StateInspector /></ScreenerProvider>)`
- **`expandPanel(user)`**：点击 `data-testid="technical-filter-header"`
- **`openModal(user, id)`**：点击 `data-testid="technical-btn-{id}"` + `findByTestId('technical-modal-{id}')`
- **`closeModal(user, id)`**：点击 `cancel` + waitFor modal 消失
- **`selectAndConfirm(user, id, option)`**：点 radio → 点 confirm → waitFor modal 消失
- **`MarketSwitcher`**：dispatch `SET_MARKET` action 触发市场切换

### data-testid 速查

| 元素 | data-testid 模板 |
|------|------------------|
| 指标按钮 | `technical-btn-{id}` + `data-selected` + `data-option` |
| 折叠面板容器 | `technical-filter-collapse` |
| 折叠面板头部 | `technical-filter-header` |
| 徽标 | `technical-filter-badge` |
| 弹窗容器 | `technical-modal-{id}` |
| 弹窗 Radio | `technical-modal-{id}-option-{value}` |
| 弹窗"已选"区域 | `technical-modal-{id}-selected` |
| 弹窗"取消"按钮 | `technical-modal-{id}-cancel` |
| 弹窗"确定"按钮 | `technical-modal-{id}-confirm` |
| 弹窗"清除已选"按钮 | `technical-modal-{id}-clear` |

---

## 维护要点

### 测试容易踩的坑

1. **`screen.getByText('多头排列')` 失败**：Radio label 文本和"当前已选"区域都有"多头排列"，必须用 `data-testid="technical-modal-{id}-selected"` 容器精确定位
2. **连续打开 3 个 Modal 超时**：A10b 集成测试，连续 open/close 3 个弹窗 > 5s，coverage 模式更慢 — 解决方案：`vi.setConfig({ testTimeout: 15000 })` 加在测试文件顶部
3. **vitest module isolation**：`TECHNICAL_INDICATORS` 是模块级常量，跨 test file 不会污染，但同文件内 `beforeEach` 仍需清理 disabled 残留

### Modal 交互要点

- `maskClosable={false}`：点击遮罩不关闭弹窗（K 决策避免误操作）
- `destroyOnClose` + `destroyOnHidden` warning：Antd 5.x 的 deprecation，不影响功能
- 弹窗内部 `useEffect` 同步 `tempOption` 到 `currentOption`：确保"清除已选"后 confirm 重新 disabled

---

## 变更记录

- 2026-06-16：初始版本（K 决定"按钮+弹窗+Radio"风格 + 取消"自定义"）
  - 4 个指标（ma/macd/boll/rsi）+ 14 个 option
  - 紧凑 Modal width=400（<520）
  - 通用 TechnicalIndicatorModal 组件
- 2026-06-16：K 13 条 review 建议（高 1-4 / 中 5-9 / 低 10-13）整改：19 → 27 用例
  - 高 1：修正矛盾测试（未传 onClear 单独测试）
  - 高 2 + 中 8：合并"MA 改选项 + badge 仍为 1"测试
  - 高 3：补"清除后 confirm 重新 disabled"
  - 高 4：补 BOLL "当前已选：升穿中轨"文案
  - 中 5/6/7：补"直接取消无变化" / "radio 后 confirm 启用" / "切换市场关弹窗"
  - 低 10/13：提取 helpers + state 用 `readState() + toEqual({...})` 严格比较
  - 副带：TechnicalIndicatorModal 单独 3 边界测试 + `testTimeout: 15000`
