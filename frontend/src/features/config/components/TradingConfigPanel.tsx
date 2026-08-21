/**
 * TradingConfigPanel.tsx — 交易设置面板
 *
 * 功能：
 * - 风控参数设置（单笔/月度风险上限、最大持仓总资金、硬止损线）
 * - 其他交易相关设置（自动打分开关）
 * - 数据保存带版本管理和修改原因追溯
 *
 * 迁移来源：PDCA SystemConfig（2026-08-12 迁移）
 * 保留风控参数 + 其他设置，移除数据管理（导出/备份）功能
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  InputNumber, Button, App, Space, Typography, Card, Switch, Input, Modal,
} from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import { fetchConfig, updateConfig } from '@/features/pdca/api';
import type { SystemConfigItem } from '@/features/pdca/types';

const { Text } = Typography;

/** 默认风控参数值（数据库无记录时使用） */
const DEFAULTS = {
  risk_per_trade: 2,      // 单笔风险总资金 2%
  risk_per_month: 6,      // 月度风险总资金 6%
  max_position_funds: 80, // 最大持仓总资金 80%
  stop_loss_hard_limit: 8, // 硬止损线总资金 8%
} as const;

const TradingConfigPanel: React.FC = () => {
  const { message } = App.useApp();
  const [configs, setConfigs] = useState<SystemConfigItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [modifyReason, setModifyReason] = useState('');
  const [reasonModalVisible, setReasonModalVisible] = useState(false);
  const [pendingSave, setPendingSave] = useState<{
    configKey: string;
    numericValue: number | null;
    boolValue: boolean | null;
  } | null>(null);

  // 本地编辑值（InputNumber 无 onChange 时保存按钮会提交原始值，导致修改无效）
  const [riskPerTradeValue, setRiskPerTradeValue] = useState<number | null>(null);
  const [riskPerMonthValue, setRiskPerMonthValue] = useState<number | null>(null);
  const [maxPositionFundsValue, setMaxPositionFundsValue] = useState<number | null>(null);
  const [stopLossHardLimitValue, setStopLossHardLimitValue] = useState<number | null>(null);

  const loadConfig = useCallback(async () => {
    try {
      const items = await fetchConfig();
      setConfigs(items);
      // 同步本地编辑值（数据库存储 0.02=2% → 前端显示 2）
      const getNum = (key: string) => {
        const val = items.find((c: { config_key: string }) => c.config_key === key)?.numeric_value ?? null;
        return val !== null ? val * 100 : null;
      };
      setRiskPerTradeValue(getNum('risk_per_trade'));
      setRiskPerMonthValue(getNum('risk_per_month'));
      setMaxPositionFundsValue(getNum('max_position_funds'));
      setStopLossHardLimitValue(getNum('stop_loss_hard_limit'));
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载配置失败');
    }
  }, [message]);

  useEffect(() => { loadConfig(); }, [loadConfig]);

  const handleSaveRequest = useCallback((configKey: string, numericValue: number | null, boolValue: boolean | null) => {
    setPendingSave({ configKey, numericValue, boolValue });
    setModifyReason('');
    setReasonModalVisible(true);
  }, []);

  const handleConfirmSave = useCallback(async () => {
    if (!pendingSave) return;
    const { configKey, numericValue, boolValue } = pendingSave;
    const reason = modifyReason.trim() || '用户手动修改';
    setSaving(true);
    setSavingKey(configKey);
    setReasonModalVisible(false);
    try {
      await updateConfig(configKey, {
        numeric_value: numericValue ?? undefined,
        bool_value: boolValue ?? undefined,
        modify_reason: reason,
      });
      message.success('配置已保存');
      loadConfig();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败，请检查网络连接');
    } finally {
      setSaving(false);
      setSavingKey(null);
      setPendingSave(null);
    }
  }, [pendingSave, modifyReason, message, loadConfig]);

  const getConfig = (key: string): SystemConfigItem | undefined =>
    configs.find((c) => c.config_key === key);

  const autoScoreEnabled = getConfig('auto_score_enabled');

  return (
    <div className="space-y-4">
      {/* 风控参数 */}
      <Card title="风控参数" size="small" className="bg-bg-panel">
        <div className="space-y-3">
          {/* 单笔风险总资金 */}
          <div className="flex items-center justify-between">
            <div>
              <Text className="text-text-primary">单笔风险总资金</Text>
              <Text className="text-text-secondary text-xs ml-2">（占账户总资产百分比）</Text>
            </div>
            <Space>
              <InputNumber
                value={riskPerTradeValue ?? DEFAULTS.risk_per_trade}
                onChange={(v) => setRiskPerTradeValue(v)}
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
                onClick={() => handleSaveRequest('risk_per_trade', (riskPerTradeValue ?? DEFAULTS.risk_per_trade) / 100, null)}
              >
                保存
              </Button>
            </Space>
          </div>

          {/* 月度风险总资金 */}
          <div className="flex items-center justify-between">
            <div>
              <Text className="text-text-primary">月度风险总资金</Text>
              <Text className="text-text-secondary text-xs ml-2">（含未平仓浮动亏损，占月初总资产百分比）</Text>
            </div>
            <Space>
              <InputNumber
                value={riskPerMonthValue ?? DEFAULTS.risk_per_month}
                onChange={(v) => setRiskPerMonthValue(v)}
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
                onClick={() => handleSaveRequest('risk_per_month', (riskPerMonthValue ?? DEFAULTS.risk_per_month) / 100, null)}
              >
                保存
              </Button>
            </Space>
          </div>

          {/* 最大持仓总资金 */}
          <div className="flex items-center justify-between">
            <div>
              <Text className="text-text-primary">最大持仓总资金</Text>
              <Text className="text-text-secondary text-xs ml-2">（占账户总资产百分比）</Text>
            </div>
            <Space>
              <InputNumber
                value={maxPositionFundsValue ?? DEFAULTS.max_position_funds}
                onChange={(v) => setMaxPositionFundsValue(v)}
                min={10}
                max={100}
                step={5}
                precision={0}
                style={{ width: 80 }}
                suffix="%"
              />
              <Button
                type="primary"
                size="small"
                icon={<SaveOutlined />}
                loading={saving && savingKey === 'max_position_funds'}
                onClick={() => handleSaveRequest('max_position_funds', (maxPositionFundsValue ?? DEFAULTS.max_position_funds) / 100, null)}
              >
                保存
              </Button>
            </Space>
          </div>

          {/* 硬止损线 */}
          <div className="flex items-center justify-between">
            <div>
              <Text className="text-text-primary">硬止损线</Text>
              <Text className="text-text-secondary text-xs ml-2">（总资产亏损超过此比例强制平仓提醒）</Text>
            </div>
            <Space>
              <InputNumber
                value={stopLossHardLimitValue ?? DEFAULTS.stop_loss_hard_limit}
                onChange={(v) => setStopLossHardLimitValue(v)}
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
                onClick={() => handleSaveRequest('stop_loss_hard_limit', (stopLossHardLimitValue ?? DEFAULTS.stop_loss_hard_limit) / 100, null)}
              >
                保存
              </Button>
            </Space>
          </div>
        </div>
      </Card>

      {/* 其他设置 */}
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

export default TradingConfigPanel;