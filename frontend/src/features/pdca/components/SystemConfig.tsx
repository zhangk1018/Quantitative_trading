/**
 * SystemConfig.tsx — 系统配置页面
 *
 * 功能：
 * - 展示/编辑系统配置（2%/6% 风控阈值等）
 * - 数据导出 Excel（使用通用下载工具）
 * - 全量备份下载（使用通用下载工具）
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  InputNumber, Button, Divider, App, Space, Typography, Empty, Card, Switch, Skeleton, Input, Modal,
} from 'antd';
import { ExportOutlined, DownloadOutlined, SaveOutlined } from '@ant-design/icons';
import type { SystemConfigItem } from '../types';
import { fetchConfig, updateConfig, exportRecords, backupDatabase, downloadExcel, downloadBackup } from '../api';

const { Text, Title } = Typography;

const SystemConfig: React.FC = () => {
  const { message } = App.useApp();
  const [configs, setConfigs] = useState<SystemConfigItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [backingUp, setBackingUp] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [modifyReason, setModifyReason] = useState('');
  const [reasonModalVisible, setReasonModalVisible] = useState(false);
  const [pendingSave, setPendingSave] = useState<{
    configKey: string;
    numericValue: number | null;
    boolValue: boolean | null;
  } | null>(null);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchConfig();
      if (res.code === 200) setConfigs(Array.isArray(res.data) ? res.data : (res.data?.items || []));
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载配置失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => { loadConfig(); }, [loadConfig]);

  // 打开修改原因弹窗，收集用户输入后再保存
  const handleSaveRequest = useCallback((configKey: string, numericValue: number | null, boolValue: boolean | null) => {
    setPendingSave({ configKey, numericValue, boolValue });
    setModifyReason('');
    setReasonModalVisible(true);
  }, []);

  // 确认保存（带修改原因）
  const handleConfirmSave = useCallback(async () => {
    if (!pendingSave) return;
    const { configKey, numericValue, boolValue } = pendingSave;
    const reason = modifyReason.trim() || '用户手动修改';
    setSaving(true);
    setSavingKey(configKey);
    setReasonModalVisible(false);
    try {
      const res = await updateConfig(configKey, {
        numeric_value: numericValue ?? undefined,
        bool_value: boolValue ?? undefined,
        modify_reason: reason,
      });
      if (res.code === 200) {
        message.success('配置已保存');
        loadConfig();
      } else {
        message.error(res.message || '保存失败');
      }
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message);
      } else {
        message.error('保存失败，请检查网络连接');
      }
    } finally {
      setSaving(false);
      setSavingKey(null);
      setPendingSave(null);
    }
  }, [pendingSave, modifyReason, message, loadConfig]);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      await downloadExcel(exportRecords(), '交易台账');
      message.success('导出成功');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '导出失败');
    } finally {
      setExporting(false);
    }
  }, [message]);

  const handleBackup = useCallback(async () => {
    setBackingUp(true);
    try {
      await downloadBackup(backupDatabase());
      message.success('备份下载成功');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '备份失败');
    } finally {
      setBackingUp(false);
    }
  }, [message]);

  const getConfig = (key: string): SystemConfigItem | undefined =>
    configs.find((c) => c.config_key === key);

  const riskPerTrade = getConfig('risk_per_trade');
  const riskPerMonth = getConfig('risk_per_month');
  const maxPositionCount = getConfig('max_position_count');
  const stopLossHardLimit = getConfig('stop_loss_hard_limit');
  const autoScoreEnabled = getConfig('auto_score_enabled');

  return (
    <div className="p-4 max-w-2xl">
      <Title level={5} className="text-text-primary mb-4">系统配置</Title>

      {loading ? (
        <div className="p-4">
          <Skeleton active paragraph={{ rows: 6 }} />
        </div>
      ) : configs.length === 0 ? (
        <Empty description="暂无配置数据" />
      ) : (
        <div className="space-y-4">
          {/* 风控配置 */}
          <Card title="风控参数" size="small" className="bg-bg-panel">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <Text className="text-text-primary">单笔风险上限</Text>
                  <Text className="text-text-secondary text-xs ml-2">（占账户总资产百分比）</Text>
                </div>
                <Space>
                  <InputNumber
                    value={riskPerTrade?.numeric_value ?? 2}
                    min={0.1}
                    max={10}
                    step={0.1}
                    precision={1}
                    style={{ width: 80 }}
                    suffix="%"
                  />
                  <Button
                    type="primary"
                    size="small"
                    icon={<SaveOutlined />}
                    loading={saving && savingKey === 'risk_per_trade'}
                    onClick={() => handleSaveRequest('risk_per_trade', riskPerTrade?.numeric_value ?? 2, null)}
                  >
                    保存
                  </Button>
                </Space>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Text className="text-text-primary">月度总风险上限</Text>
                  <Text className="text-text-secondary text-xs ml-2">（含未平仓浮动亏损，占月初总资产百分比）</Text>
                </div>
                <Space>
                  <InputNumber
                    value={riskPerMonth?.numeric_value ?? 6}
                    min={0.1}
                    max={20}
                    step={0.1}
                    precision={1}
                    style={{ width: 80 }}
                    suffix="%"
                  />
                  <Button
                    type="primary"
                    size="small"
                    icon={<SaveOutlined />}
                    loading={saving && savingKey === 'risk_per_month'}
                    onClick={() => handleSaveRequest('risk_per_month', riskPerMonth?.numeric_value ?? 6, null)}
                  >
                    保存
                  </Button>
                </Space>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Text className="text-text-primary">最大同时持仓数</Text>
                </div>
                <Space>
                  <InputNumber
                    value={maxPositionCount?.numeric_value ?? 5}
                    min={1}
                    max={20}
                    step={1}
                    precision={0}
                    style={{ width: 80 }}
                  />
                  <Button
                    type="primary"
                    size="small"
                    icon={<SaveOutlined />}
                    loading={saving && savingKey === 'max_position_count'}
                    onClick={() => handleSaveRequest('max_position_count', maxPositionCount?.numeric_value ?? 5, null)}
                  >
                    保存
                  </Button>
                </Space>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Text className="text-text-primary">硬止损线</Text>
                  <Text className="text-text-secondary text-xs ml-2">（亏损超过此比例强制平仓提醒）</Text>
                </div>
                <Space>
                  <InputNumber
                    value={stopLossHardLimit?.numeric_value ?? 8}
                    min={1}
                    max={50}
                    step={0.5}
                    precision={1}
                    style={{ width: 80 }}
                    suffix="%"
                  />
                  <Button
                    type="primary"
                    size="small"
                    icon={<SaveOutlined />}
                    loading={saving && savingKey === 'stop_loss_hard_limit'}
                    onClick={() => handleSaveRequest('stop_loss_hard_limit', stopLossHardLimit?.numeric_value ?? 8, null)}
                  >
                    保存
                  </Button>
                </Space>
              </div>
            </div>
          </Card>

          {/* 其他配置 */}
          <Card title="其他设置" size="small" className="bg-bg-panel">
            <div className="flex items-center justify-between">
              <div>
                <Text className="text-text-primary">自动打分</Text>
                <Text className="text-text-secondary text-xs ml-2">（三期功能，开启后系统自动计算进场/出场/总得分）</Text>
              </div>
              <Switch
                checked={autoScoreEnabled?.bool_value ?? false}
                onChange={(checked) => handleSaveRequest('auto_score_enabled', null, checked)}
                loading={saving && savingKey === 'auto_score_enabled'}
              />
            </div>
          </Card>
        </div>
      )}

      <Divider />

      {/* 数据导出 & 备份 */}
      <Title level={5} className="text-text-primary mb-4">数据管理</Title>
      <div className="flex gap-3">
        <Button
          icon={<ExportOutlined />}
          onClick={handleExport}
          loading={exporting}
        >
          导出台账为 Excel
        </Button>
        <Button
          icon={<DownloadOutlined />}
          onClick={handleBackup}
          loading={backingUp}
        >
          全量备份下载
        </Button>
      </div>
      <Text className="text-text-secondary text-xs mt-2 block">
        导出的 Excel 文件首行包含免责声明。备份文件为 SQL 格式，仅包含 pdca schema 数据。
      </Text>

      {/* 修改原因弹窗 */}
      <Modal
        title="修改原因"
        open={reasonModalVisible}
        onOk={handleConfirmSave}
        onCancel={() => { setReasonModalVisible(false); setPendingSave(null); }}
        okText="确认保存"
        cancelText="取消"
        confirmLoading={saving}
      >
        <div className="py-2">
          <Text className="text-text-secondary text-xs mb-2 block">
            请说明修改配置的原因（可选，用于审计追溯）
          </Text>
          <Input
            placeholder="如：调整风控参数以适应市场波动"
            value={modifyReason}
            onChange={(e) => setModifyReason(e.target.value)}
            maxLength={200}
            showCount
          />
        </div>
      </Modal>
    </div>
  );
};

export default SystemConfig;