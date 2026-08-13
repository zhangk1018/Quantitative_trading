/**
 * TradingRecordForm.tsx — 交易记录录入/编辑表单
 *
 * 功能：
 * - 股票代码自动补全（搜索 stock_basic，带防抖）
 * - 数值范围校验（前后端双重）
 * - 日期先后校验（出场日期 > 入场日期）
 * - 支持新增和编辑模式
 * - 卖出子单管理（一买多卖）：支持批量新增、编辑、删除
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Modal, Form, Input, InputNumber, DatePicker, Select, App, Row, Col, AutoComplete,
  Button, Space, Table, Popconfirm, Card,
} from 'antd';
import { PlusOutlined, EditOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { TradingRecord, TradingRecordFormData, StockSearchResult, ExitSlip, ExitSlipFormData } from '../types';
import {
  INSTRUMENT_TYPE_OPTIONS, LONG_SHORT_OPTIONS, ORDER_TYPE_OPTIONS,
  TRADE_GRADE_OPTIONS, EXIT_REASON_OPTIONS, TRIGGER_SOURCE_OPTIONS,
} from '../types';
import { createRecord, updateRecord, searchStocks, fetchExitSlips, updateExitSlip, deleteExitSlip, batchCreateExitSlips } from '../api';

interface Props {
  open: boolean;
  record: TradingRecord | null;
  onClose: () => void;
  onSuccess: () => void;
}

const { Option } = Select;

const TradingRecordForm: React.FC<Props> = ({ open, record, onClose, onSuccess }) => {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [loadingExitSlips, setLoadingExitSlips] = useState(false);
  const [stockOptions, setStockOptions] = useState<{ value: string; label: string; code: string }[]>([]);
  const [exitSlips, setExitSlips] = useState<ExitSlip[]>([]);
  const [exitSlipModalOpen, setExitSlipModalOpen] = useState(false);
  const [editingSlip, setEditingSlip] = useState<ExitSlip | null>(null);
  const [snapshotMaxSellQty, setSnapshotMaxSellQty] = useState(0);
  const [exitSlipForm] = Form.useForm<ExitSlipFormData>();
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tempIdCounterRef = useRef(0);
  const isEdit = !!record;

  // --- 加载已有卖出子单（编辑模式） ---
  useEffect(() => {
    if (open && record) {
      setLoadingExitSlips(true);
      fetchExitSlips(record.id)
        .then(res => {
          if (res.code === 200) {
            setExitSlips(res.data.items || []);
          } else {
            message.warning(res.message || '加载卖出记录失败');
          }
        })
        .catch(() => {
          message.warning('加载卖出记录失败，请检查网络连接');
        })
        .finally(() => {
          setLoadingExitSlips(false);
        });
    } else {
      setExitSlips([]);
    }
  }, [open, record, message]);

  // --- 表单初始值 ---
  useEffect(() => {
    if (open) {
      if (record) {
        form.setFieldsValue({
          ...record,
          entry_date: record.entry_date ? dayjs(record.entry_date) : null,
          exit_date: record.exit_date ? dayjs(record.exit_date) : null,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          instrument_type: 'stock',
          long_short: 'long',
          order_type: 'limit',
          quantity: 100,
          commission_entry: 0,
          commission_exit: 0,
          slip_point: 0,
          settlement_currency: 'CNY',
        });
      }
    }
  }, [open, record, form]);

  // --- 股票搜索（防抖） ---
  const handleStockSearch = useCallback((q: string) => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    if (!q || q.length < 1) {
      setStockOptions([]);
      return;
    }
    debounceTimer.current = setTimeout(async () => {
      try {
        const res = await searchStocks(q);
        if (res.code === 200) {
          setStockOptions(
            res.data.map((s: StockSearchResult) => ({
              value: s.code,
              label: `${s.code} ${s.name}`,
              code: s.code,
            })),
          );
        }
      } catch {
        message.warning('股票搜索失败，请检查网络连接');
      }
    }, 300);
  }, [message]);

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  const handleStockSelect = useCallback((_value: string, option: { label: string }) => {
    const name = option.label.replace(/^\d+\s*/, '');
    form.setFieldsValue({ security_name: name });
  }, [form]);

  // --- 计算统计数据（使用 useMemo 缓存，避免每次渲染重复计算） ---
  const entryQty = form.getFieldValue('quantity') || 0;
  const totalExitQty = useMemo(
    () => exitSlips.reduce((sum, slip) => sum + slip.quantity, 0),
    [exitSlips],
  );
  const remainQty = useMemo(() => entryQty - totalExitQty, [entryQty, totalExitQty]);

  // --- 卖出子单管理 ---
  const openNewExitSlip = useCallback(() => {
    setEditingSlip(null);
    setSnapshotMaxSellQty(Math.max(0, remainQty));
    exitSlipForm.resetFields();
    exitSlipForm.setFieldsValue({
      exit_date: dayjs().format('YYYY-MM-DD'),
      commission: 0,
      slip_point: 0,
    });
    setExitSlipModalOpen(true);
  }, [exitSlipForm, remainQty]);

  const editExitSlip = useCallback((slip: ExitSlip) => {
    setEditingSlip(slip);
    const maxQty = Math.max(0, entryQty - (totalExitQty - slip.quantity));
    setSnapshotMaxSellQty(maxQty);
    exitSlipForm.setFieldsValue({
      exit_date: slip.exit_date,
      exit_price: slip.exit_price,
      quantity: slip.quantity,
      commission: slip.commission,
      exit_reason: slip.exit_reason ?? undefined,
      exit_score: slip.exit_score ?? undefined,
      actual_stop_loss: slip.actual_stop_loss ?? undefined,
      slip_point: slip.slip_point,
    });
    setExitSlipModalOpen(true);
  }, [exitSlipForm, entryQty, totalExitQty]);

  const saveExitSlip = useCallback(async () => {
    try {
      const values = await exitSlipForm.validateFields();
      const data: ExitSlipFormData = {
        ...values,
        exit_date: dayjs.isDayjs(values.exit_date) ? values.exit_date.format('YYYY-MM-DD') : values.exit_date,
      };

      if (editingSlip) {
        // 编辑已有子单 → 实时保存到后端
        const res = await updateExitSlip(editingSlip.id, data);
        if (res.code === 200) {
          setExitSlips(prev => prev.map(s => s.id === editingSlip.id ? { ...s, ...data, id: s.id } : s));
          message.success('更新成功');
          setExitSlipModalOpen(false);
        } else {
          message.error(res.message || '更新失败');
        }
      } else {
        // 新增临时子单 → 暂存本地，主单保存后批量提交
        tempIdCounterRef.current -= 1;
        const tempId = tempIdCounterRef.current;
        const newSlip: ExitSlip = {
          id: tempId,
          record_id: record?.id || 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ...data,
        } as ExitSlip;
        setExitSlips(prev => [...prev, newSlip]);
        setExitSlipModalOpen(false);
        message.success('已添加卖出记录，保存主记录时一并提交');
      }
    } catch {
      // 表单校验失败，不处理
    }
  }, [exitSlipForm, editingSlip, record, message]);

  const removeExitSlip = useCallback(async (id: number) => {
    if (id < 0) {
      // 本地临时记录，直接删除
      setExitSlips(prev => prev.filter(s => s.id !== id));
      return;
    }
    // 已保存到后端的记录，调用删除接口
    const res = await deleteExitSlip(id);
    if (res.code === 200) {
      setExitSlips(prev => prev.filter(s => s.id !== id));
      message.success('删除成功');
      // 删除后刷新父表数据，保持 remain_qty / gross_profit 同步，并关闭表单
      onSuccess();
    } else {
      message.error(res.message || '删除失败');
    }
  }, [message, onSuccess]);

  // --- 主表单提交 ---
  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      const data: TradingRecordFormData = {
        ...values,
        security_name: form.getFieldValue('security_name') || '',
        entry_date: values.entry_date?.format('YYYY-MM-DD'),
        exit_date: values.exit_date?.format('YYYY-MM-DD') || undefined,
      };

      // 清理空字段
      Object.keys(data).forEach(key => {
        const k = key as keyof TradingRecordFormData;
        if (data[k] === undefined || data[k] === null || data[k] === '') {
          delete data[k];
        }
      });

      // 收集本地新增的临时子单（id < 0）
      const localSlips = exitSlips.filter(s => s.id < 0).map(s => ({
        exit_date: s.exit_date,
        exit_price: s.exit_price,
        quantity: s.quantity,
        commission: s.commission,
        exit_reason: s.exit_reason ?? undefined,
        exit_score: s.exit_score ?? undefined,
        actual_stop_loss: s.actual_stop_loss ?? undefined,
        slip_point: s.slip_point,
      }));

      let res;
      if (isEdit) {
        res = await updateRecord(record!.id, data);
      } else {
        res = await createRecord(data);
      }

      if (res.code === 200) {
        const recordData = res.data;
        const recordId = isEdit
          ? record!.id
          : (recordData && typeof recordData === 'object' && 'id' in recordData)
            ? (recordData as { id: number }).id
            : 0;

        if (!recordId) {
          message.error('创建记录失败：返回数据异常');
          return;
        }

        // 批量提交本地新增的子单（仅针对新增的临时子单）
        if (localSlips.length > 0) {
          const batchRes = await batchCreateExitSlips(recordId, localSlips);
          if (batchRes.code !== 200) {
            // 清理本地临时子单，防止重复提交导致数据重复
            setExitSlips(prev => prev.filter(s => s.id >= 0));
            message.warning(
              `主记录已保存，但 ${localSlips.length} 条卖出记录同步失败：${batchRes.message || '未知错误'}。请重新编辑该记录并添加卖出记录。`,
            );
          }
        }

        message.success(isEdit ? '更新成功' : '新增成功');
        onSuccess();
      } else {
        message.error(res.message || '保存失败');
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        // 表单校验失败，不处理
        return;
      }
      message.error(err instanceof Error ? err.message : '保存失败，请检查网络连接');
    } finally {
      setLoading(false);
    }
  }, [form, isEdit, record, exitSlips, message, onSuccess]);

  // --- 卖出子单表格列（使用 useMemo 缓存） ---
  const exitSlipColumns = useMemo(
    () => [
      { title: '出场日期', dataIndex: 'exit_date', key: 'exit_date', width: 100 },
      {
        title: '出场价',
        dataIndex: 'exit_price',
        key: 'exit_price',
        width: 90,
        align: 'right' as const,
        render: (v: number) => (Number.isFinite(v) ? v.toFixed(2) : '-'),
      },
      {
        title: '数量',
        dataIndex: 'quantity',
        key: 'quantity',
        width: 70,
        align: 'right' as const,
        render: (v: number) => (Number.isFinite(v) ? v.toLocaleString() : '-'),
      },
      {
        title: '出场原因',
        dataIndex: 'exit_reason',
        key: 'exit_reason',
        width: 100,
        render: (v: string | null) => (v ? EXIT_REASON_OPTIONS.find(o => o.value === v)?.label || v : '-'),
      },
      {
        title: '操作',
        key: 'action',
        width: 100,
        render: (_: unknown, slip: ExitSlip) => (
          <Space size="small">
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => editExitSlip(slip)}>
              编辑
            </Button>
            <Popconfirm
              title="确定删除此卖出记录？"
              onConfirm={() => removeExitSlip(slip.id)}
              okText="删除"
              cancelText="取消"
            >
              <Button type="link" size="small" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [editExitSlip, removeExitSlip],
  );

  return (
    <>
      <Modal
        title={isEdit ? '编辑交易记录' : '新增交易记录'}
        open={open}
        onCancel={onClose}
        onOk={handleSubmit}
        confirmLoading={loading}
        width={800}
        destroyOnClose
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" className="mt-4">
          {/* ---- 股票代码 & 名称 ---- */}
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="code"
                label="股票代码"
                rules={[{ required: true, message: '请输入股票代码' }]}
              >
                <AutoComplete
                  options={stockOptions}
                  onSearch={handleStockSearch}
                  onSelect={handleStockSelect}
                  placeholder="输入代码或名称搜索"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="security_name" label="股票名称">
                <Input placeholder="自动补全" disabled />
              </Form.Item>
            </Col>
          </Row>

          {/* ---- 品种 / 方向 / 订单类型 ---- */}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="instrument_type" label="品种" rules={[{ required: true }]}>
                <Select options={INSTRUMENT_TYPE_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="long_short" label="方向" rules={[{ required: true }]}>
                <Select options={LONG_SHORT_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="order_type" label="订单类型">
                <Select options={ORDER_TYPE_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>

          {/* ---- 入场日期 / 入场价 / 数量 ---- */}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="entry_date" label="入场日期" rules={[{ required: true, message: '请选择' }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="entry_price" label="入场价" rules={[{ required: true, message: '请输入' }]}>
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="quantity" label="数量(股)" rules={[{ required: true, message: '请输入' }]}>
                <InputNumber style={{ width: '100%' }} min={1} step={100} precision={0} />
              </Form.Item>
            </Col>
          </Row>

          {/* ---- 卖出子单卡片 ---- */}
          <Card
            title={`卖出记录（一买多卖） — 总持仓 ${entryQty} / 已卖出 ${totalExitQty} / 剩余 ${remainQty}`}
            size="small"
            className="mb-4"
            extra={
              <Button type="primary" size="small" icon={<PlusOutlined />} onClick={openNewExitSlip}>
                新增卖出
              </Button>
            }
          >
            <Table
              columns={exitSlipColumns}
              dataSource={exitSlips}
              rowKey="id"
              pagination={false}
              size="small"
              loading={loadingExitSlips}
              locale={{ emptyText: '暂无卖出记录' }}
            />
            {totalExitQty > entryQty && (
              <div className="text-red-500 text-sm mt-2">
                ⚠️ 卖出数量 {totalExitQty} 超过买入数量 {entryQty}，请检查
              </div>
            )}
          </Card>

          {/* ---- 佣金 & 滑点 ---- */}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="commission_entry" label="入场佣金">
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="commission_exit" label="出场佣金（汇总）">
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="slip_point" label="滑点(元/股)" tooltip="每股滑点金额，总滑点=滑点×数量">
                <InputNumber style={{ width: '100%' }} min={0} step={0.001} precision={4} />
              </Form.Item>
            </Col>
          </Row>

          {/* ---- 毛盈亏 / 通道高度 / 实际止损 ---- */}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="gross_profit" label="毛盈亏" tooltip="应用层计算，可手动覆盖">
                <InputNumber style={{ width: '100%' }} step={0.01} precision={4} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="channel_height" label="通道高度" tooltip="价格通道高度，用于打分">
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="actual_stop_loss" label="实际止损价">
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
          </Row>

          {/* ---- 评分 & 等级 ---- */}
          <Row gutter={16}>
            <Col span={6}>
              <Form.Item name="entry_score" label="进场得分" rules={[{ type: 'number', min: 0, max: 100 }]}>
                <InputNumber style={{ width: '100%' }} min={0} max={100} step={0.1} precision={1} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="exit_score" label="出场得分" rules={[{ type: 'number', min: 0, max: 100 }]}>
                <InputNumber style={{ width: '100%' }} min={0} max={100} step={0.1} precision={1} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="trade_score" label="总得分" rules={[{ type: 'number', min: 0, max: 100 }]}>
                <InputNumber style={{ width: '100%' }} min={0} max={100} step={0.1} precision={1} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="trade_grade" label="等级">
                <Select allowClear placeholder="选择" options={TRADE_GRADE_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="trigger_source" label="触发来源">
            <Select allowClear placeholder="选择触发来源" options={TRIGGER_SOURCE_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>

      {/* ---- 新增/编辑卖出子单弹窗 ---- */}
      <Modal
        title={editingSlip ? '编辑卖出记录' : '新增卖出记录'}
        open={exitSlipModalOpen}
        onCancel={() => setExitSlipModalOpen(false)}
        onOk={saveExitSlip}
        okText="保存"
        cancelText="取消"
        width={560}
        destroyOnClose
      >
        <Form form={exitSlipForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="exit_date" label="出场日期" rules={[{ required: true, message: '请选择' }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="exit_price" label="出场价" rules={[{ required: true, message: '请输入' }]}>
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="quantity"
                label="卖出数量"
                rules={[{ required: true, message: '请输入' }]}
                extra={`可卖 ${snapshotMaxSellQty} 股`}
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={1}
                  max={snapshotMaxSellQty}
                  step={100}
                  precision={0}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="commission" label="佣金">
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="exit_reason" label="出场原因">
                <Select allowClear placeholder="选择">
                  {EXIT_REASON_OPTIONS.map(opt => (
                    <Option key={opt.value} value={opt.value}>
                      {opt.label}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="exit_score" label="出场得分">
                <InputNumber style={{ width: '100%' }} min={0} max={100} step={0.1} precision={1} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="actual_stop_loss" label="实际止损价">
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="slip_point" label="滑点(元/股)">
                <InputNumber style={{ width: '100%' }} min={0} step={0.001} precision={4} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </>
  );
};

export default TradingRecordForm;