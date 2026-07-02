import React from 'react';
import { Typography, Slider, Collapse } from 'antd';
import { SlidersOutlined } from '@ant-design/icons';
import { useScreenerSelector, useScreenerDispatch } from '../context/ScreenerContext';
import { FACTOR_CONFIG } from '../config/indicatorConfig';

const { Text } = Typography;
const { Panel } = Collapse;

const FactorScoringConfig: React.FC = () => {
  const factorWeights = useScreenerSelector(s => s.factor.weights);
  const collapsedPanels = useScreenerSelector(s => s.panels.collapsed);
  const dispatch = useScreenerDispatch();

  const updateWeight = (factorId: string, value: number) => {
    dispatch({ type: 'SET_FACTOR_WEIGHT', payload: { factorId, weight: value } });
  };

  const activeKey = collapsedPanels.factor ? ['factor'] : [];

  return (
    <Collapse
      activeKey={activeKey}
      ghost
      className="border-b border-border-color"
      onChange={() => dispatch({ type: 'TOGGLE_PANEL', payload: 'factor' })}
    >
      <Panel
        header={
          <span className="flex items-center gap-2">
            <SlidersOutlined className="text-color-accent" />
            <Text className="text-text-primary font-semibold">因子打分配置</Text>
          </span>
        }
        key="factor"
      >
        <div className="space-y-3">
          {FACTOR_CONFIG.map((factor) => (
            <div key={factor.id}>
              <div className="flex items-center justify-between mb-1">
                <Text className="text-text-secondary text-sm">{factor.label}</Text>
                <Text className="text-text-primary text-sm">{factorWeights[factor.id]}%</Text>
              </div>
              <div className="flex items-center gap-2">
                <Slider
                  min={0}
                  max={100}
                  value={factorWeights[factor.id]}
                  onChange={(value) => updateWeight(factor.id, value)}
                  className="flex-1"
                  style={{
                    '--slider-track-background': '#2A2E39',
                    '--slider-track-fill': factor.color,
                  } as React.CSSProperties}
                />
                <div
                  className="w-16 h-4 rounded"
                  style={{
                    background: `linear-gradient(to right, ${factor.color} ${factorWeights[factor.id]}%, #2A2E39 ${factorWeights[factor.id]}%)`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </Collapse>
  );
};

export default FactorScoringConfig;
