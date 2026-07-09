import React from 'react';
import { Button } from 'antd';
import { PlayCircleOutlined, ReloadOutlined, LoadingOutlined } from '@ant-design/icons';
import RangeSelector from './RangeSelector';
import IndicatorFilter from './IndicatorFilter';
import FinancialFilter from './FinancialFilter';
import TechnicalFilter from './TechnicalFilter';
import ConditionBuilder from './ConditionBuilder';
import FactorScoringConfig from './FactorScoringConfig';

interface StockPickerSidebarProps {
  loading: boolean;
  onStartScreening: () => void;
  onReset: () => void;
}

/**
 * 选股器左侧筛选面板
 *
 * 包含所有筛选组件（RangeSelector / IndicatorFilter / FinancialFilter / TechnicalFilter / ConditionBuilder / FactorScoringConfig）
 * 底部固定开始选股 & 重置按钮
 */
export const StockPickerSidebar: React.FC<StockPickerSidebarProps> = React.memo(({
  loading, onStartScreening, onReset,
}) => (
  <div
    className="w-[280px] flex-shrink-0 bg-bg-panel border-r border-border-color flex flex-col"
    style={{ height: 'calc(100vh - 56px)' }}
  >
    <div className="flex-1 overflow-y-auto overflow-x-hidden min-h-0">
      <RangeSelector />
      <IndicatorFilter />
      <FinancialFilter />
      <TechnicalFilter />
      <ConditionBuilder />
      <FactorScoringConfig />
    </div>
    <div className="p-3 border-t border-border-color bg-bg-panel">
      <div className="flex gap-2">
        <Button
          type="primary"
          data-testid="start-screener"
          className={`flex-1 border-color-accent ${
            loading ? 'bg-color-accent/60 cursor-not-allowed' : 'bg-color-accent hover:bg-color-accent/80'
          }`}
          icon={loading ? <LoadingOutlined spin /> : <PlayCircleOutlined />}
          onClick={onStartScreening}
          disabled={loading}
        >
          {loading ? '选股中...' : '开始选股'}
        </Button>
        <Button
          data-testid="reset-screener"
          className="flex-1 bg-bg-card border-border-color text-text-secondary hover:text-text-primary"
          icon={<ReloadOutlined />}
          onClick={onReset}
          disabled={loading}
        >
          重置
        </Button>
      </div>
    </div>
  </div>
));
StockPickerSidebar.displayName = 'StockPickerSidebar';