/**
 * TagInput.tsx — 标签输入组件
 *
 * 支持 Enter 添加标签、点击 × 删除标签、输出 string[] 数组
 * 配合 Form.Item 的 valuePropName 为 'value'，getValueFromEvent 从 onChange 获取数组
 */
import React, { useState, useCallback } from 'react';
import { Input, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';

interface TagInputProps {
  value?: string[];
  onChange?: (tags: string[]) => void;
  placeholder?: string;
  maxTags?: number;
}

const TagInput: React.FC<TagInputProps> = ({
  value = [],
  onChange,
  placeholder = '输入后按 Enter 添加',
  maxTags = 20,
}) => {
  const [inputValue, setInputValue] = useState('');

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const trimmed = inputValue.trim();
      if (!trimmed) return;
      if (value.length >= maxTags) return;
      if (value.includes(trimmed)) return;
      onChange?.([...value, trimmed]);
      setInputValue('');
    },
    [inputValue, value, onChange, maxTags],
  );

  const handleRemove = useCallback(
    (removedTag: string) => {
      onChange?.(value.filter((t) => t !== removedTag));
    },
    [value, onChange],
  );

  return (
    <div className="border border-solid border-border rounded p-2 min-h-[40px]">
      <div className="flex flex-wrap gap-1 mb-1">
        {value.map((tag) => (
          <Tag key={tag} closable onClose={() => handleRemove(tag)}>
            {tag}
          </Tag>
        ))}
      </div>
      <Input
        size="small"
        variant="borderless"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={value.length >= maxTags ? '已达上限' : placeholder}
        disabled={value.length >= maxTags}
        prefix={value.length === 0 ? <PlusOutlined /> : undefined}
        style={{ width: 160 }}
      />
    </div>
  );
};

export default TagInput;