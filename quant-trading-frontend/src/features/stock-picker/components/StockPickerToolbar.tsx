import React from 'react';
import { Typography, Button, Divider } from 'antd';
import { SaveOutlined, FolderOpenOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface StockPickerToolbarProps {
  totalFiltersCount: number;
  total: number;
  onOpenSaveModal: () => void;
  onOpenStrategyDrawer: () => void;
}

/**
 * 选股器顶部工具栏
 *
 * 显示筛选条件数量、结果总数，以及策略保存/加载按钮
 */
export const StockPickerToolbar: React.FC<StockPickerToolbarProps> = React.memo(({
  totalFiltersCount, total, onOpenSaveModal, onOpenStrategyDrawer,
}) => (
  <div className="h-12 px-4 flex items-center justify-between border-b border-border-color bg-bg-panel">
    <div className="flex items-center gap-4">
      <Text className="text-text-primary font-semibold">因子综合排名</Text>
      <div className="flex items-center gap-2 text-text-secondary text-sm">
        <span className="px-2 py-0.5 bg-bg-card rounded text-xs">
          筛选条件: {totalFiltersCount}个
        </span>
        <span>共 {total} 只</span>
      </div>
    </div>
    <div className="flex items-center gap-2">
      <Divider type="vertical" className="h-6 bg-border-color" />
      <Button
        icon={<SaveOutlined />}
        onClick={onOpenSaveModal}
        className="bg-bg-card text-text-primary border-border-color hover:bg-border-color"
      >
        保存策略
      </Button>
      <Button
        icon={<FolderOpenOutlined />}
        onClick={onOpenStrategyDrawer}
        className="bg-bg-card text-text-primary border-border-color hover:bg-border-color"
      >
        我的策略
      </Button>
    </div>
  </div>
));
StockPickerToolbar.displayName = 'StockPickerToolbar';