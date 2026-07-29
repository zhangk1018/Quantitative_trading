import { useState, useCallback } from 'react';
import { Modal, App } from 'antd';
import { useScreenerSelector } from '../context/ScreenerContext';
import { useWatchlist, SYSTEM_GROUP_SET } from '../../watchlist/store';
import { MARKET_CONFIG } from '../config/marketConfig';

// ==================== 错误类型守卫 ====================
function getErrorMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === 'string') return e;
  return '未知错误';
}

/**
 * 添加自选股操作 Hook
 *
 * 职责：
 * - 添加自选弹窗的开关状态
 * - 分组选择 / 新建分组 / 确认添加逻辑
 * - 结果统计与错误反馈
 */
export function useWatchlistAdd(
  selectedCodes: Set<string>,
  selectedCount: number,
  setSelectedCodes: (codes: Set<string>) => void,
) {
  const { message } = App.useApp();
  const { addMany, state: watchlistState, createGroup } = useWatchlist();
  const screenerMarket = useScreenerSelector((s) => s.market.selectedMarket);
  const selectedMarketLabel = MARKET_CONFIG[screenerMarket]?.label || '沪深';

  const [addModalOpen, setAddModalOpen] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState(selectedMarketLabel);
  const [newGroupName, setNewGroupName] = useState('');
  const [adding, setAdding] = useState(false);

  const handleAddClick = useCallback(() => {
    if (selectedCount === 0) {
      Modal.info({
        title: '请先勾选股票',
        content: '点击表格左侧复选框选择要加入自选股的股票',
        okText: '我知道了',
      });
      return;
    }
    setSelectedGroup(selectedMarketLabel);
    setNewGroupName('');
    setAddModalOpen(true);
  }, [selectedCount, selectedMarketLabel]);

  const handleConfirmAdd = useCallback(async () => {
    if (adding) return;
    setAdding(true);
    try {
      const codes = Array.from(selectedCodes);
      let targetGroup = selectedGroup;
      if (selectedGroup === '__new__') {
        const trimmed = newGroupName.trim();
        if (!trimmed) { message.warning('请输入分组名称'); setAdding(false); return; }
        if (SYSTEM_GROUP_SET.has(trimmed)) { message.warning('不能使用系统分组名称'); setAdding(false); return; }
        if (!createGroup(trimmed)) { message.warning('分组已存在'); setAdding(false); return; }
        targetGroup = trimmed;
      }
      const result = addMany(codes, targetGroup);
      const parts = [];
      if (result.added > 0) parts.push(`新增 ${result.added}`);
      if (result.skipped > 0) parts.push(`跳过 ${result.skipped}（已在自选）`);
      if (result.failed > 0) parts.push(`失败 ${result.failed}`);
      const summary = parts.length > 0 ? parts.join('，') : '无变化';
      if (result.failed > 0) {
        message.warning(`添加自选完成：${summary}。失败股票：${result.errors.join(', ')}`);
      } else {
        message.success(`添加自选完成：${summary}`);
      }
      setSelectedCodes(new Set());
      setAddModalOpen(false);
      setSelectedGroup(selectedMarketLabel);
      setNewGroupName('');
    } catch (e: unknown) {
      message.error(`添加自选失败: ${getErrorMessage(e)}`);
    } finally {
      setAdding(false);
    }
  }, [addMany, selectedCodes, selectedGroup, newGroupName, adding, createGroup, message, selectedMarketLabel, setSelectedCodes]);

  return {
    addModalOpen, setAddModalOpen, selectedGroup, setSelectedGroup,
    newGroupName, setNewGroupName, adding, selectedMarketLabel,
    handleAddClick, handleConfirmAdd, watchlistState,
  } as const;
}