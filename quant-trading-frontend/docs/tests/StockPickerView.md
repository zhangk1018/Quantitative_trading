# StockPickerView.test.tsx

> **测试代码**：[`quant-trading-frontend/tests/views/StockPickerView.test.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/views/StockPickerView.test.tsx)
> **被测源码**：[`src/features/stock-picker/StockPickerView.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/StockPickerView.tsx)
> **用例数**：**13** | **覆盖率**：视图层（未配置 v8 范围）

---

## 模块职责

StockPicker 视图是整个**选股交互**的容器。集成测试覆盖：
- 行情指标 + 范围 → URL 参数映射
- **行情字段单位换算**：`market_cap` ×10000（亿→万）、`amount` ×10000（亿→万）
- **技术指标 → URL 参数**：`tech_ma=long_align` / `tech_rsi=low_golden_cross` 等 14 个 pattern
- loading → 成功 → 表格渲染
- 重置按钮联动

---

## 测试用例清单

### 1. A10: runScreening 参数映射（5 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 未传任何筛选条件时请求参数不带 listed_board / *_min / *_max | URL 仅含默认 limit/sort |
| 2 | 单选一个行情指标 + 设置范围后，URL 包含 *_min 和 *_max | |
| 3 | 多个行情指标 range 全部正确序列化 | market_cap ×10000、volume 不换算 |
| 4 | 单位换算验证：market_cap 50 亿元 → 500000 万元 | ×10000 转换 |
| 5 | 选满 indicator 全部 range | 全 9 个指标序列化 |

### 2. A10b: 技术指标 URL 序列化（3 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 选中 1 个技术指标（MA）后，URL 包含 `tech_ma=<option>` | |
| 2 | 选中多个技术指标（MA + RSI + BOLL）后，URL 包含 `tech_*=*` | 未选 MACD 不出现 |
| 3 | 未选任何技术指标时，URL 不包含 `tech_*` | |

> **测试时间预算**：3 个 A10b 测试连续打开/关闭 3 个 Modal + 等待 runScreening，**默认 5s 超时不够**，已在测试文件顶部加 `vi.setConfig({ testTimeout: 15000 })`

### 3. A11: loading → 成功 → 表格渲染（3 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 点击"开始选股"后表格渲染 mock 数据 | "招商银行" / "平安银行" 可见 |
| 2 | 顶部"共 N 只"显示 mock total | `findByText(/^共\s*2\s*只$/)` |
| 3 | 成功加载后表格行显示格式化市值（亿） | "1.50亿" / "0.50亿" 格式化 |

### 4. A12: 重置清空非 context 状态（2 用例）

| # | it 标题 | 关键断言 |
|---|--------|---------|
| 1 | 点击重置后清空表格，回到"暂无数据"提示 | |
| 2 | 重置后 context 中行情指标选择也被清空 | indicator state 清空 |

---

## 关键 mock / helper

### MSW handler（顶层 `beforeEach` 注册）

- **`http.get('/api/stocks/')`**：拦截 `GET /api/stocks/`
  - 记录 `lastRequestUrl` 用于 URL 断言
  - 返回 2 条 mock 数据："招商银行" / "平安银行"
  - 支持 offset / limit / sort_by / sort_asc 分页

### helper 组件

- **`expandIndicatorPanel(user)`**：展开"行情指标"折叠面板
- **`expandTechnicalPanel()`**：展开"技术指标"折叠面板

### 关键配置

- **`vi.setConfig({ testTimeout: 15000 })`**：coverage 模式下 MSW + jsdom 慢，5s 不够

---

## 维护要点

### 行情指标 URL 序列化规则

| 指标 | 单位换算 | 序列化参数 |
|------|---------|-----------|
| `market_cap` | ×10000（亿→万） | `market_cap_min` / `market_cap_max` |
| `amount` | ×10000（亿→万） | `amount_min` / `amount_max` |
| `volume` | 不换算（手） | `volume_min` / `volume_max` |
| `price` | 不换算（元） | `price_min` / `price_max` |
| `pe_static` / `pe_ttm` / `pb` | 不换算 | `pe_static_min` / `pe_static_max` 等 |
| `change_pct` / `turnover` / `volume_ratio` | 不换算 | 同上 |

> **6.5-MARKETCAP-20260615** 修复根因：`indicatorConfig.ts` unit 标"亿元"，前端 ×10000 转换

### 技术指标 URL 序列化规则

`{indicatorId}_{optionValue}` 格式，例：
- `?tech_ma=long_align` → MA 多头排列
- `?tech_ma=short_align` → MA 空头排列
- `?tech_macd=low_golden_cross` → MACD 低位金叉
- `?tech_boll=break_upper` → BOLL 升穿上轨
- `?tech_rsi=bottom_divergence` → RSI 底背离

共 14 个 pattern，详见 [TechnicalFilter.md](./TechnicalFilter.md)

### 表格格式化

- `market_cap` 显示格式：`1.50亿` / `0.50亿`（保留 2 位小数）
- "共 N 只"使用 `^共\s*N\s*只$` 严格正则匹配，避免和 ant-message 提示的 "选股成功，共 N 只" 冲突

### 脆弱点

- `screen.getByText('共 2 只')` 会和 antd message 的 "选股成功，共 2 只" 冲突 — 解决：用 `findByText(/^共\s*2\s*只$/)` 锚定完整匹配
- 切换 market 时可能 antd 内部 message 提示污染 — 接受现状，不在测试中 mock message

---

## 变更记录

- 2026-06-15：初始 10 用例（A10/A11/A12）
- 2026-06-15：[6.5-MARKETCAP-20260615] 修复 `market_cap` ×10000 单位转换，配套 A10 用例
- 2026-06-16：新增 3 个 A10b 用例（技术指标 URL 序列化），K 13 条 review 后整体 13 用例
- 2026-06-16：加 `vi.setConfig({ testTimeout: 15000 })` 解决 coverage 模式超时
