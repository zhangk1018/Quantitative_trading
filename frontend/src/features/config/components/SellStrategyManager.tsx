// SellStrategyManager.tsx — 自编卖出策略管理区块（系统设置 → 自编指标 → 卖出策略）
// 内嵌区块（非弹窗）：列表 + 新增/编辑表单，localStorage 持久化。
// 数据来源与回测面板卖出策略下拉共享同一 storage（customSellStrategyStorage）。

import React, { useEffect, useState } from 'react';
import {
  Button, Form, Input, Select, Typography, Space, Popconfirm, Table, message,
} from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { INDICATOR_OPERATORS, type IndicatorOperator } from '../../stock-picker/types/customIndicator';
import {
  listCustomSellStrategies,
  saveCustomSellStrategy,
  removeCustomSellStrategy,
  validateSellStrategyFormula,
  type CustomSellStrategy,
} from '../../backtest/utils/customSellStrategyStorage';
import type { BacktestIndicatorThreshold } from '../../backtest/backtestTypes';

const { Text } = Typography;
const { TextArea } = Input;

interface FormValues {
  id?: string;
  name: string;
  formula: string;
  operator: IndicatorOperator;
  defaultThreshold: number;
  description?: string;
}

const SellStrategyManager: React.FC = () => {
  const [strategies, setStrategies] = useState<CustomSellStrategy[]>([]);
  const [editing, setEditing] = useState<CustomSellStrategy | null>(null);
  const [form] = Form.useForm<FormValues>();

  const reload = () => setStrategies(listCustomSellStrategies());

  useEffect(() => {
    reload();
  }, []);

  const handleAdd = () => {
    setEditing(null);
    form.resetFields();
  };

  const handleEdit = (s: CustomSellStrategy) => {
    setEditing(s);
    form.setFieldsValue({
      id: s.id,
      name: s.name,
      formula: s.formula,
      operator: s.operator,
      defaultThreshold: Number(s.defaultThreshold),
      description: s.description,
    });
  };

  const handleDelete = (s: CustomSellStrategy) => {
    removeCustomSellStrategy(s.id);
    message.success(`已删除卖出策略「${s.name}」`);
    reload();
  };

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      // 公式校验（复用自编指标校验：calculate 签名/括号/危险字符/import 白名单）
      const check = validateSellStrategyFormula(values.formula);
      if (!check.valid) {
        message.error(`公式校验失败：${check.errors.join('；')}`);
        return;
      }
      try {
        saveCustomSellStrategy({
          id: editing?.id,
          name: values.name,
          formula: values.formula,
          operator: values.operator,
          defaultThreshold: values.defaultThreshold as BacktestIndicatorThreshold,
          description: values.description ?? '',
        });
        message.success(editing ? `卖出策略「${values.name}」已更新` : `卖出策略「${values.name}」已创建`);
        reload();
        handleAdd();
      } catch (e) {
        message.error(e instanceof Error ? e.message : '保存失败');
      }
    });
  };

  return (
    <div className="space-y-4" data-testid="sell-strategy-manager">
      {/* 顶部操作栏 */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <Space size="small">
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={handleAdd}
            data-testid="sell-strategy-create-btn"
          >
            新建卖出策略
          </Button>
        </Space>
        <Text className="text-text-secondary text-sm" data-testid="sell-strategy-count">
          已有 {strategies.length} 条
        </Text>
      </div>

      {/* 策略列表 */}
      <Table<CustomSellStrategy>
        size="small"
        rowKey="id"
        dataSource={strategies}
        pagination={false}
        locale={{ emptyText: '暂无自编卖出策略，点击上方「新建卖出策略」创建' }}
        columns={[
          { title: '名称', dataIndex: 'name', width: 160 },
          { title: '说明', dataIndex: 'description', ellipsis: true },
          {
            title: '操作',
            width: 120,
            render: (_, record) => (
              <Space size="small">
                <Button size="small" onClick={() => handleEdit(record)}>编辑</Button>
                <Popconfirm
                  title={`删除卖出策略「${record.name}」？`}
                  onConfirm={() => handleDelete(record)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      {/* 新增/编辑表单 */}
      <div
        style={{ borderTop: '1px solid var(--border-color, #d9d9d9)', paddingTop: 12 }}
        data-testid="sell-strategy-form"
      >
        <Space style={{ marginBottom: 8 }}>
          <Text strong>{editing ? `编辑卖出策略：${editing.name}` : '新建卖出策略'}</Text>
          {editing && (
            <Button size="small" onClick={handleAdd}>取消编辑</Button>
          )}
        </Space>
        <Form form={form} layout="vertical" style={{ maxWidth: 720 }}>
          <Form.Item
            name="name"
            label="策略名称"
            rules={[{ required: true, message: '请输入策略名称' }, {
              validator: (_, v: string) => {
                if (!v) return Promise.resolve();
                if (v.length < 2 || v.length > 30) return Promise.reject(new Error('名称长度须为 2-30 字符'));
                return Promise.resolve();
              },
            }]}
          >
            <Input placeholder="如：跌破5日均线卖出" />
          </Form.Item>
          <Form.Item
            name="formula"
            label="Python 脚本"
            rules={[{ required: true, message: '请输入 Python 脚本' }]}
            extra="定义 def calculate(open_prices, high_prices, low_prices, close_prices, volumes): 返回每日卖出信号数组（长度与 K 线一致）。回测引擎仅在持仓状态下消费该信号。"
          >
            <TextArea rows={8} placeholder={'def calculate(open_prices, high_prices, low_prices, close_prices, volumes):\n    ma5 = [...]  # 计算 5 日均线\n    return [1 if c < ma else 0 for c, ma in zip(close_prices, ma5)]'} />
          </Form.Item>
          <Space size="large" wrap>
            <Form.Item
              name="operator"
              label="判定算子"
              style={{ minWidth: 160 }}
            >
              <Select
                options={INDICATOR_OPERATORS.map((o) => ({ value: o.value, label: o.label }))}
              />
            </Form.Item>
            <Form.Item
              name="defaultThreshold"
              label="判定阈值（默认）"
              style={{ minWidth: 140 }}
            >
              <Input type="number" placeholder="如：0.97" />
            </Form.Item>
          </Space>
          <Form.Item name="description" label="说明">
            <Input placeholder="策略说明（可选）" />
          </Form.Item>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleSubmit}>
            {editing ? '保存修改' : '创建策略'}
          </Button>
        </Form>
      </div>
    </div>
  );
};

export default SellStrategyManager;