# 量化前端测试文档（行情指标模块）

> 本目录 `quant-trading-frontend/tests/` 存放"行情指标"模块的单元测试与组件测试。
> 创建日期：2026-06-15　　负责人：方舟

---

## 1. 测试框架

| 项目 | 选型 | 版本 |
|------|------|------|
| 测试运行器 | **Vitest** | ^2.1.9 |
| DOM 环境 | **jsdom** | ^24.1.3 |
| 组件渲染 | **@testing-library/react** | ^16.3.2 |
| 用户交互 | **@testing-library/user-event** | ^14.6.1 |
| 断言扩展 | **@testing-library/jest-dom** | ^6.9.1 |
| 网络 Mock | **MSW** (msw/node) | ^2.14.6 |
| 覆盖率 | **@vitest/coverage-v8** | ^2.1.9 |
| 覆盖率 UI | **@vitest/ui** | ^2.1.9 |

**配置文件**：[vitest.config.ts](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/vitest.config.ts)

- `environment: 'jsdom'` —— 浏览器 DOM 模拟
- `setupFiles: ['./tests/setup.ts']` —— 全局初始化
- `coverage.include: src/features/stock-picker/**/*.{ts,tsx}` —— 范围限定在选股功能
- `coverage.exclude` —— 排除数据层（api.ts/store.ts）、入口（index.tsx）和视图主组件（StockPickerView.tsx）

---

## 2. 目录结构

```
tests/
├── README.md                       # 本文档
├── setup.ts                        # 全局初始化（MSW + cleanup）
├── mocks/
│   ├── handlers.ts                 # MSW HTTP 拦截器
│   ├── server.ts                   # setupServer 实例
│   └── types.ts                    # 测试用类型（StockItem / ApiEnvelope）
├── config/
│   └── indicatorConfig.test.ts     # 指标配置静态校验（17 用例）
├── context/
│   └── ScreenerContext.test.tsx    # 选股 Context reducer 测试（16 用例）
├── components/
│   ├── IndicatorFilter.test.tsx    # 行情指标筛选组件测试（16 用例）
│   ├── FinancialFilter.test.tsx    # 财务指标筛选组件测试（29 用例）
│   └── TechnicalFilter.test.tsx    # 技术指标筛选组件 + Modal 测试（27 用例）
└── views/
    └── StockPickerView.test.tsx    # 选股视图集成测试（13 用例）
```

---

## 3. 运行方式

```bash
cd quant-trading-frontend

# 单次运行（CI / 提交前）
npm test

# 监听模式（开发时）
npm run test:watch

# UI 界面（可视化用例）
npm run test:ui

# 覆盖率报告（生成 coverage/ 目录）
npm run test:coverage
```

---

## 4. 测试覆盖总览

| 文件 | 用例数 | 关键覆盖点 |
|------|------:|------------|
| [tests/config/indicatorConfig.test.ts](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/config/indicatorConfig.test.ts) | **17** | 行情/财务/技术指标 id 唯一性、label 唯一性、字段映射、disabled 默认值、颜色 hex 格式、FACTOR_CONFIG 权重=100 |
| [tests/context/ScreenerContext.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/context/ScreenerContext.test.tsx) | **16** | reducer 全部 action、Provider 初始状态、SET_MARKET 重置联动状态、RESET_ALL、未知 action 兜底 |
| [tests/components/IndicatorFilter.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/IndicatorFilter.test.tsx) | **16** | 徽标渲染、折叠展开、多选计数、min/max 输入、清空按钮、多指标独立范围 |
| [tests/components/FinancialFilter.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/FinancialFilter.test.tsx) | **29** | 财务徽标、折叠展开、3 指标多选、min/max 独立范围、负数/min>max 边界、清除按钮完整生命周期（4 子用例）、disabled + Tooltip disabledReason 展示、与 ScreenerContext 市场切换联动（2 用例） |
| [tests/components/TechnicalFilter.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/TechnicalFilter.test.tsx) | **27** | 技术指标徽标、折叠展开、4 指标（MA/MACD/BOLL/RSI）弹窗打开、4 弹窗 Radio → 确定 → state 写入、**更改已有选项（长→短对齐 state 覆盖）**、**同一指标重复选不同 option 后 badge 仍为 1**、**点击 radio 后 confirm 启用**、**打开弹窗后直接取消（无任何选择）state 保持空**、**清除已选后 confirm 重新 disabled**、已选回显、**BOLL 已选后弹窗显示"当前已选：升穿中轨"**、清除已选、多选同时存在、**切换市场时关闭打开中的弹窗**、确定按钮初始 disabled、**disabled 指标按钮不可点击且不打开弹窗**、**TechnicalIndicatorModal 单独测试 3 个边界** |
| [tests/views/StockPickerView.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/views/StockPickerView.test.tsx) | **13** | runScreening 拼参（含 `*_min/*_max` 序列化 + 行情字段 `×10000` 单位转换 + `tech_*=*` 技术指标序列化 3 用例）、空值过滤、loading→success 流转、表格渲染、total 显示、reset 清空 |
| **合计** | **118** | 30+ 个 describe 块 |

### 4.1 行覆盖率（v8 provider）

| 源文件 | Lines | Branches | Functions | 备注 |
|--------|------:|---------:|----------:|------|
| [IndicatorFilter.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/IndicatorFilter.tsx) | **100%** | 82.75% | **100%** | 行情指标 |
| [FinancialFilter.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/FinancialFilter.tsx) | **100%** | 91.17% | **100%** | 财务指标 |
| [TechnicalFilter.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/TechnicalFilter.tsx) | **100%** | 95% | **100%** | 技术指标 |
| [TechnicalIndicatorModal.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/TechnicalIndicatorModal.tsx) | **100%** | **100%** | **100%** | 通用技术指标配置弹窗 |
| [config/indicatorConfig.ts](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/config/indicatorConfig.ts) | **100%** | **100%** | **100%** | 静态配置（含 TECHNICAL_INDICATORS 4 指标 + 14 个 Radio option） |
| [config/marketConfig.ts](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/config/marketConfig.ts) | **100%** | **100%** | **100%** | 静态配置 |
| [context/ScreenerContext.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/context/ScreenerContext.tsx) | 88.48% | 88.88% | **100%** | 全部 reducer 函数覆盖；非 reducer 辅助函数由视图测试间接覆盖 |
| **总计** | **83.33%** | **86.33%** | 76.59% | 范围限定 `src/features/stock-picker/**` |

> 完整 HTML 报告：[coverage/index.html](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/coverage/index.html)

---

## 5. 各模块说明

### 5.1 指标配置静态校验（config/indicatorConfig.test.ts）

锁定"行情指标"配置表的硬约束，防止后续修改破坏结构：

- **MARKET_INDICATORS**：8 个字段（`price`/`change_pct`/`pe`/`pe_ttm`/`pb`/`volume_ratio`/`amount`/`volume`/`market_cap`），每个含 `id` / `label` / `field` / `unit` / `color` 五项
- **FINANCIAL_INDICATORS**：3 个字段（`revenue`/`net_profit`/`roe`）
- **TECHNICAL_INDICATORS**：4 个**配置型**指标（`ma`/`macd`/`boll`/`rsi`），K 决定 2026-06-16 取消"自定义"后全部使用 `TechnicalIndicatorItem` 结构（id + label + options[]）；14 个 Radio option 全部覆盖
- **FACTOR_CONFIG**：权重总和 = 100
- 颜色格式：`#RRGGBB` 正则校验
- id/label 全表唯一

### 5.2 ScreenerContext 状态机（context/ScreenerContext.test.tsx）

覆盖 [ScreenerContext.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/context/ScreenerContext.tsx) 中 reducer 的全部 action：

- `TOGGLE_MARKET_INDICATOR` —— 行情指标多选 toggle
- `SET_MARKET_INDICATOR_RANGE` —— 单指标 min/max 范围写入
- `SET_MARKET` —— 切换市场时联动清空 `selectedMarketIndicators` / `marketIndicatorRanges`
- `TOGGLE_PANEL` —— 折叠面板展开/收起
- `RESET_ALL` —— 完整状态重置
- 未知 action —— 兜底返回原 state
- Provider 初始状态校验

> 关键技术点：`renderHook` 必须用组件形式包装 Provider
> ```tsx
> const Wrapper = ({ children }: { children: ReactNode }) =>
>   <ScreenerProvider>{children}</ScreenerProvider>
> renderHook(() => useScreener(), { wrapper: Wrapper })
> ```

### 5.3 IndicatorFilter 组件（components/IndicatorFilter.test.tsx）

针对 [IndicatorFilter.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/IndicatorFilter.tsx) 行为级覆盖：

- 折叠面板默认收起、点击头部展开
- 徽标显示已选指标数（`X/9`）
- 指标按钮点击 toggle `data-selected` 属性
- `InputNumber` min/max 输入（Antd 把 data-testid 直接放在 `<input>` 上，查询时无需 `querySelector('input')`）
- 至少一个 min/max 输入后才显示"清空范围"按钮
- 多个指标的范围状态相互独立

**已添加的 data-testid**（便于 E2E / 单元测试定位）：

| 元素 | data-testid 模板 |
|------|------------------|
| 指标按钮 | `indicator-btn-{id}` + `data-selected` |
| 折叠面板容器 | `indicator-filter-collapse` |
| 徽标 | `indicator-filter-badge` |
| 范围输入框 | `indicator-range-{id}` / `indicator-min-{id}` / `indicator-max-{id}` |
| 清空按钮 | `indicator-clear-{id}` |
| 空状态提示 | `indicator-empty-hint` |

### 5.4 FinancialFilter 组件（components/FinancialFilter.test.tsx）

针对 [FinancialFilter.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/FinancialFilter.tsx) 行为级覆盖（结构与 IndicatorFilter 高度对称）：

- 折叠面板默认收起、点击头部展开
- 徽标显示已选财务指标数（`X/3`）
- 3 个财务指标按钮（净利润/营业收入/净资产收益率）多选 toggle
- `InputNumber` min/max 输入，与 `financialIndicatorRanges` state 双向同步
- 只输入 min 或只输入 max 时清空按钮也显示
- **取消选中指标时 reducer 自动清空该指标的 range**（与 IndicatorFilter 行为一致）
- 选中指标后空状态提示消失，"范围条件:" 标题出现
- 多个指标的范围状态相互独立
- `disabled` 状态下按钮不可点击

**已添加的 data-testid**：

| 元素 | data-testid 模板 |
|------|------------------|
| 指标按钮 | `financial-btn-{id}` + `data-selected` |
| 折叠面板容器 | `financial-filter-collapse` |
| 徽标 | `financial-filter-badge` |
| 范围输入框 | `financial-range-{id}` / `financial-min-{id}` / `financial-max-{id}` |
| 清空按钮 | `financial-clear-{id}` |
| 空状态提示 | `financial-empty-hint` |

### 5.5 TechnicalFilter 组件（components/TechnicalFilter.test.tsx）

针对 [TechnicalFilter.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/TechnicalFilter.tsx) 行为级覆盖，与"行情/财务"筛选的"按钮多选 + 范围输入"模式**不同**——技术指标采用"按钮 + 弹窗"模式：

- 折叠面板默认收起、点击头部展开
- 徽标显示已选技术指标数（`X/4`）
- 4 个技术指标按钮（MA/MACD/BOLL/RSI）点击**打开弹窗**（非 toggle）
- 弹窗内部展示 `TECHNICAL_INDICATORS[id].options` 的 Radio 列表
- 选 Radio + 点"确定" → 写入 `selectedTechnicalIndicators[id]=option` → 关闭弹窗 → 按钮变红 + 显示 `data-option`
- 弹窗内部维护 `tempOption` 临时状态，仅在点"确定"时回写父级（K 2026-06-16 要求"取消自定义、风格一致、紧凑"）
- 选 Radio + 点"取消" → 弹窗关闭但不写入 state
- 再次打开弹窗 → Radio 回显当前已选项
- 已选时弹窗底部显示"清除已选"按钮，点击后清空 state（弹窗保持打开）
- 4 个技术指标可同时选择，state 为 `Record<string, string>` 结构
- 切换市场（`SET_MARKET`）时清空 `selectedTechnicalIndicators` 和 `openTechnicalModal`
- 弹窗刚打开时"确定"按钮 disabled（未选 Radio 时）

**已添加的 data-testid**：

| 元素 | data-testid 模板 |
|------|------------------|
| 指标按钮 | `technical-btn-{id}` + `data-selected` + `data-option` |
| 折叠面板容器 | `technical-filter-collapse` |
| 折叠面板头部 | `technical-filter-header` |
| 徽标 | `technical-filter-badge` |
| 弹窗容器 | `technical-modal-{id}` |
| 弹窗 Radio | `technical-modal-{id}-option-{value}` |
| 弹窗"取消"按钮 | `technical-modal-{id}-cancel` |
| 弹窗"确定"按钮 | `technical-modal-{id}-confirm` |
| 弹窗"清除已选"按钮 | `technical-modal-{id}-clear` |

**架构说明**：通用弹窗组件 [TechnicalIndicatorModal.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/TechnicalIndicatorModal.tsx) 100% 行/100% 分支覆盖，4 个指标共用同一组件 + 不同 `options` 配置。

### 5.6 StockPickerView 集成测试（views/StockPickerView.test.tsx）

通过 MSW 拦截 `/api/stocks/`，端到端验证 [StockPickerView.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/StockPickerView.tsx) 的核心数据流：

- runScreening 序列化 `*_min` / `*_max` 参数（验证 URL 包含 `market_cap_min=...&market_cap_max=...`）
- 空范围不写入查询参数
- loading → success 状态切换 + "共 N 只" 渲染
- 表格 20 行渲染
- `RESET_ALL` 后 selectedBoards / marketIndicatorRanges 清空
- 错误场景走 `/api/stocks/error` 返回 500

**MSW handlers** ([mocks/handlers.ts](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/mocks/handlers.ts))：

- 3 只 mock 股票（招商银行 / 平安银行 / 宁德时代），覆盖 4 个板块
- 支持 `offset` / `limit` / `sort_by` / `sort_asc` 参数模拟排序分页
- `setupFiles` 中 `onUnhandledRequest: 'error'` —— 未声明的 HTTP 请求直接报错

---

## 6. 设计原则

1. **范围限定**：测试只覆盖 `src/features/stock-picker/**`，不污染全仓
2. **行为优先**：断言可见行为（DOM 文案、属性、URL 参数）而非实现细节
3. **网络隔离**：所有外部调用走 MSW，CI 环境无网络也能跑
4. **零硬编码**：测试断言不依赖具体数字（除 mock 数据本身），保证重构时不易碎
5. **data-testid 命名规范**：所有 E2E 元素可定位，组件测试无需 querySelector 拼装

---

## 7. 已知遗留与扩展方向

| 序号 | 模块 | 状态 | 备注 |
|------|------|------|------|
| 1 | RangeSelector 联动逻辑 | ❌ 不测 | 项目硬约束——"范围"模块禁止改动，测试也同步冻结 |
| 2 | ✅ FinancialFilter | **已完成** | 29 用例 / 100% 行 / 91.17% 分支 覆盖（2026-06-16 K 二次审阅后完善） |
| 3 | ✅ TechnicalFilter | **已完成** | 19 用例 / 100% 行 / 95% 分支 覆盖；含 TechnicalIndicatorModal 100%/100%/100% 覆盖 |
| 4 | ConditionBuilder / FactorScoringConfig | 待补 | 已有 IndicatorFilter / FinancialFilter / TechnicalFilter 模板 |
| 5 | StockTable 渲染 | 待补 | 当前 0% 覆盖，下阶段补 Table 排序/格式化/滚动测试 |
| 6 | 覆盖率阈值门禁 | 未启用 | 等测试体系稳定后加入 `coverage.thresholds` |

---

## 8. 关联文档

- [docs/协作单.md](file:///Users/zhangk/workspace/Quantitative_trading/docs/协作单.md) —— 协作单系统
- [.trae/topics.md](file:///Users/zhangk/workspace/Quantitative_trading/.trae/topics.md) —— 跨会话通知
- [docs/daily_report/2026/06/](file:///Users/zhangk/workspace/Quantitative_trading/docs/daily_report/2026/06/) —— 日报
- [量化交易系统前端调测交接手册.md](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/docs/量化交易系统前端调测交接手册.md) —— 测试相关章节
