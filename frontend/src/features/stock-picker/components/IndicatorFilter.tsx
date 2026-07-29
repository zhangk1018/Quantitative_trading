import React from 'react';
import { Typography, Button, InputNumber, Collapse, Tooltip } from 'antd';
import { CloseCircleOutlined } from '@ant-design/icons';
import { useScreenerSelector, useScreenerDispatch } from '../context/ScreenerContext';
import { MARKET_INDICATORS } from '../config/indicatorConfig';

const { Text } = Typography;

const IndicatorFilter: React.FC = () => {
  const selectedMarketIndicators = useScreenerSelector(s => s.marketIndicators.selected);
  const marketIndicatorRanges = useScreenerSelector(s => s.marketIndicators.ranges);
  const collapsedPanels = useScreenerSelector(s => s.panels.collapsed);
  const dispatch = useScreenerDispatch();

  const toggleIndicator = (id: string) => {
    dispatch({ type: 'TOGGLE_MARKET_INDICATOR', payload: id });
  };

  const updateRange = (indicatorId: string, field: 'min' | 'max', value: number | null) => {
    const currentRange = marketIndicatorRanges[indicatorId] || { min: '', max: '' };
    dispatch({
      type: 'SET_MARKET_INDICATOR_RANGE',
      payload: {
        indicatorId,
        range: { ...currentRange, [field]: value === null ? '' : String(value) },
      },
    });
  };

  const clearRange = (indicatorId: string) => {
    dispatch({
      type: 'SET_MARKET_INDICATOR_RANGE',
      payload: {
        indicatorId,
        range: { min: '', max: '' },
      },
    });
  };

  const activeKey = collapsedPanels.market ? [] : ['market'];

  return (
    <Collapse
      activeKey={activeKey}
      ghost
      className="border-b border-border-color"
      onChange={() => dispatch({ type: 'TOGGLE_PANEL', payload: 'market' })}
      data-testid="indicator-filter-collapse"
      items={[
        {
          key: 'market',
          label: (
            <span className="flex items-center gap-2">
              <Text className="text-text-primary font-semibold">行情指标</Text>
              <span
                data-testid="indicator-filter-badge"
                className="px-1.5 py-0.5 bg-color-up/20 text-color-up text-xs rounded-full"
              >
                {selectedMarketIndicators.length}
              </span>
            </span>
          ),
          children: (
            <>
              <div className="grid grid-cols-2 gap-2 mb-3">
          {MARKET_INDICATORS.map((indicator) => (
            <Button
              key={indicator.id}
              onClick={() => toggleIndicator(indicator.id)}
              disabled={indicator.disabled}
              data-testid={`indicator-btn-${indicator.id}`}
              data-selected={selectedMarketIndicators.includes(indicator.id)}
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

        {selectedMarketIndicators.length > 0 ? (
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
                <div key={indicatorId} className="mb-3" data-testid={`indicator-range-${indicatorId}`}>
                  <div className="flex items-center justify-between mb-1">
                    <Text className="text-text-secondary text-sm">
                      {indicator?.label}({indicator?.unit || ''})
                    </Text>
                    {(range.min !== '' || range.max !== '') && (
                      <Tooltip title="清除范围">
                        <Button
                          type="text"
                          size="small"
                          icon={<CloseCircleOutlined />}
                          onClick={() => clearRange(indicatorId)}
                          data-testid={`indicator-clear-${indicatorId}`}
                          className="text-text-secondary hover:text-red-500"
                        />
                      </Tooltip>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <InputNumber
                      value={range.min === '' ? null : Number(range.min)}
                      onChange={(val) => updateRange(indicatorId, 'min', val)}
                      placeholder="min"
                      data-testid={`indicator-min-${indicatorId}`}
                      className="flex-1"
                      controls={false}
                      style={{ width: '100%' }}
                    />
                    <span className="text-text-secondary">~</span>
                    <InputNumber
                      value={range.max === '' ? null : Number(range.max)}
                      onChange={(val) => updateRange(indicatorId, 'max', val)}
                      placeholder="max"
                      data-testid={`indicator-max-${indicatorId}`}
                      className="flex-1"
                      controls={false}
                      style={{ width: '100%' }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="border-t border-border-color pt-3" data-testid="indicator-empty-hint" />
        )}
            </>
          ),
        },
      ]}
    >
    </Collapse>
  );
};

export default IndicatorFilter;
