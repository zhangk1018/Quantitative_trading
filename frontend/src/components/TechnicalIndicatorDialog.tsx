/**
 * TechnicalIndicatorDialog.tsx - 技术指标配置弹窗
 *
 * 三种指标的形态：
 * 1. MA：自定义条件行（最多 10 行，重置后为空）
 *    - 字段下拉只有 [价格, MA]
 *    - 当 field=价格 时，数值输入框禁用（缺省用收盘价）
 *    - 指标下拉只有 [MA]
 * 2. MACD：4 个单选（低位金叉/底背离/高位死叉/顶背离）
 *    - 重置后无任何选择；未选时"确定"禁用
 * 3. BOLL：4 个单选（升穿上轨/升穿中轨/跌穿中轨/跌穿下轨）
 *    - 重置后无任何选择；未选时"确定"禁用
 *
 * 设计原则：
 * - 紧凑（窄宽度 + 小内边距）
 * - 顶部无 macOS 三色圆点
 * - 底部只有 [重置] [确定]（无"取消"）
 * - 点击遮罩或 ESC 静默关闭（不保存），仅"确定"提交
 *
 * 周期统一显示"日K"（侧边栏已移除周期 Tab）。
 */

import { useState, useEffect } from "react";

// ============================================
// 数据模型
// ============================================

export type TechnicalIndicator = "MA" | "MACD" | "BOLL";

/** MA 自定义条件行 */
export interface MaCondition {
  /** 字段：价格 / MA */
  field: "价格" | "MA";
  /** 数值（当 field=价格 时忽略，使用收盘价） */
  value: string;
  /** 关系运算符 */
  operator: "升穿" | "跌穿" | "大于" | "小于" | "等于";
  /** 参与比较的指标（仅 MA） */
  indicator: "MA";
  /** 指标参数（窗口，如 5/10/20/60） */
  parameter: string;
}

export const EMPTY_MA_CONDITION: MaCondition = {
  field: "价格",
  value: "",
  operator: "升穿",
  indicator: "MA",
  parameter: "20",
};

export type MacdSignal = "低位金叉" | "底背离" | "高位死叉" | "顶背离" | "";
export type BollSignal = "升穿上轨" | "升穿中轨" | "跌穿中轨" | "跌穿下轨" | "";

export interface MaConfig {
  conditions: MaCondition[];
}
export interface MacdConfig {
  signal: MacdSignal;
}
export interface BollConfig {
  signal: BollSignal;
}

export type IndicatorConfig = MaConfig | MacdConfig | BollConfig;

/** 默认配置：全部空（重置状态） */
export const DEFAULT_TECHNICAL_CONFIG: {
  MA: MaConfig;
  MACD: MacdConfig;
  BOLL: BollConfig;
} = {
  MA: { conditions: [] },
  MACD: { signal: "" },
  BOLL: { signal: "" },
};

/** 校验"确定"按钮是否可点击 */
function isConfigValid(
  indicator: TechnicalIndicator,
  cfg: IndicatorConfig
): boolean {
  if (indicator === "MA") {
    const c = cfg as MaConfig;
    // 至少 1 条条件；任意一行有任一字段非空即视为有效
    return c.conditions.length > 0;
  }
  if (indicator === "MACD") {
    return (cfg as MacdConfig).signal !== "";
  }
  return (cfg as BollConfig).signal !== "";
}

// ============================================
// 弹窗组件
// ============================================

interface TechnicalIndicatorDialogProps {
  /** 弹窗对应的指标 */
  indicator: TechnicalIndicator;
  /** 当前已保存配置（编辑时回显；首次添加通常为空） */
  initialConfig: IndicatorConfig;
  /** 弹窗标题后缀（默认"日K"） */
  cycleLabel?: string;
  /** 确认回调（父组件接管持久化） */
  onConfirm: (config: IndicatorConfig) => void;
  /** 关闭回调（点击遮罩 / ESC 触发，不提交） */
  onCancel: () => void;
}

export default function TechnicalIndicatorDialog({
  indicator,
  initialConfig,
  cycleLabel = "日K",
  onConfirm,
  onCancel,
}: TechnicalIndicatorDialogProps) {
  // 各指标在弹窗内维护一份编辑态草稿
  const [maDraft, setMaDraft] = useState<MaConfig>(
    () => (indicator === "MA" ? (initialConfig as MaConfig) : { conditions: [] })
  );
  const [macdDraft, setMacdDraft] = useState<MacdConfig>(
    () => (indicator === "MACD" ? (initialConfig as MacdConfig) : { signal: "" })
  );
  const [bollDraft, setBollDraft] = useState<BollConfig>(
    () => (indicator === "BOLL" ? (initialConfig as BollConfig) : { signal: "" })
  );

  // ESC 静默关闭（不提交）
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel]);

  // 重置：全部清空
  const handleReset = () => {
    if (indicator === "MA") {
      setMaDraft({ conditions: [] });
    } else if (indicator === "MACD") {
      setMacdDraft({ signal: "" });
    } else {
      setBollDraft({ signal: "" });
    }
  };

  // 当前生效的草稿（用于校验/确认）
  const currentDraft: IndicatorConfig =
    indicator === "MA"
      ? maDraft
      : indicator === "MACD"
        ? macdDraft
        : bollDraft;
  const confirmDisabled = !isConfigValid(indicator, currentDraft);

  const handleConfirm = () => {
    if (confirmDisabled) return;
    onConfirm(currentDraft);
  };

  // 标题：MA·日K
  const title = `${indicator}·${cycleLabel}`;

  // 不同指标的弹窗宽度
  const widthClass = indicator === "MA" ? "w-[520px]" : "w-[320px]";

  return (
    // 遮罩：点击静默关闭
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60"
      onClick={onCancel}
      data-testid={`tech-dialog-${indicator}`}
    >
      {/* 弹窗本体（紧凑） */}
      <div
        className={`bg-white text-gray-900 rounded-lg shadow-2xl ${widthClass} max-w-[92vw] overflow-hidden`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题栏：无三色圆点，仅居中标题 */}
        <div className="px-4 py-2.5 border-b border-gray-200 bg-gray-50 text-center">
          <h3 className="text-sm font-medium text-gray-700">{title}</h3>
        </div>

        {/* 内容区（紧凑） */}
        <div className="p-4">
          {indicator === "MA" && (
            <MaForm config={maDraft} onChange={setMaDraft} />
          )}
          {indicator === "MACD" && (
            <RadioList
              options={["低位金叉", "底背离", "高位死叉", "顶背离"]}
              value={macdDraft.signal}
              onChange={(v) => setMacdDraft({ signal: v as MacdSignal })}
            />
          )}
          {indicator === "BOLL" && (
            <RadioList
              options={["升穿上轨", "升穿中轨", "跌穿中轨", "跌穿下轨"]}
              value={bollDraft.signal}
              onChange={(v) => setBollDraft({ signal: v as BollSignal })}
            />
          )}
        </div>

        {/* 底部操作栏：重置 / 确定（无取消） */}
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-200 bg-gray-50">
          <button
            onClick={handleReset}
            className="px-3 py-1 text-xs border border-gray-300 rounded text-gray-700 hover:bg-gray-100 transition-colors"
            data-testid={`tech-dialog-${indicator}-reset`}
          >
            重置
          </button>
          <button
            onClick={handleConfirm}
            disabled={confirmDisabled}
            className="px-4 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
            data-testid={`tech-dialog-${indicator}-confirm`}
          >
            确定
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================
// MA 自定义条件表单
// ============================================

const MA_MAX_ROWS = 10;

function MaForm({
  config,
  onChange,
}: {
  config: MaConfig;
  onChange: (next: MaConfig) => void;
}) {
  const { conditions } = config;

  const updateRow = (idx: number, patch: Partial<MaCondition>) => {
    const next = conditions.map((row, i) => (i === idx ? { ...row, ...patch } : row));
    onChange({ conditions: next });
  };

  const removeRow = (idx: number) => {
    onChange({ conditions: conditions.filter((_, i) => i !== idx) });
  };

  const addRow = () => {
    if (conditions.length >= MA_MAX_ROWS) return;
    onChange({ conditions: [...conditions, { ...EMPTY_MA_CONDITION }] });
  };

  return (
    <div data-testid="ma-form">
      {/* 自定义单选 + 添加按钮（同行紧凑） */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-3.5 h-3.5 rounded-full border-2 border-blue-500 flex items-center justify-center">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
          </span>
          <span className="text-xs text-gray-700">自定义</span>
        </div>
        <button
          onClick={addRow}
          disabled={conditions.length >= MA_MAX_ROWS}
          className="flex items-center gap-1 text-xs text-blue-500 hover:text-blue-600 disabled:text-gray-400 disabled:cursor-not-allowed"
          data-testid="ma-add-row"
        >
          <span className="inline-block w-3.5 h-3.5 rounded-full border-2 border-current flex items-center justify-center text-[10px] leading-none">
            +
          </span>
          <span>
            添加({conditions.length}/{MA_MAX_ROWS})
          </span>
        </button>
      </div>

      {/* 条件行：紧凑布局 */}
      <div className="space-y-1.5">
        {conditions.map((row, idx) => {
          // field=价格 时数值禁用（缺省用收盘价）
          const valueDisabled = row.field === "价格";
          return (
            <div
              key={idx}
              className="flex items-center gap-1.5"
              data-testid={`ma-row-${idx}`}
            >
              {/* 字段：[价格, MA] */}
              <SelectCell
                value={row.field}
                options={["价格", "MA"]}
                onChange={(v) =>
                  updateRow(idx, { field: v as MaCondition["field"] })
                }
              />
              {/* 数值：field=价格 时禁用 */}
              <input
                type="text"
                value={valueDisabled ? "" : row.value}
                onChange={(e) => updateRow(idx, { value: e.target.value })}
                disabled={valueDisabled}
                placeholder={valueDisabled ? "收盘价" : ""}
                title={valueDisabled ? "选'价格'时缺省使用收盘价" : ""}
                className="w-16 px-1.5 py-1 text-xs border border-gray-300 rounded text-gray-800 focus:outline-none focus:border-blue-500 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed"
                data-testid={`ma-row-${idx}-value`}
              />
              {/* 运算符 */}
              <SelectCell
                value={row.operator}
                options={["升穿", "跌穿", "大于", "小于", "等于"]}
                onChange={(v) =>
                  updateRow(idx, { operator: v as MaCondition["operator"] })
                }
              />
              {/* 比较指标：仅 MA */}
              <SelectCell
                value={row.indicator}
                options={["MA"]}
                onChange={(v) =>
                  updateRow(idx, { indicator: v as MaCondition["indicator"] })
                }
              />
              {/* 参数 */}
              <input
                type="text"
                value={row.parameter}
                onChange={(e) => updateRow(idx, { parameter: e.target.value })}
                className="w-12 px-1.5 py-1 text-xs border border-gray-300 rounded text-gray-800 focus:outline-none focus:border-blue-500"
                data-testid={`ma-row-${idx}-param`}
              />
              {/* 删除按钮 */}
              <button
                onClick={() => removeRow(idx)}
                className="w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center text-xs leading-none hover:bg-red-600 transition-colors flex-shrink-0"
                title="删除该条件"
                data-testid={`ma-row-${idx}-remove`}
              >
                −
              </button>
            </div>
          );
        })}
        {conditions.length === 0 && (
          <div
            className="text-center text-xs text-gray-400 py-4 border border-dashed border-gray-200 rounded"
            data-testid="ma-empty"
          >
            暂无条件，点上方"添加"创建一行
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================
// 单选列表（MACD / BOLL 共用）— 2x2 紧凑网格
// ============================================

function RadioList({
  options,
  value,
  onChange,
}: {
  options: readonly string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-1.5" data-testid="radio-grid">
      {options.map((opt) => {
        const selected = value === opt;
        return (
          <button
            key={opt}
            type="button"
            onClick={() => onChange(opt)}
            className={`flex items-center gap-1.5 px-2 py-1.5 text-xs rounded border transition-colors text-left ${
              selected
                ? "border-blue-500 bg-blue-50 text-blue-700"
                : "border-gray-200 text-gray-700 hover:bg-gray-50"
            }`}
            data-testid={`radio-${opt}`}
          >
            <span
              className={`inline-block w-3 h-3 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                selected ? "border-blue-500" : "border-gray-300"
              }`}
            >
              {selected && <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />}
            </span>
            <span className="truncate">{opt}</span>
          </button>
        );
      })}
    </div>
  );
}

// ============================================
// 通用单元格（下拉）
// ============================================

function SelectCell({
  value,
  options,
  onChange,
}: {
  value: string;
  options: readonly string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none pl-1.5 pr-5 py-1 text-xs border border-gray-300 rounded text-gray-800 bg-white focus:outline-none focus:border-blue-500 cursor-pointer"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 text-gray-500 text-[10px]">
        ▼
      </span>
    </div>
  );
}
