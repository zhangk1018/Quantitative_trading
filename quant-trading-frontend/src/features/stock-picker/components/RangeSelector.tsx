import React from 'react';
import { Typography, Radio, Select, Collapse } from 'antd';
import { useScreenerSelector, useScreenerDispatch } from '../context/ScreenerContext';
import { MARKET_CONFIG, STOCK_RANGE_OPTIONS } from '../config/marketConfig';

const { Text } = Typography;
const { Panel } = Collapse;

const RangeSelector: React.FC = () => {
  const stockRange = useScreenerSelector(s => s.market.stockRange);
  const selectedMarket = useScreenerSelector(s => s.market.selectedMarket);
  const selectedBoards = useScreenerSelector(s => s.market.selectedBoards);
  const collapsedPanels = useScreenerSelector(s => s.panels.collapsed);
  const dispatch = useScreenerDispatch();
  const currentMarketConfig = MARKET_CONFIG[selectedMarket];
  const availableBoardValues = currentMarketConfig?.boards.map((b) => b.value) || [];

  const handleMarketChange = (value: string) => {
    dispatch({ type: 'SET_MARKET', payload: value });
  };

  const handleBoardsChange = (values: string[]) => {
    const hadAll = selectedBoards.includes('all');
    const nowHasAll = values.includes('all');
    const specificValues = values.filter((v) => v !== 'all');

    // 情况1：当前选中了"全部"
    if (nowHasAll) {
      if (!hadAll) {
        // 用户主动勾选"全部" -> 全选所有板块
        dispatch({ type: 'SET_BOARDS', payload: ['all'] });
      } else {
        // 之前已是全选，现在可能通过操作具体板块触发了 onChange
        if (specificValues.length === availableBoardValues.length) {
          // 具体板块全选，保持全选状态
          dispatch({ type: 'SET_BOARDS', payload: ['all'] });
        } else {
          // 具体板块不全，去掉"全部"，只保留选中的具体板块
          dispatch({ type: 'SET_BOARDS', payload: specificValues });
        }
      }
    }
    // 情况2：当前没有选中"全部"
    else {
      // 如果之前是全选状态，现在"全部"被取消
      if (hadAll) {
        // 用户显式取消"全部"时，values 中会包含所有具体板块（因为显示上会包含全部具体选项）
        // 此时应该清空所有具体板块，实现"全部"去掉勾选时，所有板块也都去掉勾选
        if (specificValues.length === availableBoardValues.length) {
          dispatch({ type: 'SET_BOARDS', payload: [] });
        } else {
          // 用户通过取消某个具体板块导致"全部"自然消失，则保留剩余的具体板块
          dispatch({ type: 'SET_BOARDS', payload: specificValues });
        }
      }
      // 之前不是全选状态
      else {
        if (specificValues.length === availableBoardValues.length && availableBoardValues.length > 0) {
          // 所有具体板块都被选中 -> 自动勾选"全部"
          dispatch({ type: 'SET_BOARDS', payload: ['all'] });
        } else {
          // 否则只保存具体板块
          dispatch({ type: 'SET_BOARDS', payload: specificValues });
        }
      }
    }
  };

  const handleStockRangeChange = (value: string) => {
    dispatch({ type: 'SET_STOCK_RANGE', payload: value });
  };

  // 用于展示的已选项：如果当前是 "全部" 状态，则显示 "all" 及所有具体板块（便于用户取消任意具体板块）
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