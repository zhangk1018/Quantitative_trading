/**
 * TradingRecordForm.tsx — 交易记录录入/编辑表单
 *
 * 功能：
 * - 股票代码自动补全（搜索 stock_basic，带防抖）
 * - 数值范围校验（前后端双重）
 * - 日期先后校验（出场日期 > 入场日期）
 * - 支持新增和编辑模式
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Modal, Form, Input, InputNumber, DatePicker, Select, App, Row, Col, AutoComplete,
} from 'antd';
import dayjs from 'dayjs';
import type { TradingRecord, TradingRecordFormData, StockSearchResult } from '../types';
import {
  INSTRUMENT_TYPE_LABELS, LONG_SHORT_LABELS, ORDER_TYPE_LABELS,
  TRADE_GRADE_LABELS, EXIT_REASON_LABELS, TRIGGER_SOURCE_LABELS,
} from '../types';
import { createRecord, updateRecord, searchStocks } from '../api';

interface Props {
  open: boolean;
  record: TradingRecord | null;
  onClose: () => void;
  onSuccess: () => void;
}

const TradingRecordForm: React.FC<Props> = ({ open, record, onClose, onSuccess }) => {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [stockOptions, setStockOptions] = useState<{ value: string; label: string; code: string }[]>([]);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isEdit = !!record;

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

  // 搜索防抖（300ms）
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
        // 后端未就绪时静默
      }
    }, 300);
  }, []);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  const handleStockSelect = useCallback((_value: string, option: { label: string }) => {
    const name = option.label.replace(/^\d+\s*/, '');
    form.setFieldsValue({ security_name: name });
  }, [form]);

  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      const data: TradingRecordFormData = {
        ...values,
        entry_date: values.entry_date?.format('YYYY-MM-DD'),
        exit_date: values.exit_date?.format('YYYY-MM-DD') || undefined,
        // pdca_cycle_id 不硬编码，让后端按默认周期处理
      };
      // 删除未设置的可选字段，避免发送 undefined
      if (!data.entry_score) delete data.entry_score;
      if (!data.exit_score) delete data.exit_score;
      if (!data.trade_score) delete data.trade_score;
      if (!data.trade_grade) delete data.trade_grade;
      if (!data.trigger_source) delete data.trigger_source;
      if (!data.exit_reason) delete data.exit_reason;
      if (!data.actual_stop_loss) delete data.actual_stop_loss;
      if (!data.channel_height) delete data.channel_height;
      if (!data.gross_profit) delete data.gross_profit;

      let res;
      if (isEdit) {
        res = await updateRecord(record!.id, data);
      } else {
        res = await createRecord(data);
      }

      if (res.code === 200) {
        message.success(isEdit ? '更新成功' : '新增成功');
        onSuccess();
      } else {
        message.error(res.message || '保存失败');
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        // 表单校验失败，不处理
      } else {
        message.error('保存失败，请检查网络连接');
      }
    } finally {
      setLoading(false);
    }
  }, [form, isEdit, record, message, onSuccess]);

  return (
    <Modal
      title={isEdit ? '编辑交易记录' : '新增交易记录'}
      open={open}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={loading}
      width={720}
      destroyOnClose
      okText="保存"
      cancelText="取消"
    >
      <Form form={form} layout="vertical" className="mt-4">
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

        <Row gutter={16}>
          <Col span={8}>
            <Form.Item name="instrument_type" label="品种" rules={[{ required: true }]}>
              <Select options={Object.entries(INSTRUMENT_TYPE_LABELS).map(([k, v]) => ({ value: k, label: v }))} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="long_short" label="方向" rules={[{ required: true }]}>
              <Select options={Object.entries(LONG_SHORT_LABELS).map(([k, v]) => ({ value: k, label: v }))} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="order_type" label="订单类型">
              <Select options={Object.entries(ORDER_TYPE_LABELS).map(([k, v]) => ({ value: k, label: v }))} />
            </Form.Item>
          </Col>
        </Row>

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

        <Row gutter={16}>
          <Col span={8}>
            <Form.Item
              name="exit_date"
              label="出场日期"
              dependencies={['entry_date']}
              rules={[
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || !getFieldValue('entry_date')) return Promise.resolve();
                    if (value.isBefore(getFieldValue('entry_date'), 'day')) {
                      return Promise.reject(new Error('出场日期必须晚于或等于入场日期'));
                    }
                    return Promise.resolve();
                  },
                }),
              ]}
            >
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="exit_price" label="出场价">
              <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="exit_reason" label="出场原因">
              <Select
                allowClear
                placeholder="选择出场原因"
                options={Object.entries(EXIT_REASON_LABELS).map(([k, v]) => ({ value: k, label: v }))}
              />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={8}>
            <Form.Item name="commission_entry" label="入场佣金">
              <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="commission_exit" label="出场佣金">
              <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="slip_point" label="滑点(元/股)" tooltip="每股滑点金额，总滑点=滑点×数量">
              <InputNumber style={{ width: '100%' }} min={0} step={0.001} precision={4} />
            </Form.Item>
          </Col>
        </Row>

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
              <Select
                allowClear
                placeholder="选择"
                options={Object.entries(TRADE_GRADE_LABELS).map(([k, v]) => ({ value: k, label: v }))}
              />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item name="trigger_source" label="触发来源">
          <Select
            allowClear
            placeholder="选择触发来源"
            options={Object.entries(TRIGGER_SOURCE_LABELS).map(([k, v]) => ({ value: k, label: v }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default TradingRecordForm;