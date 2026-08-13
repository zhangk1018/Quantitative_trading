/**
 * CycleOverview.tsx — PDCA 周期总览页面
 *
 * 功能：
 * - 展示 PDCA 周期列表（卡片形式）
 * - 状态流转按钮（PLAN→DO→CHECK→ACT）
 * - 新建周期（弹窗表单）
 * - 删除周期（仅 PLAN 状态可删除）
 *
 * 依赖后端 API（由量量实现 8.1/8.2）：
 * - GET  /api/pdca/cycles          — 列表现有
 * - POST /api/pdca/cycles          — 新建
 * - PUT  /api/pdca/cycles/{id}     — 更新
 * - DELETE /api/pdca/cycles/{id}   — 删除
 * - PUT  /api/pdca/cycles/{id}/transition — 状态流转
 */

import React, { memo, useEffect, useState, useCallback } from 'react';
import {
  Card, Button, Tag, Modal, Form, Input, DatePicker, Select, message, Spin, Empty, Space, Typography, Popconfirm,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, ReloadOutlined, RightCircleOutlined, CheckCircleOutlined,
  AuditOutlined, SyncOutlined,
} from '@ant-design/icons';
import type { PDCACycle, CycleStatus, CycleType } from '../types';
import { CYCLE_TYPE_LABELS, CYCLE_TYPE_OPTIONS } from '../types';
import { fetchCycles, createCycle, deleteCycle, transitionCycle } from '../api';

const { Text, Title } = Typography;
const { RangePicker } = DatePicker;

// ── 状态标签配置 ──
const STATUS_CONFIG: Record<CycleStatus, { color: string; label: string; icon: React.ReactNode }> = {
  PLAN:  { color: 'blue',   label: '计划中',   icon: <RightCircleOutlined /> },
  DO:    { color: 'orange', label: '执行中',   icon: <SyncOutlined spin /> },
  CHECK: { color: 'purple', label: '复盘中',   icon: <AuditOutlined /> },
  ACT:   { color: 'green',  label: '改进中',   icon: <CheckCircleOutlined /> },
};

// ── 状态流转箭头文案 ──
const TRANSITION_BUTTONS: Record<CycleStatus, { target: CycleStatus; label: string } | null> = {
  PLAN:  { target: 'DO',    label: '开始执行' },
  DO:    { target: 'CHECK', label: '进入复盘' },
  CHECK: { target: 'ACT',   label: '进入改进' },
  ACT:   { target: 'PLAN',  label: '开始新周期' },
};

const CycleOverview: React.FC = () => {
  const [cycles, setCycles] = useState<PDCACycle[]>([]);
  const [loading, setLoading] = useState(true);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [transitioning, setTransitioning] = useState<number | null>(null);
  const [form] = Form.useForm();

  // ── 加载周期列表 ──
  const loadCycles = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchCycles();
      if (res.code === 200) {
        const items = res.data.items || [];
        setCycles(items);
      } else {
        message.error(res.message || '加载周期列表失败');
      }
    } catch (err: unknown) {
      message.error('加载周期列表失败: ' + (err instanceof Error ? err.message : '未知错误'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCycles();
  }, [loadCycles]);

  // ── 新建周期 ──
  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      const [start, end] = values.dateRange;
      const payload = {
        cycle_name: values.cycle_name,
        cycle_type: values.cycle_type || 'week',
        start_date: start.format('YYYY-MM-DD'),
        end_date: end.format('YYYY-MM-DD'),
        goal_text: values.goal_text || null,
      };
      const res = await createCycle(payload);
      if (res.code === 200) {
        message.success('周期创建成功');
        setCreateModalOpen(false);
        form.resetFields();
        loadCycles();
      } else {
        message.error(res.message || '创建失败');
      }
    } catch (err: unknown) {
      if (err instanceof Error) message.error('创建失败: ' + err.message);
    }
  };

  // ── 状态流转 ──
  const handleTransition = async (cycleId: number, targetStatus: CycleStatus) => {
    setTransitioning(cycleId);
    try {
      const res = await transitionCycle(cycleId, targetStatus);
      if (res.code === 200) {
        message.success(`状态已变更为 ${STATUS_CONFIG[targetStatus].label}`);
        loadCycles();
      } else {
        message.error(res.message || '状态流转失败');
      }
    } catch (err: unknown) {
      message.error('状态流转失败: ' + (err instanceof Error ? err.message : '未知错误'));
    } finally {
      setTransitioning(null);
    }
  };

  // ── 删除周期 ──
  const handleDelete = async (cycleId: number) => {
    try {
      const res = await deleteCycle(cycleId);
      if (res.code === 200) {
        message.success('周期已删除');
        loadCycles();
      } else {
        message.error(res.message || '删除失败');
      }
    } catch (err: unknown) {
      message.error('删除失败: ' + (err instanceof Error ? err.message : '未知错误'));
    }
  };

  // ── 渲染单个周期卡片（React.memo 优化） ──
  const CycleCard = memo(({ cycle, transitioning, onTransition, onDelete }: {
    cycle: PDCACycle;
    transitioning: number | null;
    onTransition: (id: number, target: CycleStatus) => void;
    onDelete: (id: number) => void;
  }) => {
    const statusConfig = STATUS_CONFIG[cycle.status as CycleStatus] || STATUS_CONFIG.PLAN;
    const transition = TRANSITION_BUTTONS[cycle.status as CycleStatus];
    const canDelete = cycle.status === 'PLAN';

    return (
      <Card className="mb-3" size="small" styles={{ body: { padding: '16px 20px' } }}>
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-2">
              <Text strong className="text-base">{cycle.cycle_name}</Text>
              <Tag color={statusConfig.color} icon={statusConfig.icon}>{statusConfig.label}</Tag>
              <Text className="text-text-secondary text-xs">
                {CYCLE_TYPE_LABELS[cycle.cycle_type as CycleType] || cycle.cycle_type}
              </Text>
            </div>
            <div className="text-text-secondary text-sm mb-1">
              {cycle.start_date} ~ {cycle.end_date}
            </div>
            {cycle.goal_text && (
              <div className="text-text-secondary text-sm mt-1">
                <Text type="secondary">目标：{cycle.goal_text}</Text>
              </div>
            )}
          </div>
          <Space className="flex-shrink-0 ml-4">
            {transition && (
              <Button type="primary" size="small" icon={<RightCircleOutlined />}
                loading={transitioning === cycle.id}
                onClick={() => onTransition(cycle.id, transition.target)}>
                {transition.label}
              </Button>
            )}
            {canDelete && (
              <Popconfirm title="确定删除此周期？" description="删除后不可恢复"
                onConfirm={() => onDelete(cycle.id)} okText="确定" cancelText="取消">
                <Button danger size="small" icon={<DeleteOutlined />} />
              </Popconfirm>
            )}
          </Space>
        </div>
      </Card>
    );
  });

  return (
    <div className="p-4">
      {/* 顶部操作栏 */}
      <div className="flex items-center justify-between mb-4">
        <Title level={5} className="!mb-0">PDCA 周期列表</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadCycles} size="small">
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalOpen(true)}
          >
            新建周期
          </Button>
        </Space>
      </div>

      {/* 周期列表 */}
      {loading ? (
        <div className="flex justify-center py-16">
          <Spin tip="加载中..." />
        </div>
      ) : cycles.length === 0 ? (
        <Empty description="暂无周期数据，点击「新建周期」开始" />
      ) : (
        <div>
          {cycles.map((cycle) => (
            <CycleCard
              key={cycle.id}
              cycle={cycle}
              transitioning={transitioning}
              onTransition={handleTransition}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {/* 新建周期弹窗 */}
      <Modal
        title="新建 PDCA 周期"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateModalOpen(false);
          form.resetFields();
        }}
        okText="创建"
        cancelText="取消"
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ cycle_type: 'week' }}
        >
          <Form.Item
            name="cycle_name"
            label="周期名称"
            rules={[{ required: true, message: '请输入周期名称' }]}
          >
            <Input placeholder="如：2026-08 第三周" />
          </Form.Item>
          <Form.Item
            name="dateRange"
            label="起止日期"
            rules={[{ required: true, message: '请选择起止日期' }]}
          >
            <RangePicker className="w-full" />
          </Form.Item>
          <Form.Item
            name="cycle_type"
            label="周期类型"
            rules={[{ required: true, message: '请选择周期类型' }]}
          >
            <Select options={CYCLE_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="goal_text" label="周期目标">
            <Input.TextArea rows={3} placeholder="输入本周期目标（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CycleOverview;