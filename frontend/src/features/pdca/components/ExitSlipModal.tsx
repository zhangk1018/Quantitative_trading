/**
 * ExitSlipModal.tsx — 卖出子单新增/编辑弹窗
 *
 * 从 TradingRecordForm.tsx 抽取，降低主表单复杂度。
 */

import React, { useEffect } from 'react';
import { Modal, Form, InputNumber, DatePicker, Select, Row, Col } from 'antd';
import dayjs from 'dayjs';
import type { ExitSlip, ExitSlipFormData } from '../types';
import { EXIT_REASON_OPTIONS } from '../types';

const { Option } = Select;

interface Props {
  open: boolean;
  editingSlip: ExitSlip | null;
  snapshotMaxSellQty: number;
  onSave: (values: ExitSlipFormData, editingSlip: ExitSlip | null) => Promise<void>;
  onCancel: () => void;
}

const ExitSlipModal: React.FC<Props> = ({ open, editingSlip, snapshotMaxSellQty, onSave, onCancel }) => {
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) {
      if (editingSlip) {
        form.setFieldsValue({
          exit_date: dayjs(editingSlip.exit_date),
          exit_price: editingSlip.exit_price,
          quantity: editingSlip.quantity,
          commission: editingSlip.commission,
          exit_reason: editingSlip.exit_reason ?? undefined,
          exit_score: editingSlip.exit_score ?? undefined,
          actual_stop_loss: editingSlip.actual_stop_loss ?? undefined,
          slip_point: editingSlip.slip_point,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          exit_date: dayjs(),
          commission: 0,
          slip_point: 0,
        });
      }
    }
  }, [open, editingSlip, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const data: ExitSlipFormData = {
        ...values,
        exit_date: dayjs.isDayjs(values.exit_date) ? values.exit_date.format('YYYY-MM-DD') : values.exit_date,
      };
      await onSave(data, editingSlip);
    } catch {
      // 表单校验失败，不处理
    }
  };

  return (
    <Modal
      title={editingSlip ? '编辑卖出记录' : '新增卖出记录'}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      okText="保存"
      cancelText="取消"
      width={560}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
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
  );
};

export default ExitSlipModal;