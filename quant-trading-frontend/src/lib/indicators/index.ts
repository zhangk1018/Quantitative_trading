// lib/indicators/index.ts

// 类型导出
export * from './types';

// 纯算法
export {
  cleanBars,
  sma,
  ema,
  sampleStdDev,
  calcRSI,
  calcKDJ,
  calcAllIndicators,
  type KlineBar,
  type CalculatedIndicators,
} from './indicators';

// 图表适配
export {
  buildChartData,
  makeHorizontalLine,
  type ChartDataResult,
} from './chart-adapter';

// 常量与配置
export {
  DETECTION_CONFIG,
  PATTERN_MARKER_CONFIG,
  MA_CONFIG,
  ChartError,
  ChartErrorType,
  validateConfig,
  CONFIG_RANGES,
} from './chartConstants';

// 工具函数
export {
  getOpen,
  getHigh,
  getLow,
  getClose,
  getVolume,
  isValidBar,
  getBodyTop,
  getBodyBottom,
  getBodySize,
  getRange,
  isBullish,
  isBearish,
  getUpperShadow,
  getLowerShadow,
  precomputeBars,
  type PrecomputedBar,
} from './barUtils';

// 形态检测
export {
  detectAllPatterns,
  hasAnyPattern,
} from './patternDetector';

// 注意：chartUtils 为 hooks 层，单独导出
// 如需使用，可从 hooks/chartUtils 导入