import React, { useState, useEffect } from 'react';
import { Modal, Radio, Space, Button } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import type { TechnicalIndicatorItem } from '../config/indicatorConfig';

interface TechnicalIndicatorModalProps {
  /** 弹窗标题（如 "MA·日K"） */
  title: string;
  /** 当前打开的指标配置 */
  indicator: TechnicalIndicatorItem;
  /** 当前已选项的 value（可能是 undefined） */
  currentOption: string | undefined;
  /** 点击确定时回调，传入选中的 option value */
  onConfirm: (option: string) => void;
  /** 点击取消或关闭时回调 */
  onCancel: () => void;
  /** 点击清除已选项时回调（可选） */
  onClear?: () => void;
}

/**
 * 通用技术指标配置弹窗
 * - 取消"自定义"选项，仅展示固定 Radio 选项（紧凑风格）
 * - 弹窗内部维护 temp 选中状态，仅在点击"确定"时回写父级
 */
export const TechnicalIndicatorModal: React.FC<TechnicalIndicatorModalProps> = ({
  title,
  indicator,
  currentOption,
  onConfirm,
  onCancel,
  onClear,
}) => {
  // 弹窗内部维护 temp 选中值
  const [tempOption, setTempOption] = useState<string | undefined>(currentOption);

  // 每次弹窗打开时同步当前已选
  useEffect(() => {
    setTempOption(currentOption);
  }, [currentOption]);

  const hasSelected = !!currentOption;

  return (
    <Modal
      open
      title={title}
      onCancel={onCancel}
      footer={null}
      width={400}
      centered
      destroyOnHidden
      maskClosable={false}
      data-testid={`technical-modal-${indicator.id}`}
    >
      <div className="py-1">
        <Radio.Group
          value={tempOption}
          onChange={(e) => setTempOption(e.target.value)}
          className="w-full"
        >
          <Space direction="vertical" size={4} className="w-full">
            {indicator.options.map((opt) => (
              <Radio
                key={opt.value}
                value={opt.value}
                className="text-text-primary text-sm"
                data-testid={`technical-modal-${indicator.id}-option-${opt.value}`}
              >
                {opt.label}
              </Radio>
            ))}
          </Space>
        </Radio.Group>

        {hasSelected && (
          <div
            className="mt-2 text-xs text-text-secondary"
            data-testid={`technical-modal-${indicator.id}-selected`}
          >
            当前已选：<span className="text-text-primary font-medium">
              {indicator.options.find((o) => o.value === currentOption)?.label}
            </span>
            {onClear && (
              <Button
                type="link"
                size="small"
                danger
                onClick={onClear}
                data-testid={`technical-modal-${indicator.id}-clear`}
                className="ml-2"
              >
                清除已选
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="flex justify-end gap-2 pt-2 border-t border-border-color mt-2">
        <Button
          size="small"
          onClick={onCancel}
          data-testid={`technical-modal-${indicator.id}-cancel`}
        >
          取消
        </Button>
        <Button
          size="small"
          type="primary"
          disabled={!tempOption}
          onClick={() => tempOption && onConfirm(tempOption)}
          data-testid={`technical-modal-${indicator.id}-confirm`}
        >
          确定
        </Button>
      </div>
    </Modal>
  );
};
