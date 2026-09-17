import { useRef, useState } from 'react';
import { Drawer, List, Button, Popconfirm, Typography, Empty, message, Modal, Checkbox, Space, Table, Tag, Alert } from 'antd';
import {
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
  DownloadOutlined,
  UploadOutlined,
  CheckCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  buildStrategyExportFile,
  parseStrategyImportFile,
  computeStrategyImportPreview,
  mergeImportedStrategies,
  type SavedStrategy,
  type StrategyImportErrorDetail,
  type StrategyImportErrorType,
  type StrategyExportFile,
} from '../hooks/useSavedStrategies';

const { Text } = Typography;

const IMPORT_ERROR_TYPE_META: Record<StrategyImportErrorType, { label: string; color: string }> = {
  name_duplicate: { label: '名称重复已跳过', color: 'orange' },
  field_invalid: { label: '字段缺失/类型错误', color: 'volcano' },
  parse_error: { label: '解析失败', color: 'magenta' },
};

interface StrategyListDrawerProps {
  visible: boolean;
  strategies: SavedStrategy[];
  onClose: () => void;
  onLoad: (strategy: SavedStrategy) => void;
  onRename: (id: string, newName: string) => void;
  onDelete: (id: string) => void;
  /** 批量导入策略（UI 层已去重/重命名，hook 负责持久化） */
  onImport: (strategies: SavedStrategy[]) => void;
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
    console.warn('[Screener] 日期格式化失败:', iso);
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
  onImport,
}: StrategyListDrawerProps) {
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renamingText, setRenamingText] = useState('');
  // 导出选择 Modal 状态
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportSelected, setExportSelected] = useState<string[]>([]);
  const exportAllChecked = exportSelected.length === strategies.length && strategies.length > 0;
  const exportIndeterminate = exportSelected.length > 0 && !exportAllChecked;
  // 导入 Preview 状态
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importPreview, setImportPreview] = useState<{
    visible: boolean;
    file: StrategyExportFile | null;
    errors: StrategyImportErrorDetail[];
    previewAdded: number;
    previewSkipped: number;
  }>({ visible: false, file: null, errors: [], previewAdded: 0, previewSkipped: 0 });
  const [importing, setImporting] = useState(false);

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

  // 打开导出选择 Modal：默认全选
  const handleOpenExportModal = () => {
    setExportSelected(strategies.map((s) => s.id));
    setExportModalOpen(true);
  };

  const handleToggleSelectAll = (e: { target: { checked: boolean } }) => {
    setExportSelected(e.target.checked ? strategies.map((s) => s.id) : []);
  };

  const handleCancelExport = () => {
    setExportModalOpen(false);
    setExportSelected([]);
  };

  // 真正执行导出下载
  const doExport = (ids: string[]) => {
    const file = buildStrategyExportFile(strategies, ids);
    const json = JSON.stringify(file, null, 2);
    const blob = new Blob([json], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const today = new Date().toISOString().slice(0, 10);
    const filename = `screener-strategies-${today}.json`;

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    message.success(`已导出 ${file.strategies.length} 条策略到 ${filename}`);
  };

  const handleConfirmExport = () => {
    if (exportSelected.length === 0) {
      message.warning('请至少选择 1 条策略');
      return;
    }
    doExport(exportSelected);
    handleCancelExport();
  };

  const handleCloseDrawer = () => {
    setExportModalOpen(false);
    setExportSelected([]);
    setImportPreview({ visible: false, file: null, errors: [], previewAdded: 0, previewSkipped: 0 });
    onClose();
  };

  // ========== 导入 ==========
  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (e.target) e.target.value = '';
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      message.error(`文件过大（${(file.size / 1024 / 1024).toFixed(2)}MB），最大支持 5MB`);
      return;
    }

    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result;
      if (typeof text !== 'string') {
        message.error('文件读取失败');
        return;
      }
      processImportText(text);
    };
    reader.onerror = () => message.error('文件读取失败');
    reader.readAsText(file);
  };

  const processImportText = (text: string) => {
    let parsed: StrategyExportFile;
    try {
      parsed = parseStrategyImportFile(text);
    } catch (e) {
      message.error((e as Error).message);
      return;
    }

    const previewResult = computeStrategyImportPreview(parsed, strategies);
    setImportPreview({
      visible: true,
      file: parsed,
      errors: previewResult.errors,
      previewAdded: previewResult.added,
      previewSkipped: previewResult.skipped,
    });
  };

  const handleConfirmImport = () => {
    if (!importPreview.file) return;
    setImporting(true);
    try {
      const { added, skipped } = mergeImportedStrategies(importPreview.file, strategies);
      if (added.length > 0) {
        onImport(added);
      }
      message.success(
        `导入完成：新增 ${added.length} 条${skipped > 0 ? `，跳过 ${skipped} 条` : ''}`,
      );
      setImportPreview({ visible: false, file: null, errors: [], previewAdded: 0, previewSkipped: 0 });
    } catch (e) {
      message.error(e instanceof Error ? e.message : '导入失败');
    } finally {
      setImporting(false);
    }
  };

  const handleCancelImport = () => {
    setImportPreview({ visible: false, file: null, errors: [], previewAdded: 0, previewSkipped: 0 });
  };

  return (
    <>
      <Drawer
        title="我的策略"
        open={visible}
        onClose={handleCloseDrawer}
        width={420}
        extra={
          <Space size={4}>
            <Button
              size="small"
              icon={<UploadOutlined />}
              onClick={handleImportClick}
              data-testid="strategy-import-btn"
            >
              导入
            </Button>
            <Button
              size="small"
              icon={<DownloadOutlined />}
              onClick={handleOpenExportModal}
              disabled={strategies.length === 0}
              data-testid="strategy-export-btn"
            >
              导出{strategies.length > 0 ? `(${strategies.length})` : ''}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/json,.json"
              onChange={handleFileChange}
              style={{ display: 'none' }}
              data-testid="strategy-import-file-input"
            />
          </Space>
        }
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
                      style={{ width: '100%', padding: '4px 8px', border: '1px solid #1677ff', borderRadius: 4, background: '#1E222D', color: '#EAECEF' }}
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

      {/* 导出选择 Modal：勾选要导出的策略 */}
      <Modal
        open={exportModalOpen}
        title="选择要导出的策略"
        onCancel={handleCancelExport}
        destroyOnHidden
        maskClosable={false}
        width={480}
        footer={[
          <Button key="cancel" onClick={handleCancelExport}>取消</Button>,
          <Button
            key="confirm"
            type="primary"
            onClick={handleConfirmExport}
            disabled={exportSelected.length === 0}
            data-testid="strategy-export-confirm"
          >
            导出{exportSelected.length > 0 ? `（${exportSelected.length} 条）` : ''}
          </Button>,
        ]}
        data-testid="strategy-export-modal"
      >
        {/* 全选行 */}
        <div className="flex items-center justify-between py-2 border-b border-border-color mb-2">
          <Checkbox
            checked={exportAllChecked}
            indeterminate={exportIndeterminate}
            onChange={handleToggleSelectAll}
          >
            {exportAllChecked ? '取消全选' : '全选'}
          </Checkbox>
          <span className="text-text-secondary text-xs">
            已选 {exportSelected.length} / {strategies.length}
          </span>
        </div>
        {/* 可滚动的 Checkbox 列表 */}
        <div className="max-h-[320px] overflow-y-auto pr-1">
          <Checkbox.Group
            value={exportSelected}
            onChange={(vals) => setExportSelected(vals as string[])}
            className="w-full"
          >
            <Space direction="vertical" size="small" className="w-full">
              {strategies.map((s) => (
                <Checkbox
                  key={s.id}
                  value={s.id}
                  className="w-full text-text-primary"
                >
                  {s.name}
                </Checkbox>
              ))}
            </Space>
          </Checkbox.Group>
        </div>
      </Modal>

      {/* 导入 Preview 弹窗：确认制导入 */}
      <Modal
        open={importPreview.visible}
        title="导入预览"
        onCancel={handleCancelImport}
        destroyOnHidden
        maskClosable={false}
        width={720}
        footer={[
          <Button key="cancel" onClick={handleCancelImport}>取消</Button>,
          <Button
            key="confirm"
            type="primary"
            loading={importing}
            onClick={handleConfirmImport}
            disabled={!importPreview.file || importPreview.previewAdded === 0}
          >
            确认导入{importPreview.previewAdded > 0 ? `（${importPreview.previewAdded} 条）` : ''}
          </Button>,
        ]}
        data-testid="strategy-import-preview-modal"
      >
        {importPreview.file && (
          <Space direction="vertical" size="middle" className="w-full">
            <div className="text-text-secondary text-sm">
              <div>导出时间：<span className="text-text-primary">{importPreview.file.exportedAt}</span></div>
              <div>
                格式版本：<span className="text-text-primary">v{importPreview.file.version}</span>
              </div>
              <div>包含策略：<span className="text-text-primary">{importPreview.file.strategies.length} 条</span></div>
            </div>

            <Space size="large" className="w-full">
              <div className="flex items-center gap-2">
                <CheckCircleOutlined className="text-color-up" />
                <span>将新增：<strong>{importPreview.previewAdded}</strong> 条</span>
              </div>
              {importPreview.previewSkipped > 0 && (
                <div className="flex items-center gap-2">
                  <WarningOutlined className="text-color-warn" />
                  <span>将跳过：<strong>{importPreview.previewSkipped}</strong> 条</span>
                </div>
              )}
              {importPreview.errors.length > 0 && (
                <div className="flex items-center gap-2">
                  <WarningOutlined className="text-color-down" />
                  <span>错误：<strong>{importPreview.errors.length}</strong> 条</span>
                </div>
              )}
            </Space>

            {importPreview.errors.length > 0 ? (
              <div>
                <Alert type="warning" showIcon message="以下策略将无法导入（按错误类型分组）" className="mb-2" />
                <Table
                  size="small"
                  dataSource={importPreview.errors}
                  columns={[
                    { title: '索引', dataIndex: 'index', key: 'index', width: 80 },
                    {
                      title: '名称',
                      dataIndex: 'name',
                      key: 'name',
                      width: 160,
                      render: (v: string | undefined) => v ?? <span className="text-text-secondary">—</span>,
                    },
                    {
                      title: '错误类型',
                      dataIndex: 'type',
                      key: 'type',
                      width: 160,
                      render: (type: StrategyImportErrorType) => (
                        <Tag color={IMPORT_ERROR_TYPE_META[type].color}>{IMPORT_ERROR_TYPE_META[type].label}</Tag>
                      ),
                    },
                    { title: '说明', dataIndex: 'message', key: 'message' },
                  ]}
                  rowKey={(r: StrategyImportErrorDetail) => `${r.type}-${r.index}`}
                  pagination={false}
                  scroll={{ y: 240 }}
                />
              </div>
            ) : (
              <Alert type="success" showIcon message="全部策略可正常导入" />
            )}
          </Space>
        )}
      </Modal>
    </>
  );
}
