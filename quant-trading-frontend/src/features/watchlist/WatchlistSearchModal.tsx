import React, { useState, useCallback } from 'react';
import { Modal, Input, Typography, Select, App } from 'antd';
import { useWatchlist, SYSTEM_GROUP_SET, detectMarketGroup } from './store';

const { Text } = Typography;

interface WatchlistSearchModalProps {
  open: boolean;
  onClose: () => void;
}

const WatchlistSearchModal: React.FC<WatchlistSearchModalProps> = ({ open, onClose }) => {
  const { message } = App.useApp();
  const { state, addOne, createGroup } = useWatchlist();
  const [code, setCode] = useState('');
  const [selectedGroup, setSelectedGroup] = useState<string>('沪深');
  const [newGroupName, setNewGroupName] = useState('');
  const [adding, setAdding] = useState(false);

  // 构建下拉选项：系统分组 + 自建分组
  const groupOptions = [
    { label: '沪深', value: '沪深' },
    { label: '港股', value: '港股' },
    { label: '美股', value: '美股' },
    ...state.customGroups.map((g) => ({ label: g, value: g })),
    { label: '+ 新建分组', value: '__new__' },
  ];

  const handleAdd = useCallback(async () => {
    const trimmed = code.trim();
    if (!trimmed) {
      message.warning('请输入股票代码');
      return;
    }
    if (!/^\d{6}$/.test(trimmed)) {
      message.warning('请输入6位数字股票代码');
      return;
    }

    let groupName = selectedGroup;
    if (selectedGroup === '__new__') {
      const newName = newGroupName.trim();
      if (!newName) {
        message.warning('请输入分组名称');
        return;
      }
      if (SYSTEM_GROUP_SET.has(newName)) {
        message.warning('不能使用系统分组名称');
        return;
      }
      if (!createGroup(newName)) {
        message.warning('分组已存在');
        return;
      }
      groupName = newName;
    }

    setAdding(true);
    try {
      // 检查是否已在目标分组中
      const existing = state.stocks[groupName] || [];
      if (existing.includes(trimmed)) {
        message.info(`${trimmed} 已在该分组中`);
        setAdding(false);
        return;
      }
      addOne(trimmed, groupName);
      message.success(`${trimmed} 已添加到 ${groupName}（同时加入"全部"和"${detectMarketGroup(trimmed)}"）`);
      setCode('');
      setNewGroupName('');
    } catch {
      message.error('添加失败，请稍后重试');
    } finally {
      setAdding(false);
    }
  }, [code, selectedGroup, newGroupName, state.stocks, addOne, createGroup, message]);

  const handleClose = useCallback(() => {
    if (!adding) {
      setCode('');
      setNewGroupName('');
      setSelectedGroup('沪深');
      onClose();
    }
  }, [adding, onClose]);

  return (
    <Modal
      title="添加自选股"
      open={open}
      onCancel={handleClose}
      onOk={handleAdd}
      confirmLoading={adding}
      okText="添加"
      cancelText="取消"
      destroyOnHidden
      maskClosable={!adding}
      okButtonProps={{ 'data-testid': 'watchlist-search-modal-ok' }}
      cancelButtonProps={{ 'data-testid': 'watchlist-search-modal-cancel' }}
      data-testid="watchlist-search-modal"
    >
      <div className="py-2 space-y-3">
        <div>
          <Text className="text-text-secondary text-sm mb-1 block">股票代码</Text>
          <Input
            placeholder="输入6位数字代码，例如：600519"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onPressEnter={handleAdd}
            maxLength={6}
            disabled={adding}
            data-testid="watchlist-search-input"
            autoFocus
          />
        </div>
        <div>
          <Text className="text-text-secondary text-sm mb-1 block">目标分组</Text>
          <Select
            value={selectedGroup}
            onChange={(v) => setSelectedGroup(v)}
            options={groupOptions}
            className="w-full"
            data-testid="watchlist-search-group-select"
            disabled={adding}
          />
        </div>
        {selectedGroup === '__new__' && (
          <div>
            <Text className="text-text-secondary text-sm mb-1 block">新分组名称</Text>
            <Input
              placeholder="输入分组名称"
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              onPressEnter={handleAdd}
              maxLength={20}
              disabled={adding}
              data-testid="watchlist-search-new-group"
              autoFocus
            />
          </div>
        )}
        <Text className="text-text-secondary text-xs">
          添加后自动加入"全部"和所属市场分组
        </Text>
      </div>
    </Modal>
  );
};

export default WatchlistSearchModal;