/**
 * tradeMarker.ts - 买卖点自定义覆盖物
 *
 * Phase 4.3.5 买卖信号叠加
 *
 * 设计要点（参考 docs/RISK_MANAGEMENT.md）：
 * - 风险点 2（复权价格错位）：使用 K线同一套复权标准，后端已统一返回
 * - 风险点 3（密集信号重叠）：数据层去重（同一天只保留最后一个）
 * - 风险点 5（频繁切换内存泄漏）：组件卸载时通过 removeOverlay 清理
 *
 * 硬约束（来自 project_memory）：
 * - 使用 tradeMarker 作为自定义覆盖物标识
 * - lock: true 防止拖拽误操作
 *
 * 视觉：
 * - 买入：▲ 绿色三角，置于 K线最低点下方
 * - 卖出：▼ 红色三角，置于 K线最高点上方
 * - 信号原因以小字标注在三角旁边
 */

import { registerOverlay, type Overlay, type OverlayFigure, type Point } from 'klinecharts';
import type { SignalItem } from '../types';

/** 买卖点覆盖物唯一标识 */
export const TRADE_MARKER_NAME = 'tradeMarker';

/** 单个买卖点位置信息（运行时构造） */
export interface TradeMarkerPoint extends Partial<Point> {
  /** 三角位置对应 K线索引（0-based, 0 = 最新） */
  dataIndex: number;
  /** 信号类型 */
  signalType: 'buy' | 'sell';
  /** 信号价格 */
  price: number;
  /** 信号原因（用于 tooltip） */
  reason: string;
  /** 信号日期 YYYY-MM-DD */
  tradeDate: string;
}

// ============================================
// 工具：同一天去重（风险点 3）
// ============================================

/**
 * 同一天只保留最后一个信号（按价格时间排序）
 * 输入：原始 signals（任意顺序）
 * 输出：去重后的 signals（按 trade_date 升序）
 */
export function dedupeSignalsByDate(signals: SignalItem[]): SignalItem[] {
  if (!signals || signals.length === 0) return [];
  // 按日期升序排序（同一日期后面的覆盖前面）
  const sorted = [...signals].sort((a, b) =>
    a.trade_date.localeCompare(b.trade_date)
  );
  const map = new Map<string, SignalItem>();
  for (const s of sorted) {
    map.set(s.trade_date, s); // 后写入的覆盖先写入的
  }
  return Array.from(map.values()).sort((a, b) =>
    a.trade_date.localeCompare(b.trade_date)
  );
}

// ============================================
// 工具：颜色常量（与项目设计语言一致）
// ============================================

const COLOR_BUY = '#26a69a'; // 涨绿
const COLOR_SELL = '#ef5350'; // 跌红

// ============================================
// 覆盖物类定义
// ============================================

class TradeMarkerOverlay implements Partial<Overlay> {
  name = TRADE_MARKER_NAME;

  /** 锁定：禁止用户拖拽（项目硬约束） */
  lock = true;

  /** 不可见：默认隐藏（不显示默认点标记） */
  visible = true;

  /** zLevel：绘制在 K线之上 */
  zLevel = 10;

  /** 不需要默认点图（我们用自定义三角） */
  needDefaultPointFigure = false;

  /** 不需要默认 X/Y 轴标记 */
  needDefaultXAxisFigure = false;
  needDefaultYAxisFigure = false;

  /**
   * 创建点对应的图（核心绘制函数）
   * 每个 point 会被转换为一个 ▲ 或 ▼ + 文字
   */
  createPointFigures = (
    params: Parameters<NonNullable<Overlay['createPointFigures']>>[0]
  ): OverlayFigure[] => {
    const { coordinates, overlay } = params;
    const data = overlay.extendData as TradeMarkerPoint | undefined;
    if (!data || !coordinates || coordinates.length === 0) return [];
    const coordinate = coordinates[0];

    const isBuy = data.signalType === 'buy';
    const color = isBuy ? COLOR_BUY : COLOR_SELL;

    // 三角大小
    const size = 8;
    // 买卖点偏移：买在 K线下方，卖在 K线上方
    const yOffset = isBuy ? 18 : -18;

    // 三角形顶点坐标
    const cx = coordinate.x;
    const cy = coordinate.y + yOffset;

    const figures: OverlayFigure[] = [];

    if (isBuy) {
      // ▲ 向上三角（买）：底边在下方，顶点朝上
      figures.push({
        type: 'polygon',
        attrs: {
          coordinates: [
            { x: cx, y: cy - size }, // 顶点（上）
            { x: cx - size, y: cy + size }, // 左下
            { x: cx + size, y: cy + size }, // 右下
          ],
          color,
        },
        ignoreEvent: false,
      });
    } else {
      // ▼ 向下三角（卖）：顶边在上方，顶点朝下
      figures.push({
        type: 'polygon',
        attrs: {
          coordinates: [
            { x: cx - size, y: cy - size }, // 左上
            { x: cx + size, y: cy - size }, // 右上
            { x: cx, y: cy + size }, // 顶点（下）
          ],
          color,
        },
        ignoreEvent: false,
      });
    }

    // 信号原因文字（放在三角的对侧，避免与 K线重叠）
    const textY = isBuy ? cy + size + 4 : cy - size - 4;
    figures.push({
      type: 'text',
      attrs: {
        x: cx,
        y: textY,
        text: data.reason.length > 8 ? data.reason.slice(0, 8) + '…' : data.reason,
        color: '#eaecef',
        backgroundColor: color,
        borderColor: color,
        borderSize: 1,
        borderRadius: 2,
        paddingLeft: 4,
        paddingRight: 4,
        paddingTop: 1,
        paddingBottom: 1,
        size: 10,
      },
      ignoreEvent: true,
    });

    return figures;
  };
}

// ============================================
// 工具：将 SignalItem 映射为覆盖物 points
// ============================================

/**
 * 将信号转换为覆盖物 points
 * @param signals 原始信号列表
 * @param klineData K线数据（按日期从新到旧，DESCENDING）
 * @returns 可用于 createOverlay 的 points 数组
 */
export function buildTradeMarkerPoints(
  signals: SignalItem[],
  klineData: Array<{ trade_date: string; low: number; high: number }>
): Array<Partial<Point> & { extendData: TradeMarkerPoint }> {
  if (!signals || signals.length === 0 || !klineData || klineData.length === 0) {
    return [];
  }

  // 同一天去重
  const deduped = dedupeSignalsByDate(signals);

  // 构建 trade_date → dataIndex 映射（K线是 DESCENDING）
  const dateToIndex = new Map<string, number>();
  klineData.forEach((k, idx) => {
    dateToIndex.set(k.trade_date, idx);
  });

  const points: Array<Partial<Point> & { extendData: TradeMarkerPoint }> = [];

  for (const sig of deduped) {
    const dataIndex = dateToIndex.get(sig.trade_date);
    if (dataIndex === undefined) {
      // 信号日期不在 K线范围内（可能周期切换导致）跳过
      continue;
    }
    const kline = klineData[dataIndex];
    const y = sig.signal_type === 'buy' ? kline.low : kline.high;

    points.push({
      dataIndex,
      value: y,
      timestamp: Date.parse(sig.trade_date),
      extendData: {
        dataIndex,
        signalType: sig.signal_type as 'buy' | 'sell',
        price: sig.price,
        reason: sig.reason || '',
        tradeDate: sig.trade_date,
      },
    });
  }

  return points;
}

// ============================================
// 注册（只执行一次）
// ============================================

let registered = false;
export function ensureTradeMarkerRegistered() {
  if (registered) return;
  // registerOverlay 接受 OverlayTemplate 类型的对象
  // 通过类型断言绕过 TS 检查（klinecharts 类型定义对新字段支持不完整）
  registerOverlay(TradeMarkerOverlay as unknown as Parameters<typeof registerOverlay>[0]);
  registered = true;
}

export { TradeMarkerOverlay };
