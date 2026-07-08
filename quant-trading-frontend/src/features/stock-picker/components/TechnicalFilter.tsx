import React, { memo, useCallback, useMemo } from 'react';
import { Collapse, Button } from 'antd';
import clsx from 'clsx';
import { useScreenerSelector, useScreenerDispatch } from '../context/ScreenerContext';
import {
  TECHNICAL_INDICATORS,
  PANEL_KEYS,
  type TechnicalOptionValue,
} from '../config/indicatorConfig';
import { TechnicalIndicatorModal } from './TechnicalIndicatorModal';

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

// ==================== 技术指标面板 ====================
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
      items={[
        {
          key: 'technical',
          label: (
            <span data-testid="technical-filter-header" className="flex items-center gap-2">
              <span className="text-text-primary font-semibold">技术指标</span>
              <span
                data-testid="technical-filter-badge"
                className="px-1.5 py-0.5 bg-color-up/20 text-color-up text-xs rounded-full"
              >
                {selectedCount}
              </span>
            </span>
          ),
          children: (
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
          ),
        },
      ]}
    >
    </Collapse>
  );
});
TechnicalPanel.displayName = 'TechnicalPanel';

// ==================== 主组件 ====================
export const TechnicalFilter: React.FC = () => {
  const technical = useScreenerSelector(s => s.technical);
  const panelCollapsed = useScreenerSelector(s => s.panels.collapsed[PANEL_KEYS.TECHNICAL]);

  const dispatch = useScreenerDispatch();

  const toggleTechnicalPanel = useCallback(() => {
    dispatch({ type: 'TOGGLE_PANEL', payload: PANEL_KEYS.TECHNICAL });
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

  const openModalIndicator = useMemo(
    () => technical.openModalId
      ? TECHNICAL_INDICATORS.find(i => i.id === technical.openModalId)
      : null,
    [technical.openModalId]
  );

  if (TECHNICAL_INDICATORS.length === 0) {
    return <div className="text-text-secondary p-4 text-center">暂无技术指标配置</div>;
  }

  return (
    <>
      <TechnicalPanel
        technical={technical}
        panelCollapsed={panelCollapsed}
        onTogglePanel={toggleTechnicalPanel}
        onOpenModal={openModal}
      />

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