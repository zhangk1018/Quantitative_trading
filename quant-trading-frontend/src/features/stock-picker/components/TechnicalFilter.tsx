import React, { memo, useCallback, useMemo } from 'react';
import { Collapse, Button, Select, Tag } from 'antd';
import clsx from 'clsx';
import { useScreenerSelector, useScreenerDispatch } from '../context/ScreenerContext';
import {
  TECHNICAL_INDICATORS,
  PATTERN_INDICATORS,
  LOOKBACK_OPTIONS,
  PANEL_KEYS,
  type TechnicalOptionValue,
} from '../config/indicatorConfig';
import { TechnicalIndicatorModal } from './TechnicalIndicatorModal';


const { Panel } = Collapse;

// 静态选项缓存
const lookbackSelectOptions = LOOKBACK_OPTIONS.map(o => ({ value: o.value, label: o.label }));

// ==================== 子组件：技术指标按钮 ====================
interface TechnicalButtonProps {
  indicatorId: string;
  label: string;
  disabled?: boolean;
  selectedOption: TechnicalOptionValue | undefined;
  onOpenModal: (id: string) => void;
}

const TechnicalButton = memo<TechnicalButtonProps>(
  ({ indicatorId, label, disabled, selectedOption, onOpenModal }) => {
    const handleClick = useCallback(() => {
      if (!disabled) onOpenModal(indicatorId);
    }, [disabled, indicatorId, onOpenModal]);

    return (
      <Button
        onClick={handleClick}
        disabled={disabled}
        data-testid={`technical-btn-${indicatorId}`}
        data-selected={!!selectedOption}
        data-option={selectedOption || ''}
        className={clsx(
          'text-sm',
          {
            'bg-color-up hover:bg-color-up/80 border-color-up text-white': !!selectedOption,
            'bg-bg-card border-border-color text-text-secondary hover:text-text-primary': !selectedOption,
            'opacity-50 cursor-not-allowed': disabled,
          }
        )}
      >
        {label}
      </Button>
    );
  }
);
TechnicalButton.displayName = 'TechnicalButton';

// ==================== 子组件：K线形态行 ====================
interface PatternRowProps {
  patternId: string;
  label: string;
  selected: boolean;
  lookbackDays: number;
  onToggle: (id: string) => void;
  onLookbackChange: (id: string, days: number) => void;
}

const PatternRow = memo<PatternRowProps>(
  ({ patternId, label, selected, lookbackDays, onToggle, onLookbackChange }) => {
    const handleToggle = useCallback(() => onToggle(patternId), [patternId, onToggle]);
    // 转换为 string 适配 Antd Select
    const value = String(lookbackDays);
    const handleChange = useCallback(
      (val: string) => {
        const num = parseInt(val, 10);
        if (!isNaN(num)) onLookbackChange(patternId, num);
      },
      [patternId, onLookbackChange]
    );

    return (
      <div className="flex items-center gap-2" data-testid={`pattern-row-${patternId}`}>
        <Button
          size="small"
          onClick={handleToggle}
          data-testid={`pattern-btn-${patternId}`}
          data-selected={selected}
          className={clsx(
            'text-xs flex-1',
            {
              'bg-color-accent border-color-accent text-white': selected,
              'bg-bg-card border-border-color text-text-secondary': !selected,
            }
          )}
        >
          {label}
        </Button>
        {selected && (
          <Select
            size="small"
            value={value}
            onChange={handleChange}
            options={lookbackSelectOptions}
            className="w-16"
            data-testid={`pattern-lookback-${patternId}`}
            popupClassName="pattern-lookback-dropdown"
            aria-label={`${label}回溯天数`}
          />
        )}
      </div>
    );
  }
);
PatternRow.displayName = 'PatternRow';

// ==================== 技术指标面板（独立组件） ====================
const TechnicalPanel: React.FC<{
  technical: TechnicalState;
  panelCollapsed: boolean;
  onTogglePanel: () => void;
  onOpenModal: (id: string) => void;
}> = memo(({ technical, panelCollapsed, onTogglePanel, onOpenModal }) => {
  const selectedCount = Object.keys(technical.selected).length;
  return (
    <Collapse
      activeKey={panelCollapsed ? [] : ['technical']}
      ghost
      className="border-b border-border-color"
      onChange={onTogglePanel}
      data-testid="technical-filter-collapse"
    >
      <Panel
        header={
          <span data-testid="technical-filter-header" className="flex items-center gap-2">
            <span className="text-text-primary font-semibold">技术指标</span>
            <span
              data-testid="technical-filter-badge"
              className="px-1.5 py-0.5 bg-color-up/20 text-color-up text-xs rounded-full"
            >
              {selectedCount}
            </span>
          </span>
        }
        key="technical"
      >
        <div className="grid grid-cols-2 gap-2">
          {TECHNICAL_INDICATORS.map(indicator => (
            <TechnicalButton
              key={indicator.id}
              indicatorId={indicator.id}
              label={indicator.label}
              disabled={indicator.disabled}
              selectedOption={technical.selected[indicator.id]}
              onOpenModal={onOpenModal}
            />
          ))}
        </div>
      </Panel>
    </Collapse>
  );
});
TechnicalPanel.displayName = 'TechnicalPanel';

// ==================== K线形态面板（独立组件） ====================
const PatternPanel: React.FC<{
  patterns: PatternState;
  patternPanelCollapsed: boolean;
  onTogglePanel: () => void;
  onTogglePattern: (id: string) => void;
  onSetLookback: (id: string, days: number) => void;
}> = memo(({ patterns, patternPanelCollapsed, onTogglePanel, onTogglePattern, onSetLookback }) => {
  const patternCount = Object.keys(patterns.selected).length;
  return (
    <div className="border-b border-border-color px-3 py-2">
      <div
        role="button"
        tabIndex={0}
        aria-expanded={!patternPanelCollapsed}
        aria-controls="pattern-panel-content"
        className="flex items-center justify-between cursor-pointer select-none"
        onClick={onTogglePanel}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onTogglePanel();
          }
        }}
        data-testid="pattern-filter-header"
      >
        <span className="flex items-center gap-2">
          <span className="text-text-primary font-semibold text-sm">K线形态</span>
          {patternCount > 0 && (
            <Tag color="blue" className="text-xs leading-none m-0">
              {patternCount}
            </Tag>
          )}
        </span>
        <span
          className={clsx(
            'text-text-secondary text-xs transition-transform',
            { 'rotate-180': !patternPanelCollapsed }
          )}
        >
          ▼
        </span>
      </div>
      <div
        id="pattern-panel-content"
        className={clsx('mt-2 space-y-2', { hidden: patternPanelCollapsed })}
      >
        {PATTERN_INDICATORS.map(pattern => (
          <PatternRow
            key={pattern.id}
            patternId={pattern.id}
            label={pattern.label}
            selected={pattern.id in patterns.selected}
            lookbackDays={patterns.selected[pattern.id] ?? pattern.defaultLookbackDays}
            onToggle={onTogglePattern}
            onLookbackChange={onSetLookback}
          />
        ))}
      </div>
    </div>
  );
});
PatternPanel.displayName = 'PatternPanel';

// ==================== 主组件 ====================
export const TechnicalFilter: React.FC = () => {
  // 细粒度订阅
  const technical = useScreenerSelector(s => s.technical);
  const patterns = useScreenerSelector(s => s.patterns);
  const panelCollapsed = useScreenerSelector(s => s.panels.collapsed[PANEL_KEYS.TECHNICAL]);
  const patternPanelCollapsed = useScreenerSelector(s => s.patterns.panelCollapsed);

  const dispatch = useScreenerDispatch();

  // 稳定回调
  const toggleTechnicalPanel = useCallback(() => {
    dispatch({ type: 'TOGGLE_PANEL', payload: PANEL_KEYS.TECHNICAL });
  }, [dispatch]);

  const togglePatternPanel = useCallback(() => {
    dispatch({ type: 'TOGGLE_PATTERN_PANEL' });
  }, [dispatch]);

  const openModal = useCallback(
    (id: string) => dispatch({ type: 'OPEN_TECHNICAL_MODAL', payload: id }),
    [dispatch]
  );
  const closeModal = useCallback(
    () => dispatch({ type: 'CLOSE_TECHNICAL_MODAL' }),
    [dispatch]
  );
  const confirmOption = useCallback(
    (indicatorId: string, option: TechnicalOptionValue) =>
      dispatch({ type: 'SET_TECHNICAL_INDICATOR_OPTION', payload: { indicatorId, option } }),
    [dispatch]
  );
  const clearOption = useCallback(
    (indicatorId: string) =>
      dispatch({ type: 'CLEAR_TECHNICAL_INDICATOR_OPTION', payload: indicatorId }),
    [dispatch]
  );
  const togglePattern = useCallback(
    (id: string) => dispatch({ type: 'TOGGLE_PATTERN', payload: id }),
    [dispatch]
  );
  const setPatternLookback = useCallback(
    (id: string, days: number) =>
      dispatch({ type: 'SET_PATTERN_LOOKBACK', payload: { patternId: id, lookbackDays: days } }),
    [dispatch]
  );

  // 记忆化派生对象
  const openModalIndicator = useMemo(
    () => technical.openModalId
      ? TECHNICAL_INDICATORS.find(i => i.id === technical.openModalId)
      : null,
    [technical.openModalId]
  );

  // 空状态
  if (TECHNICAL_INDICATORS.length === 0 && PATTERN_INDICATORS.length === 0) {
    return <div className="text-text-secondary p-4 text-center">暂无技术指标配置</div>;
  }

  return (
    <>
      {TECHNICAL_INDICATORS.length > 0 && (
        <TechnicalPanel
          technical={technical}
          panelCollapsed={panelCollapsed}
          onTogglePanel={toggleTechnicalPanel}
          onOpenModal={openModal}
        />
      )}

      {PATTERN_INDICATORS.length > 0 && (
        <PatternPanel
          patterns={patterns}
          patternPanelCollapsed={patternPanelCollapsed}
          onTogglePanel={togglePatternPanel}
          onTogglePattern={togglePattern}
          onSetLookback={setPatternLookback}
        />
      )}

      {openModalIndicator && (
        <TechnicalIndicatorModal
          title={`${openModalIndicator.label}·日K`}
          indicator={openModalIndicator}
          currentOption={technical.selected[openModalIndicator.id]}
          onConfirm={(option) => confirmOption(openModalIndicator.id, option as TechnicalOptionValue)}
          onCancel={closeModal}
          onClear={() => clearOption(openModalIndicator.id)}
        />
      )}
    </>
  );
};

export default TechnicalFilter;