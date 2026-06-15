import React from 'react';
import { Typography, Button, Collapse } from 'antd';
import { useScreener } from '../context/ScreenerContext';
import { TECHNICAL_INDICATORS } from '../config/indicatorConfig';

const { Text } = Typography;
const { Panel } = Collapse;

const TechnicalFilter: React.FC = () => {
  const { state, dispatch } = useScreener();
  const { selectedTechnicalIndicators, collapsedPanels } = state;

  const toggleIndicator = (id: string) => {
    dispatch({ type: 'TOGGLE_TECHNICAL_INDICATOR', payload: id });
  };

  const activeKey = collapsedPanels.technical ? ['technical'] : [];

  return (
    <Collapse
      activeKey={activeKey}
      ghost
      className="border-b border-border-color"
      onChange={() => dispatch({ type: 'TOGGLE_PANEL', payload: 'technical' })}
    >
      <Panel
        header={
          <span className="flex items-center gap-2">
            <Text className="text-text-primary font-semibold">技术指标</Text>
            <span className="px-1.5 py-0.5 bg-color-up/20 text-color-up text-xs rounded-full">
              {selectedTechnicalIndicators.length}
            </span>
          </span>
        }
        key="technical"
      >
        <div className="grid grid-cols-2 gap-2">
          {TECHNICAL_INDICATORS.map((indicator) => (
            <Button
              key={indicator.id}
              onClick={() => toggleIndicator(indicator.id)}
              disabled={indicator.disabled}
              className={`text-sm ${
                selectedTechnicalIndicators.includes(indicator.id)
                  ? 'bg-color-up hover:bg-color-up/80 border-color-up text-white'
                  : 'bg-bg-card border-border-color text-text-secondary hover:text-text-primary'
              } ${indicator.disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {indicator.label}
            </Button>
          ))}
        </div>
      </Panel>
    </Collapse>
  );
};

export default TechnicalFilter;
