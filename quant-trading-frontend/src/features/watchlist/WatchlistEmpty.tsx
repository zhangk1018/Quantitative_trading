import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Typography, Button } from 'antd';
import { SearchOutlined } from '@ant-design/icons';

const { Text } = Typography;

const WatchlistEmpty: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center py-20" data-testid="watchlist-empty">
      <div className="text-6xl mb-4 opacity-30">📋</div>
      <Text className="text-text-secondary text-lg mb-2">暂无自选股</Text>
      <Text className="text-text-secondary text-sm mb-6">
        前往选股器筛选股票，或直接搜索代码添加
      </Text>
      <div className="flex gap-3">
        <Button
          type="primary"
          icon={<SearchOutlined />}
          onClick={() => navigate('/picker')}
          data-testid="watchlist-empty-goto-picker"
        >
          前往选股器
        </Button>
      </div>
    </div>
  );
};

export default WatchlistEmpty;