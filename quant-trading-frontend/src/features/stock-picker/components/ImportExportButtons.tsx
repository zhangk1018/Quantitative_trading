/**
 * 自编指标导入/导出按钮组件（P3.2）
 *
 * 设计要点（K 2026-06-17 决策）：
 * - 导入流程：Preview 弹窗确认制（按错误类型分组展示明细）
 *   1) 触发隐藏 file input 选择 .json
 *   2) FileReader 读取为文本
 *   3) parseImportFile 校验：file-level 错误（版本/格式）→ 直接 alert
 *   4) 进入 Preview 弹窗：显示新增/跳过/错误统计 + 错误明细（按 type 分组）
 *   5) 用户点击"确认导入" → importCustomIndicators 写入 + dispatch
 * - 导出流程：调用 exportCustomIndicators → Blob URL → 触发下载
 *   文件名格式：custom-indicators-YYYY-MM-DD.json
 *
 * 复用约束：
 * - 不修改 customIndicatorStorage.ts（K 决策：导入导出 API 已落地 P1.2）
 * - 不修改 types/customIndicator.ts（K 决策：IndicatorExportFile + ImportResult 已落地）
 * - 仅消费既有 API，新增 UI 层
 */

import React, { useRef, useState } from 'react';
import { Button, Modal, Table, Tag, Space, Alert, message } from 'antd';
import {
  DownloadOutlined,
  UploadOutlined,
  CheckCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  exportCustomIndicators,
  parseImportFile,
  importCustomIndicators,
  MOCK_USER_ID,
  ImportErrorType,
  ImportErrorDetail,
} from '../utils/customIndicatorStorage';
import { IndicatorExportFile, EXPORT_FORMAT_VERSION } from '../types/customIndicator';

interface ImportExportButtonsProps {
  /** 当前 customIndicators（用于显示导出数量 + 决定导出按钮可用性） */
  customIndicators: ReadonlyArray<{ id: string; name: string }>;
  /** 当前 user_id（V1.0 mock） */
  userId?: string;
  /** 导入成功回调：父组件 dispatch IMPORT_CUSTOM_INDICATORS */
  onImportSuccess: (indicators: IndicatorExportFile['indicators']) => void;
}

// 错误类型 → 中文标签 + Tag 颜色（K 偏好：明确显示覆盖率异常及原因）
const ERROR_TYPE_META: Record<ImportErrorType, { label: string; color: string }> = {
  name_invalid: { label: '名称格式错误', color: 'red' },
  name_duplicate: { label: '名称重复已跳过', color: 'orange' },
  field_invalid: { label: '字段缺失/类型错误', color: 'volcano' },
  parse_error: { label: '解析失败', color: 'magenta' },
};

interface PreviewState {
  visible: boolean;
  file: IndicatorExportFile | null;
  /** 预览阶段的错误明细（parseImportFile 抛错时为空） */
  errors: ImportErrorDetail[];
  /** 解析后预计的 added/skipped（由 parseImportFile 给出） */
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

export const ImportExportButtons: React.FC<ImportExportButtonsProps> = ({
  customIndicators,
  userId = MOCK_USER_ID,
  onImportSuccess,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<PreviewState>(initialPreviewState);
  const [importing, setImporting] = useState(false);

  /**
   * 触发文件选择对话框
   */
  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  /**
   * 文件选择后处理：
   * 1) FileReader 读取文本
   * 2) parseImportFile 校验 → file-level 错误则 alert 不进入预览
   * 3) 计算预计 added/skipped（基于 name 去重），构造预览数据
   */
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // 重置 input value 允许重复选择同一文件
    if (e.target) e.target.value = '';
    if (!file) return;

    // 文件大小硬限制：5MB（localStorage 同等限制）
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
    reader.onerror = () => {
      message.error('文件读取失败');
    };
    reader.readAsText(file);
  };

  /**
   * 解析导入文本：file-level 错误弹错；否则进入 Preview 弹窗
   */
  const processImportText = (text: string) => {
    let parsed: IndicatorExportFile;
    try {
      parsed = parseImportFile(text);
    } catch (e) {
      // file-level 错误：版本不支持 / 格式无效 / indicators 非数组
      message.error((e as Error).message);
      return;
    }

    // 计算预览阶段的 added/skipped/errors（不实际写入）
    const existingNames = new Set(customIndicators.map((i) => i.name));
    let previewAdded = 0;
    let previewSkipped = 0;
    const errors: ImportErrorDetail[] = [];

    parsed.indicators.forEach((ind, index) => {
      // 字段缺失/类型错误
      if (typeof ind !== 'object' || ind === null) {
        errors.push({
          type: 'field_invalid',
          index,
          message: '指标不是对象',
        });
        return;
      }
      if (!ind.name || typeof ind.name !== 'string') {
        errors.push({
          type: 'field_invalid',
          index,
          message: '字段 name 缺失或类型错误',
        });
        return;
      }
      if (existingNames.has(ind.name)) {
        errors.push({
          type: 'name_duplicate',
          name: ind.name,
          index,
          message: `指标名称"${ind.name}"已存在，已跳过`,
        });
        previewSkipped += 1;
      } else {
        previewAdded += 1;
      }
    });

    setPreview({
      visible: true,
      file: parsed,
      errors,
      previewAdded,
      previewSkipped,
    });
  };

  /**
   * 确认导入：写入 localStorage + 通知父组件 dispatch
   */
  const handleConfirmImport = () => {
    if (!preview.file) return;
    setImporting(true);
    try {
      const result = importCustomIndicators(preview.file, userId);
      // 从写入后的 storage 取出实际新增的指标（带新 id/createdAt/updatedAt）
      // K 决策：使用 listCustomIndicators 按 updatedAt 倒序取最新 N 条
      // 但 IMPORT_CUSTOM_INDICATORS reducer 按 id 去重，需要"新写入"的子集
      // 简单实现：取 result.added 条最新的即可
      const allAfter = (window.localStorage.getItem(`qt_custom_indicators_v1_${userId}`) ?? '[]');
      let stored: IndicatorExportFile['indicators'] = [];
      try {
        stored = JSON.parse(allAfter);
      } catch {
        stored = [];
      }
      // 按 updatedAt 倒序
      stored.sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
      // 取前 result.added 条（即刚导入的）
      const newlyAdded = stored.slice(0, result.added);

      onImportSuccess(newlyAdded);
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

  /**
   * 取消导入
   */
  const handleCancelImport = () => {
    setPreview(initialPreviewState);
  };

  /**
   * 导出为 JSON 文件
   */
  const handleExport = () => {
    const data = exportCustomIndicators(userId);
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const today = new Date().toISOString().slice(0, 10);
    const filename = `custom-indicators-${today}.json`;

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    message.success(`已导出 ${data.indicators.length} 条自编指标到 ${filename}`);
  };

  const exportDisabled = customIndicators.length === 0;

  // 错误明细表格列
  const errorColumns = [
    {
      title: '索引',
      dataIndex: 'index',
      key: 'index',
      width: 80,
    },
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
      render: (type: ImportErrorType) => (
        <Tag color={ERROR_TYPE_META[type].color}>{ERROR_TYPE_META[type].label}</Tag>
      ),
    },
    {
      title: '说明',
      dataIndex: 'message',
      key: 'message',
    },
  ];

  return (
    <>
      <div className="flex items-center gap-2" data-testid="import-export-buttons">
        <Button
          size="small"
          icon={<UploadOutlined />}
          onClick={handleImportClick}
          data-testid="import-export-import-btn"
        >
          导入
        </Button>
        <Button
          size="small"
          icon={<DownloadOutlined />}
          onClick={handleExport}
          disabled={exportDisabled}
          data-testid="import-export-export-btn"
        >
          导出{customIndicators.length > 0 ? `(${customIndicators.length})` : ''}
        </Button>
        {/* 隐藏的 file input：accept 限定 .json 避免用户选错文件 */}
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          onChange={handleFileChange}
          style={{ display: 'none' }}
          data-testid="import-export-file-input"
        />
      </div>

      {/* Preview 弹窗：按错误类型分组展示明细 */}
      <Modal
        open={preview.visible}
        title="导入预览"
        onCancel={handleCancelImport}
        destroyOnHidden
        maskClosable={false}
        width={720}
        footer={[
          <Button
            key="cancel"
            onClick={handleCancelImport}
            data-testid="import-export-preview-cancel"
          >
            取消
          </Button>,
          <Button
            key="confirm"
            type="primary"
            loading={importing}
            onClick={handleConfirmImport}
            disabled={!preview.file}
            data-testid="import-export-preview-confirm"
          >
            确认导入{preview.previewAdded > 0 ? `（${preview.previewAdded} 条）` : ''}
          </Button>,
        ]}
        data-testid="import-export-preview-modal"
      >
        {preview.file && (
          <Space direction="vertical" size="middle" className="w-full">
            {/* 文件元信息 */}
            <div className="text-text-secondary text-sm">
              <div>
                导出时间：<span className="text-text-primary">{preview.file.exportedAt}</span>
              </div>
              <div>
                来源用户：<span className="text-text-primary">{preview.file.userId}</span>
              </div>
              <div>
                格式版本：<span className="text-text-primary">v{preview.file.version}</span>
                （当前 v{EXPORT_FORMAT_VERSION}）
              </div>
              <div>
                包含指标：<span className="text-text-primary">{preview.file.indicators.length} 条</span>
              </div>
            </div>

            {/* 预计结果统计 */}
            <Space size="large" className="w-full">
              <div className="flex items-center gap-2" data-testid="import-export-preview-added">
                <CheckCircleOutlined className="text-color-up" />
                <span>将新增：<strong>{preview.previewAdded}</strong> 条</span>
              </div>
              <div className="flex items-center gap-2" data-testid="import-export-preview-skipped">
                <WarningOutlined className="text-color-warn" />
                <span>将跳过：<strong>{preview.previewSkipped}</strong> 条</span>
              </div>
              <div className="flex items-center gap-2" data-testid="import-export-preview-errors">
                <WarningOutlined className="text-color-down" />
                <span>错误：<strong>{preview.errors.length}</strong> 条</span>
              </div>
            </Space>

            {/* 错误明细（按类型分组） */}
            {preview.errors.length > 0 ? (
              <div>
                <Alert
                  type="warning"
                  showIcon
                  message="以下指标将无法导入（按错误类型分组）"
                  className="mb-2"
                />
                <Table
                  size="small"
                  dataSource={preview.errors}
                  columns={errorColumns}
                  rowKey={(r) => `${r.type}-${r.index}`}
                  pagination={false}
                  scroll={{ y: 240 }}
                  data-testid="import-export-preview-errors-table"
                />
              </div>
            ) : (
              <Alert type="success" showIcon message="全部指标可正常导入" />
            )}
          </Space>
        )}
      </Modal>
    </>
  );
};

export default ImportExportButtons;
