import React, { useState, useCallback } from 'react';
import { Modal, Input, Typography, Select, App, AutoComplete } from 'antd';
import { useWatchlist, SYSTEM_GROUP_SET, detectMarketGroup } from './store';
import { isValidStockCode } from './utils/stock-utils';
import { useStockSearch } from '../backtest/useStockSearch';
import { searchStocksAll } from '../stock-detail/api';

const { Text } = Typography;

interface WatchlistSearchModalProps {
  open: boolean;
  onClose: () => void;
}

const WatchlistSearchModal: React.FC<WatchlistSearchModalProps> = ({ open, onClose }) => {
  const { message } = App.useApp();
  const { state, addOne, createGroup } = useWatchlist();
  // 代码/名称模糊搜索（防抖，复用 /stocks/search）
  const { keyword, setKeyword, options, loading, clearOptions } = useStockSearch(300);
  // 从下拉选中解析出的股票代码（输入名称时用于回落）
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<string>('沪深');
  const [newGroupName, setNewGroupName] = useState('');
  const [adding, setAdding] = useState(false);

  // AutoComplete 选项（展示"名称 (代码)"，选中值为代码）
  const autoOptions = options.map((s) => ({
    value: s.stock_code,
    label: `${s.stock_name} (${s.stock_code})`,
  }));

  // 构建下拉选项：系统分组 + 自建分组
  const groupOptions = [
    { label: '沪深', value: '沪深' },
    { label: '港股', value: '港股' },
    { label: '美股', value: '美股' },
    ...state.customGroups.map((g) => ({ label: g, value: g })),
    { label: '+ 新建分组', value: '__new__' },
  ];

  const resolveCode = useCallback(async (raw: string): Promise<string | null> => {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    // 直接输入合法代码 → 原样使用
    if (isValidStockCode(trimmed)) return trimmed;
    // 输入名称：优先用下拉选中的代码
    if (selectedCode) return selectedCode;
    // 输入名称但未选中：实时搜索精确匹配（名称完全一致，或仅一个候选）
    const result = await searchStocksAll(trimmed);
    const items = result.items || [];
    const exact = items.filter((i) => i.stock_name === trimmed);
    const match = exact[0] ?? (items.length === 1 ? items[0] : null);
    return match ? match.stock_code : null;
  }, [selectedCode]);

  const handleAdd = useCallback(async () => {
    const trimmed = keyword.trim();
    const resolved = await resolveCode(trimmed);
    if (!resolved) {
      message.warning('请输入正确的股票代码或从下拉列表选择股票');
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
      if (existing.includes(resolved)) {
        const match = options.find(o => o.stock_code === resolved);
        const display = match ? `${match.stock_name} (${resolved})` : resolved;
        message.info(`${display} 已在该分组中`);
        setAdding(false);
        return;
      }
      addOne(resolved, groupName);
      const match = options.find(o => o.stock_code === resolved);
      const display = match ? `${match.stock_name} (${resolved})` : resolved;
      message.success(`${display} 已添加到 ${groupName}（同时加入"全部"和"${detectMarketGroup(resolved)}"）`);
      setKeyword('');
      setSelectedCode(null);
      clearOptions();
      setNewGroupName('');
    } catch (err) {
      console.warn('[Watchlist] 添加自选股失败', err);
      message.error('添加失败，请稍后重试');
    } finally {
      setAdding(false);
    }
  }, [keyword, selectedGroup, newGroupName, state.stocks, addOne, createGroup, message, resolveCode, options, setKeyword, clearOptions]);

  const handleClose = useCallback(() => {
    if (!adding) {
      setKeyword('');
      setSelectedCode(null);
      clearOptions();
      setNewGroupName('');
      setSelectedGroup('沪深');
      onClose();
    }
  }, [adding, onClose, setKeyword, clearOptions]);

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
          <Text className="text-text-secondary text-sm mb-1 block">股票代码或名称</Text>
          <AutoComplete
            id="watchlist-search-input"
            value={keyword}
            options={autoOptions}
            onChange={(v) => {
              setKeyword(v);
              setSelectedCode((prev) => (prev === v ? prev : null));
            }}
            onSelect={(val) => {
              // 立即更新状态，避免点击冒泡到添加按钮导致读取 stale 状态（点击从下拉菜单冒泡到 modal 底部的按钮）
              setKeyword(val);
              setSelectedCode(val);
              // 强制清空下拉，让后续点击不会命中同一元素冒泡
              setTimeout(() => {
                clearOptions();
              }, 0);
            }}
            disabled={adding}
            autoFocus
            allowClear
            filterOption={false}
            notFoundContent={loading ? '搜索中…' : '未找到匹配的股票'}
            placeholder="输入股票代码或名称，例如：600519 / 平安银行"
            // 关键修复：让输入框撑满宽度，避免过窄
            className="w-full"
            style={{ width: '100%' }}
            size="large"
            // 下拉面板宽度与输入框对齐，并保证足够高度
            popupMatchSelectWidth
            listHeight={280}
            dropdownStyle={{ minWidth: 280 }}
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