/**
 * ImportExcel.tsx — 券商 Excel 导入
 *
 * 功能：
 * - 选择券商适配器（华泰/中信）
 * - 上传 Excel 文件
 * - 预览解析结果
 * - 确认导入
 */

import React, { useState, useCallback } from 'react';
import {
  Upload, Select, Button, Table, Alert, App, Typography, Divider,
} from 'antd';
import { UploadOutlined, InboxOutlined } from '@ant-design/icons';
import type { BrokerAdapter, ImportParseResult } from '../types';
import { parseImportExcel, confirmImport, fetchBrokerAdapters } from '../api';

const { Dragger } = Upload;
const { Text } = Typography;

const ImportExcel: React.FC = () => {
  const { message } = App.useApp();
  const [brokers, setBrokers] = useState<BrokerAdapter[]>([]);
  const [selectedBroker, setSelectedBroker] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const [parseResult, setParseResult] = useState<ImportParseResult | null>(null);
  const [importing, setImporting] = useState(false);
  const [brokersLoaded, setBrokersLoaded] = useState(false);

  // 加载券商列表
  const loadBrokers = useCallback(async () => {
    if (brokersLoaded) return;
    try {
      const res = await fetchBrokerAdapters();
      if (res.code === 200) {
        setBrokers(res.data);
        setBrokersLoaded(true);
      }
    } catch { /* 后端未就绪 */ }
  }, [brokersLoaded]);

  // 打开面板时加载
  React.useEffect(() => { loadBrokers(); }, [loadBrokers]);

  const handleParse = useCallback(async () => {
    if (!file || !selectedBroker) {
      message.warning('请选择券商和文件');
      return;
    }
    setParsing(true);
    setParseResult(null);
    try {
      const res = await parseImportExcel(file, selectedBroker);
      if (res.code === 200) {
        setParseResult(res.data);
        message.success(`解析完成：${res.data.valid_rows} 条有效，${res.data.error_rows} 条错误`);
      } else {
        message.error(res.message || '解析失败');
      }
    } catch {
      message.error('解析失败，请检查网络连接');
    } finally {
      setParsing(false);
    }
  }, [file, selectedBroker, message]);

  const handleConfirmImport = useCallback(async () => {
    if (!parseResult || parseResult.records.length === 0) {
      message.warning('没有可导入的数据');
      return;
    }
    setImporting(true);
    try {
      const res = await confirmImport(parseResult.records);
      if (res.code === 200) {
        message.success(`成功导入 ${res.data.imported} 条交易记录`);
        setParseResult(null);
        setFile(null);
      } else {
        message.error(res.message || '导入失败');
      }
    } catch {
      message.error('导入失败');
    } finally {
      setImporting(false);
    }
  }, [parseResult, message]);

  const previewColumns = [
    { title: '代码', dataIndex: 'code', key: 'code', width: 80 },
    { title: '名称', dataIndex: 'security_name', key: 'security_name', width: 80 },
    { title: '入场日', dataIndex: 'entry_date', key: 'entry_date', width: 100 },
    { title: '入场价', dataIndex: 'entry_price', key: 'entry_price', width: 80, align: 'right' as const },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 70, align: 'right' as const },
    { title: '方向', dataIndex: 'long_short', key: 'long_short', width: 50,
      render: (v: string) => v === 'long' ? '做多' : '做空' },
  ];

  return (
    <div className="p-4 max-w-3xl">
      <Text className="text-text-primary font-semibold mb-4 block">券商成交单导入</Text>

      {/* 券商选择 */}
      <div className="mb-4">
        <Text className="text-text-secondary text-xs mb-2 block">选择券商模板</Text>
        <Select
          placeholder="选择券商（华泰证券/中信证券）"
          value={selectedBroker || undefined}
          onChange={setSelectedBroker}
          style={{ width: 280 }}
          options={brokers.map((b) => ({ value: b.broker_name, label: b.display_name }))}
        />
      </div>

      {/* 文件上传 */}
      <div className="mb-4">
        <Dragger
          accept=".xlsx,.xls"
          maxCount={1}
          beforeUpload={(f) => {
            // 文件大小校验（≤10MB）
            const maxSize = 10 * 1024 * 1024;
            if (f.size > maxSize) {
              message.error('文件大小不超过 10MB');
              return Upload.LIST_IGNORE;
            }
            // 文件类型校验（检查扩展名和 MIME 类型）
            const ext = f.name.split('.').pop()?.toLowerCase();
            const validExts = ['xlsx', 'xls'];
            if (!ext || !validExts.includes(ext)) {
              message.error('仅支持 .xlsx / .xls 格式的 Excel 文件');
              return Upload.LIST_IGNORE;
            }
            // 检查文件头魔数（xlsx = PK\x03\x04, xls = \xD0\xCF\x11\xE0）
            // 仅读取前 4 字节做快速检查
            return new Promise((resolve) => {
              const reader = new FileReader();
              reader.onload = (e) => {
                const arr = new Uint8Array(e.target!.result as ArrayBuffer);
                const header = Array.from(arr.slice(0, 4)).map(b => b.toString(16)).join('');
                const validHeaders = ['504b0304', 'd0cf11e0'];
                if (validHeaders.includes(header)) {
                  setFile(f);
                  setParseResult(null);
                  resolve(false);
                } else {
                  message.error('文件格式异常，请确认是有效的 Excel 文件');
                  resolve(Upload.LIST_IGNORE);
                }
              };
              reader.onerror = () => {
                message.error('无法读取文件');
                resolve(Upload.LIST_IGNORE);
              };
              reader.readAsArrayBuffer(f.slice(0, 4));
            });
          }}
          onRemove={() => { setFile(null); setParseResult(null); }}
          fileList={file ? [{ uid: '-1', name: file.name, status: 'done' } as never] : []}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="text-text-secondary">点击或拖拽 Excel 文件到此处</p>
          <p className="text-text-secondary text-xs">支持 .xlsx / .xls 格式，最大 10MB</p>
        </Dragger>
      </div>

      <Button
        type="primary"
        icon={<UploadOutlined />}
        onClick={handleParse}
        loading={parsing}
        disabled={!file || !selectedBroker}
      >
        解析文件
      </Button>

      {/* 解析结果 */}
      {parseResult && (
        <div className="mt-4">
          <Divider />
          {parseResult.error_rows > 0 && (
            <Alert
              type="warning"
              message={`${parseResult.error_rows} 行数据解析失败`}
              description={parseResult.errors.slice(0, 5).map((e, i) => (
                <div key={i}>第 {e.row} 行: {e.message}</div>
              ))}
              className="mb-3"
              showIcon
              closable
            />
          )}
          <div className="mb-3">
            <Text>
              共 {parseResult.total_rows} 条，{parseResult.valid_rows} 条有效，{parseResult.error_rows} 条错误
            </Text>
          </div>
          <Table
            columns={previewColumns}
            dataSource={parseResult.records.slice(0, 20).map((r, i) => ({ ...r, key: i }))}
            size="small"
            pagination={false}
            scroll={{ y: 300 }}
            locale={{ emptyText: '无有效数据' }}
          />
          <div className="mt-3">
            <Button
              type="primary"
              onClick={handleConfirmImport}
              loading={importing}
              disabled={parseResult.records.length === 0}
            >
              确认导入 ({parseResult.records.length} 条)
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ImportExcel;