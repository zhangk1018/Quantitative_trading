/**
 * watchlist/index.tsx — 自选股页面主组件（localStorage 存储，零后端依赖）
 *
 * 数据流：
 * 1. useWatchlist → localStorage 读写（分组 + 股票代码）
 * 2. useWatchlistQuotes → 后端 fetchStocks 拉取行情
 * 3. 合并 → WatchlistStockRow（前端 useMemo）
 * 4. 分组筛选 → 前端 useMemo 派生
 * 5. 表格渲染 → WatchlistTable（含列排序）
 * 6. 列排序 → 前端 useMemo
 */

import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { Typography, Button, Spin, App, Modal, Input } from 'antd';
import { PlusOutlined, ReloadOutlined, FolderAddOutlined } from '@ant-design/icons';
import { useWatchlist, SYSTEM_GROUP_SET } from './store';
import { useWatchlistQuotes } from './hooks/useWatchlistQuotes';
import StockAnalysisModal from '@/features/stock-picker/components/StockAnalysisModal';
import WatchlistTable from './WatchlistTable';
import WatchlistFilter from './WatchlistFilter';
import WatchlistEmpty from './WatchlistEmpty';
import WatchlistSearchModal from './WatchlistSearchModal';

const { Text } = Typography;

/** 合并后的自选股行数据 */
export interface WatchlistStockRow {
  stock_code: string;
  stock_name: string;
  close: number | null;
  change_pct: number | null;
  pe: number | null;
  pe_ttm: number | null;
  pb: number | null;
  market_cap: number | null;
  amount: number | null;
  turnover_rate: number | null;
  listed_board: string | null;
  group_name: string;
}

function toModalStock(row: WatchlistStockRow) {
  return {
    stock_code: row.stock_code,
    stock_name: row.stock_name,
    close: row.close ?? 0,
    change_pct: row.change_pct ?? 0,
    turnover_rate: row.turnover_rate ?? 0,
    pe: row.pe ?? row.pe_ttm ?? 0,
    pb: row.pb ?? 0,
    market_cap: row.market_cap ?? 0,
    amount: row.amount ?? 0,
    listed_board: row.listed_board,
  };
}

const Watchlist: React.FC = () => {
  const { message } = App.useApp();
  const { state, addOne, addMany, removeOne, createGroup, allGroups, refresh: refreshWatchlist } = useWatchlist();

  // 暴露 addMany 到 window，供 E2E 性能测试使用
  useEffect(() => {
    if (typeof window !== 'undefined') {
      (window as any).__watchlistHelpers__ = { addMany };
    }
    return () => {
      delete (window as any).__watchlistHelpers__;
    };
  }, [addMany]);

  const [activeGroup, setActiveGroup] = useState<string | null>(null);
  const [analysisStock, setAnalysisStock] = useState<WatchlistStockRow | null>(null);
  const [searchModalOpen, setSearchModalOpen] = useState(false);
  const [createGroupModalOpen, setCreateGroupModalOpen] = useState(false);
  const [newGroupInput, setNewGroupInput] = useState('');

  // 计算当前分组对应的股票代码列表
  const visibleCodes = useMemo(() => {
    if (activeGroup === null) {
      // 默认显示：优先显示"全部"分组，若不存在则显示第一个有数据的分组
      const all = state.stocks['全部'] || [];
      if (all.length > 0) return all;
      // 找第一个有数据的系统分组
      for (const sys of ['沪深', '港股', '美股']) {
        if (state.stocks[sys] && state.stocks[sys].length > 0) return state.stocks[sys];
      }
      return [];
    }
    return state.stocks[activeGroup] || [];
  }, [activeGroup, state.stocks]);

  // 所有唯一代码（用于行情查询）
  const allCodes = useMemo(() => {
    const set = new Set<string>();
    for (const codes of Object.values(state.stocks)) {
      codes.forEach((c) => set.add(c));
    }
    return Array.from(set);
  }, [state.stocks]);

  // 行情数据
  const {
    quotesMap,
    loading: quotesLoading,
    refreshing: quotesRefreshing,
    error: quotesError,
    refresh: refreshQuotes,
  } = useWatchlistQuotes(allCodes);

  // 合并数据：代码 → WatchlistStockRow
  const mergedRows = useMemo<WatchlistStockRow[]>(() => {
    const codeToGroups = new Map<string, string[]>();
    for (const [group, codes] of Object.entries(state.stocks)) {
      for (const code of codes) {
        if (!codeToGroups.has(code)) codeToGroups.set(code, []);
        codeToGroups.get(code)!.push(group);
      }
    }

    return visibleCodes.map((code) => {
      const quote = quotesMap.get(code);
      const groups = codeToGroups.get(code) || [];
      const groupName = activeGroup || groups.filter((g) => !SYSTEM_GROUP_SET.has(g)).join(', ') || groups[0] || '';
      return {
        stock_code: code,
        stock_name: quote?.stock_name ?? code,
        close: quote?.close ?? null,
        change_pct: quote?.change_pct ?? null,
        pe: quote?.pe ?? null,
        pe_ttm: quote?.pe_ttm ?? null,
        pb: quote?.pb ?? null,
        market_cap: quote?.market_cap ?? null,
        amount: quote?.amount ?? null,
        turnover_rate: quote?.turnover_rate ?? null,
        listed_board: quote?.listed_board ?? null,
        group_name: groupName,
      };
    });
  }, [visibleCodes, quotesMap, state.stocks, activeGroup]);

  // 删除：根据当前分组决定删除范围
  const handleDelete = useCallback(
    (code: string) => {
      const group = activeGroup || '全部';
      removeOne(code, group);
      message.success('已从自选股移除');
    },
    [activeGroup, removeOne, message],
  );

  // 双击查看K线
  const handleDoubleClick = useCallback((row: WatchlistStockRow) => {
    setAnalysisStock(row);
  }, []);

  // 手动刷新
  const handleRefresh = useCallback(async () => {
    refreshQuotes();
    message.success('刷新完成');
  }, [refreshQuotes, message]);

  // 创建分组
  const handleCreateGroup = useCallback(() => {
    const name = newGroupInput.trim();
    if (!name) {
      message.warning('请输入分组名称');
      return;
    }
    if (SYSTEM_GROUP_SET.has(name)) {
      message.warning('不能使用系统分组名称');
      return;
    }
    if (state.customGroups.includes(name)) {
      message.warning('分组已存在');
      return;
    }
    createGroup(name);
    setNewGroupInput('');
    setCreateGroupModalOpen(false);
    message.success(`分组 "${name}" 已创建`);
  }, [newGroupInput, state.customGroups, createGroup, message]);

  const totalStocks = allCodes.length;
  const hasData = totalStocks > 0;

  return (
    <div className="min-h-screen flex flex-col bg-bg-base">
      {/* 顶部工具栏 */}
      <div className="h-12 px-4 flex items-center justify-between border-b border-border-color bg-bg-panel">
        <div className="flex items-center gap-4">
          <Text className="text-text-primary font-semibold">自选股</Text>
          <span className="text-text-secondary text-sm">
            共 {totalStocks} 只
          </span>
          {quotesRefreshing && (
            <Spin size="small" data-testid="watchlist-refreshing-spinner" />
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            icon={<PlusOutlined />}
            onClick={() => setSearchModalOpen(true)}
            data-testid="watchlist-add-btn"
          >
            添加自选
          </Button>
          <Button
            icon={<FolderAddOutlined />}
            onClick={() => setCreateGroupModalOpen(true)}
            data-testid="watchlist-create-group-btn"
          >
            添加分组
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            disabled={quotesLoading}
            data-testid="watchlist-refresh-btn"
          >
            刷新
          </Button>
        </div>
      </div>

      {/* 分组筛选 */}
      {allGroups.length > 0 && (
        <div className="px-4 py-2 border-b border-border-color bg-bg-panel">
          <WatchlistFilter
            activeGroup={activeGroup}
            onGroupChange={setActiveGroup}
          />
        </div>
      )}

      {/* 错误提示 */}
      {quotesError && hasData && (
        <div className="px-4 py-2 bg-red-500/10 text-red-500 text-sm flex items-center gap-2" data-testid="watchlist-error-banner">
          <span>行情数据加载失败：{quotesError}</span>
          <Button size="small" type="link" onClick={refreshQuotes} className="text-red-500">
            重试
          </Button>
        </div>
      )}

      {/* 内容区 */}
      <div className="flex-1 overflow-auto">
        {quotesLoading && !hasData ? (
          <div className="flex items-center justify-center py-20" data-testid="watchlist-first-load">
            <Spin tip="加载自选股..." />
          </div>
        ) : !hasData ? (
          <WatchlistEmpty />
        ) : (
          <>
            {quotesLoading && (
              <div className="flex items-center justify-center py-2" data-testid="watchlist-quotes-loading">
                <Spin size="small" />
                <Text className="text-text-secondary text-sm ml-2">加载行情数据...</Text>
              </div>
            )}
            <WatchlistTable
              rows={mergedRows}
              activeGroup={activeGroup}
              onDelete={handleDelete}
              onDoubleClick={handleDoubleClick}
            />
          </>
        )}
      </div>

      {/* 搜索添加弹窗 */}
      <WatchlistSearchModal
        open={searchModalOpen}
        onClose={() => setSearchModalOpen(false)}
      />

      {/* 创建分组弹窗 */}
      <Modal
        title="新建分组"
        open={createGroupModalOpen}
        onCancel={() => {
          setNewGroupInput('');
          setCreateGroupModalOpen(false);
        }}
        onOk={handleCreateGroup}
        okText="创建"
        cancelText="取消"
        okButtonProps={{ 'data-testid': 'watchlist-create-group-ok' }}
        cancelButtonProps={{ 'data-testid': 'watchlist-create-group-cancel' }}
        data-testid="watchlist-create-group-modal"
      >
        <div className="py-2">
          <Text className="text-text-secondary text-sm mb-2 block">分组名称</Text>
          <Input
            placeholder="输入分组名称"
            value={newGroupInput}
            onChange={(e) => setNewGroupInput(e.target.value)}
            onPressEnter={handleCreateGroup}
            maxLength={20}
            autoFocus
            data-testid="watchlist-create-group-input"
          />
        </div>
      </Modal>

      {/* K线图弹窗 */}
      <StockAnalysisModal
        open={!!analysisStock}
        stock={analysisStock ? toModalStock(analysisStock) : null}
        onClose={() => setAnalysisStock(null)}
      />
    </div>
  );
};

export default Watchlist;