/**
 * CycleOverview.tsx — PDCA 周期总览页面
 *
 * 功能：
 * - 展示 PDCA 周期列表（卡片形式）
 * - 状态流转按钮（PLAN→DO→CHECK→ACT）
 * - 新建周期（弹窗表单）
 * - 删除周期（所有状态均可删除，非PLAN状态解除关联记录并删除交易计划）
 * - Do 模块增强：执行跟踪（DO 状态卡片可展开查看计划 vs 实际执行对比）
 *
 * 依赖后端 API（由量量实现 8.1/8.2）：
 * - GET  /api/pdca/cycles          — 列表现有
 * - POST /api/pdca/cycles          — 新建
 * - PUT  /api/pdca/cycles/{id}     — 更新
 * - DELETE /api/pdca/cycles/{id}   — 删除
 * - PUT  /api/pdca/cycles/{id}/transition — 状态流转
 * - GET  /api/pdca/cycles/{id}/execution-summary — 执行跟踪（Phase B）
 */

import React, { memo, useEffect, useState, useCallback } from 'react';
import {
  Card, Button, Tag, Modal, Form, Input, DatePicker, Select, message, Spin, Empty, Space, Typography, Popconfirm,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, ReloadOutlined, RightCircleOutlined, CheckCircleOutlined,
  AuditOutlined, SyncOutlined, ExclamationCircleOutlined, BarChartOutlined,
} from '@ant-design/icons';
import type { PDCACycle, CycleStatus, CycleType } from '../types';
import { CYCLE_TYPE_LABELS, CYCLE_TYPE_OPTIONS } from '../constants';
import { fetchCycles, createCycle, deleteCycle, transitionCycle } from '../services/cycle';
import DoExecutionTracker from './DoExecutionTracker';

const { Text, Title } = Typography;

// ── CycleCard 组件（外部定义，支持 memo 有效比较） ──
interface CycleCardProps {
  cycle: PDCACycle;
  transitioning: number | null;
  expandedTracker: number | null;
  onTransition: (id: number, target: CycleStatus) => void;
  onDelete: (id: number) => void;
  onToggleTracker: (id: number | null) => void;
}

const CycleCard = memo<CycleCardProps>(({ cycle, transitioning, expandedTracker, onTransition, onDelete, onToggleTracker }) => {
  const statusConfig = STATUS_CONFIG[cycle.status as CycleStatus] || STATUS_CONFIG.PLAN;
  const transition = TRANSITION_BUTTONS[cycle.status as CycleStatus];
  const isDo = cycle.status === 'DO';
  const trackerExpanded = expandedTracker === cycle.id;

  return (
    <div className="mb-3">
      <Card className={trackerExpanded ? '!rounded-b-none' : ''} size="small" styles={{ body: { padding: '16px 20px' } }}>
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
            {isDo && (
              <Button
                size="small"
                icon={<BarChartOutlined />}
                type={trackerExpanded ? 'primary' : 'default'}
                onClick={() => onToggleTracker(trackerExpanded ? null : cycle.id)}
              >
                {trackerExpanded ? '收起跟踪' : '执行跟踪'}
              </Button>
            )}
            {transition && (
              <Button type="primary" size="small" icon={<RightCircleOutlined />}
                loading={transitioning === cycle.id}
                onClick={() => onTransition(cycle.id, transition.target)}>
                {transition.label}
              </Button>
            )}
            <Popconfirm
              title="确定删除此周期？"
              description={cycle.status === 'PLAN'
                ? '删除后不可恢复（关联交易计划将一并删除）'
                : `周期处于「${statusConfig.label}」状态，删除后关联交易记录将解除绑定，交易计划将一并删除`}
              onConfirm={() => onDelete(cycle.id)} okText="确定" cancelText="取消"
            >
              <Button danger size="small" icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        </div>
      </Card>
      {trackerExpanded && (
        <div className="border border-t-0 border-border-color rounded-b-lg p-4 bg-bg-secondary">
          <DoExecutionTracker cycleId={cycle.id} cycleName={cycle.cycle_name} />
        </div>
      )}
    </div>
  );
});

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
  const [expandedTracker, setExpandedTracker] = useState<number | null>(null);
  const [form] = Form.useForm();

  // ── 加载周期列表 ──
  const loadCycles = useCallback(async () => {
    setLoading(true);
    try {
      const items = await fetchCycles();
      setCycles(items);
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
      await createCycle(payload);
      message.success('周期创建成功');
      setCreateModalOpen(false);
      form.resetFields();
      loadCycles();
    } catch (err: unknown) {
      if (err instanceof Error) message.error('创建失败: ' + err.message);
    }
  };

  // ── 状态流转（useCallback 确保 memo 比较有效） ──
  const [transitionError, setTransitionError] = useState<string | null>(null);
  const handleTransition = useCallback(async (cycleId: number, targetStatus: CycleStatus) => {
    setTransitioning(cycleId);
    try {
      await transitionCycle(cycleId, targetStatus);
      message.success(`状态已变更为 ${STATUS_CONFIG[targetStatus].label}`);
      loadCycles();
    } catch (err: unknown) {
      setTransitionError(err instanceof Error ? err.message : '状态流转失败');
    } finally {
      setTransitioning(null);
    }
  }, [loadCycles]);

  // ── 切换执行跟踪展开/收起 ──
  const handleToggleTracker = useCallback((cycleId: number | null) => {
    setExpandedTracker(cycleId);
  }, []);

  // ── 删除周期（useCallback 确保 memo 比较有效） ──
  const handleDelete = useCallback(async (cycleId: number) => {
    try {
      await deleteCycle(cycleId);
      message.success('周期已删除');
      loadCycles();
    } catch (err: unknown) {
      message.error('删除失败: ' + (err instanceof Error ? err.message : '未知错误'));
    }
  }, [loadCycles]);

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
              expandedTracker={expandedTracker}
              onTransition={handleTransition}
              onDelete={handleDelete}
              onToggleTracker={handleToggleTracker}
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

      {/* 状态流转失败提示弹窗 */}
      <Modal
        open={!!transitionError}
        onCancel={() => setTransitionError(null)}
        footer={[
          <Button key="ok" type="primary" onClick={() => setTransitionError(null)}>
            知道了
          </Button>,
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
              <span className="text-base font-semibold">无法进入复盘</span>
              <span className="text-text-secondary text-sm leading-6">{transitionError}</span>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default CycleOverview;