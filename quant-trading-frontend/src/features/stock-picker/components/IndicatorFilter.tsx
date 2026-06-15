import React from 'react';
import { Typography, Button, Input, Collapse } from 'antd';
import { useScreener } from '../context/ScreenerContext';
import { MARKET_INDICATORS } from '../config/indicatorConfig';

const { Text } = Typography;
const { Panel } = Collapse;

const IndicatorFilter: React.FC = () => {
  const { state, dispatch } = useScreener();
  const { selectedMarketIndicators, marketIndicatorRanges, collapsedPanels } = state;

  const toggleIndicator = (id: string) => {
    dispatch({ type: 'TOGGLE_MARKET_INDICATOR', payload: id });
  };

  const updateRange = (indicatorId: string, field: 'min' | 'max', value: string) => {
    const currentRange = marketIndicatorRanges[indicatorId] || { min: '', max: '' };
    dispatch({
      type: 'SET_MARKET_INDICATOR_RANGE',
      payload: {
        indicatorId,
        range: { ...currentRange, [field]: value },
      },
    });
  };

  const activeKey = collapsedPanels.market ? ['market'] : [];

  return (
    <Collapse
      activeKey={activeKey}
      ghost
      className="border-b border-border-color"
      onChange={() => dispatch({ type: 'TOGGLE_PANEL', payload: 'market' })}
    >
      <Panel
        header={
          <span className="flex items-center gap-2">
            <Text className="text-text-primary font-semibold">行情指标</Text>
            <span className="px-1.5 py-0.5 bg-color-up/20 text-color-up text-xs rounded-full">
              {selectedMarketIndicators.length}
            </span>
          </span>
        }
        key="market"
      >
        <div className="grid grid-cols-2 gap-2 mb-3">
          {MARKET_INDICATORS.map((indicator) => (
            <Button
              key={indicator.id}
              onClick={() => toggleIndicator(indicator.id)}
              disabled={indicator.disabled}
              className={`text-sm ${
                selectedMarketIndicators.includes(indicator.id)
                  ? 'bg-color-up hover:bg-color-up/80 border-color-up text-white'
                  : 'bg-bg-card border-border-color text-text-secondary hover:text-text-primary'
              } ${indicator.disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {indicator.label}
            </Button>
          ))}
        </div>

        {selectedMarketIndicators.length > 0 && (
          <div className="border-t border-border-color pt-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-color-up" />
                <span className="w-2 h-2 rounded-full bg-yellow-500" />
                <span className="w-2 h-2 rounded-full bg-red-500" />
              </span>
              <Text className="text-text-secondary text-sm">范围条件:</Text>
            </div>

            {selectedMarketIndicators.map((indicatorId) => {
              const indicator = MARKET_INDICATORS.find((i) => i.id === indicatorId);
              const range = marketIndicatorRanges[indicatorId] || { min: '', max: '' };
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

export default IndicatorFilter;
