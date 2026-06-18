/**
 * 自编指标管理组件（K 2026-06-17 决策：从 ConditionBuilder 迁移至 /config 页面）
 *
 * 设计要点：
 * - 统一封装 4 组件：CustomIndicatorModal / CustomIndicatorList / ImportExportButtons + storage
 * - 5 个 handler：Save / Update / Edit / Delete / ImportSuccess
 * - useScreener() 共享状态（AppLayout 层 Provider 跨页面共享 customIndicators）
 * - useSearchParams 解析 ?action=new 自动打开新建弹窗；关闭时清除 URL 参数
 *
 * 复用约束：
 * - 不修改 storage / reducer / types（仅消费既有 API）
 * - CustomIndicatorModal/List/ImportExportButtons 不修改（P3.1/3.2/3.3 已完成）
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button, message, Space, Typography, Card } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useScreener } from '../../stock-picker/context/ScreenerContext';
import { CustomIndicatorModal } from '../../stock-picker/components/CustomIndicatorModal';
import { CustomIndicatorList } from '../../stock-picker/components/CustomIndicatorList';
import { ImportExportButtons } from '../../stock-picker/components/ImportExportButtons';
import {
  saveCustomIndicator,
  removeCustomIndicator,
  MOCK_USER_ID,
} from '../../stock-picker/utils/customIndicatorStorage';
import type { CustomIndicator } from '../../stock-picker/types/customIndicator';

const { Text } = Typography;

export const CustomIndicatorManager: React.FC = () => {
  const { state, dispatch } = useScreener();
  const { customIndicators, filterGroup } = state;
  const [searchParams, setSearchParams] = useSearchParams();

  // K 2026-06-18 任务 #9：从 state.filterGroup.conditions 实时计算已引用的指标 ID
  // （替代之前 CustomIndicatorList 内直接调 storage.isIndicatorReferenced 读 localStorage）
  // K 2026-06-18 反馈 #4：使用 isIndicatorReferencedByConditions 纯函数从内存计算，
  // 不再依赖 localStorage 读 plans_<userId>，避免 React state 与 storage 脱节
  // K 2026-06-18 反馈 #5：过滤掉 invalid 条件，避免失效引用触发"被方案引用"提示
  const referencedIds = useMemo(() => {
    const ids = new Set<string>();
    const conds = filterGroup?.conditions ?? [];
    conds.forEach((c) => {
      // 失效条件不再视为"被方案引用"（指标已删除后条件标记 invalid，
      // 删除时不应再提示"被引用"风险）
      if (c.invalid) return;
      if (c.source === 'custom' && c.sourceId) ids.add(c.sourceId);
    });
    return ids;
  }, [filterGroup?.conditions]);

  // 弹窗状态
  const [showCustomModal, setShowCustomModal] = useState(false);
  const [editingIndicator, setEditingIndicator] = useState<CustomIndicator | null>(null);

  // 路由参数 ?action=new → 自动打开新建弹窗
  // K 2026-06-17 决策：配置页做参数解析自动唤起新建弹窗
  useEffect(() => {
    const action = searchParams.get('action');
    if (action === 'new' && !showCustomModal) {
      setEditingIndicator(null);
      setShowCustomModal(true);
    }
  }, [searchParams, showCustomModal]);

  /**
   * 关闭弹窗 + 清除 URL 中的 action 参数
   * K 偏好：URL 是弹窗状态的唯一来源（避免状态/URL 不一致）
   */
  const handleCloseModal = useCallback(() => {
    setShowCustomModal(false);
    setEditingIndicator(null);
    if (searchParams.get('action')) {
      const next = new URLSearchParams(searchParams);
      next.delete('action');
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  /**
   * P3.1：保存自编指标
   * - 调用 storage API 持久化
   * - dispatch ADD_CUSTOM_INDICATOR 更新 state
   * - 关闭抽屉 + 清除 URL 参数
   */
  const handleSave = (data: Parameters<typeof saveCustomIndicator>[0]) => {
    try {
      const saved = saveCustomIndicator(data);
      dispatch({ type: 'ADD_CUSTOM_INDICATOR', payload: saved });
      message.success(`自编指标"${saved.name}"已创建`);
      handleCloseModal();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  /**
   * P3.3：编辑自编指标（保存）
   * - 调用 saveCustomIndicator 持久化（带 id 会走更新分支）
   * - dispatch UPDATE_CUSTOM_INDICATOR 更新 state
   * - 关闭抽屉 + 清除 URL 参数
   */
  const handleUpdate = (data: Parameters<typeof saveCustomIndicator>[0]) => {
    if (!editingIndicator) return;
    try {
      const updated = saveCustomIndicator({ ...data, id: editingIndicator.id });
      dispatch({ type: 'UPDATE_CUSTOM_INDICATOR', payload: updated });
      message.success(`自编指标"${updated.name}"已更新`);
      handleCloseModal();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  /**
   * P3.3：编辑入口
   * - 列表项点击编辑按钮 → 设置 editingIndicator + 打开抽屉
   */
  const handleEdit = (ind: CustomIndicator) => {
    setEditingIndicator(ind);
    setShowCustomModal(true);
  };

  /**
   * P3.3：删除自编指标
   * - 调用 removeCustomIndicator 软删除
   * - dispatch REMOVE_CUSTOM_INDICATOR 更新 state（reducer 自动扫描 filterGroup 标记失效）
   */
  const handleDelete = (id: string) => {
    const ind = customIndicators.find((i) => i.id === id);
    if (!ind) return;
    try {
      removeCustomIndicator(id, MOCK_USER_ID);
      dispatch({ type: 'REMOVE_CUSTOM_INDICATOR', payload: id });
      message.success(`自编指标"${ind.name}"已删除`);
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  /**
   * P3.2：导入自编指标成功回调
   * - IMPORT_CUSTOM_INDICATORS reducer 按 id 去重
   * - 一次性 dispatch 多个新增指标
   */
  const handleImportSuccess = (newIndicators: CustomIndicator[]) => {
    dispatch({ type: 'IMPORT_CUSTOM_INDICATORS', payload: newIndicators });
  };

  return (
    <div className="space-y-4" data-testid="custom-indicator-manager">
      {/* 顶部操作栏：新建 + 导入导出 + 计数 */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <Space size="small">
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingIndicator(null);
              setShowCustomModal(true);
            }}
            data-testid="custom-manager-create-btn"
          >
            新建自编指标
          </Button>
          <ImportExportButtons
            customIndicators={customIndicators}
            onImportSuccess={handleImportSuccess}
          />
        </Space>
        <Text
          className="text-text-secondary text-sm"
          data-testid="custom-manager-count"
        >
          已有 {customIndicators.length} 条
        </Text>
      </div>

      {/* 指标列表 */}
      <CustomIndicatorList
        indicators={customIndicators}
        referencedIds={referencedIds}
        onEdit={handleEdit}
        onDelete={handleDelete}
      />

      {/* 弹窗 */}
      {showCustomModal && (
        <CustomIndicatorModal
          title={editingIndicator ? '编辑自编指标' : '新建自编指标'}
          editing={editingIndicator}
          onConfirm={editingIndicator ? handleUpdate : handleSave}
          onCancel={handleCloseModal}
        />
      )}
    </div>
  );
};

export default CustomIndicatorManager;
