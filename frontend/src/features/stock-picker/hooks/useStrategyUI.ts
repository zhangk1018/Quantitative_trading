import { useState, useCallback } from 'react';
import { App } from 'antd';
import { useScreener } from '../context/ScreenerContext';
import { useSavedStrategies } from './useSavedStrategies';

/**
 * 策略 UI 状态管理 Hook
 *
 * 职责：
 * - 策略保存/加载模态框的开关状态
 * - 保存/重命名/删除操作（含失败反馈）
 * - 策略列表数据
 */
export function useStrategyUI() {
  const { message } = App.useApp();
  const screenerState = useScreener();
  const { strategies, saveStrategy, updateStrategyName, deleteStrategy } = useSavedStrategies();

  const [saveModalVisible, setSaveModalVisible] = useState(false);
  const [strategyDrawerVisible, setStrategyDrawerVisible] = useState(false);

  const handleSaveStrategy = useCallback(
    (name: string) => {
      const result = saveStrategy(name, screenerState.state);
      if (result.ok) {
        message.success('策略已保存');
      } else {
        message.error(result.error || '策略保存失败');
      }
    },
    [saveStrategy, screenerState.state, message],
  );

  const handleRenameStrategy = useCallback(
    (id: string, newName: string) => {
      const result = updateStrategyName(id, newName);
      if (!result.ok) {
        message.error(result.error || '重命名失败');
      }
    },
    [updateStrategyName, message],
  );

  const handleDeleteStrategy = useCallback(
    (id: string) => {
      const result = deleteStrategy(id);
      if (!result.ok) {
        message.error(result.error || '删除失败');
      }
    },
    [deleteStrategy, message],
  );

  return {
    saveModalVisible, setSaveModalVisible,
    strategyDrawerVisible, setStrategyDrawerVisible,
    strategies,
    handleSaveStrategy, handleRenameStrategy, handleDeleteStrategy,
  } as const;
}