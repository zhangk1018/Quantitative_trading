import React, { useState, useEffect } from 'react';
import {
  Modal,
  Form,
  Input,
  Select,
  Radio,
  Space,
  Button,
  InputNumber,
  Tooltip,
  Alert,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
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

const { TextArea } = Input;

interface CustomIndicatorModalProps {
  /** 弹窗标题 */
  title: string;
  /** 编辑时传入已有指标（创建时为 null） */
  editing?: CustomIndicator | null;
  /** 当前用户 ID（V1.0 用 MOCK_USER_ID） */
  userId?: string;
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
  syntax: 'tdx',
  formula: '',
  params: [],
  operator: '>',
  defaultThreshold: 0,
  description: '',
  visibility: 'private',
};

/**
 * 自编指标创建/编辑弹窗
 * - 8 字段表单：名称 / 分类 / 公式语法 / 公式 / 动态参数 / 默认运算符 / 说明 / 可见范围
 *   （默认阈值嵌在运算符下方动态显示，单值或双值）
 * - 弹窗内部维护 form state，仅在用户点击"确定"时回写父级（K 偏好：取消不回滚）
 * - width=480（K 偏好：弹窗整体缩小至少五分之一，原默认 520px）
 */
export const CustomIndicatorModal: React.FC<CustomIndicatorModalProps> = ({
  title,
  editing = null,
  userId = MOCK_USER_ID,
  onConfirm,
  onCancel,
}) => {
  // 弹窗内部维护 temp 表单状态
  const [formState, setFormState] = useState<FormState>(() => buildFromEditing(editing));
  const [nameError, setNameError] = useState<string | null>(null);
  const [formulaError, setFormulaError] = useState<string | null>(null);

  // 弹窗打开时同步
  useEffect(() => {
    setFormState(buildFromEditing(editing));
    setNameError(null);
    setFormulaError(null);
  }, [editing]);

  const currentOperatorMode = getOperatorMode(formState.operator);

  // 字段更新辅助
  const updateField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setFormState((s) => ({ ...s, [key]: value }));
  };

  // 名称实时校验
  const handleNameChange = (v: string) => {
    updateField('name', v);
    const err = validateIndicatorName(v);
    if (err) {
      setNameError(err);
    } else if (isNameTaken(v, editing?.id ?? null, userId)) {
      setNameError(`指标名称"${v}"已存在`);
    } else {
      setNameError(null);
    }
  };

  // 公式实时校验
  const handleFormulaChange = (v: string) => {
    updateField('formula', v);
    const result = validateFormula(v, formState.syntax);
    setFormulaError(result.valid ? null : result.errors[0] || '公式无效');
  };

  // 切换语法时重算公式错误
  useEffect(() => {
    if (formState.formula) {
      const result = validateFormula(formState.formula, formState.syntax);
      setFormulaError(result.valid ? null : result.errors[0] || '公式无效');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formState.syntax]);

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

  // 切换运算符时重置阈值
  const handleOperatorChange = (op: CustomIndicator['operator']) => {
    updateField('operator', op);
    const mode = getOperatorMode(op);
    if (mode === 'single') {
      updateField('defaultThreshold', ensureSingle(formState.defaultThreshold));
    } else if (currentOperatorMode === 'double') {
      updateField('defaultThreshold', ensureDouble(formState.defaultThreshold));
    }
  };

  // 提交前最终校验
  const handleSubmit = () => {
    const nameErr = validateIndicatorName(formState.name);
    if (nameErr) {
      setNameError(nameErr);
      return;
    }
    if (isNameTaken(formState.name, editing?.id ?? null, userId)) {
      setNameError(`指标名称"${formState.name}"已存在`);
      return;
    }
    const formulaResult = validateFormula(formState.formula, formState.syntax);
    if (!formulaResult.valid) {
      setFormulaError(formulaResult.errors[0] || '公式无效');
      return;
    }
    for (let i = 0; i < formState.params.length; i++) {
      const pn = validateParamName(formState.params[i].name);
      if (pn) {
        Modal.error({ title: '参数名校验失败', content: `第 ${i + 1} 个参数：${pn}` });
        return;
      }
    }
    // K 2026-06-16 代码审阅建议 4b：参数名唯一性校验
    // 重复参数名会导致公式引用歧义（MA(p1) 不知用哪个 p1）
    const paramNames = formState.params.map((p) => p.name).filter((n) => n);
    const duplicate = paramNames.find((n, idx) => paramNames.indexOf(n) !== idx);
    if (duplicate) {
      Modal.error({
        title: '参数名重复',
        content: `参数名"${duplicate}"重复，请使用唯一参数名（公式中通过参数名引用）`,
      });
      return;
    }

    onConfirm({
      name: formState.name,
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
  const submitDisabled = !!nameError || !!formulaError || !formState.name || !formState.formula;

  return (
    <Modal
      open
      title={title}
      onCancel={onCancel}
      footer={null}
      width={480}
      centered
      destroyOnHidden
      maskClosable={false}
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
            onChange={(e) => handleNameChange(e.target.value)}
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

        {/* 3. 公式语法 */}
        <Form.Item label="公式语法" required>
          <Select
            value={formState.syntax}
            onChange={(v) => updateField('syntax', v)}
            options={INDICATOR_SYNTAXES}
            data-testid="custom-indicator-modal-syntax"
          />
        </Form.Item>

        {/* 4. 指标公式 */}
        <Form.Item
          label={
            <span>
              指标公式{' '}
              <Tooltip title="支持通达信公式或 Python Ta-Lib 表达式，禁止 import/exec/eval 等危险关键字">
                <QuestionCircleOutlined className="text-text-secondary" />
              </Tooltip>
            </span>
          }
          required
          validateStatus={formulaError ? 'error' : ''}
          help={formulaError || ''}
        >
          <TextArea
            value={formState.formula}
            onChange={(e) => handleFormulaChange(e.target.value)}
            placeholder="如：CLOSE > MA(CLOSE, N)"
            autoSize={{ minRows: 2, maxRows: 5 }}
            data-testid="custom-indicator-modal-formula"
          />
        </Form.Item>

        {/* 5. 动态参数 */}
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

        {/* 6. 默认运算符 + 阈值 */}
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

        {/* 7. 指标说明 */}
        <Form.Item label="指标说明">
          <TextArea
            value={formState.description}
            onChange={(e) => updateField('description', e.target.value)}
            placeholder="如：自定义 RSI，超卖阈值 30，超买阈值 70"
            autoSize={{ minRows: 2, maxRows: 4 }}
            data-testid="custom-indicator-modal-description"
          />
        </Form.Item>

        {/* 8. 可见范围 */}
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

      <div className="flex justify-end gap-2 pt-2 border-t border-border-color mt-2">
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
      </div>
    </Modal>
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

/** K 2026-06-16 6c：取双值的第一个（区间下界 / 上穿线 A） */
function getMin(v: number | [number, number] | null | undefined): number {
  if (Array.isArray(v)) return v[0];
  if (typeof v === 'number') return v;
  return 0;
}

/** K 2026-06-16 6c：取双值的第二个（区间上界 / 上穿线 B） */
function getMax(v: number | [number, number] | null | undefined): number {
  if (Array.isArray(v)) return v[1];
  if (typeof v === 'number') return v;
  return 0;
}
