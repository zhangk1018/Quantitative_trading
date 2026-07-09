import React, { useState, useEffect } from 'react';
import { Modal, Input, Form, message } from 'antd';
import type { SavedStrategy } from '../hooks/useSavedStrategies';

interface SaveStrategyModalProps {
  visible: boolean;
  existingStrategies: SavedStrategy[];
  onClose: () => void;
  onSave: (name: string) => void;
}

/**
 * 保存策略弹窗 — 用户输入策略名称，校验非空和不重复
 */
export function SaveStrategyModal({ visible, existingStrategies, onClose, onSave }: SaveStrategyModalProps) {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (visible) {
      form.resetFields();
    }
  }, [visible, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const name = values.name.trim();

      // 校验重名
      const duplicate = existingStrategies.some(s => s.name.trim() === name);
      if (duplicate) {
        message.error('策略名称已存在，请使用其他名称');
        return;
      }

      setSaving(true);
      onSave(name);
      setSaving(false);
      onClose();
    } catch {
      // 用户取消或校验失败
    }
  };

  return (
    <Modal
      title="保存当前策略"
      open={visible}
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      data-testid="save-strategy-modal"
      okButtonProps={{ 'data-testid': 'save-strategy-modal-ok' }}
      cancelButtonProps={{ 'data-testid': 'save-strategy-modal-cancel' }}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="策略名称"
          rules={[
            { required: true, message: '请输入策略名称' },
            { max: 30, message: '策略名称不能超过 30 个字符' }
          ]}
        >
          <Input placeholder="请输入策略名称，如“高ROE低PE”" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
