import React from 'react';
import { Typography, Button, Collapse, Radio, Tooltip } from 'antd';
import {
  ControlOutlined,
  ReloadOutlined,
  PlusOutlined,
  EyeOutlined,
  CloseOutlined,
  BookOutlined,
} from '@ant-design/icons';
import { useScreener } from '../context/ScreenerContext';
import { FILTER_PRESETS, FilterOp } from '../types/filterTree';

const { Text } = Typography;
const { Panel } = Collapse;

const RELATION_OPS: { value: FilterOp; label: string; color: string }[] = [
  { value: 'AND', label: 'AND', color: 'bg-cyan-500' },
  { value: 'OR', label: 'OR', color: 'bg-blue-500' },
  { value: 'NOT', label: 'NOT', color: 'bg-red-500' },
];

const ConditionBuilder: React.FC = () => {
  const { state, dispatch } = useScreener();
  const { collapsedPanels, filterTree, nextConditionOp } = state;

  const conditionCount = filterTree?.conditions.length || 0;

  const handleReset = () => {
    dispatch({ type: 'CLEAR_CONDITIONS' });
  };

  const handleApplyPreset = (presetIndex: number) => {
    const preset = FILTER_PRESETS[presetIndex];
    if (!preset) return;
    dispatch({ type: 'APPLY_PRESET', payload: preset.conditions });
  };

  const handleAddCondition = () => {
    // 默认添加一个"自定义"空条件
    dispatch({
      type: 'ADD_CONDITION',
      payload: { fieldKey: 'custom', label: '自定义条件' },
    });
  };

  const handleRemoveCondition = (id: string) => {
    dispatch({ type: 'REMOVE_CONDITION', payload: id });
  };

  const handleCycleOp = (id: string, currentOp: FilterOp) => {
    // 循环切换 AND → OR → NOT → AND
    const cycle: FilterOp[] = ['AND', 'OR', 'NOT'];
    const idx = cycle.indexOf(currentOp);
    const next = cycle[(idx + 1) % cycle.length];
    dispatch({ type: 'UPDATE_CONDITION_OP', payload: { id, op: next } });
  };

  const handleSetNextOp = (op: FilterOp) => {
    dispatch({ type: 'SET_NEXT_CONDITION_OP', payload: op });
  };

  const activeKey = collapsedPanels.condition ? [] : ['condition'];

  return (
    <Collapse
      activeKey={activeKey}
      ghost
      destroyOnHidden
      className="border-b border-border-color"
      data-testid="condition-builder-collapse"
      onChange={() => dispatch({ type: 'TOGGLE_PANEL', payload: 'condition' })}
    >
      <Panel
        header={
          <span className="flex items-center justify-between w-full">
            <span className="flex items-center gap-2">
              <ControlOutlined className="text-color-up" />
              <Text className="text-text-primary font-semibold" data-testid="condition-builder-header">
                条件构建器
              </Text>
            </span>
            <span className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
              <Text
                className="text-text-secondary text-sm"
                data-testid="condition-builder-count"
              >
                {conditionCount} 个条件
              </Text>
              <Tooltip title="重置所有条件">
                <Button
                  type="text"
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={handleReset}
                  data-testid="condition-builder-reset"
                  className="text-text-secondary hover:text-text-primary"
                >
                  重置
                </Button>
              </Tooltip>
            </span>
          </span>
        }
        key="condition"
      >
        <div className="space-y-3">
          {/* 预设区（6 个预设） */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <BookOutlined className="text-text-secondary" />
              <Text className="text-text-secondary text-sm">预设：</Text>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {FILTER_PRESETS.map((preset, index) => (
                <Button
                  key={preset.fieldKey}
                  size="small"
                  onClick={() => handleApplyPreset(index)}
                  data-testid={`condition-preset-${preset.fieldKey}`}
                  className="text-text-primary"
                >
                  {preset.label}
                </Button>
              ))}
            </div>
          </div>

          {/* 关系选择器 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Text className="text-text-secondary text-sm">关系：</Text>
              <div className="flex gap-1">
                {RELATION_OPS.map((op) => {
                  const isActive = nextConditionOp === op.value;
                  return (
                    <Button
                      key={op.value}
                      size="small"
                      type={isActive ? 'primary' : 'default'}
                      onClick={() => handleSetNextOp(op.value)}
                      data-testid={`condition-op-${op.value.toLowerCase()}`}
                      data-active={isActive}
                      className={isActive ? '' : 'text-text-secondary'}
                    >
                      {op.label}
                    </Button>
                  );
                })}
              </div>
              <Tooltip title="查看关系说明">
                <Button
                  type="text"
                  size="small"
                  icon={<EyeOutlined />}
                  data-testid="condition-op-help"
                  className="text-text-secondary ml-1"
                />
              </Tooltip>
            </div>
          </div>

          {/* 添加条件按钮 */}
          <div>
            <Button
              type="dashed"
              size="small"
              icon={<PlusOutlined />}
              onClick={handleAddCondition}
              data-testid="condition-add"
              className="w-full"
            >
              条件
            </Button>
          </div>

          {/* 条件列表 / 空状态 */}
          {conditionCount === 0 ? (
            <div
              className="text-text-secondary text-sm text-center py-3"
              data-testid="condition-empty"
            >
              — 暂无条件，点击"+ 条件"添加 —
            </div>
          ) : (
            <div className="space-y-1" data-testid="condition-list">
              {filterTree?.conditions.map((cond, idx) => (
                <div
                  key={cond.id}
                  className="flex items-center justify-between bg-bg-elevated rounded px-2 py-1"
                  data-testid={`condition-item-${cond.id}`}
                >
                  <div className="flex items-center gap-2">
                    <Button
                      type="text"
                      size="small"
                      onClick={() => handleCycleOp(cond.id, cond.op)}
                      data-testid={`condition-item-op-${cond.id}`}
                      data-op={cond.op}
                      className="text-color-accent font-mono text-xs px-2"
                    >
                      {cond.op}
                    </Button>
                    <Text className="text-text-primary text-sm">{cond.label}</Text>
                  </div>
                  <Button
                    type="text"
                    size="small"
                    icon={<CloseOutlined />}
                    onClick={() => handleRemoveCondition(cond.id)}
                    data-testid={`condition-item-remove-${cond.id}`}
                    className="text-text-secondary hover:text-color-down"
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </Panel>
    </Collapse>
  );
};

export default ConditionBuilder;
