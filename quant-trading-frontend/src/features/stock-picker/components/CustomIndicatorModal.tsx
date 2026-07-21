/**
 * 自编指标创建/编辑抽屉（K 2026-06-17 决策升级）
 *
 * 升级要点（vs V1.0 Modal 版）：
 * - Modal → Drawer（更宽布局适合 8 字段表单 + Monaco 编辑器）
 * - TextArea → Monaco Editor（@monaco-editor/react 懒加载，TDX/Python 高亮）
 * - onChange 实时校验 → onBlur 校验（避免输入过程中频繁报错干扰）
 * - 新增"字段插入"按钮（一键插入参数名/股票字段到公式光标位置）
 *
 * 设计原则（沿用 K 2026-06-16 偏好）：
 * - 抽屉内部维护 temp 表单状态，仅在用户点击"确定"时回写父级
 * - 取消不回滚（内部状态独立于父级）
 * - 参数名唯一性校验（防止公式引用歧义）
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Drawer,
  Form,
  Input,
  Select,
  Radio,
  Space,
  Button,
  InputNumber,
  Tooltip,
  Alert,
  message,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import Editor, { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';
import type { editor } from 'monaco-editor';

loader.config({ monaco });
import {
  CustomIndicator,
  CustomIndicatorParam,
  INDICATOR_CATEGORIES,
  INDICATOR_OPERATORS,
  INDICATOR_VISIBILITY,
  INDICATOR_SYNTAXES,
  validateIndicatorName,
  validateFormula,
  validateParamName,
} from '../types/customIndicator';
import { isNameTaken, MOCK_USER_ID } from '../utils/customIndicatorStorage';

interface CustomIndicatorModalProps {
  /** 抽屉标题 */
  title: string;
  /** 编辑时传入已有指标（创建时为 null） */
  editing?: CustomIndicator | null;
  /** 当前用户 ID（V1.0 用 MOCK_USER_ID） */
  userId?: string;
  /**
   * 名称唯一性校验函数（依赖注入，P3.2 4a）
   * 不传时 fallback 到 storage 模块的 isNameTaken（向后兼容）
   */
  isNameTaken?: (name: string, excludeId: string | null) => boolean;
  /** 点击确定时回调，传入已校验通过的指标数据（不含 id/userId/dates） */
  onConfirm: (data: Omit<CustomIndicator, 'id' | 'userId' | 'createdAt' | 'updatedAt' | 'deleted' | 'deletedAt'>) => void;
  /** 点击取消或关闭时回调 */
  onCancel: () => void;
}

// 内部表单状态类型
interface FormState {
  name: string;
  category: CustomIndicator['category'];
  syntax: CustomIndicator['syntax'];
  formula: string;
  params: CustomIndicatorParam[];
  operator: CustomIndicator['operator'];
  defaultThreshold: number | [number, number] | null;
  description: string;
  visibility: CustomIndicator['visibility'];
}

const defaultFormState: FormState = {
  name: '',
  category: 'trend',
  syntax: 'python_talib',
  formula: '',
  params: [],
  operator: '>',
  defaultThreshold: 0,
  description: '',
  visibility: 'private',
};

// 字段插入候选项（用于"插入字段"按钮）
interface FieldCandidate {
  key: string;
  label: string;
  /** 插入时的文本（光标位置替换为该文本） */
  insertText: string;
  group: 'params' | 'data' | 'numpy' | 'pattern';
}

/**
 * Python 自编指标可插入的代码片段
 * 数据字段：close/high/low/open/volume 均为 list[float]（单只股票的日序列，一维数组）
 */
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

// Monaco Editor 加载配置：
// - 通过 loader.config({ monaco }) 直接传入本地 ESM 版本的 monaco-editor
// - 完全本地加载，不依赖 CDN
// - vite-plugin-monaco-editor 处理 Worker 加载

/**
 * 自编指标创建/编辑抽屉
 */
export const CustomIndicatorModal: React.FC<CustomIndicatorModalProps> = ({
  title,
  editing = null,
  userId = MOCK_USER_ID,
  isNameTaken: isNameTakenProp,
  onConfirm,
  onCancel,
}) => {
  // P3.2 4a：props 注入的 isNameTaken 优先；不传则用 storage 模块（向后兼容）
  const checkNameTaken = useCallback(
    (name: string, excludeId: string | null) =>
      isNameTakenProp ? isNameTakenProp(name, excludeId) : isNameTaken(name, excludeId, userId),
    [isNameTakenProp, userId],
  );
  // 抽屉内部维护 temp 表单状态
  const [formState, setFormState] = useState<FormState>(() => buildFromEditing(editing));
  const [nameError, setNameError] = useState<string | null>(null);
  const [formulaError, setFormulaError] = useState<string | null>(null);
  const [formulaWarnings, setFormulaWarnings] = useState<string[]>([]);

  // Monaco editor 实例引用
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

  // 抽屉打开时同步 editing 状态
  useEffect(() => {
    setFormState(buildFromEditing(editing));
    setNameError(null);
    setFormulaError(null);
    setFormulaWarnings([]);
  }, [editing]);

  const currentOperatorMode = getOperatorMode(formState.operator);

  // 字段更新辅助
  const updateField = useCallback(<K extends keyof FormState>(key: K, value: FormState[K]) => {
    setFormState((s) => ({ ...s, [key]: value }));
  }, []);

  /**
   * 名称 OnBlur 校验
   * - 校验格式（2-30 字符 + 合法字符集）
   * - 校验唯一性（同一用户下指标名称不能重复）
   */
  const handleNameBlur = () => {
    const v = formState.name.trim();
    if (!v) {
      setNameError(null); // 空值不报错（让"必填"在提交时检查）
      return;
    }
    const err = validateIndicatorName(v);
    if (err) {
      setNameError(err);
    } else if (isNameTaken(v, editing?.id ?? null, userId)) {
      setNameError(`指标名称"${v}"已存在`);
    } else {
      setNameError(null);
    }
  };

  /**
   * 公式 OnBlur 校验
   * - 非空校验
   * - 长度限制（≤ 8000 字符）
   * - 危险关键字检测（import/exec/eval 等）
   * - calculate 函数签名校验
   * - 常见错误模式检测
   */
  const handleFormulaBlur = () => {
    const v = formState.formula;
    if (!v || !v.trim()) {
      setFormulaError(null); // 空值不报错（让"必填"在提交时检查）
      setFormulaWarnings([]);
      return;
    }
    const result = validateFormula(v, formState.syntax);
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

  // 存储最新的 handleFormulaBlur 引用，避免 Monaco 闭包陈旧问题
  const handleFormulaBlurRef = useRef<() => void>(() => {});
  handleFormulaBlurRef.current = handleFormulaBlur;

  /**
   * Monaco 挂载回调：
   * - 保存 editor 实例到 ref（用于字段插入）
   * - 绑定 onDidBlurEditorWidget 事件做 OnBlur 校验
   *   通过 ref 调用最新 handleFormulaBlur，避免闭包捕获旧 formState
   */
  const handleEditorMount = (editorInstance: editor.IStandaloneCodeEditor) => {
    editorRef.current = editorInstance;
    editorInstance.onDidBlurEditorWidget(() => {
      handleFormulaBlurRef.current();
    });
  };

  /**
   * 在 Monaco 光标位置插入文本
   * - 字段插入按钮调用此函数
   * - 插入后自动聚焦 editor
   */
  const insertAtCursor = (text: string) => {
    const editor = editorRef.current;
    if (!editor) return;
    const position = editor.getPosition();
    if (!position) return;
    editor.executeEdits('custom-indicator-insert', [
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
    // 插入后将光标移动到文本末尾
    const lines = text.split('\n');
    const newColumn =
      lines.length === 1 ? position.column + text.length : lines[lines.length - 1].length + 1;
    const newLine = position.lineNumber + lines.length - 1;
    editor.setPosition({ lineNumber: newLine, column: newColumn });
    editor.focus();
  };

  // 动态参数增删
  const handleAddParam = () => {
    const newParam: CustomIndicatorParam = {
      name: `p${formState.params.length + 1}`,
      defaultValue: '0',
      description: '',
    };
    updateField('params', [...formState.params, newParam]);
  };

  const handleRemoveParam = (idx: number) => {
    updateField('params', formState.params.filter((_, i) => i !== idx));
  };

  const handleUpdateParam = (idx: number, patch: Partial<CustomIndicatorParam>) => {
    updateField('params', formState.params.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  };

  // 切换运算符时根据新模式自动转换阈值类型（K 2026-06-18 任务 #17）
  // 规则：
  //   新 mode = single → ensureSingle（数字保留数字，数组取首个，null 兜底 0）
  //   新 mode = double → ensureDouble（数组保留，数字复制为 [n, n]，null 兜底 [0, 0]）
  // 旧逻辑仅在 `currentOperatorMode === 'double'` 时才 ensureDouble，遗漏
  //   "double → single → double" 中第二次 mode 切换，导致阈值类型不匹配。
  const handleOperatorChange = (op: CustomIndicator['operator']) => {
    updateField('operator', op);
    const mode = getOperatorMode(op);
    if (mode === 'single') {
      updateField('defaultThreshold', ensureSingle(formState.defaultThreshold));
    } else {
      updateField('defaultThreshold', ensureDouble(formState.defaultThreshold));
    }
  };

  // 提交前最终校验
  const handleSubmit = () => {
    const trimmedName = formState.name.trim();
    if (!trimmedName) {
      setNameError('指标名称不能为空');
      return;
    }
    const nameErr = validateIndicatorName(trimmedName);
    if (nameErr) {
      setNameError(nameErr);
      return;
    }
    if (checkNameTaken(trimmedName, editing?.id ?? null)) {
      setNameError(`指标名称"${trimmedName}"已存在`);
      return;
    }
    const trimmedFormula = formState.formula.trim();
    if (!trimmedFormula) {
      setFormulaError('公式不能为空');
      return;
    }
    const formulaResult = validateFormula(formState.formula, formState.syntax);
    if (!formulaResult.valid) {
      setFormulaError(formulaResult.errors[0] || '公式无效');
      setFormulaWarnings([]);
      return;
    }
    setFormulaWarnings(formulaResult.warnings);
    for (let i = 0; i < formState.params.length; i++) {
      const pn = validateParamName(formState.params[i].name);
      if (pn) {
        message.error(`第 ${i + 1} 个参数：${pn}`);
        return;
      }
    }
    // K 2026-06-16 代码审阅建议 4b：参数名唯一性校验
    const paramNames = formState.params.map((p) => p.name).filter((n) => n);
    const duplicate = paramNames.find((n, idx) => paramNames.indexOf(n) !== idx);
    if (duplicate) {
      message.error(`参数名"${duplicate}"重复，请使用唯一参数名（公式中通过参数名引用）`);
      return;
    }

    onConfirm({
      name: trimmedName,
      category: formState.category,
      syntax: formState.syntax,
      formula: formState.formula,
      params: formState.params,
      operator: formState.operator,
      defaultThreshold: formState.defaultThreshold ?? 0,
      description: formState.description,
      visibility: formState.visibility,
    });
  };

  const isEdit = !!editing;
  const submitDisabled =
    !formState.name.trim() || !formState.formula.trim() || !!nameError || !!formulaError;

  // Monaco 语言始终为 Python
  const monacoLanguage = 'python';

  // 字段插入候选项：参数名 + 行情字段 + 指标字段
  const paramCandidates: FieldCandidate[] = formState.params
    .filter((p) => p.name.trim())
    .map((p) => ({
      key: `param_${p.name}`,
      label: `${p.name} (参数)`,
      insertText: p.name,
      group: 'params',
    }));

  return (
    <Drawer
      open
      title={title}
      onClose={onCancel}
      width={720}
      destroyOnHidden
      maskClosable={false}
      // K 2026-06-17 反馈：取消/创建按钮移至 Drawer 顶部右侧（extra 区域）
      extra={
        <Space size="small" data-testid="custom-indicator-modal-extra">
          <Button size="small" onClick={onCancel} data-testid="custom-indicator-modal-cancel">
            取消
          </Button>
          <Button
            size="small"
            type="primary"
            disabled={submitDisabled}
            onClick={handleSubmit}
            data-testid="custom-indicator-modal-confirm"
          >
            {isEdit ? '保存' : '创建'}
          </Button>
        </Space>
      }
      data-testid="custom-indicator-modal"
    >
      <Form layout="vertical" size="small" className="py-1">
        {/* 1. 指标名称 */}
        <Form.Item
          label="指标名称"
          required
          validateStatus={nameError ? 'error' : ''}
          help={nameError || '2-30 字符，中英文数字下划线连字符括号'}
        >
          <Input
            value={formState.name}
            onChange={(e) => {
              updateField('name', e.target.value);
              // OnBlur 校验：清空错误显示（输入过程中不打扰）
              if (nameError) setNameError(null);
            }}
            onBlur={handleNameBlur}
            placeholder="如：RSI 自定义"
            maxLength={30}
            data-testid="custom-indicator-modal-name"
          />
        </Form.Item>

        {/* 2. 指标分类 */}
        <Form.Item label="指标分类" required>
          <Select
            value={formState.category}
            onChange={(v) => updateField('category', v)}
            options={INDICATOR_CATEGORIES.map((c) => ({ value: c.value, label: c.label }))}
            data-testid="custom-indicator-modal-category"
          />
        </Form.Item>

        {/* 3. 指标公式 + 字段插入按钮 */}
        <Form.Item
          label={
            <span className="flex items-center justify-between w-full">
              <span>
                指标公式{' '}
                <Tooltip title="Python 脚本，定义 calculate(open_prices, high_prices, low_prices, close_prices, volumes) 函数，输入为单只股票的一维数组，返回单值或等长数组">
                  <QuestionCircleOutlined className="text-text-secondary" />
                </Tooltip>
              </span>
              <span className="text-text-secondary text-xs font-normal">
                Python · Monaco Editor
              </span>
            </span>
          }
          required
          validateStatus={formulaError ? 'error' : formulaWarnings.length > 0 ? 'warning' : ''}
          help={
            formulaError
              ? formulaError
              : formulaWarnings.length > 0
                ? formulaWarnings.map((w, i) => (
                    <div key={i} className="text-warning">⚠ {w}</div>
                  ))
                : 'OnBlur 时校验（输入过程中不打扰）'
          }
        >
          {/* Monaco Editor（懒加载，Drawer 打开时才下载） */}
          <div
            className="border border-border-color rounded overflow-hidden bg-bg-elevated"
            data-testid="custom-indicator-modal-formula-editor"
          >
            <Editor
              height="180px"
              language={monacoLanguage}
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

          {/* 字段插入按钮区 */}
          <div className="mt-2 space-y-1.5" data-testid="custom-indicator-modal-field-insert">
            {paramCandidates.length > 0 && (
              <div className="flex items-start gap-2 flex-wrap">
                <span className="text-text-secondary text-xs mt-1 w-14 flex-shrink-0">参数：</span>
                <Space size={4} wrap>
                  {paramCandidates.map((c) => (
                    <Button
                      key={c.key}
                      size="small"
                      icon={<ThunderboltOutlined />}
                      onClick={() => insertAtCursor(c.insertText)}
                      data-testid={`custom-indicator-modal-insert-${c.key}`}
                    >
                      {c.label}
                    </Button>
                  ))}
                </Space>
              </div>
            )}
            <div className="flex items-start gap-2 flex-wrap">
              <span className="text-text-secondary text-xs mt-1 w-14 flex-shrink-0">
                行情数据：
              </span>
              <Space size={4} wrap>
                {PYTHON_HELPERS.filter((c) => c.group === 'data').map((c) => (
                  <Button
                    key={c.key}
                    size="small"
                    onClick={() => insertAtCursor(c.insertText)}
                    data-testid={`custom-indicator-modal-insert-${c.key}`}
                  >
                    {c.label}
                  </Button>
                ))}
              </Space>
            </div>
            <div className="flex items-start gap-2 flex-wrap">
              <span className="text-text-secondary text-xs mt-1 w-14 flex-shrink-0">
                NumPy 函数：
              </span>
              <Space size={4} wrap>
                {PYTHON_HELPERS.filter((c) => c.group === 'numpy').map((c) => (
                  <Button
                    key={c.key}
                    size="small"
                    onClick={() => insertAtCursor(c.insertText)}
                    data-testid={`custom-indicator-modal-insert-${c.key}`}
                  >
                    {c.label}
                  </Button>
                ))}
              </Space>
            </div>
            <div className="flex items-start gap-2 flex-wrap">
              <span className="text-text-secondary text-xs mt-1 w-14 flex-shrink-0">
                常用模式：
              </span>
              <Space size={4} wrap>
                {PYTHON_HELPERS.filter((c) => c.group === 'pattern').map((c) => (
                  <Button
                    key={c.key}
                    size="small"
                    onClick={() => insertAtCursor(c.insertText)}
                    data-testid={`custom-indicator-modal-insert-${c.key}`}
                  >
                    {c.label}
                  </Button>
                ))}
              </Space>
            </div>
          </div>
        </Form.Item>

        {/* 4. 动态参数 */}
        <Form.Item
          label={
            <span>
              自定义参数{' '}
              <Tooltip title="参数名须以字母/下划线开头，≤20 字符；defaultValue 在公式中以参数名引用">
                <QuestionCircleOutlined className="text-text-secondary" />
              </Tooltip>
            </span>
          }
        >
          <Space direction="vertical" size={4} className="w-full">
            {formState.params.map((p, idx) => (
              <Space.Compact key={idx} className="w-full">
                <Input
                  value={p.name}
                  onChange={(e) => handleUpdateParam(idx, { name: e.target.value })}
                  placeholder="参数名"
                  style={{ width: '30%' }}
                  data-testid={`custom-indicator-modal-param-name-${idx}`}
                />
                <Input
                  value={p.defaultValue}
                  onChange={(e) => handleUpdateParam(idx, { defaultValue: e.target.value })}
                  placeholder="默认值"
                  style={{ width: '20%' }}
                  data-testid={`custom-indicator-modal-param-default-${idx}`}
                />
                <Input
                  value={p.description}
                  onChange={(e) => handleUpdateParam(idx, { description: e.target.value })}
                  placeholder="参数说明"
                  className="flex-1"
                  data-testid={`custom-indicator-modal-param-desc-${idx}`}
                />
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => handleRemoveParam(idx)}
                  data-testid={`custom-indicator-modal-param-remove-${idx}`}
                />
              </Space.Compact>
            ))}
            <Button
              type="dashed"
              size="small"
              icon={<PlusOutlined />}
              onClick={handleAddParam}
              block
              data-testid="custom-indicator-modal-param-add"
            >
              添加参数
            </Button>
          </Space>
        </Form.Item>

        {/* 5. 默认运算符 + 阈值 */}
        <Form.Item label="默认运算符" required>
          <Select
            value={formState.operator}
            onChange={handleOperatorChange}
            options={INDICATOR_OPERATORS.map((o) => ({ value: o.value, label: o.label }))}
            data-testid="custom-indicator-modal-operator"
          />
        </Form.Item>

        {currentOperatorMode === 'single' && (
          <Form.Item label="默认阈值（单值）">
            <InputNumber
              value={typeof formState.defaultThreshold === 'number' ? formState.defaultThreshold : 0}
              onChange={(v) => updateField('defaultThreshold', v ?? 0)}
              className="w-full"
              data-testid="custom-indicator-modal-threshold-single"
            />
          </Form.Item>
        )}

        {currentOperatorMode === 'double' && (
          <Form.Item label="默认阈值（双值：区间/上穿/下穿）">
            <Space.Compact className="w-full">
              <InputNumber
                value={getMin(formState.defaultThreshold)}
                onChange={(v) =>
                  updateField('defaultThreshold', [v ?? 0, getMax(formState.defaultThreshold)])
                }
                placeholder="最小值/线A"
                className="w-full"
                data-testid="custom-indicator-modal-threshold-min"
              />
              <InputNumber
                value={getMax(formState.defaultThreshold)}
                onChange={(v) =>
                  updateField('defaultThreshold', [getMin(formState.defaultThreshold), v ?? 0])
                }
                placeholder="最大值/线B"
                className="w-full"
                data-testid="custom-indicator-modal-threshold-max"
              />
            </Space.Compact>
          </Form.Item>
        )}

        {/* 6. 指标说明 */}
        <Form.Item label="指标说明">
          <Input.TextArea
            value={formState.description}
            onChange={(e) => updateField('description', e.target.value)}
            placeholder="如：自定义 RSI，超卖阈值 30，超买阈值 70"
            autoSize={{ minRows: 2, maxRows: 4 }}
            data-testid="custom-indicator-modal-description"
          />
        </Form.Item>

        {/* 7. 可见范围 */}
        <Form.Item label="可见范围" required>
          <Radio.Group
            value={formState.visibility}
            onChange={(e) => updateField('visibility', e.target.value)}
            data-testid="custom-indicator-modal-visibility"
          >
            <Space direction="vertical" size={4}>
              {INDICATOR_VISIBILITY.map((opt) => (
                <Radio
                  key={opt.value}
                  value={opt.value}
                  disabled={opt.disabled}
                  className="text-sm"
                  data-testid={`custom-indicator-modal-visibility-${opt.value}`}
                >
                  {opt.label}
                </Radio>
              ))}
            </Space>
          </Radio.Group>
        </Form.Item>

        {isEdit && (
          <Alert
            type="info"
            showIcon
            message="编辑模式：保存后会更新原指标的 updatedAt 时间戳，软删除状态不变"
            className="text-xs"
          />
        )}
      </Form>

      <div className="hidden">
        {/* 底部按钮区已移至 Drawer extra（K 2026-06-17 反馈），
            保留 hidden div 是为了不破坏后续扩展需要（如 sticky 提示） */}
      </div>
    </Drawer>
  );
};

// ============================================================
// helpers（K 2026-06-16 代码审阅建议 6c：抽取 ensureSingle/ensureDouble 工具）
// ============================================================

function buildFromEditing(editing: CustomIndicator | null | undefined): FormState {
  if (!editing) return defaultFormState;
  return {
    name: editing.name,
    category: editing.category,
    syntax: editing.syntax,
    formula: editing.formula,
    params: editing.params.map((p) => ({ ...p })),
    operator: editing.operator,
    defaultThreshold: editing.defaultThreshold,
    description: editing.description,
    visibility: editing.visibility,
  };
}

function getOperatorMode(op: CustomIndicator['operator']): 'single' | 'double' {
  const meta = INDICATOR_OPERATORS.find((o) => o.value === op);
  return meta?.needsTwoValues ? 'double' : 'single';
}

/** K 2026-06-16 6c：确保阈值为单值（数组取第一个，null 取 0） */
function ensureSingle(v: number | [number, number] | null | undefined): number {
  if (typeof v === 'number') return v;
  if (Array.isArray(v)) return v[0];
  return 0;
}

/** K 2026-06-16 6c：确保阈值为双值（数字复制为 [n, n]，null 取 [0, 0]） */
function ensureDouble(
  v: number | [number, number] | null | undefined
): [number, number] {
  if (Array.isArray(v)) return [v[0], v[1]];
  if (typeof v === 'number') return [v, v];
  return [0, 0];
}

/** K 2026-06-16 6c：取双值的第一个 */
function getMin(v: number | [number, number] | null | undefined): number {
  if (Array.isArray(v)) return v[0];
  if (typeof v === 'number') return v;
  return 0;
}

/** K 2026-06-16 6c：取双值的第二个 */
function getMax(v: number | [number, number] | null | undefined): number {
  if (Array.isArray(v)) return v[1];
  if (typeof v === 'number') return v;
  return 0;
}
