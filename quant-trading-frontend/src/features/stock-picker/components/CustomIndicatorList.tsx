/**
 * 自编指标列表组件（P3.3）
 *
 * 设计要点（K 2026-06-17 决策）：
 * - 显示当前 customIndicators 列表，每行：名称 + 分类 + 运算符/阈值 + 公式预览 + 编辑/删除按钮
 * - 编辑按钮 → 父组件 onEdit 回调（打开 CustomIndicatorModal with editing）
 * - 删除按钮 → Popconfirm 二次确认（基于 isIndicatorReferenced 区分未引用/已引用提示）
 *
 * 复用约束：
 * - 不修改 storage / reducer / types（仅消费既有 API）
 * - 删除二次确认文案基于 storage.isIndicatorReferenced 实时判断
 */

import React from 'react';
import { Button, Popconfirm, Tag, Tooltip, Typography } from 'antd';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  CustomIndicator,
  INDICATOR_OPERATORS,
  getCategoryMeta,
} from '../types/customIndicator';
import { isIndicatorReferenced, MOCK_USER_ID } from '../utils/customIndicatorStorage';

const { Text } = Typography;

interface CustomIndicatorListProps {
  /** 自编指标列表（从 state.customIndicators 传入） */
  indicators: ReadonlyArray<CustomIndicator>;
  /** 当前 user_id（V1.0 mock） */
  userId?: string;
  /** 点击编辑按钮回调 */
  onEdit: (indicator: CustomIndicator) => void;
  /** 点击删除确认回调 */
  onDelete: (id: string) => void;
}

/**
 * 阈值转可读字符串
 *  - number: 直接显示
 *  - [a, b]: 区间 [a, b]
 */
function formatThreshold(t: number | [number, number]): string {
  if (Array.isArray(t)) return `[${t[0]}, ${t[1]}]`;
  return String(t);
}

/** 运算符元数据查找 */
function getOperatorLabel(op: string): string {
  const meta = INDICATOR_OPERATORS.find((o) => o.value === op);
  return meta?.label.split(' ')[0] ?? op;
}

/** 公式预览（截断到 40 字符） */
function previewFormula(formula: string, max = 40): string {
  if (formula.length <= max) return formula;
  return formula.slice(0, max) + '...';
}

export const CustomIndicatorList: React.FC<CustomIndicatorListProps> = ({
  indicators,
  userId = MOCK_USER_ID,
  onEdit,
  onDelete,
}) => {
  if (indicators.length === 0) {
    return (
      <div
        className="text-text-secondary text-xs text-center py-2"
        data-testid="custom-list-empty"
      >
        — 暂无自编指标 —
      </div>
    );
  }

  return (
    <div className="space-y-1" data-testid="custom-list">
      {indicators.map((ind) => {
        const category = getCategoryMeta(ind.category);
        const referenced = isIndicatorReferenced(ind.id, userId);
        return (
          <div
            key={ind.id}
            className="flex items-center justify-between gap-2 bg-bg-elevated rounded px-2 py-1.5"
            data-testid={`custom-list-item-${ind.id}`}
          >
            <div className="flex-1 min-w-0">
              {/* 第 1 行：名称 + 分类 Tag */}
              <div className="flex items-center gap-1.5">
                <Text
                  className="text-text-primary text-sm font-medium truncate"
                  data-testid={`custom-list-item-name-${ind.id}`}
                >
                  {ind.name}
                </Text>
                <Tag color={category.color} className="text-xs leading-none">
                  {category.label}
                </Tag>
              </div>
              {/* 第 2 行：运算符 + 阈值 + 公式预览 */}
              <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                <span>{getOperatorLabel(ind.operator)}</span>
                <span>{formatThreshold(ind.defaultThreshold)}</span>
                <span>·</span>
                <Tooltip title={ind.formula}>
                  <code className="font-mono text-xs truncate">
                    {previewFormula(ind.formula)}
                  </code>
                </Tooltip>
              </div>
            </div>
            {/* 操作按钮 */}
            <div className="flex items-center gap-0.5 flex-shrink-0">
              <Tooltip title="编辑">
                <Button
                  type="text"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => onEdit(ind)}
                  data-testid={`custom-list-edit-${ind.id}`}
                  className="text-text-secondary hover:text-color-accent"
                />
              </Tooltip>
              <Popconfirm
                title={
                  referenced
                    ? '该指标被方案引用'
                    : '确认删除该自编指标？'
                }
                description={
                  referenced
                    ? '删除后引用该指标的条件将自动标记为失效（invalid），是否继续？'
                    : '此操作不可撤销（仅标记软删除）。'
                }
                okText="删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
                onConfirm={() => onDelete(ind.id)}
                data-testid={`custom-list-delete-popconfirm-${ind.id}`}
              >
                <Tooltip title="删除">
                  <Button
                    type="text"
                    size="small"
                    icon={<DeleteOutlined />}
                    data-testid={`custom-list-delete-${ind.id}`}
                    className="text-text-secondary hover:text-color-down"
                  />
                </Tooltip>
              </Popconfirm>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default CustomIndicatorList;
