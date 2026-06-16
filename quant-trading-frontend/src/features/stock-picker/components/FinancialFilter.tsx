import React from 'react';
import { Typography, Button, InputNumber, Collapse, Tooltip } from 'antd';
import { CloseCircleOutlined } from '@ant-design/icons';
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

  const updateRange = (indicatorId: string, field: 'min' | 'max', value: number | null) => {
    const currentRange = financialIndicatorRanges[indicatorId] || { min: '', max: '' };
    dispatch({
      type: 'SET_FINANCIAL_INDICATOR_RANGE',
      payload: {
        indicatorId,
        range: { ...currentRange, [field]: value === null ? '' : String(value) },
      },
    });
  };

  const clearRange = (indicatorId: string) => {
    dispatch({
      type: 'SET_FINANCIAL_INDICATOR_RANGE',
      payload: {
        indicatorId,
        range: { min: '', max: '' },
      },
    });
  };

  const activeKey = collapsedPanels.financial ? [] : ['financial'];

  return (
    <Collapse
      activeKey={activeKey}
      ghost
      className="border-b border-border-color"
      onChange={() => dispatch({ type: 'TOGGLE_PANEL', payload: 'financial' })}
      data-testid="financial-filter-collapse"
    >
      <Panel
        header={
          <span
            data-testid="financial-filter-header"
            className="flex items-center gap-2"
          >
            <Text className="text-text-primary font-semibold">财务指标</Text>
            <span
              data-testid="financial-filter-badge"
              className="px-1.5 py-0.5 bg-color-up/20 text-color-up text-xs rounded-full"
            >
              {selectedFinancialIndicators.length}
            </span>
          </span>
        }
        key="financial"
      >
        <div className="grid grid-cols-2 gap-2 mb-3">
          {FINANCIAL_INDICATORS.map((indicator) => {
            const btn = (
              <Button
                key={indicator.id}
                onClick={() => toggleIndicator(indicator.id)}
                disabled={indicator.disabled}
                data-testid={`financial-btn-${indicator.id}`}
                data-selected={selectedFinancialIndicators.includes(indicator.id)}
                className={`text-sm ${
                  selectedFinancialIndicators.includes(indicator.id)
                    ? 'bg-color-up hover:bg-color-up/80 border-color-up text-white'
                    : 'bg-bg-card border-border-color text-text-secondary hover:text-text-primary'
                } ${indicator.disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {indicator.label}
              </Button>
            );
            // disabled 指标若配置了 disabledReason，则 Tooltip 展示禁用原因
            if (indicator.disabled && indicator.disabledReason) {
              return (
                <Tooltip key={indicator.id} title={indicator.disabledReason} placement="top">
                  <span data-testid={`financial-btn-wrapper-${indicator.id}`}>{btn}</span>
                </Tooltip>
              );
            }
            return btn;
          })}
        </div>

        {selectedFinancialIndicators.length > 0 ? (
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
                <div key={indicatorId} className="mb-3" data-testid={`financial-range-${indicatorId}`}>
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
                          data-testid={`financial-clear-${indicatorId}`}
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
                      data-testid={`financial-min-${indicatorId}`}
                      className="flex-1"
                      controls={false}
                      style={{ width: '100%' }}
                    />
                    <span className="text-text-secondary">~</span>
                    <InputNumber
                      value={range.max === '' ? null : Number(range.max)}
                      onChange={(val) => updateRange(indicatorId, 'max', val)}
                      placeholder="max"
                      data-testid={`financial-max-${indicatorId}`}
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
          <div className="border-t border-border-color pt-3" data-testid="financial-empty-hint">
            <Text className="text-text-secondary text-xs">点击上方按钮添加筛选条件</Text>
          </div>
        )}
      </Panel>
    </Collapse>
  );
};

export default FinancialFilter;
