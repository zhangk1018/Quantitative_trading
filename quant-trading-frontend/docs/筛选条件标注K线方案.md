# 筛选条件标注 K 线 — 实施计划 v1.0

## 一、功能背景

条件构建器（ConditionBuilder）支持 11 种预设条件，用户可自由组合（AND/OR）并用于选股。双击选股结果打开 K 线弹窗时，需将**每个条件在 K 线上的具体触发日期**以可视化标记（marker）的形式展示，便于用户回溯分析。

**核心认知澄清**：组合条件用于筛选股票，K 线标注标的是**每个条件各自的触发日期**，不计算 AND/OR 组合结果。举例：选了"早晨之星 AND RSI超卖"，K 线图上同时显示早晨之星和 RSI 超卖的标记，用户自行观察时间轴上的分布关系。

## 二、条件检测可行性

全部基于前端 K 线数据（OHLCV + volume）检测，零后端改动。

| 条件 | fieldKey | 检测方式 | 数据依赖 |
|------|----------|---------|---------|
| RSI超卖 | `rsi_oversold` | RSI(6) < 30 | close |
| 放量突破 | `volume_breakout` | volume > MA5(volume) × 2 | volume |
| MACD金叉 | `macd_golden_cross` | DIF 上穿 DEA | close |
| 底部放量 | `bottom_volume_macd` | RSI超卖 AND 放量突破（同日） | close + volume |
| 连续上涨 | `consecutive_up` | 连涨 ≥ 3 天 | close |
| 低估值 | `low_valuation` | ❌ 不可标注（需 PE/PB） | N/A |
| 早晨之星 | `pattern_morning_star` | `detectAllPatterns` | OHLCV |
| 黄昏之星 | `pattern_evening_star` | `detectAllPatterns` | OHLCV |
| 看涨吞没 | `pattern_bullish_engulfing` | `detectAllPatterns` | OHLCV |
| 看跌吞没 | `pattern_bearish_engulfing` | `detectAllPatterns` | OHLCV |
| 锤子线 | `pattern_hammer` | `detectAllPatterns` | OHLCV |

## 三、数据流

```
条件构建器（ScreenerContext.filterGroup.conditions[]）
  ↓  StockPickerView 读取
StockAnalysisModal（新增 conditions prop）
  ↓  K线数据加载完成后
condition-detector.ts 检测引擎
  ├─ 指标复用层：先计算 RSI、MACD、VolumeMA5
  ├─ 逐条件检测：注册表映射 fieldKey → detectFn
  └─ 输出 ConditionEvent[]
  ↓
StockAnalysisModal 转换为 LWC markers
  ↓
KLineChart（新增 markers prop）→ candle.setMarkers()
```

## 四、类型定义

```typescript
// 检测结果事件
interface ConditionEvent {
  time: string;           // K线日期，YYYY-MM-DD
  label: string;          // 条件显示名，如 "RSI超卖"
  type: ConditionFieldKey; // 条件类型
  color: string;          // 标记颜色
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square' | 'diamond';
  direction: 'buy' | 'sell' | 'neutral';
  value?: string;         // 触发时的具体数值，如 "RSI 28.3"
}

// 检测引擎接口
interface DetectResult {
  events: ConditionEvent[];
  undetectable: { fieldKey: string; label: string; reason: string }[];
}
```

## 五、检测引擎实现（condition-detector.ts）

### 5.1 架构：注册表模式

```typescript
// fieldKey → 检测函数 + 视觉配置 的映射表
const CONDITION_DETECTORS: Record<string, ConditionDetector> = {
  rsi_oversold: { detect: detectRsiOversold, config: { color: '#26A69A', shape: 'arrowUp', label: 'RSI超卖' } },
  volume_breakout: { detect: detectVolumeBreakout, config: { color: '#FF9800', shape: 'circle', label: '放量突破' } },
  macd_golden_cross: { detect: detectMacdGoldenCross, config: { color: '#2196F3', shape: 'arrowUp', label: 'MACD金叉' } },
  bottom_volume_macd: { detect: detectBottomVolumeMacd, config: { color: '#4CAF50', shape: 'diamond', label: '底部放量' } },
  consecutive_up: { detect: detectConsecutiveUp, config: { color: '#9C27B0', shape: 'square', label: '连续上涨' } },
  low_valuation: { detect: () => [], config: { color: '#888', shape: 'circle', label: '低估值' }, detectable: false },
  pattern_morning_star: { detect: detectPattern('morning_star'), config: { color: '#26A69A', shape: 'arrowUp', label: '早晨之星' } },
  pattern_evening_star: { detect: detectPattern('evening_star'), config: { color: '#EF5350', shape: 'arrowDown', label: '黄昏之星' } },
  pattern_bullish_engulfing: { detect: detectPattern('bullish_engulfing'), config: { color: '#26A69A', shape: 'arrowUp', label: '看涨吞没' } },
  pattern_bearish_engulfing: { detect: detectPattern('bearish_engulfing'), config: { color: '#EF5350', shape: 'arrowDown', label: '看跌吞没' } },
  pattern_hammer: { detect: detectPattern('hammer'), config: { color: '#2962FF', shape: 'arrowUp', label: '锤子线' } },
};
```

### 5.2 检测函数

| 条件 | 检测逻辑 |
|------|---------|
| RSI超卖 | `calcRSI(closes, 6)[i] < 30` |
| 放量突破 | `volume[i] > sma(volumes, 5)[i] * 2` |
| MACD金叉 | `dif[i] > dea[i] && dif[i-1] <= dea[i-1]` |
| 底部放量 | 同日满足 RSI超卖 AND 放量突破 |
| 连续上涨 | `close[i] > close[i-1]` 连续 ≥ 3 天 |
| pattern_* | 调用 `detectAllPatterns`，配置 `targetPatterns` 参数 |

### 5.3 指标复用

检测引擎内部在首次计算时，将 RSI、MACD、VolumeMA5 等中间结果缓存到局部变量，后续条件直接读取，避免重复计算 O(N)。

```
klineData → 一次性计算共用指标:
  closes: number[]
  rsi6: (number|null)[]
  dif: (number|null)[]
  dea: (number|null)[]
  volMa5: (number|null)[]
  volumes: number[]
  → 各 detectFn 直接从上述数组中取值判断
```

## 六、视觉配置

```typescript
CONDITION_VISUAL_CONFIG = {
  rsi_oversold:       { color: '#26A69A', shape: 'arrowUp',  label: 'RSI超卖', direction: 'buy' },
  volume_breakout:    { color: '#FF9800', shape: 'circle',   label: '放量突破', direction: 'neutral' },
  macd_golden_cross:  { color: '#2196F3', shape: 'arrowUp',  label: 'MACD金叉', direction: 'buy' },
  bottom_volume_macd: { color: '#4CAF50', shape: 'diamond',  label: '底部放量', direction: 'buy' },
  consecutive_up:     { color: '#9C27B0', shape: 'square',    label: '连续上涨', direction: 'buy' },
  pattern_morning_star:      { color: '#26A69A', shape: 'arrowUp',  label: '早晨之星', direction: 'buy' },
  pattern_evening_star:      { color: '#EF5350', shape: 'arrowDown', label: '黄昏之星', direction: 'sell' },
  pattern_bullish_engulfing: { color: '#26A69A', shape: 'arrowUp',  label: '看涨吞没', direction: 'buy' },
  pattern_bearish_engulfing: { color: '#EF5350', shape: 'arrowDown', label: '看跌吞没', direction: 'sell' },
  pattern_hammer:            { color: '#2962FF', shape: 'arrowUp',  label: '锤子线', direction: 'buy' },
}
```

## 七、文件变更清单

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/lib/indicators/condition-detector.ts` | **新增** | 检测引擎：注册表 + 各条件 detectFn + 指标复用 + 入口函数 `detectConditions()` |
| `src/lib/indicators/chart-config.ts` | 修改 | 新增 `CONDITION_VISUAL_CONFIG`，图例相关颜色 |
| `src/features/stock-picker/components/StockAnalysisModal.tsx` | 修改 | 新增 `conditions` prop；K 线加载完后调检测引擎；转换 markers；不可标注提示 |
| `src/features/stock-picker/components/KLineChart.tsx` | 修改 | 新增 `markers` prop；`candle.setMarkers()` 渲染；顶部图例条 |
| `src/features/stock-picker/StockPickerView.tsx` | 修改 | 从 ScreenerContext 读 `filterGroup.conditions`，传给 Modal |
| `src/features/stock-detail/api.ts` | 修改 | 新增 `ConditionEvent` 类型导出 |

## 八、交互细节

1. **图例条**：弹窗 K 线图上方显示当前条件的图例，每条对应一个颜色块 + 条件名，用户可点击显隐某个条件的标记
2. **悬浮详情**：鼠标悬浮 marker 时显示 `{条件名}: {数值}`，如 "RSI超卖: RSI 28.3"
3. **不可标注**：`low_valuation` 在顶部图例中灰色显示 + "需基本面数据" 文字提示
4. **加载状态**：检测期间显示 "正在检测条件..." 文字，完成后显示标记
5. **缓存**：`StockAnalysisModal` 内部用 `Map<stockCode, ConditionEvent[]>` 缓存检测结果，同股票不重算

## 九、不涉及的工作

- 后端 API 无需改动
- 数据库 / ETL 无需改动
- 无需引入新 npm 依赖
- 无需 Web Worker（500 条 × 8 条件 < 5ms）
- 无需策略模式 / 插件化架构（11 个条件用映射表足够）
- 无需 Zod 输入校验（数据来自前端 Context 自身）

## 十、验收标准

| 编号 | 场景 | 预期 |
|------|------|------|
| SC01 | 打开 K 线弹窗 | 图例条正确显示用户选中的条件（颜色 + 名称） |
| SC02 | 条件检测 | 各条件在对应日期显示正确颜色的 marker |
| SC03 | 图例显隐 | 点击图例条目，对应条件标记隐藏/显示 |
| SC04 | 悬浮详情 | 鼠标悬浮 marker 显示条件名 + 数值 |
| SC05 | 不可标注条件 | `low_valuation` 灰色显示并提示"需基本面数据" |
| SC06 | 切换股票 | 检测结果随股票切换更新 |
| SC07 | 缓存复用 | 同一股票再次打开不重复计算 |
| SC08 | 无选条件 | 未选任何条件时，弹窗不展示图例和标记 |