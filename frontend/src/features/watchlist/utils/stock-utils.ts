/**
 * utils/stock-utils.ts — 股票代码工具函数（单一事实来源）
 *
 * 所有市场判定逻辑在此统一维护，避免 store / UI 层重复实现。
 */

/** 系统分组（硬编码，不可删除） */
export const SYSTEM_GROUPS = ['全部', '沪深', '港股', '美股'] as const;
export type SystemGroup = (typeof SYSTEM_GROUPS)[number];
export const SYSTEM_GROUP_SET: ReadonlySet<string> = new Set(SYSTEM_GROUPS);

/**
 * 根据代码前缀判定所属市场分组。
 * - 沪深：6xxxx(上海) / 0xxxx,3xxxx(深圳)，6 位数字无后缀
 * - 港股：带 `.HK` 后缀
 * - 美股：其余（纯字母代码）
 */
export function detectMarketGroup(code: string): string {
  if (!code || code.length < 2) return '沪深';
  if (/\.HK$/i.test(code)) return '港股';
  const prefix = code.substring(0, 1);
  if (['6', '0', '3'].includes(prefix)) return '沪深';
  return '美股';
}

/** 市场键（cn/hk/us），供接口参数/逻辑分支复用；A股默认 cn */
export type MarketKey = 'cn' | 'hk' | 'us';
export function inferMarketKey(code: string | undefined): MarketKey | undefined {
  if (!code) return undefined;
  if (/\.HK$/i.test(code)) return 'hk';
  if (/^[A-Za-z][A-Za-z.-]*$/.test(code)) return 'us';
  return 'cn';
}

/**
 * 港股代码展示层补零（K 对齐口径：恒生主板个股展示 5 位，对齐港股通/交易软件惯例）。
 * - 接口层统一去前导零（yfinance：`9988.HK` / `700.HK` / `1.HK`）
 * - 展示层按 market padStart(5, '0') 补零至 5 位：`9988.HK→09988.HK`、`700.HK→00700.HK`、`1.HK→00001.HK`
 * - A股 / 美股原样返回
 */
export function formatStockCodeForDisplay(code: string, market?: string): string {
  const isHk = market === 'hk' || /\.HK$/i.test(code);
  if (isHk) {
    const num = code.replace(/\.HK$/i, '');
    return `${num.padStart(5, '0')}.HK`;
  }
  return code;
}