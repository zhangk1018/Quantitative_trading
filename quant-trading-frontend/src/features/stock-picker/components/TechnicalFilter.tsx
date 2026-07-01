import React from 'react';
import { Collapse, Button, Select, Tag } from 'antd';
import { useScreener } from '../context/ScreenerContext';
import { TECHNICAL_INDICATORS, PATTERN_INDICATORS, LOOKBACK_OPTIONS } from '../config/indicatorConfig';
import { TechnicalIndicatorModal } from './TechnicalIndicatorModal';

const { Panel } = Collapse;

export const TechnicalFilter: React.FC = () => {
  const { state, dispatch } = useScreener();
  const activeKey = state.collapsedPanels.technical ? [] : ['technical'];
  const selectedCount = Object.keys(state.selectedTechnicalIndicators).length;
  const openModal = state.openTechnicalModal
    ? TECHNICAL_INDICATORS.find((i) => i.id === state.openTechnicalModal)
    : null;

  const openModalFor = (id: string) => {
    dispatch({ type: 'OPEN_TECHNICAL_MODAL', payload: id });
  };

  const closeModal = () => {
    dispatch({ type: 'CLOSE_TECHNICAL_MODAL' });
  };

  const confirmOption = (indicatorId: string, option: string) => {
    dispatch({ type: 'SET_TECHNICAL_INDICATOR_OPTION', payload: { indicatorId, option } });
  };

  const clearOption = (indicatorId: string) => {
    dispatch({ type: 'CLEAR_TECHNICAL_INDICATOR_OPTION', payload: indicatorId });
  };

  const patternCount = Object.keys(state.selectedPatterns).length;

  return (
    <>
      {/* 技术指标（原有） */}
      <Collapse
        activeKey={activeKey}
        ghost
        className="border-b border-border-color"
        onChange={() => dispatch({ type: 'TOGGLE_PANEL', payload: 'technical' })}
        data-testid="technical-filter-collapse"
      >
        <Panel
          header={
            <span
              data-testid="technical-filter-header"
              className="flex items-center gap-2"
            >
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
            {TECHNICAL_INDICATORS.map((indicator) => {
              const selectedOption = state.selectedTechnicalIndicators[indicator.id];
              return (
                <Button
                  key={indicator.id}
                  onClick={() => openModalFor(indicator.id)}
                  disabled={indicator.disabled}
                  data-testid={`technical-btn-${indicator.id}`}
                  data-selected={!!selectedOption}
                  data-option={selectedOption || ''}
                  className={`text-sm ${
                    selectedOption
                      ? 'bg-color-up hover:bg-color-up/80 border-color-up text-white'
                      : 'bg-bg-card border-border-color text-text-secondary hover:text-text-primary'
                  } ${indicator.disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  {indicator.label}
                </Button>
              );
            })}
          </div>
        </Panel>
      </Collapse>

      {/* K 线形态（新增） */}
      <div className="border-b border-border-color px-3 py-2">
        <div
          className="flex items-center justify-between cursor-pointer select-none"
          onClick={() => dispatch({ type: 'TOGGLE_PATTERN_PANEL' })}
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
          <span className={`text-text-secondary text-xs transition-transform ${state.patternPanelCollapsed ? '' : 'rotate-180'}`}>
            ▼
          </span>
        </div>
        {!state.patternPanelCollapsed && (
          <div className="mt-2 space-y-2">
            {PATTERN_INDICATORS.map((pattern) => {
              const selected = pattern.id in state.selectedPatterns;
              const lookbackDays = state.selectedPatterns[pattern.id] ?? pattern.defaultLookbackDays;
              return (
                <div key={pattern.id} className="flex items-center gap-2" data-testid={`pattern-row-${pattern.id}`}>
                  <Button
                    size="small"
                    onClick={() => dispatch({ type: 'TOGGLE_PATTERN', payload: pattern.id })}
                    data-testid={`pattern-btn-${pattern.id}`}
                    data-selected={selected}
                    className={`text-xs flex-1 ${
                      selected
                        ? 'bg-color-accent border-color-accent text-white'
                        : 'bg-bg-card border-border-color text-text-secondary'
                    }`}
                  >
                    {pattern.label}
                  </Button>
                  {selected && (
                    <Select
                      size="small"
                      value={lookbackDays}
                      onChange={(v) => dispatch({ type: 'SET_PATTERN_LOOKBACK', payload: { patternId: pattern.id, lookbackDays: v } })}
                      options={LOOKBACK_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                      className="w-16"
                      data-testid={`pattern-lookback-${pattern.id}`}
                      popupClassName="pattern-lookback-dropdown"
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {openModal && (
        <TechnicalIndicatorModal
          title={`${openModal.label}·日K`}
          indicator={openModal}
          currentOption={state.selectedTechnicalIndicators[openModal.id]}
          onConfirm={(option) => confirmOption(openModal.id, option)}
          onCancel={closeModal}
          onClear={() => clearOption(openModal.id)}
        />
      )}
    </>
  );
};

export default TechnicalFilter;
