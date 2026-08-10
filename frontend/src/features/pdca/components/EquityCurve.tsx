/**
 * EquityCurve.tsx — 资金曲线图表
 *
 * 功能：
 * - 资金快照录入
 * - 资金曲线展示（SVG 简单折线图）
 * - 出入金节点标注
 * - 调整后净值展示
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  Button, Modal, Form, InputNumber, DatePicker, App, Space, Spin, Empty,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { AccountSnapshotFormData, CapitalCurvePoint } from '../types';
import { saveSnapshot, fetchCapitalCurve } from '../api';

const SVG_WIDTH = 800;
const SVG_HEIGHT = 400;
const PADDING = { top: 30, right: 30, bottom: 40, left: 70 };

/** 简单的 SVG 资金曲线折线图 */
const CurveChart: React.FC<{ data: CapitalCurvePoint[] }> = ({ data }) => {
  if (data.length === 0) return null;

  const chartW = SVG_WIDTH - PADDING.left - PADDING.right;
  const chartH = SVG_HEIGHT - PADDING.top - PADDING.bottom;

  const navValues = data.map((p) => p.adjusted_nav ?? p.total_asset);
  const minVal = Math.min(...navValues) * 0.95;
  const maxVal = Math.max(...navValues) * 1.05;
  const valRange = maxVal - minVal || 1;

  const xScale = (i: number) => PADDING.left + (i / (data.length - 1)) * chartW;
  const yScale = (v: number) => PADDING.top + chartH - ((v - minVal) / valRange) * chartH;

  const linePath = data
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i).toFixed(1)} ${yScale(p.adjusted_nav ?? p.total_asset).toFixed(1)}`)
    .join(' ');

  // Y轴刻度
  const yTicks = 5;
  const yLabels = Array.from({ length: yTicks }, (_, i) => {
    const v = minVal + (valRange / (yTicks - 1)) * i;
    return { v, y: yScale(v) };
  });

  return (
    <svg width="100%" height="100%" viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} preserveAspectRatio="xMidYMid meet">
      {/* 网格线 */}
      {yLabels.map(({ v, y }) => (
        <g key={v}>
          <line x1={PADDING.left} y1={y} x2={SVG_WIDTH - PADDING.right} y2={y} stroke="#222" strokeWidth={0.5} />
          <text x={PADDING.left - 8} y={y + 4} textAnchor="end" fill="#999" fontSize={11}>
            {v >= 10000 ? `${(v / 10000).toFixed(1)}万` : v.toFixed(0)}
          </text>
        </g>
      ))}

      {/* 折线 */}
      <path d={linePath} fill="none" stroke="#1677ff" strokeWidth={2} />

      {/* 数据点 */}
      {data.map((p, i) => {
        const x = xScale(i);
        const y = yScale(p.adjusted_nav ?? p.total_asset);
        return (
          <g key={i}>
            <circle cx={x} cy={y} r={3} fill="#1677ff" />
            {/* 出入金标注 */}
            {p.deposit > 0 && (
              <>
                <text x={x} y={y - 15} textAnchor="middle" fill="#52c41a" fontSize={10}>
                  +{p.deposit}
                </text>
                <polygon points={`${x},${y - 8} ${x - 5},${y - 3} ${x + 5},${y - 3}`} fill="#52c41a" />
              </>
            )}
            {p.withdrawal > 0 && (
              <>
                <text x={x} y={y - 15} textAnchor="middle" fill="#ff4d4f" fontSize={10}>
                  -{p.withdrawal}
                </text>
                <polygon points={`${x},${y - 3} ${x - 5},${y - 8} ${x + 5},${y - 8}`} fill="#ff4d4f" />
              </>
            )}
          </g>
        );
      })}

      {/* X轴日期标签（每 5 个点显示一个） */}
      {data.map((p, i) => {
        if (i % Math.max(1, Math.floor(data.length / 10)) !== 0) return null;
        const x = xScale(i);
        return (
          <text key={i} x={x} y={SVG_HEIGHT - 8} textAnchor="middle" fill="#999" fontSize={10}>
            {p.date.slice(5)}
          </text>
        );
      })}
    </svg>
  );
};

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
      if (curveRes.code === 0) setCurveData(curveRes.data);
    } catch { /* 后端未就绪 */ }
    finally { setLoading(false); }
  }, []);

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
    } catch {
      // 表单校验失败
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