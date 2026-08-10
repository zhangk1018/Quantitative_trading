/**
 * EquityCurve.tsx — 资金曲线页面（数据获取 + 快照录入）
 *
 * 职责：
 * - 获取资金曲线数据
 * - 渲染资金曲线图表（委托给 CurveChart）
 * - 资金快照录入弹窗
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  Button, Modal, Form, InputNumber, DatePicker, App, Space, Spin, Empty,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { AccountSnapshotFormData, CapitalCurvePoint } from '../types';
import { saveSnapshot, fetchCapitalCurve } from '../api';
import CurveChart from './CurveChart';

const EquityCurve: React.FC = () => {
  const { message } = App.useApp();
  const [curveData, setCurveData] = useState<CapitalCurvePoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const curveRes = await fetchCapitalCurve();
      if (curveRes.code === 200) setCurveData(curveRes.data);
    } catch (err) {
      message.error('加载资金曲线失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSave = useCallback(async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const data: AccountSnapshotFormData = {
        snapshot_date: values.snapshot_date.format('YYYY-MM-DD'),
        total_asset: values.total_asset,
        available_cash: values.available_cash,
        position_value: values.position_value,
        deposit: values.deposit || 0,
        withdrawal: values.withdrawal || 0,
        realized_pnl: values.realized_pnl || 0,
      };
      const res = await saveSnapshot(data);
      if (res.code === 200) {
        message.success('保存成功');
        setFormOpen(false);
        form.resetFields();
        loadData();
      } else {
        message.error(res.message || '保存失败');
      }
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message);
      }
      // 表单校验失败静默
    } finally {
      setSaving(false);
    }
  }, [form, message, loadData]);

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setFormOpen(true)}>
            录入资金快照
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        </Space>
      </div>

      <div className="flex-1 min-h-0">
        {loading ? (
          <div className="flex justify-center py-20"><Spin /></div>
        ) : curveData.length === 0 ? (
          <Empty description="暂无资金数据，请先录入资金快照" />
        ) : (
          <div className="h-full bg-bg-panel rounded p-4 flex items-center justify-center">
            <CurveChart data={curveData} />
          </div>
        )}
      </div>

      {/* 资金快照录入弹窗 */}
      <Modal
        title="录入资金快照"
        open={formOpen}
        onCancel={() => { setFormOpen(false); form.resetFields(); }}
        onOk={handleSave}
        confirmLoading={saving}
        destroyOnClose
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="snapshot_date" label="快照日期" rules={[{ required: true, message: '请选择日期' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="total_asset" label="账户总资产" rules={[{ required: true, message: '请输入' }]}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={2} prefix="¥" />
          </Form.Item>
          <Form.Item name="available_cash" label="可用资金" rules={[{ required: true, message: '请输入' }]}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={2} prefix="¥" />
          </Form.Item>
          <Form.Item name="position_value" label="持仓市值" rules={[{ required: true, message: '请输入' }]}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={2} prefix="¥" />
          </Form.Item>
          <Form.Item name="deposit" label="当日入金" initialValue={0}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={2} prefix="¥" />
          </Form.Item>
          <Form.Item name="withdrawal" label="当日出金" initialValue={0}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={2} prefix="¥" />
          </Form.Item>
          <Form.Item name="realized_pnl" label="当日已实现盈亏" initialValue={0}>
            <InputNumber style={{ width: '100%' }} step={0.01} precision={2} prefix="¥" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default EquityCurve;