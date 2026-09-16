/**
 * 自编卖出策略创建/编辑抽屉（对齐买入策略 CustomIndicatorModal 设计风格）
 *
 * 设计要点：
 * - Drawer + Monaco Editor（与买入策略一致）
 * - 字段插入按钮（行情数据 + NumPy 函数 + 常用模式）
 * - OnBlur 实时校验（名称唯一性 + 公式合法性）
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Drawer,
  Form,
  Input,
  Select,
  Space,
  Button,
  InputNumber,
  Tooltip,
  Alert,
} from 'antd';
import { QuestionCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import Editor, { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';
import type { editor } from 'monaco-editor';

loader.config({ monaco });

import { INDICATOR_OPERATORS, validateIndicatorName } from '../../stock-picker/types/customIndicator';
import {
  CustomSellStrategy,
  isSellStrategyNameTaken,
  validateSellStrategyFormula,
  MOCK_USER_ID,
} from '../../backtest/utils/customSellStrategyStorage';
import type { BacktestIndicatorOperator, BacktestIndicatorThreshold } from '../../backtest/backtestTypes';

interface SellStrategyModalProps {
  /** 抽屉标题 */
  title: string;
  /** 编辑时传入已有策略（创建时为 null） */
  editing?: CustomSellStrategy | null;
  /** 当前用户 ID */
  userId?: string;
  /** 点击确定时回调（由父组件调 storage 保存） */
  onConfirm: (data: {
    name: string;
    formula: string;
    operator: BacktestIndicatorOperator;
    defaultThreshold: BacktestIndicatorThreshold;
    description: string;
  }) => void;
  /** 点击取消或关闭时回调 */
  onCancel: () => void;
}

// 内部表单状态
interface FormState {
  name: string;
  formula: string;
  operator: BacktestIndicatorOperator;
  defaultThreshold: number | [number, number];
  description: string;
}

const defaultFormState: FormState = {
  name: '',
  formula: '',
  operator: '>' as BacktestIndicatorOperator,
  defaultThreshold: 0,
  description: '',
};

// 字段插入候选项
interface FieldCandidate {
  key: string;
  label: string;
  insertText: string;
  group: 'data' | 'numpy' | 'pattern';
}

const PYTHON_HELPERS: FieldCandidate[] = [
  // 行情数据
  { key: 'close', label: 'close 收盘价数组', insertText: 'close_prices', group: 'data' },
  { key: 'high', label: 'high 最高价数组', insertText: 'high_prices', group: 'data' },
  { key: 'low', label: 'low 最低价数组', insertText: 'low_prices', group: 'data' },
  { key: 'open', label: 'open 开盘价数组', insertText: 'open_prices', group: 'data' },
  { key: 'volume', label: 'volume 成交量数组', insertText: 'volumes', group: 'data' },
  // numpy 函数
  { key: 'np_array', label: 'np.array()', insertText: 'np.array(close_prices, dtype=float)', group: 'numpy' },
  { key: 'np_mean', label: 'np.mean()', insertText: 'np.mean(', group: 'numpy' },
  { key: 'np_max', label: 'np.max()', insertText: 'np.max(', group: 'numpy' },
  { key: 'np_min', label: 'np.min()', insertText: 'np.min(', group: 'numpy' },
  { key: 'np_std', label: 'np.std()', insertText: 'np.std(', group: 'numpy' },
  { key: 'np_convolve', label: 'np.convolve()', insertText: 'np.convolve(', group: 'numpy' },
  // 常用模式
  { key: 'for_loop', label: 'for 循环(天)', insertText: 'for i in range(len(c)):', group: 'pattern' },
  { key: 'range_len', label: 'range(len())', insertText: 'range(len(c))', group: 'pattern' },
  { key: 'tolist', label: '.tolist()', insertText: '.tolist()', group: 'pattern' },
  { key: 'none_pad', label: '[None] * n', insertText: '[None] * n', group: 'pattern' },
];

// 卖出策略公式示例
const SELL_FORMULA_EXAMPLE =
  'def calculate(open_prices, high_prices, low_prices, close_prices, volumes):\n' +
  '    """返回每日卖出信号数组（1=卖出, 0=持有）"""\n' +
  '    # 计算 5 日均线\n' +
  '    ma5 = [None] * 4 + [\n' +
  '        sum(close_prices[i-4:i+1]) / 5 for i in range(4, len(close_prices))\n' +
  '    ]\n' +
  '    # 收盘价跌破 MA5 时卖出\n' +
  '    return [1 if ma5[i] and close_prices[i] < ma5[i] else 0 for i in range(len(close_prices))]';

export const SellStrategyModal: React.FC<SellStrategyModalProps> = ({
  title,
  editing = null,
  userId = MOCK_USER_ID,
  onConfirm,
  onCancel,
}) => {
  const [formState, setFormState] = useState<FormState>(() => buildFromEditing(editing));
  const [nameError, setNameError] = useState<string | null>(null);
  const [formulaError, setFormulaError] = useState<string | null>(null);
  const [formulaWarnings, setFormulaWarnings] = useState<string[]>([]);

  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const handleFormulaBlurRef = useRef<() => void>(() => {});

  useEffect(() => {
    setFormState(buildFromEditing(editing));
    setNameError(null);
    setFormulaError(null);
    setFormulaWarnings([]);
  }, [editing]);

  const updateField = useCallback(<K extends keyof FormState>(key: K, value: FormState[K]) => {
    setFormState((s) => ({ ...s, [key]: value }));
  }, []);

  // 名称 OnBlur 校验
  const handleNameBlur = () => {
    const v = formState.name.trim();
    if (!v) {
      setNameError(null);
      return;
    }
    const err = validateIndicatorName(v);
    if (err) {
      setNameError(err);
    } else if (isSellStrategyNameTaken(v, editing?.id ?? null, userId)) {
      setNameError(`卖出策略名称"${v}"已存在`);
    } else {
      setNameError(null);
    }
  };

  // 公式 OnBlur 校验
  const handleFormulaBlur = () => {
    const v = formState.formula;
    if (!v || !v.trim()) {
      setFormulaError(null);
      setFormulaWarnings([]);
      return;
    }
    const result = validateSellStrategyFormula(v);
    if (!result.valid) {
      setFormulaError(result.errors[0] || '公式无效');
      setFormulaWarnings([]);
    } else if (result.warnings.length > 0) {
      setFormulaError(null);
      setFormulaWarnings(result.warnings);
    } else {
      setFormulaError(null);
      setFormulaWarnings([]);
    }
  };
  handleFormulaBlurRef.current = handleFormulaBlur;

  // Monaco 挂载
  const handleEditorMount = (editorInstance: editor.IStandaloneCodeEditor) => {
    editorRef.current = editorInstance;
    editorInstance.onDidBlurEditorWidget(() => {
      handleFormulaBlurRef.current();
    });
  };

  // 光标位置插入
  const insertAtCursor = (text: string) => {
    const editor = editorRef.current;
    if (!editor) return;
    const position = editor.getPosition();
    if (!position) return;
    editor.executeEdits('sell-strategy-insert', [
      {
        range: {
          startLineNumber: position.lineNumber,
          startColumn: position.column,
          endLineNumber: position.lineNumber,
          endColumn: position.column,
        },
        text,
        forceMoveMarkers: true,
      },
    ]);
    const lines = text.split('\n');
    const newColumn =
      lines.length === 1 ? position.column + text.length : lines[lines.length - 1].length + 1;
    editor.setPosition({ lineNumber: position.lineNumber + lines.length - 1, column: newColumn });
    editor.focus();
  };

  // 切换算子时处理阈值
  const handleOperatorChange = (op: BacktestIndicatorOperator) => {
    updateField('operator', op);
    const mode = getOperatorMode(op);
    if (mode === 'single') {
      updateField('defaultThreshold', ensureSingle(formState.defaultThreshold));
    } else {
      updateField('defaultThreshold', ensureDouble(formState.defaultThreshold));
    }
  };

  // 提交
  const handleSubmit = () => {
    const trimmedName = formState.name.trim();
    if (!trimmedName) {
      setNameError('策略名称不能为空');
      return;
    }
    const nameErr = validateIndicatorName(trimmedName);
    if (nameErr) {
      setNameError(nameErr);
      return;
    }
    if (isSellStrategyNameTaken(trimmedName, editing?.id ?? null, userId)) {
      setNameError(`卖出策略名称"${trimmedName}"已存在`);
      return;
    }
    const trimmedFormula = formState.formula.trim();
    if (!trimmedFormula) {
      setFormulaError('公式不能为空');
      return;
    }
    const formulaResult = validateSellStrategyFormula(formState.formula);
    if (!formulaResult.valid) {
      setFormulaError(formulaResult.errors[0] || '公式无效');
      setFormulaWarnings([]);
      return;
    }

    onConfirm({
      name: trimmedName,
      formula: formState.formula,
      operator: formState.operator,
      defaultThreshold: formState.defaultThreshold ?? 0,
      description: formState.description,
    });
  };

  const isEdit = !!editing;
  const submitDisabled =
    !formState.name.trim() || !formState.formula.trim() || !!nameError || !!formulaError;

  return (
    <Drawer
      open
      title={title}
      onClose={onCancel}
      width={720}
      destroyOnHidden
      maskClosable={false}
      extra={
        <Space size="small" data-testid="sell-strategy-modal-extra">
          <Button size="small" onClick={onCancel} data-testid="sell-strategy-modal-cancel">
            取消
          </Button>
          <Button
            size="small"
            type="primary"
            disabled={submitDisabled}
            onClick={handleSubmit}
            data-testid="sell-strategy-modal-confirm"
          >
            {isEdit ? '保存' : '创建'}
          </Button>
        </Space>
      }
      data-testid="sell-strategy-modal"
    >
      <Form layout="vertical" size="small" className="py-1">
        {/* 1. 策略名称 */}
        <Form.Item
          label="策略名称"
          required
          validateStatus={nameError ? 'error' : ''}
          help={nameError || '2-30 字符，中英文数字下划线连字符括号'}
        >
          <Input
            value={formState.name}
            onChange={(e) => {
              updateField('name', e.target.value);
              if (nameError) setNameError(null);
            }}
            onBlur={handleNameBlur}
            placeholder="如：跌破5日均线卖出"
            maxLength={30}
            data-testid="sell-strategy-modal-name"
          />
        </Form.Item>

        {/* 2. 公式 */}
        <Form.Item
          label={
            <span className="flex items-center justify-between w-full">
              <span>
                卖出策略脚本{' '}
                <Tooltip title="Python 脚本，定义 calculate(open_prices, high_prices, low_prices, close_prices, volumes) 函数，返回每日卖出信号数组（1=卖出, 0=持有）">
                  <QuestionCircleOutlined className="text-text-secondary" />
                </Tooltip>
              </span>
              <span className="text-text-secondary text-xs font-normal">Python · Monaco Editor</span>
            </span>
          }
          required
          validateStatus={formulaError ? 'error' : formulaWarnings.length > 0 ? 'warning' : ''}
          help={
            formulaError
              ? formulaError
              : formulaWarnings.length > 0
                ? formulaWarnings.map((w, i) => <div key={i} className="text-warning">⚠ {w}</div>)
                : 'OnBlur 时校验（输入过程中不打扰）'
          }
        >
          <div
            className="border border-border-color rounded overflow-hidden bg-bg-elevated"
            data-testid="sell-strategy-modal-formula-editor"
          >
            <Editor
              height="180px"
              language="python"
              value={formState.formula}
              onChange={(v) => {
                updateField('formula', v ?? '');
                if (formulaError) setFormulaError(null);
                if (formulaWarnings.length > 0) setFormulaWarnings([]);
              }}
              onMount={handleEditorMount}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                tabSize: 2,
                renderLineHighlight: 'gutter',
                folding: true,
                lineDecorationsWidth: 6,
                lineNumbersMinChars: 3,
              }}
              theme="vs-dark"
            />
          </div>

          {/* 快速填充示例 + 字段插入按钮区 */}
          <div className="mt-2 space-y-1.5" data-testid="sell-strategy-modal-field-insert">
            <div>
              <Button
                size="small"
                onClick={() => {
                  updateField('formula', SELL_FORMULA_EXAMPLE);
                  setFormulaError(null);
                  setFormulaWarnings([]);
                }}
              >
                <ThunderboltOutlined /> 填充示例（跌破 MA5 卖出）
              </Button>
            </div>
            <div className="flex items-start gap-2 flex-wrap">
              <span className="text-text-secondary text-xs mt-1 w-14 flex-shrink-0">行情数据：</span>
              <Space size={4} wrap>
                {PYTHON_HELPERS.filter((c) => c.group === 'data').map((c) => (
                  <Button
                    key={c.key}
                    size="small"
                    onClick={() => insertAtCursor(c.insertText)}
                    data-testid={`sell-strategy-modal-insert-${c.key}`}
                  >
                    {c.label}
                  </Button>
                ))}
              </Space>
            </div>
            <div className="flex items-start gap-2 flex-wrap">
              <span className="text-text-secondary text-xs mt-1 w-14 flex-shrink-0">NumPy 函数：</span>
              <Space size={4} wrap>
                {PYTHON_HELPERS.filter((c) => c.group === 'numpy').map((c) => (
                  <Button
                    key={c.key}
                    size="small"
                    onClick={() => insertAtCursor(c.insertText)}
                  >
                    {c.label}
                  </Button>
                ))}
              </Space>
            </div>
            <div className="flex items-start gap-2 flex-wrap">
              <span className="text-text-secondary text-xs mt-1 w-14 flex-shrink-0">常用模式：</span>
              <Space size={4} wrap>
                {PYTHON_HELPERS.filter((c) => c.group === 'pattern').map((c) => (
                  <Button
                    key={c.key}
                    size="small"
                    onClick={() => insertAtCursor(c.insertText)}
                  >
                    {c.label}
                  </Button>
                ))}
              </Space>
            </div>
          </div>
        </Form.Item>

        {/* 3. 判定算子 + 阈值 */}
        <Form.Item label="判定算子" required>
          <Select
            value={formState.operator}
            onChange={handleOperatorChange}
            options={INDICATOR_OPERATORS.map((o) => ({ value: o.value, label: o.label }))}
            data-testid="sell-strategy-modal-operator"
          />
        </Form.Item>

        {getOperatorMode(formState.operator) === 'single' ? (
          <Form.Item label="判定阈值（单值）">
            <InputNumber
              value={typeof formState.defaultThreshold === 'number' ? formState.defaultThreshold : 0}
              onChange={(v) => updateField('defaultThreshold', v ?? 0)}
              className="w-full"
              placeholder="如：0.97"
              step={0.01}
              data-testid="sell-strategy-modal-threshold-single"
            />
          </Form.Item>
        ) : (
          <Form.Item label="判定阈值（双值：区间/上穿/下穿）">
            <Space.Compact className="w-full">
              <InputNumber
                value={getMin(formState.defaultThreshold)}
                onChange={(v) =>
                  updateField('defaultThreshold', [v ?? 0, getMax(formState.defaultThreshold)])
                }
                placeholder="最小值/线A"
                className="w-full"
              />
              <InputNumber
                value={getMax(formState.defaultThreshold)}
                onChange={(v) =>
                  updateField('defaultThreshold', [getMin(formState.defaultThreshold), v ?? 0])
                }
                placeholder="最大值/线B"
                className="w-full"
              />
            </Space.Compact>
          </Form.Item>
        )}

        {/* 4. 说明 */}
        <Form.Item label="策略说明">
          <Input.TextArea
            value={formState.description}
            onChange={(e) => updateField('description', e.target.value)}
            placeholder="如：收盘价跌破 5 日均线时触发卖出信号"
            autoSize={{ minRows: 2, maxRows: 4 }}
            data-testid="sell-strategy-modal-description"
          />
        </Form.Item>

        {isEdit && (
          <Alert
            type="info"
            showIcon
            message="编辑模式：保存后会更新原策略的 updatedAt 时间戳，软删除状态不变"
            className="text-xs"
          />
        )}
      </Form>
    </Drawer>
  );
};

// ============================================================
// helpers
// ============================================================

function buildFromEditing(editing: CustomSellStrategy | null | undefined): FormState {
  if (!editing) return defaultFormState;
  return {
    name: editing.name,
    formula: editing.formula,
    operator: editing.operator,
    defaultThreshold: editing.defaultThreshold,
    description: editing.description,
  };
}

function getOperatorMode(op: string): 'single' | 'double' {
  const meta = INDICATOR_OPERATORS.find((o) => o.value === op);
  return meta?.needsTwoValues ? 'double' : 'single';
}

function ensureSingle(v: number | [number, number] | null | undefined): number {
  if (typeof v === 'number') return v;
  if (Array.isArray(v)) return v[0];
  return 0;
}

function ensureDouble(v: number | [number, number] | null | undefined): [number, number] {
  if (Array.isArray(v)) return [v[0], v[1]];
  if (typeof v === 'number') return [v, v];
  return [0, 0];
}

function getMin(v: number | [number, number] | null | undefined): number {
  if (Array.isArray(v)) return v[0];
  if (typeof v === 'number') return v;
  return 0;
}

function getMax(v: number | [number, number] | null | undefined): number {
  if (Array.isArray(v)) return v[1];
  if (typeof v === 'number') return v;
  return 0;
}

export default SellStrategyModal;
