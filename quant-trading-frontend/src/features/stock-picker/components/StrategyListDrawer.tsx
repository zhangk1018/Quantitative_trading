import React, { useState } from 'react';
import { Drawer, List, Button, Popconfirm, Typography, Empty, message } from 'antd';
import { DeleteOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons';
import type { SavedStrategy } from '../hooks/useSavedStrategies';

const { Text } = Typography;

interface StrategyListDrawerProps {
  visible: boolean;
  strategies: SavedStrategy[];
  onClose: () => void;
  onLoad: (strategy: SavedStrategy) => void;
  onRename: (id: string, newName: string) => void;
  onDelete: (id: string) => void;
}

/**
 * 生成策略摘要文字
 */
function getStrategySummary(state: SavedStrategy['state']): string {
  const parts: string[] = [];

  if (state.market.selectedMarket) {
    parts.push(state.market.selectedMarket);
  }
  if (state.market.selectedBoards?.length > 0) {
    parts.push(state.market.selectedBoards.join('、'));
  }
  if (state.marketIndicators.selected?.length > 0) {
    parts.push(`${state.marketIndicators.selected.length} 个行情指标`);
  }
  if (state.financialIndicators.selected?.length > 0) {
    parts.push(`${state.financialIndicators.selected.length} 个财务指标`);
  }
  if (state.technical.selected && Object.keys(state.technical.selected).length > 0) {
    parts.push(`${Object.keys(state.technical.selected).length} 个技术指标`);
  }
  if (state.patterns.selected && Object.keys(state.patterns.selected).length > 0) {
    parts.push(`${Object.keys(state.patterns.selected).length} 个形态`);
  }
  if (state.custom.indicators?.length > 0) {
    parts.push(`${state.custom.indicators.length} 个自定义指标`);
  }
  if (state.condition.filterGroup) {
    parts.push('含高级筛选');
  }

  return parts.length > 0 ? parts.join(' · ') : '无筛选条件';
}

/**
 * 格式化日期显示
 */
function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

/**
 * 我的策略抽屉 — 展示已保存策略列表，支持加载、重命名、删除
 */
export function StrategyListDrawer({
  visible,
  strategies,
  onClose,
  onLoad,
  onRename,
  onDelete,
}: StrategyListDrawerProps) {
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renamingText, setRenamingText] = useState('');

  if (!visible) {
    return null;
  }

  const handleStartRename = (strategy: SavedStrategy) => {
    setRenamingId(strategy.id);
    setRenamingText(strategy.name);
  };

  const handleConfirmRename = () => {
    if (renamingId && renamingText.trim()) {
      onRename(renamingId, renamingText.trim());
      message.success('已重命名');
    }
    setRenamingId(null);
    setRenamingText('');
  };

  const handleDelete = (id: string) => {
    onDelete(id);
    message.success('已删除策略');
  };

  return (
    <Drawer
      title="我的策略"
      open={visible}
      onClose={onClose}
      width={420}
      data-testid="strategy-list-drawer"
    >
      {strategies.length === 0 ? (
        <Empty description="暂无保存的策略" />
      ) : (
        <List
          dataSource={strategies}
          renderItem={item => (
            <List.Item
              key={item.id}
              actions={[
                <Button
                  key="load"
                  type="link"
                  icon={<ReloadOutlined />}
                  onClick={() => {
                    onLoad(item);
                    message.success('已加载策略');
                  }}
                  data-testid={`strategy-load-${item.id}`}
                >
                  加载
                </Button>,
                <Button
                  key="edit"
                  type="link"
                  icon={<EditOutlined />}
                  onClick={() => handleStartRename(item)}
                  data-testid={`strategy-rename-${item.id}`}
                />,
                <Popconfirm
                  key="delete"
                  title="确定删除此策略？"
                  onConfirm={() => handleDelete(item.id)}
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ 'data-testid': `strategy-delete-ok-${item.id}` }}
                  cancelButtonProps={{ 'data-testid': `strategy-delete-cancel-${item.id}` }}
                >
                  <Button
                    type="link"
                    danger
                    icon={<DeleteOutlined />}
                    data-testid={`strategy-delete-${item.id}`}
                  />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  renamingId === item.id ? (
                    <input
                      type="text"
                      value={renamingText}
                      onChange={e => setRenamingText(e.target.value)}
                      onBlur={handleConfirmRename}
                      onKeyDown={e => {
                        if (e.key === 'Enter') handleConfirmRename();
                        if (e.key === 'Escape') {
                          setRenamingId(null);
                          setRenamingText('');
                        }
                      }}
                      autoFocus
                      style={{ width: '100%', padding: '4px 8px', border: '1px solid #1677ff', borderRadius: 4 }}
                      data-testid={`strategy-rename-input-${item.id}`}
                    />
                  ) : (
                    <Text strong>{item.name}</Text>
                  )
                }
                description={
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {getStrategySummary(item.state)}
                    </Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {formatDate(item.createdAt)}
                    </Text>
                  </div>
                }
              />
            </List.Item>
          )}
        />
      )}
    </Drawer>
  );
}
