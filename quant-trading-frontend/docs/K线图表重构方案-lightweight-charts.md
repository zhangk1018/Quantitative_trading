# K线图表重构项目实施方案（正式版 v1.1）

## 文档说明
- **文档用途**：替换页面TradingView图表，基于`lightweight-charts v4.2.3`自研全量技术指标渲染，**零后端改造**，前端统一计算MA/BOLL/MACD/RSI/KDJ/成交量
- **版本**：v1.1（修正v1.0中`addPane()` API错误——v4.2.3不支持addPane()，多副图通过priceScaleId+scaleMargins实现）
- **文档状态**：评审规划文档，编码前确认执行

---

## 一、项目基础现状梳理

### 1.1 前后端技术栈现状

#### 前端（React+TS+Vite）

| 依赖 | 版本 | 使用说明 |
|------|------|--------|
| React | 18.3.1 | 主UI框架，弹窗组件基于AntD Modal |
| TypeScript | 5.4.5 | 严格类型校验，禁止any |
| Vite | 5.2.12 | 本地开发构建工具 |
| Ant Design | 5.17.0 | 复用Modal、Segmented切换组件 |
| TailwindCSS | 3.4.3 | 页面布局样式 |
| lightweight-charts | 4.2.3 | 已预装，单Chart+多priceScale架构（**不支持addPane()**） |
| Axios | 1.7.2 | 股票K线接口请求 |
| dayjs | 1.11.11 | 时间格式化处理 |
| zod | 4.4.3 | 接口返回数据校验 |

#### 后端（Python FastAPI）

1. 核心接口：`GET /api/kline/{code}?limit=xxx&adj=forward`
2. 数据源：`stock_daily_quotes` 日线库表
3. 返回字段：`trade_date/open/high/low/close/volume`（基础OHLCV完整，api.ts映射为time/open/high/low/close/volume）
4. 现有后端指标字段现状：
    - **可用**：ma5/ma10/ma20、macd/diff/dea、rsi_6/rsi_12/rsi_24、volume（但前端仍统一自行计算，保证公式一致性）
    - **不可用**：BOLL全字段null、无KDJ、无MA60/120/250
5. 核心约束：**不改动ETL、数据库、接口**，所有缺失/无效/需扩展指标**前端自主计算**

### 1.2 现有代码文件现状

1. **弹窗入口**：`src/features/stock-picker/components/StockAnalysisModal.tsx`
    - 当前逻辑：加载TradingView远程JS，初始化TV iframe Widget，依赖外部CDN
    - 待改造：完整移除TV相关代码，替换为LWC单Chart+多priceScale架构
2. **接口文件**：`src/features/stock-detail/api.ts`
    - 当前：`fetchKLineData` 默认limit=150（API默认值），需前端请求时传limit=500
    - 修改：调用fetchKLineData时传入limit=500，满足MA250均线计算所需历史长度
3. **全局入口**：`quant-trading-frontend/index.html`
    - 存在TV远程脚本标签（cloudfront.net/tv.js），需彻底删除，消除跨境依赖
4. **类型文件**：`src/lib/indicators/types.ts`
    - 当前KLineItem仅含OHLCV基础字段，需保持兼容，无需扩展
5. **新增文件**：`src/lib/indicators/technical.ts`（纯TS指标计算工具库，无DOM依赖、无React依赖）

### 1.3 原有架构痛点

1. TradingView免费版Widget依赖`s.tradingview.com`域名，国内被墙，iframe无法渲染图表内容；
2. 后端指标字段缺失/空值（BOLL全null），无法支持MA60/120/250、KDJ、有效BOLL；
3. 第三方SaaS平台，无法自定义指标参数切换（MA周期、BOLL带宽）；
4. 无法自主控制样式、交互细节；
5. 远程JS加载有CDN失败风险，影响页面可用性。

---

## 二、整体技术架构设计

### 2.1 关键架构修正（v1.1）

> **重要**：lightweight-charts v4.2.3 **没有** `chart.addPane()` 方法。多副图通过以下API实现：
> - 创建series时指定不同的 `priceScaleId`（如 `'volume'`、`'macd'`、`'osc'`）
> - 通过 `chart.priceScale(scaleId).applyOptions({ scaleMargins: { top, bottom } })` 控制各priceScale在图表中的垂直位置
> - 同一priceScaleId下的series共享同一个价格轴和数据区域
> - 所有priceScale共享同一个时间轴，缩放/平移/十字光标天然同步

### 2.2 数据流转链路

```
前端弹窗组件 → Axios请求/api/kline（limit=500，前复权adj=forward）
        ↓
zod校验 + 类型转换 → 标准KLineItem[] (time/open/high/low/close/volume)
        ↓
technical.ts 统一计算全套技术指标（SMA/EMA/BOLL/MACD/RSI/KDJ）
        ↓
格式化LWC标准绘图数据（LineData<Time>[] / HistogramData<Time>[]）
        ↓
单Chart实例，多priceScale分层渲染：
  - priceScaleId='left'（主图）：K线蜡烛 + MA5/10/20/60 + BOLL上/下轨
  - priceScaleId='volume'（副图1）：成交量柱状
  - priceScaleId='macd'（副图2）：DIF线 + DEA线 + MACD红绿柱
  - priceScaleId='osc'（副图3）：RSI6/12/24 或 KDJ(K/D/J)，通过series.visible切换
```

### 2.3 图表分层布局（单Chart多PriceScale）

通过 `scaleMargins` 控制各区域垂直位置（margin以图表总高度的分数表示，`top`为距顶部留白，`bottom`为距底部留白）：

| 区域 | priceScaleId | scaleMargins | 占比 | 内容 |
|------|-------------|-------------|------|------|
| 主图 | `'left'` | `{ top: 0.02, bottom: 0.45 }` | ~53% | K线蜡烛 + MA5/10/20/60 + BOLL上/下轨 |
| 副图1-成交量 | `'volume'` | `{ top: 0.58, bottom: 0.27 }` | ~15% | 涨跌分色柱状图 |
| 副图2-MACD | `'macd'` | `{ top: 0.76, bottom: 0.12 }` | ~12% | DIF白线+DEA黄线+红绿柱 |
| 副图3-震荡指标 | `'osc'` | `{ top: 0.90, bottom: 0.0 }` | ~10% | RSI三线 / KDJ三线（Segmented切换） |

> 注：gap区域（主图与副图之间、副图与副图之间）自动留白作为视觉分隔，可通过在CSS中添加分隔线或LWC的watermark/plugin实现分隔线效果。最终margin值在编码后浏览器微调，确保视觉协调。

### 2.4 指标Series与priceScaleId绑定关系

| Series | 类型 | priceScaleId | 说明 |
|--------|------|-------------|------|
| candlestick | Candlestick | `'left'` | K线蜡烛，绑定左侧主图价格轴 |
| ma5/ma10/ma20/ma60 | Line | `'left'` | MA均线叠加在主图，共享价格轴 |
| boll_upper/boll_lower | Line | `'left'` | BOLL上下轨叠加主图，虚线；中轨=MA20不重绘 |
| volume_hist | Histogram | `'volume'` | 成交量独立价格轴 |
| dif_line/dea_line | Line | `'macd'` | MACD的DIF/DEA线 |
| macd_hist | Histogram | `'macd'` | MACD柱状图 |
| rsi_6/rsi_12/rsi_24 | Line | `'osc'` | RSI三线 |
| rsi_30_line/rsi_70_line | Line | `'osc'` | RSI超买超卖参考水平线 |
| kdj_k/kdj_d/kdj_j | Line | `'osc'` | KDJ三线（默认隐藏，Tab切换时显示） |
| kdj_20_line/kdj_80_line | Line | `'osc'` | KDJ参考水平线（默认隐藏） |

### 2.5 图表统一交互规范

1. **天然联动（无需手写同步代码）**：单Chart实例下，所有priceScale共享同一时间轴，缩放、横向平移、十字光标底层自动同步；
2. **刻度统一配置**：主图`leftPriceScale.visible=true`，`rightPriceScale.visible=false`，所有副图priceScale的`visible=false`（仅主图显示价格标签，副图不显示刻度值以节省空间），各priceScale设置`minimumWidth: 60`确保绘图区左边界对齐；
3. **十字光标**：LWC单实例自动处理，鼠标移动时垂直十字线贯穿所有区域，自动显示各区域的series数值；
4. **Tab切换**：RSI↔KDJ切换通过控制对应series的`.applyOptions({ visible: true/false })`实现，不销毁重建series，避免闪烁；
5. **自动清理**：弹窗关闭（destroyOnHidden）时useEffect cleanup调用`chart.remove()`销毁整个Chart实例及其DOM，清除所有series引用。

---

## 三、文件变更清单

| 文件路径 | 操作类型 | 详细变更内容 |
|--------|---------|------------|
| index.html | 修改 | 删除第8行`<script type="text/javascript" src="https://d33t3vvu2t2yu5.cloudfront.net/tv.js"></script>`标签 |
| StockAnalysisModal.tsx | 重写 | 1. 删除所有TV相关代码（window.TradingView声明、toTVSymbol、widgetRef、tvStatus、setTimeout 300ms初始化等）<br>2. 新增LWC单Chart初始化（createChart）、配置leftPriceScale/rightPriceScale<br>3. 创建4组priceScale并设置scaleMargins<br>4. 创建所有candlestick/line/histogram series，绑定priceScaleId<br>5. 数据获取→指标计算→setData渲染流程<br>6. RSI/KDJ Segmented切换（控制series.visible）<br>7. useEffect cleanup调用chart.remove()<br>8. 保留现有头部信息栏UI、Modal全屏、ESC关闭逻辑 |
| api.ts | 小幅修改 | fetchKLineData调用方（在StockAnalysisModal中）传入`{ limit: 500, adj: 'forward' }`参数；RawKLineItem类型保留boll_upper等字段但前端不依赖 |
| src/lib/indicators/types.ts | 无需修改 | KLineItem类型已满足需求，指标计算输出直接构造LineData/HistogramData即可 |
| src/lib/indicators/technical.ts | **新增** | 纯TS工具函数（无DOM、无React依赖），导出：<br>- `sma(data, period)` 简单移动平均<br>- `ema(data, period)` 指数移动平均<br>- `stddev(data, period)` 标准差<br>- `calcBollingerBands(closes, period, k)` BOLL三轨<br>- `calcMACD(closes, fast, slow, signal)` DIF/DEA/柱<br>- `calcRSI(closes, period)` RSI<br>- `calcKDJ(highs, lows, closes, n, m1, m2)` K/D/J<br>- 所有函数输入为number[]，输出含`null`的(LWC兼容)数组，前N周期不足返回null |

---

## 四、指标计算统一标准（前端独立实现）

### 4.1 通用约束

1. 周期不足前N根K线统一返回 `null`，LWC自动断开线条，杜绝0值曲线失真；
2. 所有除法增加除零保护（KDJ的diff===0、RSI的avg_loss===0），避免NaN、Infinity导致图表崩溃；
3. 所有输入强制 `Number()` 转换，非数值数据前置过滤；
4. **SMA采用滑动窗口算法O(n)**，不使用暴力O(n*N)（每点重新求和），保证500条数据计算<1ms；
5. 不引入第三方指标库（如`technicalindicators`包），原生TS实现，控制打包体积。

### 4.2 各指标计算公式

#### 1. SMA简单均线（MA5/10/20/60）

```
SMA[i] = sum(closes[i-N+1..i]) / N
实现：滑动窗口，维护runningSum，每个新点减oldest加newest，O(n)
输出：i < N-1 → null
MA5周期=5, MA10=10, MA20=20, MA60=60
```

#### 2. EMA指数移动平均（MACD计算用）

```
k = 2 / (period + 1)
EMA[i] = closes[i] * k + EMA[i-1] * (1 - k)
初始化：EMA[0] = closes[0]
输出：i < period-1 → null（预热期不输出）
```

#### 3. BOLL布林带（N=20，K=2）

```
mid = SMA(closes, 20)   → 复用MA20，不重复绘制
std = StdDev(closes, 20)（总体标准差）
upper = mid + K * std
lower = mid - K * std
输出：i < 19 → { upper: null, mid: null, lower: null }
注意：中轨与MA20完全重合，仅绘制上下轨（虚线），中轨不重复创建series
```

#### 4. MACD（fast=12, slow=26, signal=9）

```
dif = EMA(closes, 12) - EMA(closes, 26)
dea = EMA(dif, 9)         注意：EMA输入是dif数组，null项跳过
macd_bar = 2 * (dif - dea)
柱子颜色：dif >= dea → #f23645（红/多头）；dif < dea → #00d4aa（绿/空头）
注意：颜色看DIF与DEA交叉关系，不是柱子正负
输出：预热期内各字段为null
```

#### 5. RSI（Wilder平滑法，period=6/12/24）

```
delta[i] = closes[i] - closes[i-1]
gain[i] = max(delta[i], 0)
loss[i] = max(-delta[i], 0)
首段：avg_gain = SMA(gain[1..period], period)
      avg_loss = SMA(loss[1..period], period)
后续（Wilder平滑）：
      avg_gain = (prev_avg_gain * (period-1) + gain[i]) / period
      avg_loss = (prev_avg_loss * (period-1) + loss[i]) / period
RS = avg_gain / avg_loss
RSI = 100 - 100 / (1 + RS)
边界：avg_loss === 0 → RSI = 100（连续上涨）；avg_gain === 0 → RSI = 0（连续下跌）
输出：i <= period → null
参考线：30（超卖水平线）、70（超买水平线）
```

#### 6. KDJ（n=9, m1=3, m2=3）

```
llv[i] = lowest(lows[i-n+1..i])   （9日最低价）
hhv[i] = highest(highs[i-n+1..i]) （9日最高价）
diff = hhv[i] - llv[i]
rsv = diff === 0 ? 50 : ((closes[i] - llv[i]) / diff) * 100  ← 除零保护
K[i] = (2/3) * prevK + (1/3) * rsv
D[i] = (2/3) * prevD + (1/3) * K[i]
J[i] = 3 * K[i] - 2 * D[i]
初始化：prevK = 50, prevD = 50
输出：i < n-1 → { K: null, D: null, J: null }
参考线：20（超卖水平线）、80（超买水平线）
J值可超出0-100范围（K/D钳制在0-100，J不受限）
```

### 4.3 SMA滑动窗口实现（性能关键）

```typescript
function sma(values: number[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) result[i] = sum / period;
  }
  return result;
}
```

---

## 五、视觉与配色规范

### 5.1 涨跌基础色

| 类型 | 颜色 | 说明 |
|------|------|------|
| 阳线（close ≥ open） | `#00d4aa` | 蜡烛体+边框+影线（中国股市惯例：涨绿跌红） |
| 阴线（close < open） | `#f23645` | 蜡烛体+边框+影线 |

### 5.2 主图线条配色

| 线条 | 颜色 | 样式 | 线宽 |
|------|------|------|------|
| MA5 | `#ff9800` | 实线（LineStyle.Solid） | 1 |
| MA10 | `#2196f3` | 实线 | 1 |
| MA20 | `#f5a623` | 实线 | 1 |
| MA60 | `#9c27b0` | 实线 | 1 |
| BOLL上轨 | `rgba(74,144,226,0.6)` | 虚线（LineStyle.Dashed） | 1 |
| BOLL下轨 | `rgba(74,144,226,0.6)` | 虚线（LineStyle.Dashed） | 1 |
| BOLL中轨 | — | — | 与MA20（#f5a623）重合，不重复绘制 |

### 5.3 副图配色

| 副图 | 元素 | 颜色 | 样式 |
|------|------|------|------|
| 成交量 | 阳线柱 | `rgba(0,212,170,0.6)` | Histogram, 半透明 |
| 成交量 | 阴线柱 | `rgba(242,54,69,0.6)` | Histogram, 半透明 |
| MACD | DIF线 | `#ffffff` | 实线, 线宽1 |
| MACD | DEA线 | `#f5d900` | 实线, 线宽1 |
| MACD | 多头柱(DIF≥DEA) | `#f23645` | Histogram |
| MACD | 空头柱(DIF<DEA) | `#00d4aa` | Histogram |
| RSI | RSI6线 | `#ff6b6b` | 实线, 线宽1 |
| RSI | RSI12线 | `#4ecdc4` | 实线, 线宽1 |
| RSI | RSI24线 | `#ffe66d` | 实线, 线宽1 |
| RSI | 30/70参考线 | `rgba(255,255,255,0.2)` | 虚线, 线宽1 |
| KDJ | K线 | `#ff9800` | 实线, 线宽1 |
| KDJ | D线 | `#2196f3` | 实线, 线宽1 |
| KDJ | J线 | `#9c27b0` | 实线, 线宽1 |
| KDJ | 20/80参考线 | `rgba(255,255,255,0.2)` | 虚线, 线宽1 |

### 5.4 全局背景与网格

| 元素 | 颜色 |
|------|------|
| 图表背景（paneProperties.background） | `#131722` |
| 文字颜色（layout.textColor） | `#848E9C` |
| 垂直网格线 | `rgba(42,46,57,0.5)` |
| 水平网格线 | `rgba(42,46,57,0.5)` |
| 时间轴边框 | `#2A2E39` |
| 头部信息栏背景 | `#1E222D` |
| 分隔线（主图与副图之间，通过CSS border或LWC plugin实现） | `#2A2E39` |

---

## 六、LWC Chart初始化配置规格

```typescript
import { createChart, CrosshairMode, LineStyle, ColorType } from 'lightweight-charts';

const chart = createChart(containerEl, {
  layout: {
    background: { type: ColorType.Solid, color: '#131722' },
    textColor: '#848E9C',
    fontSize: 11,
  },
  grid: {
    vertLines: { color: 'rgba(42,46,57,0.5)' },
    horzLines: { color: 'rgba(42,46,57,0.5)' },
  },
  crosshair: {
    mode: CrosshairMode.Normal,
    vertLine: { color: 'rgba(255,255,255,0.2)', style: LineStyle.Dashed },
    horzLine: { color: 'rgba(255,255,255,0.2)', style: LineStyle.Dashed },
  },
  rightPriceScale: { visible: false },
  leftPriceScale: {
    visible: true,
    minimumWidth: 60,
    entireTextOnly: true,
    borderColor: '#2A2E39',
  },
  timeScale: {
    timeVisible: false,
    secondsVisible: false,
    borderColor: '#2A2E39',
    rightOffset: 5,
  },
  autoSize: true,
  handleScroll: true,
  handleScale: true,
});
```

### PriceScale配置示例

```typescript
// 主图priceScale（默认left）
chart.priceScale('left').applyOptions({
  scaleMargins: { top: 0.02, bottom: 0.45 },
  minimumWidth: 60,
});

// 成交量priceScale
chart.priceScale('volume').applyOptions({
  scaleMargins: { top: 0.58, bottom: 0.27 },
  visible: false,  // 不显示价格刻度标签
});

// MACD priceScale
chart.priceScale('macd').applyOptions({
  scaleMargins: { top: 0.76, bottom: 0.12 },
  visible: false,
});

// 震荡指标priceScale（RSI/KDJ共享）
chart.priceScale('osc').applyOptions({
  scaleMargins: { top: 0.90, bottom: 0.0 },
  visible: false,
});
```

---

## 七、功能验收标准

### 7.1 P0 核心功能用例（必过）

| 编号 | 测试场景 | 操作步骤 | 预期结果 |
|------|----------|----------|----------|
| TC01 | 打开K线弹窗 | 选股页面双击任意股票行 | Modal全屏弹出，头部信息（名称/价格/涨跌幅/PE/PB/市值/换手/板块）全部正确显示 |
| TC02 | K线蜡烛渲染 | 等待图表加载完成 | 蜡烛图正确渲染，阳线绿阴线红，时间轴显示交易日 |
| TC03 | MA均线显示 | 观察主图区域 | MA5/10/20/60四条均线可见、颜色正确，前N根bar无0值直线砸到x轴（自然留白断开） |
| TC04 | BOLL带显示 | 观察主图区域 | 上下轨虚线淡蓝色正确渲染，中轨不重复绘制（MA20已代表中轨） |
| TC05 | 成交量副图 | 观察主图下方 | 红绿柱状图，柱子颜色与当日涨跌一致（阳绿阴红） |
| TC06 | MACD副图 | 观察成交量下方 | DIF白线、DEA黄线、红绿柱正确渲染；金叉/死叉处柱子颜色切换正确（红/DIF≥DEA，绿/DIF<DEA） |
| TC07 | RSI默认显示 | 观察最下方副图 | RSI6红/RSI12青/RSI24黄三条线，30/70水平参考线可见，数值范围0-100 |
| TC08 | KDJ切换 | 点击Segmented"KDJ" | RSI系列隐藏，KDJ K橙/D蓝/J紫三条线显示，20/80参考线可见，J值可超出0-100 |
| TC09 | 十字光标 | 鼠标悬停K线上 | 垂直十字线贯穿所有4个区域，自动显示各指标数值 |
| TC10 | 缩放联动 | 鼠标滚轮缩放 | 主图+3个副图同步缩放，时间轴一致 |
| TC11 | 平移联动 | 鼠标拖动图表 | 所有区域同步横向平移 |
| TC12 | ESC关闭重开 | 按ESC关闭→重新双击打开 | 关闭正常，重新打开图表完整渲染无残留、无报错 |
| TC13 | TS编译检查 | `cd quant-trading-frontend && npx tsc -b --noEmit` | 0 errors |
| TC14 | TradingView残留清理 | grep搜索`TradingView\|tv.js\|toTVSymbol\|widgetRef` | 0 matches（注释除外） |
| TC15 | 数据请求验证 | Network面板检查/api/kline请求 | 请求参数包含limit=500&adj=forward，响应200 |

### 7.2 P1 优化验收项

| 编号 | 测试场景 | 预期结果 |
|------|----------|----------|
| TC16 | 一字涨跌停KDJ | 查找涨停/跌停股票，KDJ无NaN/Infinity，图表不白屏不崩溃 |
| TC17 | 沪市主板（60xxxx） | 600519茅台K线正常渲染 |
| TC18 | 深市主板（00xxxx） | 000001平安银行K线正常渲染 |
| TC19 | 创业板（30xxxx） | 300580贝斯特K线正常渲染 |
| TC20 | 科创板（688xxx） | 688311盟升电子K线正常渲染 |
| TC21 | 北交所（43xxxx/8xxxxx） | 北交所个股K线正常渲染 |
| TC22 | 指标计算性能 | 500条数据全指标计算总耗时 <10ms（console.time测量） |
| TC23 | 图表渲染性能 | 首次setData到图表可见 <300ms |
| TC24 | Tab切换流畅度 | RSI↔KDJ切换无明显闪烁（仅visible切换，不销毁重建） |
| TC25 | 内存泄漏检测 | 反复打开关闭Modal 5次，Chrome Memory无持续增长 |

---

## 八、性能指标目标

| 性能项 | 标准阈值 | 检测方式 |
|--------|---------|---------|
| 500条K线全指标计算耗时 | <10ms | console.time 包裹technical.ts计算函数 |
| 图表首次完整渲染耗时 | <300ms | Performance API（createChart到最后一个series.setData完成） |
| 缩放/平移交互帧率 | ≥50fps | Chrome DevTools Performance面板录制 |
| 单图表内存占用 | <50MB | Chrome DevTools Memory快照 |
| K线接口响应（limit=500） | <500ms | Network面板或curl计时 |
| 打包增量（lightweight-charts） | ~40KB (gzipped) | 已在node_modules中，无需新增 |

---

## 九、编码阶段分解

### 阶段0：API可用性前置验证（第零步，编码前立即执行）
在正式编码前，先在浏览器控制台或临时测试页面验证LWC v4.2.3多priceScale+scaleMargins能否正确堆叠多个指标区域，确认API行为与文档一致。

### 阶段1：指标工具库开发（technical.ts）
1. 创建`src/lib/indicators/technical.ts`；
2. 实现基础工具函数：`sma`（滑动窗口O(n)）、`ema`、`stddev`（总体标准差）、`highest`/`lowest`（窗口极值）；
3. 实现业务指标函数：`calcBollingerBands`、`calcMACD`、`calcRSI`、`calcKDJ`；
4. 每个函数对输入做Number转换、NaN检查，输出含null的数组；
5. 统一导出接口，TypeScript类型明确，无any。

### 阶段2：弹窗组件重构（StockAnalysisModal.tsx）
1. 删除全部TradingView相关代码（window.TradingView类型声明、toTVSymbol函数、widgetRef/initTimerRef/tvStatus相关state、setTimeout逻辑）；
2. 新增chartRef（`useRef<IChartApi | null>`）和seriesRefs对象（持有所有ISeriesApi引用）；
3. useEffect中：DOM就绪后→createChart→配置left/right priceScale→创建4个priceScale并设置scaleMargins→创建所有series（candlestick/line/histogram）绑定对应priceScaleId→fetchKLineData(limit=500,adj=forward)→technical.ts计算→series.setData()；
4. 实现RSI/KDJ Segmented切换：onChange时设置对应series的visible；
5. useEffect cleanup：调用chart.remove()并清空所有ref；
6. 保留现有头部信息栏JSX、Modal props（全屏、destroyOnHidden、maskClosable=false）；
7. 加载状态使用AntD Spin覆盖图表区域，错误状态使用Alert提示。

### 阶段3：全局入口与接口适配
1. 删除`index.html`中TradingView script标签；
2. 确认`api.ts`中fetchKLineData的params支持limit和adj参数（已支持period参数，检查是否需要显式传递limit/adj）；
3. 不引入新npm依赖（lightweight-charts 4.2.3已安装）。

### 阶段4：自测与缺陷修复
1. 启动前端dev server + 后端服务；
2. 使用内部浏览器依次执行全部P0测试用例（TC01-TC15）；
3. 执行P1测试用例（TC16-TC25）；
4. 执行`npx tsc -b --noEmit`确认0 errors；
5. 微调scaleMargins比例和配色，确保视觉与国内主流股票软件（同花顺/东方财富）对齐；
6. 修复发现的问题（线条断裂、颜色错误、指标值异常等）。

### 阶段5：交付评审
交付产物：
1. 全部变更的源代码文件；
2. 自测验证记录（P0全过、P1结果说明）；
3. tsc -b 0 errors证明；
4. 问题修复说明（如有）。

---

## 十、风险识别与应对方案

| 风险点 | 影响等级 | 应对方案 |
|--------|---------|---------|
| **v4.2.3的priceScale+scaleMargins堆叠行为与预期不符**（如副图重叠、margin不生效） | 高 | 阶段0先做最小Demo验证：1个candlestick+1个volume histogram+scaleMargins，确认堆叠正确后再写完整代码；若存在版本问题，npm升级到lightweight-charts最新4.x（minor版本） |
| 500条K线接口响应超时（>1s） | 中 | 后端limit最大支持1000，默认150返回很快；如500条超时，降级为300条（MA250前50根bar留白） |
| 原始K线存在0值/NaN/异常高低价（high<low），导致指标计算异常 | 中 | fetchKLineData已有filter过滤NaN open；technical.ts函数内部增加对closes/highs/lows/volume的Number转换和isNaN检查，异常数据点跳过或返回null |
| 弹窗反复打开/关闭内存泄漏（Chart实例未正确销毁） | 中 | useEffect cleanup严格调用chart.remove()；所有ref在cleanup中置null；destroyOnHidden配合React生命周期保证销毁 |
| Segmented切换RSI/KDJ时priceScale未正确重绘 | 低 | 通过series.applyOptions({visible:true/false})控制，不销毁重建series；切换时osc priceScale自动重绘可见series |
| scaleMargins比例导致副图过于拥挤或留白过多 | 低 | 编码时先使用文档中的初始值，浏览器测试时微调top/bottom数值直到视觉舒适；不同屏幕尺寸通过autoSize自适应 |
| BOLL中轨与MA20颜色/宽度不一致产生"双细线"视觉错觉 | 低 | 不创建BOLL中轨series，仅依赖MA20显示中轨；BOLL上下轨使用低透明度（0.6）虚线弱化视觉权重 |
| MACD颜色逻辑误用柱子正负值代替DIF/DEA交叉 | 低 | 严格按K指定逻辑：dif>=dea红，dif<dea绿；code review时重点检查此处 |

---

## 十一、交付物清单

1. **源代码变更**：
   - `index.html`（删除TV script）
   - `src/features/stock-picker/components/StockAnalysisModal.tsx`（重写）
   - `src/features/stock-detail/api.ts`（如需显式传递limit/adj参数则小幅修改）
   - `src/lib/indicators/technical.ts`（新增指标计算库）
2. **自测验证记录**：覆盖所有P0测试用例（TC01-TC15）的浏览器验证说明；
3. **TypeScript编译检查**：`npx tsc -b --noEmit` 0 errors输出；
4. **性能测量记录**：指标计算耗时、图表渲染耗时数据。

---

## 十二、方案结论

本方案**零后端改造**，依托现有OHLCV接口数据，前端自主计算全套技术指标（MA/BOLL/MACD/RSI/KDJ/成交量）。采用lightweight-charts v4.2.3单Chart实例+多priceScale（通过priceScaleId+scaleMargins实现）架构，完全替代TradingView SaaS Widget：

- ✅ 无跨境CDN依赖，本地打包渲染，无网络被墙问题；
- ✅ 单Canvas实例，十字光标/缩放/平移天然同步，无需手写同步代码；
- ✅ 技术指标公式自主可控，支持后续扩展MA120/250、BOLL参数调整、自定义指标等；
- ✅ lightweight-charts已预装（40KB gzipped），无需新增npm依赖；
- ✅ 符合A股用户看盘习惯（涨绿跌红、MACD红多头绿空头、KDJ除零保护）；
- ✅ 保留后续扩展能力（指标参数自定义、形态标注、买卖信号标记等）。

方案v1.1修正了v1.0中`addPane()` API的错误描述，明确使用v4.2.3实际支持的priceScaleId+scaleMargins API，架构可直接进入编码实施阶段。
