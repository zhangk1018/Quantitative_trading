import React from 'react';
import { Typography, Button, Select, Divider } from 'antd';
import { SaveOutlined, FolderOpenOutlined, ReloadOutlined, PlusCircleOutlined, DownloadOutlined, BlockOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { ScreenerProvider, useScreener } from './context/ScreenerContext';
import RangeSelector from './components/RangeSelector';
import IndicatorFilter from './components/IndicatorFilter';
import FinancialFilter from './components/FinancialFilter';
import TechnicalFilter from './components/TechnicalFilter';
import ConditionBuilder from './components/ConditionBuilder';
import FactorScoringConfig from './components/FactorScoringConfig';

const { Text } = Typography;

const StockPickerContent: React.FC = () => {
  const { dispatch } = useScreener();

  const handleReset = () => {
    dispatch({ type: 'RESET_ALL' });
  };

  const handleStartScreening = () => {
    console.log('开始选股');
  };

  return (
    <div className="min-h-screen flex flex-col bg-bg-base">
      {/* 主内容区 */}
      <div className="flex-1 flex overflow-hidden min-h-[calc(100vh-56px)]">
        {/* 左侧筛选区（固定宽度280px） */}
        <div className="w-[280px] flex-shrink-0 bg-bg-panel border-r border-border-color flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>
          <div className="flex-1 overflow-y-auto overflow-x-hidden">
            <RangeSelector />
            <IndicatorFilter />
            <FinancialFilter />
            <TechnicalFilter />
            <ConditionBuilder />
            <FactorScoringConfig />
          </div>
          
          {/* 左侧底部操作按钮 */}
          <div className="p-3 border-t border-border-color bg-bg-panel">
            <div className="flex gap-2">
              <Button
                type="primary"
                className="flex-1 bg-color-up hover:bg-color-up/80 border-color-up"
                icon={<PlayCircleOutlined />}
                onClick={handleStartScreening}
              >
                开始选股
              </Button>
              <Button
                className="flex-1 bg-bg-card border-border-color text-text-secondary hover:text-text-primary"
                icon={<ReloadOutlined />}
                onClick={handleReset}
              >
                重置
              </Button>
            </div>
          </div>
        </div>

        {/* 右侧数据展示区 */}
        <div className="flex-1 flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>
          {/* 顶部工具栏 */}
          <div className="h-12 px-4 flex items-center justify-between border-b border-border-color bg-bg-panel">
            <div className="flex items-center gap-4">
              <Text className="text-text-primary font-semibold">因子综合排名 Top 20</Text>
              <div className="flex items-center gap-2 text-text-secondary text-sm">
                <span className="px-2 py-0.5 bg-bg-card rounded text-xs">筛选条件: 0个</span>
                <span>共 0 只</span>
                <span>(截至 2026-06-10)</span>
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              <Select
                defaultValue="综合得分"
                className="w-28 bg-bg-card border-border-color text-text-primary"
                options={[
                  { value: 'score', label: '综合得分' },
                  { value: 'market_cap', label: '市值' },
                  { value: 'pe', label: '市盈率' },
                ]}
              />
              <Select
                defaultValue="降序"
                className="w-16 bg-bg-card border-border-color text-text-primary"
                options={[
                  { value: 'desc', label: '降序' },
                  { value: 'asc', label: '升序' },
                ]}
              />
              <Select
                defaultValue="Top 20"
                className="w-20 bg-bg-card border-border-color text-text-primary"
                options={[
                  { value: '20', label: 'Top 20' },
                  { value: '50', label: 'Top 50' },
                  { value: '100', label: 'Top 100' },
                ]}
              />
              
              <Divider type="vertical" className="h-6 bg-border-color" />
              
              <Button
                icon={<SaveOutlined />}
                className="bg-color-up/20 text-color-up border-color-up hover:bg-color-up/30"
              >
                保存策略
              </Button>
              <Button
                icon={<FolderOpenOutlined />}
                className="bg-color-up/20 text-color-up border-color-up hover:bg-color-up/30"
              >
                我的策略
              </Button>
            </div>
          </div>

          {/* 数据展示区域 */}
          <div className="flex-1 flex items-center justify-center text-text-secondary bg-bg-base/50 overflow-auto">
            暂无数据
          </div>

          {/* 底部操作栏 */}
          <div className="h-10 px-4 flex items-center justify-between border-t border-border-color bg-bg-panel">
            <div className="flex items-center gap-2">
              <Button
                icon={<PlusCircleOutlined />}
                className="bg-color-up/20 text-color-up border-color-up hover:bg-color-up/30 text-sm"
              >
                加入回测列表
              </Button>
              <Button
                icon={<PlusCircleOutlined />}
                className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
              >
                添加自选
              </Button>
              <Button
                icon={<DownloadOutlined />}
                className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
              >
                导出结果
              </Button>
              <Button
                icon={<BlockOutlined />}
                className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
              >
                加入黑名单
              </Button>
            </div>
            
            <div className="flex items-center gap-4">
              <Button
                icon={<ReloadOutlined />}
                className="bg-bg-card border-border-color text-text-secondary hover:text-text-primary text-sm"
              >
                刷新
              </Button>
              <span className="text-text-secondary text-sm">未选中 (点击行查看详情, 勾选复选框多选)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const StockPickerView: React.FC = () => {
  return (
    <ScreenerProvider>
      <StockPickerContent />
    </ScreenerProvider>
  );
};

export default StockPickerView;
