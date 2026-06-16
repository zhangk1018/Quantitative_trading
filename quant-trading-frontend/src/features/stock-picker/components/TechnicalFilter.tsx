import React from 'react';
import { Collapse, Button } from 'antd';
import { useScreener } from '../context/ScreenerContext';
import { TECHNICAL_INDICATORS } from '../config/indicatorConfig';
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

  return (
    <>
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
