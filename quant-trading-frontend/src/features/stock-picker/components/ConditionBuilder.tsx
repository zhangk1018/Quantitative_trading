import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Typography, Button, Collapse, Tooltip, Select } from 'antd';
import {
  ReloadOutlined,
  CloseOutlined,
  BookOutlined,
  ThunderboltOutlined,
  AppstoreAddOutlined,
  PlusCircleOutlined,
} from '@ant-design/icons';
import { useScreenerSelector, useScreenerDispatch } from '../context/ScreenerContext';
import {
  FILTER_PRESETS,
  PATTERN_PRESETS_GROUP,
  LOOKBACK_DAYS_OPTIONS,
  DEFAULT_LOOKBACK_DAYS,
  buildCustomFieldKey,
  FilterCondition,
} from '../types/filterTree';
import { CustomIndicator } from '../types/customIndicator';

const { Text } = Typography;

// 分组预设（技术指标 vs K线形态）
const TECHNICAL_PRESETS = FILTER_PRESETS.filter(
  (p) => !p.fieldKey.startsWith(PATTERN_PRESETS_GROUP.fieldKeyPrefix),
);
const PATTERN_PRESETS = FILTER_PRESETS.filter(
  (p) => p.fieldKey.startsWith(PATTERN_PRESETS_GROUP.fieldKeyPrefix),
);

const ConditionBuilder: React.FC = () => {
  const navigate = useNavigate();
  const collapsedPanels = useScreenerSelector((s) => s.panels.collapsed);
  const filterGroup = useScreenerSelector((s) => s.condition.filterGroup);
  const customIndicators = useScreenerSelector((s) => s.custom.indicators);
  const dispatch = useScreenerDispatch();

  const [lookbackDays, setLookbackDays] = useState<number>(DEFAULT_LOOKBACK_DAYS);

  const conditions = filterGroup?.conditions || [];
  const conditionCount = conditions.length;

  // ✅ 监听 lookbackDays 变化，自动更新所有 K线形态条件的回看天数
  useEffect(() => {
    const hasPattern = conditions.some((c) => c.fieldKey.startsWith('pattern_'));
    if (hasPattern) {
      dispatch({ type: 'UPDATE_PATTERN_LOOKBACKS', payload: lookbackDays });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lookbackDays]);

  // 可用自编指标（过滤已删除）
  const availableCustomIndicators = useMemo(
    () => customIndicators.filter((i: CustomIndicator) => !i.deleted),
    [customIndicators],
  );

  // 已添加的自编指标 ID 集合
  const addedCustomFieldKeys = useMemo(() => {
    const keys = new Set<string>();
    conditions.forEach((c) => {
      if (c.source === 'custom' && c.sourceId) {
        keys.add(c.sourceId);
      }
    });
    return keys;
  }, [conditions]);

  // 用于预设按钮高亮（仅用于单条件预设，组合预设单独处理）
  const selectedPresetFieldKeys = useMemo(() => {
    const keys = new Set<string>();
    conditions.forEach((c) => {
      if (c.source !== 'custom' && !c.fieldKey.startsWith('custom_')) {
        keys.add(c.fieldKey);
      }
    });
    return keys;
  }, [conditions]);

  const handleReset = () => {
    dispatch({ type: 'CLEAR_CONDITIONS' });
  };

  const handleGoToConfigCustom = () => {
    navigate('/config?tab=custom');
  };

  /**
   * 切换预设（支持组合预设展开/收起）
   */
  const handleTogglePreset = (preset: typeof FILTER_PRESETS[number]) => {
    const isPattern = preset.fieldKey.startsWith(PATTERN_PRESETS_GROUP.fieldKeyPrefix);
    // 使用数组存储子条件 fieldKey
    const subFieldKeys = preset.conditions.map((c) => c.fieldKey);
    // 检查是否所有子条件都已存在
    const allExist = subFieldKeys.length > 0 && subFieldKeys.every((key) =>
      conditions.some((c) => c.fieldKey === key)
    );

    if (allExist) {
      // 全部存在 → 全部移除
      conditions.forEach((c) => {
        if (subFieldKeys.includes(c.fieldKey)) {
          dispatch({ type: 'REMOVE_CONDITION', payload: c.id });
        }
      });
      return;
    }

    // 否则：补齐缺失的子条件（部分存在则保留，只添加缺失的）
    const existingKeys = new Set(conditions.map((c) => c.fieldKey));
    preset.conditions.forEach((sub) => {
      if (!existingKeys.has(sub.fieldKey)) {
        dispatch({
          type: 'ADD_CONDITION',
          payload: {
            op: sub.op || 'AND',
            fieldKey: sub.fieldKey,
            label: sub.label,
            // K线形态：使用当前下拉框的值
            ...(isPattern ? { lookbackDays } : {}),
          },
        });
      }
    });
  };

  const handleRemoveCondition = (id: string) => {
    dispatch({ type: 'REMOVE_CONDITION', payload: id });
  };

  const handleCustomIndicatorChange = (selectedIds: string[]) => {
    const newSelected = selectedIds.filter((id) => !addedCustomFieldKeys.has(id));
    newSelected.forEach((id) => {
      const ind = availableCustomIndicators.find((i: CustomIndicator) => i.id === id);
      if (!ind) return;
      dispatch({
        type: 'ADD_CONDITION',
        payload: {
          op: 'AND',
          fieldKey: buildCustomFieldKey(id),
          label: `自编:${ind.name}`,
          source: 'custom',
          sourceId: id,
        },
      });
    });
    const removed = [...addedCustomFieldKeys].filter((id) => !selectedIds.includes(id));
    if (removed.length > 0) {
      const toRemove: string[] = [];
      conditions.forEach((c) => {
        if (c.source === 'custom' && c.sourceId && removed.includes(c.sourceId)) {
          toRemove.push(c.id);
        }
      });
      toRemove.forEach((cid) => dispatch({ type: 'REMOVE_CONDITION', payload: cid }));
    }
  };

  const activeKey = collapsedPanels.condition ? [] : ['condition'];

  // ✅ 渲染预设按钮（修正 Set.every 问题，改用数组）
  const renderPresetButton = (preset: typeof FILTER_PRESETS[number]) => {
    // 使用数组存储子条件 fieldKey
    const subFieldKeys = preset.conditions.map((c) => c.fieldKey);
    // 检查是否所有子条件都已存在（用于高亮）
    const allExist = subFieldKeys.length > 0 && subFieldKeys.every((key) =>
      conditions.some((c) => c.fieldKey === key)
    );
    const isSelected = allExist;

    return (
      <Button
        key={preset.fieldKey}
        size="small"
        type={isSelected ? 'primary' : 'default'}
        onClick={() => handleTogglePreset(preset)}
        data-testid={`condition-preset-${preset.fieldKey}`}
        data-selected={isSelected}
        className="text-text-primary"
      >
        {preset.label}
      </Button>
    );
  };

  const formatCondLabel = (label: string, fieldKey: string, days?: number): string => {
    if (fieldKey.startsWith(PATTERN_PRESETS_GROUP.fieldKeyPrefix) && days) {
      return `${label}（近${days}天）`;
    }
    return label;
  };

  return (
    <Collapse
      activeKey={activeKey}
      ghost
      destroyOnHidden
      className="border-b border-border-color"
      data-testid="condition-builder-collapse"
      onChange={() => dispatch({ type: 'TOGGLE_PANEL', payload: 'condition' })}
      items={[
        {
          key: 'condition',
          label: (
            <span className="flex items-center justify-between w-full">
              <span className="flex items-center gap-2">
                <Text className="text-text-primary font-semibold" data-testid="condition-builder-header">
                  条件构建器
                </Text>
                <span
                  data-testid="condition-builder-count"
                  className="px-1.5 py-0.5 bg-color-up/20 text-color-up text-xs rounded-full"
                >
                  {conditionCount}
                </span>
              </span>
              <span onClick={(e) => e.stopPropagation()}>
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
          ),
          children: (
            <div className="space-y-4">
          {/* 技术指标 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <BookOutlined className="text-text-secondary" />
              <Text className="text-text-secondary text-sm">
                技术指标 ({TECHNICAL_PRESETS.length})
              </Text>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {TECHNICAL_PRESETS.map((preset) => renderPresetButton(preset))}
            </div>
          </div>

          {/* K线形态 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="flex items-center gap-2">
                <ThunderboltOutlined className="text-text-secondary" />
                <Text className="text-text-secondary text-sm">
                  K线形态 ({PATTERN_PRESETS.length})
                </Text>
              </span>
              <span className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <Text className="text-text-secondary text-xs">近</Text>
                <Select
                  size="small"
                  value={lookbackDays}
                  onChange={setLookbackDays}
                  data-testid="condition-lookback-days"
                  style={{ width: 70 }}
                  options={LOOKBACK_DAYS_OPTIONS.map((o) => ({
                    value: o.value,
                    label: `${o.value} 天`,
                  }))}
                />
                <Text className="text-text-secondary text-xs">内出现</Text>
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {PATTERN_PRESETS.map((preset) => renderPresetButton(preset))}
            </div>
          </div>

          {/* 自编指标 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <AppstoreAddOutlined className="text-text-secondary" />
              <Text className="text-text-secondary text-sm">自编指标</Text>
              <Text className="text-text-secondary text-xs">
                ({addedCustomFieldKeys.size}/{availableCustomIndicators.length} 已添加)
              </Text>
            </div>
            {availableCustomIndicators.length === 0 ? (
              <div
                className="text-text-secondary text-sm text-center py-2 border border-dashed border-border-color rounded cursor-pointer hover:border-color-accent"
                data-testid="condition-custom-empty"
                onClick={handleGoToConfigCustom}
              >
                暂无自编指标，<span className="text-color-accent">去配置页新建</span>
              </div>
            ) : (
              <Select
                mode="multiple"
                size="small"
                placeholder="选择自编指标"
                value={[...addedCustomFieldKeys]}
                onChange={handleCustomIndicatorChange}
                data-testid="condition-custom-select"
                className="w-full"
                optionFilterProp="label"
                options={availableCustomIndicators.map((i: CustomIndicator) => ({
                  value: i.id,
                  label: i.name,
                }))}
                popupRender={(menu) => (
                  <div>
                    {menu}
                    <div
                      className="border-t border-border-color p-1 text-center cursor-pointer hover:bg-bg-elevated"
                      data-testid="condition-custom-goto-config"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        handleGoToConfigCustom();
                      }}
                    >
                      <PlusCircleOutlined className="mr-1" />
                      <span className="text-color-accent text-sm">去配置页新建</span>
                    </div>
                  </div>
                )}
              />
            )}
          </div>

          {/* 条件列表 */}
          {conditionCount === 0 ? (
            <div
              className="text-text-secondary text-sm text-center py-3"
              data-testid="condition-empty"
            >
              — 暂无条件，点击上方 preset 添加 —
            </div>
          ) : (
            <div className="space-y-1" data-testid="condition-list">
              {conditions.map((cond) => (
                <div
                  key={cond.id}
                  className="flex items-center justify-between bg-bg-elevated rounded px-2 py-1"
                  data-testid={`condition-item-${cond.id}`}
                >
                  <Text className="text-text-primary text-sm">
                    {formatCondLabel(cond.label, cond.fieldKey, cond.lookbackDays)}
                  </Text>
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
          ),
        },
      ]}
    >
    </Collapse>
  );
};

export default ConditionBuilder;