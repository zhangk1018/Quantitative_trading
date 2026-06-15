import React from 'react';
import { Typography, Radio, Select, Collapse } from 'antd';
import { useScreener } from '../context/ScreenerContext';
import { MARKET_CONFIG, STOCK_RANGE_OPTIONS } from '../config/marketConfig';

const { Text } = Typography;
const { Panel } = Collapse;

const RangeSelector: React.FC = () => {
  const { state, dispatch } = useScreener();
  const { selectedMarket, selectedBoards, stockRange } = state;
  const currentMarketConfig = MARKET_CONFIG[selectedMarket];
  const availableBoardValues = currentMarketConfig?.boards.map((b) => b.value) || [];

  const handleMarketChange = (value: string) => {
    dispatch({ type: 'SET_MARKET', payload: value });
  };

  const handleBoardsChange = (value: string[]) => {
    const hasAll = value.includes('all');
    const prevHadAll = selectedBoards.includes('all');
    
    if (hasAll) {
      dispatch({ type: 'SET_BOARDS', payload: ['all'] });
    } else {
      if (prevHadAll) {
        dispatch({ type: 'SET_BOARDS', payload: value });
      } else if (value.length === availableBoardValues.length) {
        dispatch({ type: 'SET_BOARDS', payload: ['all'] });
      } else {
        dispatch({ type: 'SET_BOARDS', payload: value });
      }
    }
  };

  const handleStockRangeChange = (value: string) => {
    dispatch({ type: 'SET_STOCK_RANGE', payload: value });
  };

  const displayBoards = selectedBoards.includes('all')
    ? ['all', ...availableBoardValues]
    : selectedBoards;

  return (
    <Collapse
      defaultActiveKey={['range']}
      ghost
      className="border-b border-border-color"
    >
      <Panel
        header={
          <span className="flex items-center gap-2">
            <Text className="text-text-primary font-semibold">范围</Text>
            <span className="px-1.5 py-0.5 bg-color-up/20 text-color-up text-xs rounded-full">3</span>
          </span>
        }
        key="range"
      >
        <div className="space-y-4">
          {/* 所属市场 */}
          <div>
            <Text className="text-text-secondary text-sm mb-2 block">所属市场</Text>
            <Radio.Group
              value={selectedMarket}
              onChange={(e) => handleMarketChange(e.target.value)}
            >
              <div className="flex gap-4">
                {Object.values(MARKET_CONFIG).map((market) => (
                  <Radio key={market.value} value={market.value}>
                    {market.label}
                  </Radio>
                ))}
              </div>
            </Radio.Group>
          </div>

          {/* 上市地 */}
          <div>
            <Text className="text-text-secondary text-sm mb-2 block">上市地</Text>
            <Select
              mode="multiple"
              value={displayBoards}
              onChange={handleBoardsChange}
              style={{ width: '100%' }}
              className="bg-bg-card border-border-color"
              disabled={currentMarketConfig?.disabled}
              options={[
                { value: 'all', label: '全部' },
                ...(currentMarketConfig?.boards || []),
              ]}
              maxTagCount="responsive"
            />
          </div>

          {/* 股票范围 */}
          <div>
            <Text className="text-text-secondary text-sm mb-2 block">股票范围</Text>
            <Radio.Group
              value={stockRange}
              onChange={(e) => handleStockRangeChange(e.target.value)}
            >
              <div className="flex gap-4">
                {STOCK_RANGE_OPTIONS.map((option) => (
                  <Radio key={option.value} value={option.value}>
                    {option.label}
                  </Radio>
                ))}
              </div>
            </Radio.Group>
          </div>
        </div>
      </Panel>
    </Collapse>
  );
};

export default RangeSelector;
