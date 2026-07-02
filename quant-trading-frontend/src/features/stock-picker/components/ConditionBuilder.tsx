import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Typography, Button, Collapse, Tooltip, Select } from 'antd';
import {
  ControlOutlined,
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
const { Panel } = Collapse;

/** K 2026-06-17 决策：按 fieldKey 区分三组 preset */
const TECHNICAL_PRESETS = FILTER_PRESETS.filter(
  (p) => !p.fieldKey.startsWith(PATTERN_PRESETS_GROUP.fieldKeyPrefix),
);
const PATTERN_PRESETS = FILTER_PRESETS.filter(
  (p) => p.fieldKey.startsWith(PATTERN_PRESETS_GROUP.fieldKeyPrefix),
);

const ConditionBuilder: React.FC = () => {
  const navigate = useNavigate();
  const collapsedPanels = useScreenerSelector(s => s.panels.collapsed);
  const filterGroup = useScreenerSelector(s => s.condition.filterGroup);
  const customIndicators = useScreenerSelector(s => s.custom.indicators);
  const dispatch = useScreenerDispatch();

  // K 2026-06-17 新增：K线形态全局回看天数
  const [lookbackDays, setLookbackDays] = useState<number>(DEFAULT_LOOKBACK_DAYS);

  const conditions = filterGroup?.conditions || [];
  const conditionCount = conditions.length;

  // 自编指标可用列表（过滤已删除）
  const availableCustomIndicators = useMemo(
    () => customIndicators.filter((i: CustomIndicator) => !i.deleted),
    [customIndicators],
  );

  // 已添加的自编指标 fieldKey 集合
  const addedCustomFieldKeys = useMemo(() => {
    const keys = new Set<string>();
    conditions.forEach((c) => {
      if (c.source === 'custom' && c.sourceId) {
        keys.add(c.sourceId);
      }
    });
    return keys;
  }, [conditions]);

  // 已添加的 system preset fieldKey 集合（用于按钮高亮）
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

  // K 2026-06-17 决策：自编指标管理入口已迁移至 /config 页面
  const handleGoToConfigCustom = () => {
    navigate('/config?tab=custom');
  };

  /**
   * K 2026-06-17 决策：三组平级 + 全部 AND 关系，preset 按钮改为 toggle 行为。
   * - 点未选按钮 → 添加为新条件 (AND 关系)
   * - 点已选按钮 → 从 conditions 中移除
   * - K线形态 preset 自动带当前 lookbackDays
   */
  const handleTogglePreset = (preset: typeof FILTER_PRESETS[number]) => {
    const isPattern = preset.fieldKey.startsWith(PATTERN_PRESETS_GROUP.fieldKeyPrefix);
    const existing = conditions.find((c) => c.fieldKey === preset.fieldKey);
    if (existing) {
      dispatch({ type: 'REMOVE_CONDITION', payload: existing.id });
      return;
    }
    const newCond: Omit<FilterCondition, 'id'> = {
      op: 'AND',
      fieldKey: preset.fieldKey,
      label: preset.label,
      ...(isPattern ? { lookbackDays } : {}),
    };
    dispatch({ type: 'ADD_CONDITION', payload: newCond });
  };

  const handleRemoveCondition = (id: string) => {
    dispatch({ type: 'REMOVE_CONDITION', payload: id });
  };

  // K 2026-06-17 决策：自编指标下拉多选 onChange（同样是 toggle/平级 AND）
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

  // 单个 preset 按钮渲染（已选高亮 + toggle 行为）
  const renderPresetButton = (preset: typeof FILTER_PRESETS[number]) => {
    const isSelected = selectedPresetFieldKeys.has(preset.fieldKey);
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

  // K线形态 preset 在已添加条件中显示时附加"近N天"后缀
  const formatCondLabel = (label: string, fieldKey: string, days?: number): string => {
    if (fieldKey.startsWith(PATTERN_PRESETS_GROUP.fieldKeyPrefix) && days) {
      return `${label} (近${days}天)`;
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
        <div className="space-y-4">
          {/* ============== 第一组：技术指标 (6) ============== */}
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

          {/* ============== 第二组：K线形态 (5) ============== */}
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

          {/* ============== 第三组：自编指标（下拉多选） ============== */}
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

          {/* 条件列表 / 空状态 */}
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
      </Panel>
    </Collapse>
  );
};

export default ConditionBuilder;
