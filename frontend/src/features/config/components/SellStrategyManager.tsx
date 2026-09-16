/**
 * 自编卖出策略管理区块（系统设置 → 自编指标 → 卖出策略）
 *
 * 设计风格与买入策略 CustomIndicatorManager 对齐：
 * - 顶部操作栏：新建按钮 + 导入导出按钮 + 计数
 * - 卡片式列表（bg-bg-elevated 卡片 + 名称/算子/阈值/说明 + 编辑/删除操作）
 * - Drawer 弹窗创建/编辑（SellStrategyModal，对齐 CustomIndicatorModal）
 * - localStorage 持久化（customSellStrategyStorage）
 */

import React, { useEffect, useState, useCallback } from 'react';
import { Button, Popconfirm, Space, Typography, Tooltip, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import SellStrategyModal from './SellStrategyModal';
import SellImportExportButtons from './SellImportExportButtons';
import {
  listCustomSellStrategies,
  saveCustomSellStrategy,
  removeCustomSellStrategy,
  validateSellStrategyFormula,
  type CustomSellStrategy,
} from '../../backtest/utils/customSellStrategyStorage';
import { INDICATOR_OPERATORS } from '../../stock-picker/types/customIndicator';
import type { BacktestIndicatorOperator, BacktestIndicatorThreshold } from '../../backtest/backtestTypes';

const { Text } = Typography;

/** 阈值转可读字符串 */
function formatThreshold(t: BacktestIndicatorThreshold): string {
  if (Array.isArray(t)) return `[${t[0]}, ${t[1]}]`;
  return String(t);
}

/** 运算符 → 标签 */
function getOperatorLabel(op: string): string {
  const meta = INDICATOR_OPERATORS.find((o) => o.value === op);
  return meta?.label.split(' ')[0] ?? op;
}

/** 公式预览（截断到 40 字符） */
function previewFormula(formula: string, max = 40): string {
  if (formula.length <= max) return formula;
  return formula.slice(0, max) + '...';
}

const SellStrategyManager: React.FC = () => {
  const [strategies, setStrategies] = useState<CustomSellStrategy[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<CustomSellStrategy | null>(null);

  const reload = useCallback(() => setStrategies(listCustomSellStrategies()), []);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleAdd = () => {
    setEditing(null);
    setShowModal(true);
  };

  const handleEdit = (s: CustomSellStrategy) => {
    setEditing(s);
    setShowModal(true);
  };

  const handleDelete = (s: CustomSellStrategy) => {
    removeCustomSellStrategy(s.id);
    message.success(`已删除卖出策略「${s.name}」`);
    reload();
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setEditing(null);
  };

  const handleConfirm = (data: {
    name: string;
    formula: string;
    operator: BacktestIndicatorOperator;
    defaultThreshold: BacktestIndicatorThreshold;
    description: string;
  }) => {
    // 最终公式校验（双重保证）
    const check = validateSellStrategyFormula(data.formula);
    if (!check.valid) {
      message.error(`公式校验失败：${check.errors.join('；')}`);
      return;
    }
    try {
      saveCustomSellStrategy({
        id: editing?.id,
        name: data.name,
        formula: data.formula,
        operator: data.operator,
        defaultThreshold: data.defaultThreshold,
        description: data.description,
      });
      message.success(editing ? `卖出策略「${data.name}」已更新` : `卖出策略「${data.name}」已创建`);
      reload();
      handleCloseModal();
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败');
    }
  };

  const handleImportSuccess = () => {
    reload();
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
          <SellImportExportButtons
            strategies={strategies}
            onImportSuccess={handleImportSuccess}
          />
        </Space>
        <Text className="text-text-secondary text-sm" data-testid="sell-strategy-count">
          已有 {strategies.length} 条
        </Text>
      </div>

      {/* 策略列表（卡片式，对齐 CustomIndicatorList 风格） */}
      {strategies.length === 0 ? (
        <div className="text-text-secondary text-xs text-center py-2" data-testid="sell-strategy-list-empty">
          — 暂无自编卖出策略 —
        </div>
      ) : (
        <div className="space-y-1" data-testid="sell-strategy-list">
          {strategies.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between gap-2 bg-bg-elevated rounded px-2 py-1.5"
              data-testid={`sell-strategy-item-${s.id}`}
            >
              <div className="flex-1 min-w-0">
                {/* 第 1 行：名称 */}
                <Text
                  className="text-text-primary text-sm font-medium truncate block"
                  data-testid={`sell-strategy-item-name-${s.id}`}
                >
                  {s.name}
                </Text>
                {/* 第 2 行：算子 + 阈值 + 公式预览 + 说明 */}
                <div className="flex items-center gap-1.5 text-xs text-text-secondary mt-0.5">
                  <span>{getOperatorLabel(s.operator)}</span>
                  <span>{formatThreshold(s.defaultThreshold)}</span>
                  <span>·</span>
                  <Tooltip title={s.formula}>
                    <code className="font-mono text-xs truncate max-w-[240px] inline-block align-bottom">
                      {previewFormula(s.formula)}
                    </code>
                  </Tooltip>
                  {s.description && (
                    <>
                      <span>·</span>
                      <span className="truncate max-w-[160px]">{s.description}</span>
                    </>
                  )}
                </div>
              </div>
              {/* 操作按钮 */}
              <div className="flex items-center gap-0.5 flex-shrink-0">
                <Tooltip title="编辑">
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => handleEdit(s)}
                    data-testid={`sell-strategy-edit-${s.id}`}
                    className="text-text-secondary hover:text-color-accent"
                  />
                </Tooltip>
                <Popconfirm
                  title={`确认删除卖出策略「${s.name}」？`}
                  description="此操作不可撤销（仅标记软删除）。"
                  okText="删除"
                  okButtonProps={{ danger: true }}
                  cancelText="取消"
                  onConfirm={() => handleDelete(s)}
                  data-testid={`sell-strategy-delete-popconfirm-${s.id}`}
                >
                  <Tooltip title="删除">
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      data-testid={`sell-strategy-delete-${s.id}`}
                      className="text-text-secondary hover:text-color-down"
                    />
                  </Tooltip>
                </Popconfirm>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Drawer 弹窗 */}
      {showModal && (
        <SellStrategyModal
          title={editing ? '编辑卖出策略' : '新建卖出策略'}
          editing={editing}
          onConfirm={handleConfirm}
          onCancel={handleCloseModal}
        />
      )}
    </div>
  );
};

export default SellStrategyManager;
