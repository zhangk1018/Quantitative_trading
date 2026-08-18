/**
 * TradingPlanEditor.tsx — 交易计划模块（阶段A：Plan 模块）
 *
 * 功能：
 * - 交易计划 CRUD（模板选择 + 必填校验 + 风控前置校验）
 * - 标的 ABC 分类管理（支撑 PL-003 的 C 类拦截）
 *
 * 依赖后端 API：
 * - GET/POST/PUT/DELETE /api/pdca/plans
 * - GET /api/pdca/plans/templates
 * - GET/POST/PUT/DELETE /api/pdca/securities
 * - GET /api/pdca/cycles
 */

import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  Button, Tag, Modal, Form, Input, InputNumber, Select, Spin, Empty,
  Space, Typography, Popconfirm, Table, Tabs, App,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, ReloadOutlined, ExclamationCircleOutlined,
  FileTextOutlined, TagsOutlined, EditOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type {
  PDCACycle, TradingPlan, TradingPlanFormData, PlanTemplate, PlanTemplateType,
  SecurityTag, SecurityTagValue, StockSearchResult,
} from '../types';
import {
  LONG_SHORT_LABELS, PLAN_TEMPLATE_TYPE_LABELS, SECURITY_TAG_LABELS, SECURITY_TAG_OPTIONS,
} from '../constants';
import {
  fetchCycles,
} from '../services/cycle';
import {
  fetchPlans, createPlan, updatePlan, deletePlan, fetchPlanTemplates,
  fetchSecurities, upsertSecurity, updateSecurity, deleteSecurity,
} from '../services/plan';
import { searchStocks } from '../services/stock';

const { Text, Title } = Typography;

// ── 计划状态标签 ──
const PLAN_STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  active: { color: 'blue', label: '执行中' },
  executed: { color: 'green', label: '已完成' },
  cancelled: { color: 'red', label: '已取消' },
};

/** 安全格式化数值：后端 numeric 字段可能以字符串返回，统一转 Number 后再格式化 */
const fmtNum = (v: unknown, digits = 2): string => {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(digits) : '-';
};

const TradingPlanEditor: React.FC = () => {
  return (
    <Tabs
      className="trading-plan-tabs"
      items={[
        {
          key: 'plans',
          label: (
            <span className="flex items-center gap-2">
              <FileTextOutlined />
              <span>交易计划</span>
            </span>
          ),
          children: <PlanManager />,
        },
        {
          key: 'securities',
          label: (
            <span className="flex items-center gap-2">
              <TagsOutlined />
              <span>ABC 分类</span>
            </span>
          ),
          children: <SecurityManager />,
        },
      ]}
    />
  );
};

/* ============================================================
 * 交易计划管理
 * ============================================================ */
const PlanManager: React.FC = () => {
  const { message: appMessage } = App.useApp();
  const [cycles, setCycles] = useState<PDCACycle[]>([]);
  const [plans, setPlans] = useState<TradingPlan[]>([]);
  const [templates, setTemplates] = useState<PlanTemplate[]>([]);
  const [selectedCycle, setSelectedCycle] = useState<number | undefined>();
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<TradingPlan | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [riskError, setRiskError] = useState<string | null>(null);
  const [stockOptions, setStockOptions] = useState<{ value: string; label: string }[]>([]);
  const [form] = Form.useForm();
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── 加载周期与模板 ──
  const loadMeta = useCallback(async () => {
    try {
      const [cycItems, tplItems] = await Promise.all([fetchCycles(), fetchPlanTemplates()]);
      setCycles(cycItems);
      setTemplates(tplItems);
    } catch (err: unknown) {
      appMessage.error('加载基础数据失败: ' + (err instanceof Error ? err.message : '未知错误'));
    }
  }, [appMessage]);

  // ── 加载计划列表 ──
  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchPlans({ cycle_id: selectedCycle });
      setPlans(result.items || []);
    } catch (err: unknown) {
      appMessage.error('加载交易计划失败: ' + (err instanceof Error ? err.message : '未知错误'));
    } finally {
      setLoading(false);
    }
  }, [selectedCycle, appMessage]);

  useEffect(() => {
    loadMeta();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  // ── 股票搜索（防抖） ──
  const handleStockSearch = useCallback((q: string) => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    if (!q || q.length < 1) {
      setStockOptions([]);
      return;
    }
    debounceTimer.current = setTimeout(async () => {
      try {
        const results = await searchStocks(q);
        setStockOptions(
          results.map((s: StockSearchResult) => ({
            value: s.code,
            label: `${s.code} ${s.name}`,
          })),
        );
      } catch {
        appMessage.warning('股票搜索失败，请检查网络连接');
      }
    }, 300);
  }, [appMessage]);

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  const handleStockSelect = useCallback((_value: string, option: { label: string }) => {
    const name = option.label.replace(/^\d+\s*/, '');
    form.setFieldsValue({ security_name: name });
  }, [form]);

  // ── 打开新建/编辑弹窗 ──
  const openCreate = useCallback(() => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ long_short: 'long', max_risk_rate: 0.02, plan_quantity: 100 });
    setModalOpen(true);
  }, [form]);

  const openEdit = useCallback((plan: TradingPlan) => {
    setEditing(plan);
    form.setFieldsValue({
      template_id: plan.template_id ?? undefined,
      code: plan.code,
      security_name: plan.security_name ?? undefined,
      long_short: plan.long_short,
      weekly_view: plan.weekly_view,
      daily_view: plan.daily_view,
      entry_price: Number(plan.entry_price),
      stop_loss_price: Number(plan.stop_loss_price),
      target_price: plan.target_price == null ? undefined : Number(plan.target_price),
      max_risk_rate: Number(plan.max_risk_rate),
      plan_quantity: Number(plan.plan_quantity),
      abort_condition: plan.abort_condition ?? undefined,
    });
    setModalOpen(true);
  }, [form]);

  // ── 模板切换：应用默认值 ──
  const handleTemplateChange = useCallback((templateId: number) => {
    const tpl = templates.find((t) => t.id === templateId);
    if (!tpl || !tpl.default_values) return;
    const dv = tpl.default_values as Record<string, unknown>;
    const patch: Record<string, unknown> = {};
    if (dv.long_short) patch.long_short = dv.long_short;
    if (dv.abort_condition) patch.abort_condition = dv.abort_condition;
    if (Object.keys(patch).length > 0) form.setFieldsValue(patch);
  }, [templates, form]);

  // ── 保存（创建/更新） ──
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload: TradingPlanFormData = {
        pdca_cycle_id: selectedCycle!,
        template_id: values.template_id ?? null,
        code: values.code,
        security_name: values.security_name ?? null,
        long_short: values.long_short,
        weekly_view: values.weekly_view,
        daily_view: values.daily_view,
        entry_price: values.entry_price,
        stop_loss_price: values.stop_loss_price,
        target_price: values.target_price ?? null,
        max_risk_rate: values.max_risk_rate,
        plan_quantity: values.plan_quantity,
        abort_condition: values.abort_condition ?? null,
      };
      setSubmitting(true);
      if (editing) {
        await updatePlan(editing.id, payload);
      } else {
        await createPlan(payload);
      }
      appMessage.success(editing ? '交易计划已更新' : '交易计划已创建');
      setModalOpen(false);
      form.resetFields();
      loadPlans();
    } catch (err: unknown) {
      if (err instanceof Error) setRiskError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // ── 删除 ──
  const handleDelete = async (planId: number) => {
    try {
      await deletePlan(planId);
      appMessage.success('交易计划已删除');
      loadPlans();
    } catch (err: unknown) {
      setRiskError(err instanceof Error ? err.message : '删除失败');
    }
  };

  const columns: ColumnsType<TradingPlan> = [
    {
      title: '标的', dataIndex: 'code', key: 'code', width: 130,
      render: (_: unknown, r: TradingPlan) => (
        <div className="flex flex-col">
          <Text strong>{r.code}</Text>
          <Text type="secondary" className="text-xs">{r.security_name || '-'}</Text>
        </div>
      ),
    },
    {
      title: '方向', dataIndex: 'long_short', key: 'long_short', width: 70,
      render: (v: string) => LONG_SHORT_LABELS[v as 'long' | 'short'] || v,
    },
    {
      title: '入场价', dataIndex: 'entry_price', key: 'entry_price', width: 90, align: 'right',
      render: (v: number) => fmtNum(v, 2),
    },
    {
      title: '止损价', dataIndex: 'stop_loss_price', key: 'stop_loss_price', width: 90, align: 'right',
      render: (v: number) => fmtNum(v, 2),
    },
    {
      title: '目标价', dataIndex: 'target_price', key: 'target_price', width: 90, align: 'right',
      render: (v: number | null) => (v == null ? '-' : fmtNum(v, 2)),
    },
    {
      title: '风险比例', dataIndex: 'max_risk_rate', key: 'max_risk_rate', width: 90, align: 'right',
      render: (v: number) => `${fmtNum(v * 100, 2)}%`,
    },
    {
      title: '数量', dataIndex: 'plan_quantity', key: 'plan_quantity', width: 80, align: 'right',
    },
    {
      title: '状态', dataIndex: 'plan_status', key: 'plan_status', width: 80,
      render: (v: string) => {
        const cfg = PLAN_STATUS_CONFIG[v] || { color: 'default', label: v };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: '操作', key: 'action', width: 110, align: 'center',
      render: (_: unknown, r: TradingPlan) => (
        <Space size={4}>
          <Button size="small" type="text" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm
            title="确定删除此交易计划？"
            description="删除后不可恢复"
            onConfirm={() => handleDelete(r.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="p-4">
      {/* 顶部操作栏 */}
      <div className="flex items-center justify-between mb-4 gap-3">
        <div className="flex items-center gap-3">
          <Title level={5} className="!mb-0">交易计划列表</Title>
          <Select
            allowClear
            placeholder="选择周期"
            style={{ width: 220 }}
            value={selectedCycle}
            onChange={setSelectedCycle}
            options={cycles.map((c) => ({ value: c.id, label: c.cycle_name }))}
          />
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadPlans} size="small">刷新</Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            disabled={!selectedCycle}
            onClick={openCreate}
          >
            新建计划
          </Button>
        </Space>
      </div>

      {/* 计划列表 */}
      {loading ? (
        <div className="flex justify-center py-16"><Spin tip="加载中..." /></div>
      ) : plans.length === 0 ? (
        <Empty description={selectedCycle ? '该周期下暂无交易计划，点击「新建计划」' : '请先选择周期，再查看交易计划'} />
      ) : (
        <Table
          rowKey="id"
          columns={columns}
          dataSource={plans}
          size="small"
          pagination={{ pageSize: 10, showSizeChanger: false }}
        />
      )}

      {/* 新建/编辑计划弹窗 */}
      <Modal
        title={editing ? '编辑交易计划' : '新建交易计划'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        okText="保存"
        cancelText="取消"
        confirmLoading={submitting}
        width={720}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="template_id" label="模板">
              <Select
                allowClear
                placeholder="选择模板（可选）"
                options={templates.map((t) => ({
                  value: t.id,
                  label: `${t.template_name}（${PLAN_TEMPLATE_TYPE_LABELS[t.template_type as PlanTemplateType] || t.template_type}）`,
                }))}
                onChange={handleTemplateChange}
              />
            </Form.Item>
            <Form.Item
              name="long_short"
              label="多空方向"
              rules={[{ required: true, message: '请选择多空方向' }]}
            >
              <Select options={[
                { value: 'long', label: '做多' },
                { value: 'short', label: '做空' },
              ]} />
            </Form.Item>
            <Form.Item
              name="code"
              label="标的代码"
              rules={[{ required: true, message: '请选择或输入标的代码' }]}
            >
              <Select
                showSearch
                placeholder="输入代码/名称搜索"
                filterOption={false}
                onSearch={handleStockSearch}
                onSelect={handleStockSelect}
                options={stockOptions}
                notFoundContent={null}
              />
            </Form.Item>
            <Form.Item name="security_name" label="标的名称">
              <Input placeholder="自动带入，可修改" />
            </Form.Item>
            <Form.Item
              name="entry_price"
              label="入场价"
              rules={[{ required: true, message: '请输入入场价' }]}
            >
              <InputNumber className="w-full" min={0} precision={4} placeholder="0.0000" />
            </Form.Item>
            <Form.Item
              name="stop_loss_price"
              label="止损价"
              rules={[{ required: true, message: '请输入止损价' }]}
            >
              <InputNumber className="w-full" min={0} precision={4} placeholder="0.0000" />
            </Form.Item>
            <Form.Item name="target_price" label="目标价">
              <InputNumber className="w-full" min={0} precision={4} placeholder="0.0000" />
            </Form.Item>
            <Form.Item
              name="plan_quantity"
              label="计划数量（股）"
              rules={[{ required: true, message: '请输入计划数量' }]}
            >
              <InputNumber className="w-full" min={1} precision={0} placeholder="100" />
            </Form.Item>
            <Form.Item
              name="max_risk_rate"
              label="单笔风险比例（≤2%）"
              rules={[{ required: true, message: '请输入单笔风险比例' }]}
            >
              <InputNumber className="w-full" min={0} max={1} step={0.01} precision={4} placeholder="0.02" />
            </Form.Item>
          </div>
          <Form.Item
            name="weekly_view"
            label="周线分析（必填）"
            rules={[{ required: true, message: '请输入周线分析' }]}
          >
            <Input.TextArea rows={3} placeholder="描述周线趋势、关键支撑/压力位..." />
          </Form.Item>
          <Form.Item
            name="daily_view"
            label="日线分析（必填）"
            rules={[{ required: true, message: '请输入日线分析' }]}
          >
            <Input.TextArea rows={3} placeholder="描述日线形态、量价关系、入场依据..." />
          </Form.Item>
          <Form.Item name="abort_condition" label="放弃条件">
            <Input.TextArea rows={2} placeholder="触发即放弃该计划的条件（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 风控校验失败提示弹窗 */}
      <Modal
        open={!!riskError}
        onCancel={() => setRiskError(null)}
        footer={[
          <Button key="ok" type="primary" onClick={() => setRiskError(null)}>知道了</Button>,
        ]}
        closable={false}
        maskClosable
      >
        <div className="flex flex-col gap-3 py-2">
          <div className="flex items-start gap-3">
            <div
              className="flex items-center justify-center w-8 h-8 rounded-full flex-shrink-0"
              style={{ background: 'rgba(255,77,79,0.12)' }}
            >
              <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-base font-semibold">无法保存交易计划</span>
              <span className="text-text-secondary text-sm leading-6">{riskError}</span>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};

/* ============================================================
 * ABC 分类管理
 * ============================================================ */
const SecurityManager: React.FC = () => {
  const { message: appMessage } = App.useApp();
  const [securities, setSecurities] = useState<SecurityTag[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SecurityTag | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [stockOptions, setStockOptions] = useState<{ value: string; label: string }[]>([]);
  const [form] = Form.useForm();
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadSecurities = useCallback(async () => {
    setLoading(true);
    try {
      const items = await fetchSecurities();
      setSecurities(items);
    } catch (err: unknown) {
      appMessage.error('加载 ABC 分类失败: ' + (err instanceof Error ? err.message : '未知错误'));
    } finally {
      setLoading(false);
    }
  }, [appMessage]);

  useEffect(() => {
    loadSecurities();
  }, [loadSecurities]);

  const openCreate = useCallback(() => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  }, [form]);

  const openEdit = useCallback((s: SecurityTag) => {
    setEditing(s);
    form.setFieldsValue({
      code: s.code,
      security_name: s.security_name ?? undefined,
      tag: s.tag,
      note: s.note ?? undefined,
    });
    setModalOpen(true);
  }, [form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        code: values.code,
        security_name: values.security_name ?? null,
        tag: values.tag,
        note: values.note ?? null,
      };
      setSubmitting(true);
      if (editing) {
        await updateSecurity(editing.id, payload);
      } else {
        await upsertSecurity(payload);
      }
      appMessage.success(editing ? '分类已更新' : '分类已保存');
      setModalOpen(false);
      form.resetFields();
      loadSecurities();
    } catch (err: unknown) {
      if (err instanceof Error) appMessage.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteSecurity(id);
      appMessage.success('分类已删除');
      loadSecurities();
    } catch (err: unknown) {
      appMessage.error('删除失败: ' + (err instanceof Error ? err.message : '未知错误'));
    }
  };

  const handleStockSearch = useCallback((q: string) => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    if (!q || q.length < 1) {
      setStockOptions([]);
      return;
    }
    debounceTimer.current = setTimeout(async () => {
      try {
        const results = await searchStocks(q);
        setStockOptions(
          results.map((s: StockSearchResult) => ({
            value: s.code,
            label: `${s.code} ${s.name}`,
          })),
        );
      } catch {
        appMessage.warning('股票搜索失败，请检查网络连接');
      }
    }, 300);
  }, [appMessage]);

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  const handleStockSelect = useCallback((_value: string, option: { label: string }) => {
    const name = option.label.replace(/^\d+\s*/, '');
    form.setFieldsValue({ security_name: name });
  }, [form]);

  const columns: ColumnsType<SecurityTag> = [
    {
      title: '代码', dataIndex: 'code', key: 'code', width: 120,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '名称', dataIndex: 'security_name', key: 'security_name',
      render: (v: string | null) => v || '-',
    },
    {
      title: '分类', dataIndex: 'tag', key: 'tag', width: 120,
      render: (v: SecurityTagValue) => {
        const color = v === 'A' ? 'green' : v === 'B' ? 'blue' : 'red';
        return <Tag color={color}>{SECURITY_TAG_LABELS[v]}</Tag>;
      },
    },
    {
      title: '备注', dataIndex: 'note', key: 'note',
      render: (v: string | null) => v || '-',
    },
    {
      title: '操作', key: 'action', width: 110, align: 'center',
      render: (_: unknown, r: SecurityTag) => (
        <Space size={4}>
          <Button size="small" type="text" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm
            title="确定删除此分类？"
            onConfirm={() => handleDelete(r.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <Title level={5} className="!mb-0">标的 ABC 分类</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadSecurities} size="small">刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增分类</Button>
        </Space>
      </div>

      <div className="mb-3">
        <Text type="secondary" className="text-sm">
          C 类标的（不熟悉或验证失败）将被禁止创建交易计划。
        </Text>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Spin tip="加载中..." /></div>
      ) : (
        <Table
          rowKey="id"
          columns={columns}
          dataSource={securities}
          size="small"
          pagination={{ pageSize: 10, showSizeChanger: false }}
        />
      )}

      <Modal
        title={editing ? '编辑 ABC 分类' : '新增 ABC 分类'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        okText="保存"
        cancelText="取消"
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="code"
            label="标的代码"
            rules={[{ required: true, message: '请选择或输入代码' }]}
          >
            <Select
              showSearch
              placeholder="输入代码/名称搜索"
              filterOption={false}
              onSearch={handleStockSearch}
              onSelect={handleStockSelect}
              options={stockOptions}
              notFoundContent={null}
            />
          </Form.Item>
          <Form.Item name="security_name" label="标的名称">
            <Input placeholder="自动带入，可修改" />
          </Form.Item>
          <Form.Item
            name="tag"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select options={SECURITY_TAG_OPTIONS} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TradingPlanEditor;