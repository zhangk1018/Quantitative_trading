/**
 * ExitSlipModal.tsx — 卖出记录新增/编辑弹窗
 *
 * 功能：
 * - 自动从系统设置计算出场佣金和滑点
 * - 价格合规校验（出场日在最高最低价范围内）
 */

import React, { useEffect, useRef } from 'react';
import { Modal, Form, InputNumber, DatePicker, Select, Row, Col } from 'antd';
import dayjs from 'dayjs';
import type { ExitSlip, ExitSlipFormData } from '../types';
import { EXIT_REASON_OPTIONS } from '../types';
import { calcCommission, calcStampDuty, calcTransferFee, calcSlippageCost } from '../utils/tradingCostUtils';

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

  // 脏状态追踪：用户手动编辑过的字段不再自动覆盖
  const dirtyFieldsRef = useRef<Set<string>>(new Set());

  // 监听出场价和数量变化，自动计算佣金和滑点
  const exitPrice = Form.useWatch('exit_price', form);
  const quantity = Form.useWatch('quantity', form);

  useEffect(() => {
    if (exitPrice != null && quantity != null && Number.isFinite(exitPrice) && Number.isFinite(quantity)) {
      const p = Number(exitPrice);
      const q = Number(quantity);

      // 不覆盖用户手动编辑过的字段
      if (!dirtyFieldsRef.current.has('commission')) {
        form.setFieldsValue({ commission: calcCommission(p, q) });
      }
      if (!dirtyFieldsRef.current.has('stamp_duty')) {
        form.setFieldsValue({ stamp_duty: calcStampDuty(p, q) });
      }
      if (!dirtyFieldsRef.current.has('transfer_fee')) {
        form.setFieldsValue({ transfer_fee: calcTransferFee(p, q) });
      }
      if (!dirtyFieldsRef.current.has('slip_point')) {
        form.setFieldsValue({ slip_point: Math.round(calcSlippageCost(p) * 10000) / 10000 });
      }
    }
  }, [exitPrice, quantity, form]);

  useEffect(() => {
    if (open) {
      dirtyFieldsRef.current = new Set<string>();
      if (editingSlip) {
        // 编辑模式：已有值视为用户意图，标记为脏不自动覆盖
        dirtyFieldsRef.current.add('commission');
        dirtyFieldsRef.current.add('stamp_duty');
        dirtyFieldsRef.current.add('transfer_fee');
        dirtyFieldsRef.current.add('slip_point');
        form.setFieldsValue({
          exit_date: dayjs(editingSlip.exit_date),
          exit_price: editingSlip.exit_price,
          quantity: editingSlip.quantity,
          commission: editingSlip.commission,
          stamp_duty: editingSlip.stamp_duty,
          transfer_fee: editingSlip.transfer_fee,
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
          stamp_duty: 0,
          transfer_fee: 0,
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
            <Form.Item
              name="commission"
              label="券商佣金"
              tooltip="max(出场价×数量×手续费率, 最低5元)，从系统设置自动计算"
            >
              <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4}
                onChange={() => dirtyFieldsRef.current.add('commission')} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="stamp_duty"
              label="印花税"
              tooltip="出场价×数量×印花税率，仅卖出收取，从系统设置自动计算"
            >
              <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4}
                onChange={() => dirtyFieldsRef.current.add('stamp_duty')} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="transfer_fee"
              label="过户费"
              tooltip="出场价×数量×过户费率，从系统设置自动计算"
            >
              <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4}
                onChange={() => dirtyFieldsRef.current.add('transfer_fee')} />
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
            <Form.Item
              name="slip_point"
              label="滑点(元/股)"
              tooltip="从系统设置自动计算：出场价×滑点率"
            >
              <InputNumber style={{ width: '100%' }} min={0} step={0.001} precision={4}
                onChange={() => dirtyFieldsRef.current.add('slip_point')} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
};

export default ExitSlipModal;