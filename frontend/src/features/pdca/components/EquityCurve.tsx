/**
 * EquityCurve.tsx — 资金记录页面（录入 / 编辑 / 删除）
 *
 * 职责：
 * - 资金记录明细列表（增 / 改 / 删）
 * - 资金曲线展示已拆分为独立页签 EquityAutoCurve（自动计算）
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  Button, Modal, Form, InputNumber, DatePicker, App, Space, Spin, Empty,
  Table, Popconfirm,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import type { AccountSnapshot, AccountSnapshotFormData } from '../types';
import { saveSnapshot, updateSnapshot, deleteSnapshot, fetchSnapshots } from '../api';

const fmtMoney = (v: number | null | undefined) => (v == null ? '-' : `¥${Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

const EquityCurve: React.FC = () => {
  const { message } = App.useApp();
  const [snapshots, setSnapshots] = useState<AccountSnapshot[]>([]);
  const [loading, setLoading] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<AccountSnapshot | null>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const snapRes = await fetchSnapshots();
      if (snapRes.code === 200) setSnapshots(snapRes.data.items || []);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载资金记录失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => { loadData(); }, [loadData]);

  const openCreate = useCallback(() => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ deposit: 0, withdrawal: 0, realized_pnl: 0 });
    setFormOpen(true);
  }, [form]);

  const openEdit = useCallback((record: AccountSnapshot) => {
    setEditing(record);
    form.setFieldsValue({
      snapshot_date: dayjs(record.snapshot_date),
      total_asset: record.total_asset,
      available_cash: record.available_cash,
      position_value: record.position_value,
      deposit: record.deposit,
      withdrawal: record.withdrawal,
      realized_pnl: record.realized_pnl,
    });
    setFormOpen(true);
  }, [form]);

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
      const res = editing
        ? await updateSnapshot(editing.id, data)
        : await saveSnapshot(data);
      if (res.code === 200) {
        message.success(editing ? '修改成功' : '保存成功');
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
  }, [form, message, loadData, editing]);

  const handleDelete = useCallback(async (id: number) => {
    try {
      const res = await deleteSnapshot(id);
      if (res.code === 200) {
        message.success('删除成功');
        loadData();
      } else {
        message.error(res.message || '删除失败');
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  }, [message, loadData]);

  const columns: ColumnsType<AccountSnapshot> = [
    { title: '日期', dataIndex: 'snapshot_date', width: 120 },
    { title: '账户总资产', dataIndex: 'total_asset', width: 140, align: 'right', render: fmtMoney },
    { title: '可用资金', dataIndex: 'available_cash', width: 130, align: 'right', render: fmtMoney },
    { title: '持仓市值', dataIndex: 'position_value', width: 130, align: 'right', render: fmtMoney },
    { title: '净出入金', dataIndex: 'net_deposit', width: 120, align: 'right', render: fmtMoney },
    { title: '已实现盈亏', dataIndex: 'realized_pnl', width: 130, align: 'right', render: fmtMoney },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, record) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEdit(record)}>编辑</Button>
          <Popconfirm
            title="确认删除该资金记录？"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
          >
            <Button type="link" danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="h-full flex flex-col p-4 gap-4">
      <div className="flex items-center justify-between flex-shrink-0">
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            录入资金记录
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        </Space>
      </div>

      <div className="flex-1 min-h-0 bg-bg-panel rounded p-4">
        {loading ? (
          <div className="flex justify-center py-20"><Spin /></div>
        ) : (
          <>
            <Table
              rowKey="id"
              size="small"
              columns={columns}
              dataSource={snapshots}
              pagination={{ pageSize: 10, showSizeChanger: false }}
              locale={{ emptyText: <Empty description="暂无资金记录，请先录入" /> }}
            />
          </>
        )}
      </div>

      {/* 资金记录录入/编辑弹窗 */}
      <Modal
        title={editing ? '编辑资金记录' : '录入资金记录'}
        open={formOpen}
        onCancel={() => { setFormOpen(false); form.resetFields(); }}
        onOk={handleSave}
        confirmLoading={saving}
        destroyOnClose
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="snapshot_date" label="日期" rules={[{ required: true, message: '请选择日期' }]}>
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