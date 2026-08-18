/**
 * ActModule.tsx — 迭代处理记录（问题清单+改进措施）
 *
 * 功能：
 * - 选择周期（ACT 状态优先，支持切换）
 * - 查看/编辑问题清单
 * - 改进措施编辑
 * - 绑定下一周期目标
 * - 冻结经验标记
 */
import React, { useEffect, useState } from 'react';
import {
  Card, Button, Select, Spin, Empty, message, Tag, Input, Space, Typography,
  List, Modal, Form, Switch, Descriptions, Popconfirm,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, EditOutlined,
  CheckCircleOutlined, ExclamationCircleOutlined, ReloadOutlined,
} from '@ant-design/icons';
import type { ActRecord, ActRecordFormData } from '../types';
import { fetchActRecords, createActRecord, updateActRecord, deleteActRecord } from '../services/act-record';
import TagInput from './TagInput';
import { usePDCACycle } from '../hooks/usePDCACycle';

const { TextArea } = Input;
const { Title, Text } = Typography;

const ActModule: React.FC = () => {
  const {
    cycles, loading, selectedCycleId, selectedCycle, setSelectedCycleId, refresh: refreshCycles,
  } = usePDCACycle({ statusOrder: { ACT: 0, CHECK: 1, DO: 2, PLAN: 3 } });

  const [records, setRecords] = useState<ActRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // 编辑弹窗
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<ActRecord | null>(null);
  const [editForm] = Form.useForm();

  // 选择周期时加载记录
  useEffect(() => {
    if (!selectedCycleId) {
      setRecords([]);
      return;
    }
    const loadRecords = async () => {
      setRecordsLoading(true);
      try {
        const items = await fetchActRecords(selectedCycleId);
        setRecords(items);
      } catch (err: unknown) {
        message.error('加载改进记录失败: ' + (err instanceof Error ? err.message : ''));
      } finally {
        setRecordsLoading(false);
      }
    };
    loadRecords();
  }, [selectedCycleId]);

  // 打开新建弹窗
  const handleAdd = () => {
    setEditingRecord(null);
    editForm.resetFields();
    editForm.setFieldsValue({ pdca_cycle_id: selectedCycleId, is_freeze_experience: false, problem_list: [] });
    setEditModalOpen(true);
  };

  // 打开编辑弹窗
  const handleEdit = (record: ActRecord) => {
    setEditingRecord(record);
    editForm.setFieldsValue({
      ...record,
      problem_list: record.problem_list || [],
    });
    setEditModalOpen(true);
  };

  // 保存记录（乐观更新）
  const handleSave = async () => {
    try {
      const values = await editForm.validateFields();
      setSaving(true);

      if (editingRecord) {
        await updateActRecord(editingRecord.id, values);
        message.success('改进记录已更新');
        setEditModalOpen(false);
        // 乐观更新：直接修改本地记录
        setRecords((prev) =>
          prev.map((r) => (r.id === editingRecord.id ? { ...r, ...values } : r)),
        );
      } else {
        await createActRecord(values as ActRecordFormData);
        message.success('改进记录已创建');
        setEditModalOpen(false);
        // 新建后需全量拉取（因为后端生成了完整记录）
        const items = await fetchActRecords(selectedCycleId!);
        setRecords(items);
      }
    } catch (err: unknown) {
      if (err instanceof Error) message.error('保存失败: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  // 删除记录（乐观更新）
  const handleDelete = async (recordId: number) => {
    try {
      await deleteActRecord(recordId);
      message.success('改进记录已删除');
      // 乐观更新：直接从本地删除
      setRecords((prev) => prev.filter((r) => r.id !== recordId));
    } catch (err: unknown) {
      message.error('删除失败: ' + (err instanceof Error ? err.message : ''));
    }
  };

  return (
    <div className="p-4">
      {/* 顶部操作栏 */}
      <div className="flex items-center justify-between mb-4">
        <Title level={5} className="!mb-0"><CheckCircleOutlined className="mr-2" />改进措施</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refreshCycles} size="small">刷新</Button>
        </Space>
      </div>

      {/* 周期选择器 */}
      <div className="mb-4 flex items-center gap-3">
        <Select
          className="max-w-md"
          style={{ width: 400 }}
          placeholder="选择要改进的周期..."
          value={selectedCycleId}
          onChange={setSelectedCycleId}
          loading={loading}
          options={cycles.map(c => ({
            value: c.id,
            label: `${c.cycle_name}（${c.start_date} ~ ${c.end_date}）[${c.status}]`,
          }))}
        />
        {selectedCycleId && (
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            新增改进记录
          </Button>
        )}
      </div>

      {!selectedCycleId ? (
        <Empty description="请选择一个周期查看改进记录" />
      ) : recordsLoading ? (
        <div className="flex justify-center py-16"><Spin tip="加载中..." /></div>
      ) : records.length === 0 ? (
        <Empty description="暂无改进记录，点击「新增改进记录」开始">
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            新增改进记录
          </Button>
        </Empty>
      ) : (
        <div>
          {/* 周期信息 */}
          {selectedCycle && (
            <Card size="small" className="mb-4">
              <Descriptions size="small" column={4}>
                <Descriptions.Item label="周期名称">{selectedCycle.cycle_name}</Descriptions.Item>
                <Descriptions.Item label="状态">
                  <Tag color={selectedCycle.status === 'ACT' ? 'green' : 'default'}>{selectedCycle.status}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="起止日期">{selectedCycle.start_date} ~ {selectedCycle.end_date}</Descriptions.Item>
                <Descriptions.Item label="周期目标">{selectedCycle.goal_text || '-'}</Descriptions.Item>
              </Descriptions>
            </Card>
          )}

          {/* 改进记录列表 */}
          <List
            dataSource={records}
            renderItem={(record) => (
              <List.Item
                className="!block mb-3"
                actions={[
                  <Button key="edit" type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
                    编辑
                  </Button>,
                  <Popconfirm
                    key="delete"
                    title="确定删除此改进记录？"
                    onConfirm={() => handleDelete(record.id)}
                    okText="确定" cancelText="取消"
                  >
                    <Button type="link" danger icon={<DeleteOutlined />}>删除</Button>
                  </Popconfirm>,
                ]}
              >
                <Card size="small" className="mb-2">
                  <div className="mb-3">
                    <Text strong>改进计划：</Text>
                    <div className="mt-1 text-text-secondary whitespace-pre-wrap">{record.rectify_plan}</div>
                  </div>

                  {record.problem_list && record.problem_list.length > 0 && (
                    <div className="mb-3">
                      <Text strong>问题清单：</Text>
                      <div className="mt-1 flex flex-wrap gap-2">
                        {record.problem_list.map((problem, idx) => (
                          <Tag key={idx} color="red" icon={<ExclamationCircleOutlined />}>{problem}</Tag>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex items-center gap-4 text-sm text-text-secondary">
                    {record.bind_next_cycle_goal && (
                      <span>下一周期目标：{record.bind_next_cycle_goal}</span>
                    )}
                    {record.is_freeze_experience && (
                      <Tag color="blue">已冻结经验</Tag>
                    )}
                    {record.new_config_version && (
                      <Tag>配置版本：{record.new_config_version}</Tag>
                    )}
                  </div>
                </Card>
              </List.Item>
            )}
          />
        </div>
      )}

      {/* 编辑弹窗 */}
      <Modal
        title={editingRecord ? '编辑改进记录' : '新增改进记录'}
        open={editModalOpen}
        onOk={handleSave}
        onCancel={() => setEditModalOpen(false)}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        destroyOnClose
        width={640}
      >
        <Form
          form={editForm}
          layout="vertical"
          initialValues={{ is_freeze_experience: false, problem_list: [] }}
        >
          <Form.Item name="pdca_cycle_id" hidden>
            <Input />
          </Form.Item>

          <Form.Item
            name="rectify_plan"
            label="改进计划"
            rules={[{ required: true, message: '请输入改进计划' }]}
          >
            <TextArea rows={4} placeholder="描述本周期需要改进的具体措施..." />
          </Form.Item>

          <Form.Item name="bind_next_cycle_goal" label="下一周期目标">
            <TextArea rows={2} placeholder="可选：为下一周期设定改进目标" />
          </Form.Item>

          <Form.Item name="problem_list" label="问题清单">
            <TagInput placeholder="输入问题后按 Enter 添加（如：未严格执行止损）" />
          </Form.Item>

          <Space direction="vertical" className="w-full">
            <Form.Item name="is_freeze_experience" label="冻结经验" valuePropName="checked">
              <Switch checkedChildren="已冻结" unCheckedChildren="未冻结" />
            </Form.Item>
            <Text type="secondary" className="text-xs">
              冻结后，本周期的问题和经验将写入经验知识库，供后续周期参考
            </Text>
          </Space>

          <Form.Item name="new_config_version" label="配置版本号">
            <Input placeholder="可选：如调整了风控参数，记录版本号" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ActModule;