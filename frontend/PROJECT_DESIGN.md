# 量化交易系统前端 - 项目设计文档

**项目名称**：量化交易系统（Quantitative Trading System）
**模块**：前端应用（Frontend Application）
**版本**：v0.6.0
**创建日期**：2026-05-31
**最后更新**：2026-06-06
**工作目录**：`/Users/zhangk/workspace/Quantitative_trading/frontend`

---

## 一、项目概述

### 1.1 项目背景

A 股股票筛选与展示系统的前端应用。提供多维度筛选、排序、分页查看股票数据，以及专业 K 线图表 + 买卖信号可视化。

### 1.2 核心功能

- ✅ **股票列表展示** — 代码、名称、行业、涨跌幅等核心指标
- ✅ **多维度筛选** — 技术指标、K线形态、资金流向、行业、地区
- ✅ **灵活排序** — 20+ 字段升序/降序
- ✅ **分页浏览** — 每页 100 条，上下翻页
- ✅ **K线图表** — klinecharts 蜡烛图 + MA 均线 + 成交量
- ✅ **形态识别** — 5 个高胜率形态（早晨之星/黄昏之星/看涨吞没/看跌吞没/锤子线）
- ✅ **三级缓存** — 形态/K线/指标本地缓存 + 增量更新
- ✅ **买卖点标注** — 自定义 tradeMarker 覆盖物，买入绿色▲/卖出红色▼
- ✅ **副图指标切换** — VOL/MACD/RSI/KDJ 动态切换
- ✅ **信号可视化** — 点击买卖点弹出交易详情卡片（日期/方向/价格/原因）
- ✅ **独立K线页面** — `/?kline=000001&name=` 新标签页交互

### 1.3 数据范围

- A 股主板（60/000）+ 创业板（300）

---

## 二、技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| **React** | ^18.3.1 | UI 框架 |
| **TypeScript** | ^5.4.5 | 类型安全 |
| **Vite** | ^5.2.11 | 构建/开发服务器 |
| **TailwindCSS** | ^3.4.3 | 样式框架 |
| **klinecharts** | ^9.8.12 | K 线图（内置 MA/MACD/RSI/BOLL/KDJ 等 50+ 指标） |
| **klinecharts overlay API** | — | 自定义覆盖物注册（tradeMarker 买卖点） |

**开发工具**：npm、ESLint、Vite HMR、TypeScript Compiler

---

## 三、项目结构

```
frontend/
├── 📄 配置文件
│   ├── package.json / tsconfig.json / vite.config.ts
│   ├── tailwind.config.js / postcss.config.js
│   └── index.html
│
├── 📁 src/
│   ├── main.tsx              # 应用入口
│   ├── App.tsx               # 主应用（选股器 + KLinePage 路由）⭐
│   ├── api.ts                # API 封装（fetchKline/fetchSignals/fetchMeta/fetchStocks）⭐
│   ├── types.ts              # TypeScript 类型定义 ⭐
│   │
│   ├── 📁 components/
│   │   ├── StockTable.tsx    # 股票表格 ⭐
│   │   ├── FilterPanel.tsx   # 筛选面板 ⭐
│   │   ├── StatusBar.tsx     # 状态栏
│   │   ├── KLineChart.tsx    # K线图表（tradeMarker + Tooltip + 副图切换）⭐
│   │   └── KLinePage.tsx     # 独立K线页面（并行拉取K线+信号）⭐
│   │
│   ├── 📁 hooks/
│   │   ├── useKLineData.ts   # 单股 K线 + 缓存
│   │   └── useBatchKLine.ts  # 批量 K线 + 三级缓存 ⭐
│   │
│   ├── 📁 utils/
│   │   ├── patternDetector.ts # K线形态识别 ⭐
│   │   ├── patternCache.ts    # 形态结果缓存
│   │   ├── klineCache.ts     # K线数据 LRU 缓存
│   │   └── indicators.ts     # MA/RSI/MACD/BOLL/KDJ 计算 ⭐
│   │
│   └── 📁 mocks/
│       └── meta.ts           # 元数据 Mock
│
├── 📁 public/                # 静态资源
└── 📁 dist/                  # 构建输出
```

---

## 四、核心组件

### 4.1 App.tsx — 主应用

**路径**：`src/App.tsx`

**职责**：应用根路由。从 `window.location.search` 读取 `kline` 参数：

- 有 `?kline=000001` → 渲染 `<KLinePage />`
- 无参数 → 渲染选股器界面（Meta + StatusBar + FilterPanel + StockTable）

**状态管理**：`meta`、`stocks`、`activeFilters`、`sortBy/sortAsc`、`offset`

**事件**：`toggleFilter`、`toggleIndustry/Area`、`clearAll`、`handleSort`、`handleShowKLine`

### 4.2 KLineChart.tsx — K线图表（~500 行）

**路径**：`src/components/KLineChart.tsx`

核心 K 线组件，封装 klinecharts 实例和所有业务逻辑。

| 模块 | 说明 |
|------|------|
| **主图** | 蜡烛图 + MA5/10/20/30/60 均线 |
| **副图** | 默认成交量，可切换 MACD/RSI/KDJ |
| **买卖点** | 自定义 `tradeMarker` 覆盖物（`registerOverlay` 注册） |
| **Tooltip** | 点击覆盖物弹出卡片（日期/方向/类型/价格/原因） |
| **头部** | 股票名称/代码/价格/涨跌幅 + 信号统计条 |
| **遮罩** | loading 动画 + error 信息 |
| **信号同步** | `signals` prop 变化自动清除/重建覆盖物 |

**Props**：
```typescript
interface KLineChartProps {
  data: KLineItem[]
  loading: boolean
  error: string | null
  stockCode: string | null
  stockName?: string | null
  height?: number
  signals?: SignalItem[]
}
```

### 4.3 StockTable.tsx — 股票表格

**路径**：`src/components/StockTable.tsx`

- 12 个默认列 + 展开额外字段
- 点击列头排序 / 分页（上一页/下一页）
- 红涨绿跌颜色标记
- 点击行触发 `handleShowKLine` 新标签页打开 K线图

### 4.4 FilterPanel.tsx — 筛选面板

**路径**：`src/components/FilterPanel.tsx`

**筛选维度**：技术指标（突破新高/连续上涨/量比）、K 线形态（锤子线/十字星/吞没）、资金流向（净流入额/量）、行业分类、地区分布

### 4.5 KLinePage.tsx — 独立K线页面（~95 行）

**路径**：`src/components/KLinePage.tsx`

**职责**：`/?kline=000001&name=平安银行` 页面。

```
挂载 → 并行请求 fetchKline + fetchSignals
        ↓
KLineChart(data, signals) → 渲染K线 + 买卖点标注
```

- 顶部导航栏（返回按钮 + 数据统计：X 根K线 · Y 个信号）
- 404 则显示错误状态

---

## 五、klinecharts 覆盖物设计

### 5.1 tradeMarker 自定义覆盖物

使用 klinecharts `registerOverlay` API 全局注册，name 唯一。

**注册时机**：模块加载时单次执行，`overlayRegistered` 标志位防重复。

```typescript
registerOverlay({
  name: 'tradeMarker',
  totalStep: 2,          // 1 个点 + 确认
  lock: true,            // 禁止拖拽
  needDefaultPointFigure: false,
  needDefaultXAxisFigure: false,
  needDefaultYAxisFigure: false,
  createPointFigures: ({ overlay, coordinates }) => {
    // 从 overlay.extendData.direction 判断买卖方向
    // 买入：绿色▲（锚定 low 下方 +15px）
    // 卖出：红色▼（锚定 high 上方 -15px）
  },
})
```

### 5.2 视觉规格

| 类型 | 形状 | 颜色 | 位置 |
|------|------|------|------|
| 买入 | 向上三角形 ▲ 15px | `#22c55e` green（alpha 0.85） | K线最低点下方 |
| 卖出 | 向下三角形 ▼ 15px | `#ef4444` red（alpha 0.85） | K线最高点上方 |

### 5.3 生命周期

```
signals prop 变化
  ↓
chart.removeOverlay({ groupId: 'trade_signals' })   // 清除旧覆盖物
  ↓
遍历 signals → 匹配日期 → 创建覆盖物（createOverlay）
  ↓
合成 groupId = 'trade_signals'
```

### 5.4 信号方向推断

后端 signal_type 为指标类型（`macd_cross`），方向隐含在 `reason` 中：

| 关键词 | 方向 |
|--------|------|
| 金叉 / 超卖 / 下轨 | buy |
| 死叉 / 超买 / 上轨 | sell |

```typescript
function getSignalDirection(signal: SignalItem): 'buy' | 'sell'
```

---

## 六、API 接口设计

### 6.1 接口概览

| 接口 | 方法 | 用途 | 状态 |
|------|------|------|------|
| `/api/meta` | GET | 元数据（行业/地区/筛选选项） | ✅ |
| `/api/stocks` | GET | 股票列表（分页/筛选/排序） | ✅ |
| `/api/kline/{code}` | GET | K 线数据（period/limit/adj） | ✅ |
| `/api/signals/{code}` | GET | 买卖信号列表 | ✅ |

### 6.2 GET /api/kline/{code}

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| code | string | — | 股票代码（路径参数） |
| period | string | daily | daily/weekly/monthly |
| limit | number | 150 | 1-1000 |
| adj | string | none | forward/backward/none |

### 6.3 GET /api/signals/{code}

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| code | string | — | 股票代码（路径参数） |
| type | string | — | 筛选信号类型 |
| start_date | string | — | 起始日期 |
| end_date | string | — | 结束日期 |
| limit | number | 100 | 返回条数 |

**响应**：
```typescript
interface SignalResponse {
  stock_code: string
  signals: SignalItem[]
  count: number
}
```

### 6.4 POST /api/screener/scoring（规划 Phase F）

```typescript
// 请求
{ factors: [{ key: "pe", weight: 0.3, direction: "lower" }, ...] }

// 响应
{ factors: FactorMeta[], scores: ScoreItem[], top: ScoreItem[] }
```

---

## 七、数据流设计

### 7.1 选股器启动

```
App.tsx 挂载
  → 检查 URL 是否有 ?kline=xxx
    ├── 是 → 渲染 KLinePage（见 7.3）
    └── 否 → fetchMeta → fetchStocks → FilterPanel + StockTable
```

### 7.2 K线数据加载 + 信号渲染

```
用户点击股票行 → window.open(/?kline=000001)
  ↓
KLinePage 挂载 → 并行请求:
  ├── fetchKline(code, limit=250) → stock_quotes 表 → klineCache
  │     ↓
  └── fetchSignals(code, limit=200) → trade_signals 表
        ↓
KLineChart(data, signals)
  ├── chart.applyNewData(data) → 渲染K线
  └── chart.removeOverlay → 遍历 signals → createOverlay → 渲染买卖点
```

### 7.3 KLinePage 路由

```
/?kline=000001&name=平安银行
  ↓
App.tsx 读取 urlKlineCode
  ↓
<KLinePage stockCode="000001" stockName="平安银行" />
  ↓
顶部导航栏（← 返回 + "平安银行" + "4505根K线 · 12个信号"）
  ↓
KLineChart（全屏高度，含信号标注）
```

---

## 八、状态管理

| 类别 | 状态 | 说明 |
|------|------|------|
| 数据 | `meta` | 元数据 |
| 数据 | `stocks` | 股票列表 |
| 数据 | `klineData` / `signals` | K线+信号（KLinePage 局部状态） |
| UI | `loading` / `error` | 加载/错误 |
| 筛选 | `activeFilters` / `Industries` / `Areas` | 激活条件 |
| 排序 | `sortBy` / `sortAsc` | 排序配置 |
| 分页 | `offset` | 分页偏移 |

---

## 九、类型定义

### 9.1 核心类型

```typescript
interface KLineItem {
  trade_date: string    // YYYYMMDD
  open: number; high: number; low: number; close: number
  volume: number; amount: number
}

interface SignalItem {
  trade_date: string
  signal_type: string   // macd_cross, rsi_overbought, etc.
  price: number
  reason: string        // 含方向关键词（金叉/死叉/超买/超卖）
}

interface KLineResponse {
  stock_code: string; data: KLineItem[]; count: number
}
interface SignalResponse {
  stock_code: string; signals: SignalItem[]; count: number
}
```

### 9.2 资金流向字段

```typescript
interface FundFlow {
  net_mf_amount: number; net_mf_vol: number
  buy_sm_amount: number; sell_sm_amount: number
  buy_md_amount: number; sell_md_amount: number
  buy_lg_amount: number; sell_lg_amount: number
}
```

---

## 十、智能选股器蓝图（Phase F）

### 10.1 条件组合面板

```
FilterPanel（现有）
   ↓ 扩展
可视化条件"搭积木"界面
  ├── 下拉选择指标 + 阈值输入
  ├── AND/OR/NOT 逻辑组合
  ├── 预设模版（底部超卖+放量突破、MACD金叉等）
  └── 实时命中计数
```

### 10.2 多因子打分

```
条件筛选 → 打出候选池 → 多因子打分 POST /api/screener/scoring
                                    ↓
                            前端权重滑块 UI → 实时重打分
                                    ↓
                            排序 Top 50 展示（总分 + 因子分）
```

### 10.3 一键回测

```
选股池 + 条件 → 点击"回测"
        ↓
BacktestEngine（已有 frontend/backtester/）
        ↓
资金曲线 + 基准对比 + 绩效报告（胜率/夏普/最大回撤/年化）
```

---

## 十一、开发规范

### 命名

- **变量/函数**：camelCase（`activeFilters`）
- **组件/类型**：PascalCase（`StockTable`、`StockRow`）
- **常量**：UPPER_SNAKE_CASE（`LIMIT`）
- **覆盖物**：lowerCamelCase + snake 标识（`tradeMarker`）

### 架构约束

- 禁止自由推导字段 → 必须来自 `types.ts`
- 禁止跨层调用 → `组件 → api.ts → 后端 API`
- 禁止硬编码 → 配置项使用常量或环境变量
- overlay 覆盖物统一使用 `groupId` 管理生命周期

---

## 十二、部署说明

### 开发环境

```bash
cd /Users/zhangk/workspace/Quantitative_trading/frontend
npm run dev
# 访问 http://localhost:5173
# K线页面 http://localhost:5173/?kline=000001&name=平安银行
```

### 生产构建

```bash
cd /Users/zhangk/workspace/Quantitative_trading/frontend
npm run build
# dist/ 目录
```

---

**文档维护**：方舟（前端 AI 工程师）
**最后更新**：2026-06-06