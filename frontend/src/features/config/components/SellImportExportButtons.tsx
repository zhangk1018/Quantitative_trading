/**
 * 卖出策略导入/导出按钮组件（对齐 ImportExportButtons 设计风格）
 *
 * 复用同架构：
 * - 导入：Preview 弹窗确认制（按错误类型分组展示明细）
 * - 导出：选择 Modal 勾选后触发下载
 */

import React, { useRef, useState } from 'react';
import { Button, Modal, Table, Tag, Space, Alert, message, Checkbox } from 'antd';
import {
  DownloadOutlined,
  UploadOutlined,
  CheckCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  exportCustomSellStrategies,
  parseSellStrategyImportFile,
  importCustomSellStrategies,
  computeSellStrategyImportPreview,
  MOCK_USER_ID,
  SellImportErrorType,
  SellImportErrorDetail,
  SellImportResult,
  SellStrategyExportFile,
  SELL_STRATEGY_EXPORT_VERSION,
} from '../../backtest/utils/customSellStrategyStorage';

interface SellImportExportButtonsProps {
  /** 当前卖出策略（用于显示导出数量 + 决定导出按钮可用性） */
  strategies: ReadonlyArray<{ id: string; name: string }>;
  userId?: string;
  /** 导入成功回调 */
  onImportSuccess?: (addedCount: number) => void;
}

const ERROR_TYPE_META: Record<SellImportErrorType, { label: string; color: string }> = {
  name_invalid: { label: '名称格式错误', color: 'red' },
  name_duplicate: { label: '名称重复已跳过', color: 'orange' },
  field_invalid: { label: '字段缺失/类型错误', color: 'volcano' },
  parse_error: { label: '解析失败', color: 'magenta' },
};

interface PreviewState {
  visible: boolean;
  file: SellStrategyExportFile | null;
  errors: SellImportErrorDetail[];
  previewAdded: number;
  previewSkipped: number;
}

const initialPreviewState: PreviewState = {
  visible: false,
  file: null,
  errors: [],
  previewAdded: 0,
  previewSkipped: 0,
};

export const SellImportExportButtons: React.FC<SellImportExportButtonsProps> = ({
  strategies,
  userId = MOCK_USER_ID,
  onImportSuccess,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<PreviewState>(initialPreviewState);
  const [importing, setImporting] = useState(false);

  // 导出选择 Modal 状态
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportSelected, setExportSelected] = useState<string[]>([]);
  const exportAllChecked = exportSelected.length === strategies.length && strategies.length > 0;
  const exportIndeterminate = exportSelected.length > 0 && !exportAllChecked;

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

  // 真正执行导出
  const doExport = (ids: string[]) => {
    const data = exportCustomSellStrategies(userId, ids);
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const today = new Date().toISOString().slice(0, 10);
    const filename = `custom-sell-strategies-${today}.json`;

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    message.success(`已导出 ${data.strategies.length} 条卖出策略到 ${filename}`);
  };

  const handleConfirmExport = () => {
    if (exportSelected.length === 0) {
      message.warning('请至少选择 1 条策略');
      return;
    }
    doExport(exportSelected);
    handleCancelExport();
  };

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
    let parsed: SellStrategyExportFile;
    try {
      parsed = parseSellStrategyImportFile(text);
    } catch (e) {
      message.error((e as Error).message);
      return;
    }

    const previewResult = computeSellStrategyImportPreview(parsed, userId);
    setPreview({
      visible: true,
      file: parsed,
      errors: previewResult.errors,
      previewAdded: previewResult.added,
      previewSkipped: previewResult.skipped,
    });
  };

  const handleConfirmImport = () => {
    if (!preview.file) return;
    setImporting(true);
    try {
      const result: SellImportResult = importCustomSellStrategies(preview.file, userId);
      onImportSuccess?.(result.added);
      message.success(
        `导入完成：新增 ${result.added} 条，跳过 ${result.skipped} 条，错误 ${result.errors.length} 条`,
      );
      setPreview(initialPreviewState);
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setImporting(false);
    }
  };

  const handleCancelImport = () => setPreview(initialPreviewState);

  const exportDisabled = strategies.length === 0;

  const errorColumns = [
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
      render: (type: SellImportErrorType) => (
        <Tag color={ERROR_TYPE_META[type].color}>{ERROR_TYPE_META[type].label}</Tag>
      ),
    },
    { title: '说明', dataIndex: 'message', key: 'message' },
  ];

  return (
    <>
      <div className="flex items-center gap-2" data-testid="sell-import-export-buttons">
        <Button
          size="small"
          icon={<UploadOutlined />}
          onClick={handleImportClick}
          data-testid="sell-import-export-import-btn"
        >
          导入
        </Button>
        <Button
          size="small"
          icon={<DownloadOutlined />}
          onClick={handleOpenExportModal}
          disabled={exportDisabled}
          data-testid="sell-import-export-export-btn"
        >
          导出{strategies.length > 0 ? `(${strategies.length})` : ''}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          onChange={handleFileChange}
          style={{ display: 'none' }}
          data-testid="sell-import-export-file-input"
        />
      </div>

      {/* 导入 Preview 弹窗 */}
      <Modal
        open={preview.visible}
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
            disabled={!preview.file}
          >
            确认导入{preview.previewAdded > 0 ? `（${preview.previewAdded} 条）` : ''}
          </Button>,
        ]}
        data-testid="sell-import-preview-modal"
      >
        {preview.file && (
          <Space direction="vertical" size="middle" className="w-full">
            <div className="text-text-secondary text-sm">
              <div>导出时间：<span className="text-text-primary">{preview.file.exportedAt}</span></div>
              <div>来源用户：<span className="text-text-primary">{preview.file.userId}</span></div>
              <div>
                格式版本：<span className="text-text-primary">v{preview.file.version}</span>
                （当前 v{SELL_STRATEGY_EXPORT_VERSION}）
              </div>
              <div>包含策略：<span className="text-text-primary">{preview.file.strategies.length} 条</span></div>
            </div>

            <Space size="large" className="w-full">
              <div className="flex items-center gap-2">
                <CheckCircleOutlined className="text-color-up" />
                <span>将新增：<strong>{preview.previewAdded}</strong> 条</span>
              </div>
              <div className="flex items-center gap-2">
                <WarningOutlined className="text-color-warn" />
                <span>将跳过：<strong>{preview.previewSkipped}</strong> 条</span>
              </div>
              <div className="flex items-center gap-2">
                <WarningOutlined className="text-color-down" />
                <span>错误：<strong>{preview.errors.length}</strong> 条</span>
              </div>
            </Space>

            {preview.errors.length > 0 ? (
              <div>
                <Alert type="warning" showIcon message="以下策略将无法导入（按错误类型分组）" className="mb-2" />
                <Table
                  size="small"
                  dataSource={preview.errors}
                  columns={errorColumns}
                  rowKey={(r) => `${r.type}-${r.index}`}
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

      {/* 导出选择 Modal：勾选要导出的条目 */}
      <Modal
        open={exportModalOpen}
        title="选择要导出的卖出策略"
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
            data-testid="sell-import-export-export-confirm"
          >
            导出{exportSelected.length > 0 ? `（${exportSelected.length} 条）` : ''}
          </Button>,
        ]}
        data-testid="sell-import-export-export-modal"
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
    </>
  );
};

export default SellImportExportButtons;
