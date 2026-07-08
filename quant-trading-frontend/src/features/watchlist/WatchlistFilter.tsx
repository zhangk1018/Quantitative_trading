import React, { useMemo } from 'react';
import { Button, Popconfirm } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useWatchlist, SYSTEM_GROUP_SET } from './store';

interface WatchlistFilterProps {
  activeGroup: string | null;
  onGroupChange: (group: string | null) => void;
}

const WatchlistFilter: React.FC<WatchlistFilterProps> = ({ activeGroup, onGroupChange }) => {
  const { state, deleteGroup } = useWatchlist();

  const sortedGroups = useMemo(() => {
    const system = ['全部', '沪深', '港股', '美股'].filter(
      (g) => state.stocks[g] && state.stocks[g].length > 0,
    );
    const custom = [...state.customGroups].sort();
    return [...system, ...custom];
  }, [state.stocks, state.customGroups]);

  if (sortedGroups.length <= 1) return null;

  const handleDelete = (name: string) => {
    deleteGroup(name);
    if (activeGroup === name) {
      onGroupChange(null);
    }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap" data-testid="watchlist-filter">
      <Button
        size="small"
        type={activeGroup === null ? 'primary' : 'default'}
        onClick={() => onGroupChange(null)}
        data-testid="watchlist-filter-all"
      >
        全部
      </Button>
      {sortedGroups.filter((g) => g !== '全部').map((group) => {
        const isSystem = SYSTEM_GROUP_SET.has(group);
        return (
          <span key={group} className="inline-flex items-center">
            <Button
              size="small"
              type={activeGroup === group ? 'primary' : 'default'}
              onClick={() => onGroupChange(group)}
              data-testid={`watchlist-filter-${group}`}
            >
              {group}
              <span className="ml-1 text-xs opacity-60">
                ({state.stocks[group]?.length ?? 0})
              </span>
            </Button>
            {!isSystem && (
              <Popconfirm
                title={`删除分组 "${group}"？`}
                description="分组内的股票将从该分组移除"
                onConfirm={() => handleDelete(group)}
                okText="删除"
                cancelText="取消"
                placement="bottom"
              >
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  className="ml-0.5"
                  data-testid={`watchlist-delete-group-${group}`}
                />
              </Popconfirm>
            )}
          </span>
        );
      })}
    </div>
  );
};

export default WatchlistFilter;