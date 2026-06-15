import React from 'react';
import { Typography, Button, Input, Collapse } from 'antd';
import { useScreener } from '../context/ScreenerContext';
import { FINANCIAL_INDICATORS } from '../config/indicatorConfig';

const { Text } = Typography;
const { Panel } = Collapse;

const FinancialFilter: React.FC = () => {
  const { state, dispatch } = useScreener();
  const { selectedFinancialIndicators, financialIndicatorRanges, collapsedPanels } = state;

  const toggleIndicator = (id: string) => {
    dispatch({ type: 'TOGGLE_FINANCIAL_INDICATOR', payload: id });
  };

  const updateRange = (indicatorId: string, field: 'min' | 'max', value: string) => {
    const currentRange = financialIndicatorRanges[indicatorId] || { min: '', max: '' };
    dispatch({
      type: 'SET_FINANCIAL_INDICATOR_RANGE',
      payload: {
        indicatorId,
        range: { ...currentRange, [field]: value },
      },
    });
  };

  const activeKey = collapsedPanels.financial ? ['financial'] : [];

  return (
    <Collapse
      activeKey={activeKey}
      ghost
      className="border-b border-border-color"
      onChange={() => dispatch({ type: 'TOGGLE_PANEL', payload: 'financial' })}
    >
      <Panel
        header={
          <span className="flex items-center gap-2">
            <Text className="text-text-primary font-semibold">财务指标</Text>
            <span className="px-1.5 py-0.5 bg-color-up/20 text-color-up text-xs rounded-full">
              {selectedFinancialIndicators.length}
            </span>
          </span>
        }
        key="financial"
      >
        <div className="grid grid-cols-2 gap-2 mb-3">
          {FINANCIAL_INDICATORS.map((indicator) => (
            <Button
              key={indicator.id}
              onClick={() => toggleIndicator(indicator.id)}
              disabled={indicator.disabled}
              className={`text-sm ${
                selectedFinancialIndicators.includes(indicator.id)
                  ? 'bg-color-up hover:bg-color-up/80 border-color-up text-white'
                  : 'bg-bg-card border-border-color text-text-secondary hover:text-text-primary'
              } ${indicator.disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {indicator.label}
            </Button>
          ))}
        </div>

        {selectedFinancialIndicators.length > 0 && (
          <div className="border-t border-border-color pt-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-color-up" />
                <span className="w-2 h-2 rounded-full bg-yellow-500" />
                <span className="w-2 h-2 rounded-full bg-red-500" />
              </span>
              <Text className="text-text-secondary text-sm">范围条件:</Text>
            </div>

            {selectedFinancialIndicators.map((indicatorId) => {
              const indicator = FINANCIAL_INDICATORS.find((i) => i.id === indicatorId);
              const range = financialIndicatorRanges[indicatorId] || { min: '', max: '' };
              return (
                <div key={indicatorId} className="mb-2">
                  <Text className="text-text-secondary text-sm">
                    {indicator?.label}({indicator?.unit || ''})
                  </Text>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex items-center gap-1 flex-1">
                      <Input
                        type="number"
                        value={range.min}
                        onChange={(e) => updateRange(indicatorId, 'min', e.target.value)}
                        placeholder="min"
                        className="flex-1 bg-bg-base border-border-color text-text-primary text-sm"
                      />
                      <Button type="text" className="text-text-secondary">~</Button>
                      <Input
                        type="number"
                        value={range.max}
                        onChange={(e) => updateRange(indicatorId, 'max', e.target.value)}
                        placeholder="max"
                        className="flex-1 bg-bg-base border-border-color text-text-primary text-sm"
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </Collapse>
  );
};

export default FinancialFilter;
