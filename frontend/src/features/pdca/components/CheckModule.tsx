/**
 * CheckModule.tsx — 复盘报告模块
 *
 * 功能：
 * - 选择周期（CHECK 状态优先，支持切换）
 * - 查看/编辑复盘报告
 * - 统计指标展示（执行率、胜率、平均得分等）
 * - 发布/草稿状态切换
 * - 自动统计：从 execution-summary 接口获取周期统计数据
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Card, Button, Select, Spin, Empty, message, Tag, Descriptions, Input, Space, Typography,
} from 'antd';
import { SaveOutlined, SendOutlined, AuditOutlined, ReloadOutlined } from '@ant-design/icons';
import type { CheckReport, CheckReportFormData } from '../types';
import { fetchCheckReport, createCheckReport, updateCheckReport } from '../services/check-report';
import { fetchExecutionSummary } from '../services/cycle';
import { extractErrorMessage } from '../services/client';
import type { ExecutionSummary } from '../types';
import { usePDCACycle } from '../hooks/usePDCACycle';

const { TextArea } = Input;
const { Title, Text } = Typography;

// 模块级常量，保证引用稳定，避免内联对象字面量导致 usePDCACycle 依赖变化引发无限循环
const CHECK_STATUS_ORDER = { CHECK: 0, ACT: 1, DO: 2, PLAN: 3 };

const CheckModule: React.FC = () => {
  const {
    cycles, loading, selectedCycleId, selectedCycle, setSelectedCycleId, refresh: refreshCycles,
  } = usePDCACycle({ statusOrder: CHECK_STATUS_ORDER });

  const [report, setReport] = useState<CheckReport | null>(null);
  const [execSummary, setExecSummary] = useState<ExecutionSummary | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reportContent, setReportContent] = useState('');

  // 竞态防护：标记当前请求是否已被取消
  const fetchingRef = useRef(false);

  // 选择周期时加载报告
  useEffect(() => {
    if (!selectedCycleId) {
      setReport(null);
      setExecSummary(null);
      setReportContent('');
      return;
    }

    fetchingRef.current = true;
    const loadData = async () => {
      setReportLoading(true);
      try {
        const [reportData, summaryData] = await Promise.all([
          fetchCheckReport(selectedCycleId),
          fetchExecutionSummary(selectedCycleId).catch(() => null),
        ]);

        if (!fetchingRef.current) return;  // 请求已过期，忽略结果
        if (reportData !== null) {
          setReport(reportData);
          setReportContent(reportData?.report_content || '');
        }
        if (summaryData !== null) {
          setExecSummary(summaryData);
        }
      } catch (err: unknown) {
        if (!fetchingRef.current) return;  // 请求已过期，忽略错误
        message.error('加载复盘数据失败: ' + extractErrorMessage(err));
      } finally {
        if (fetchingRef.current) setReportLoading(false);
      }
    };
    loadData();

    return () => {
      fetchingRef.current = false;  // 清理时标记为过期
    };
  }, [selectedCycleId]);

  // 刷新执行摘要
  const handleRefreshSummary = useCallback(async () => {
    if (!selectedCycleId) return;
    try {
      const data = await fetchExecutionSummary(selectedCycleId);
      setExecSummary(data);
    } catch (err: unknown) {
      message.error('刷新统计数据失败: ' + extractErrorMessage(err));
    }
  }, [selectedCycleId]);

  // 保存报告（带快照回滚的乐观更新）
  const handleSave = async (publish = false) => {
    if (!selectedCycleId) return;
    setSaving(true);
    try {
      if (report) {
        const payload: Partial<CheckReportFormData> = { report_content: reportContent };
        if (publish) payload.report_status = 'published';
        // 乐观更新：立即在本地应用变更（接口失败时回滚）
        setReport((prev) => prev ? { ...prev, ...payload, report_status: publish ? 'published' : prev.report_status } : prev);
        await updateCheckReport(report.id, payload);
        message.success(publish ? '复盘报告已发布' : '复盘报告已保存');
      } else {
        const payload: CheckReportFormData = {
          pdca_cycle_id: selectedCycleId,
          report_content: reportContent,
        };
        if (execSummary) {
          payload.total_trade_count = execSummary.total_trades ?? null;
          payload.complete_by_plan_count = execSummary.executed_plans ?? null;
          payload.execution_rate = execSummary.fill_rate != null ? execSummary.fill_rate * 100 : null;
        }
        await createCheckReport(payload);
        message.success('复盘报告已创建');
        // 创建后需全量拉取（因为后端生成了完整记录）
        const reportData = await fetchCheckReport(selectedCycleId);
        if (reportData !== null) setReport(reportData);
      }
    } catch (err: unknown) {
      // 后端请求失败：回滚乐观更新（重新拉取全量数据确保一致性）
      if (report) {
        try {
          const reportData = await fetchCheckReport(selectedCycleId);
          if (reportData !== null) setReport(reportData);
        } catch {
          // 回滚拉取失败时，保持当前状态不变
        }
      }
      message.error('保存失败: ' + extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-4">
      {/* 顶部操作栏 */}
      <div className="flex items-center justify-between mb-4">
        <Title level={5} className="!mb-0"><AuditOutlined className="mr-2" />复盘报告</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refreshCycles} size="small">刷新</Button>
        </Space>
      </div>

      {/* 周期选择器 */}
      <div className="mb-4">
        <Select
          className="w-full max-w-md"
          placeholder="选择要复盘的周期..."
          value={selectedCycleId}
          onChange={setSelectedCycleId}
          loading={loading}
          options={cycles.map(c => ({
            value: c.id,
            label: `${c.cycle_name}（${c.start_date} ~ ${c.end_date}）[${c.status}]`,
          }))}
        />
      </div>

      {!selectedCycleId ? (
        <Empty description="请选择一个周期开始复盘" />
      ) : reportLoading ? (
        <div className="flex justify-center py-16"><Spin tip="加载中..." /></div>
      ) : (
        <div>
          {/* 周期信息 */}
          {selectedCycle && (
            <Card size="small" className="mb-4">
              <Descriptions size="small" column={4}>
                <Descriptions.Item label="周期名称">{selectedCycle.cycle_name}</Descriptions.Item>
                <Descriptions.Item label="状态">
                  <Tag color={selectedCycle.status === 'CHECK' ? 'purple' : 'default'}>{selectedCycle.status}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="起止日期">{selectedCycle.start_date} ~ {selectedCycle.end_date}</Descriptions.Item>
                <Descriptions.Item label="周期目标">{selectedCycle.goal_text || '-'}</Descriptions.Item>
              </Descriptions>
            </Card>
          )}

          {/* 执行摘要统计（可刷新） */}
          {execSummary && (
            <Card
              size="small"
              title="周期执行统计"
              className="mb-4"
              extra={
                <Button size="small" icon={<ReloadOutlined />} onClick={handleRefreshSummary}>
                  刷新统计
                </Button>
              }
            >
              <Descriptions size="small" column={4}>
                <Descriptions.Item label="总交易计划">{execSummary.total_plans}</Descriptions.Item>
                <Descriptions.Item label="已执行计划">{execSummary.executed_plans}</Descriptions.Item>
                <Descriptions.Item label="执行率">{execSummary.fill_rate}</Descriptions.Item>
                <Descriptions.Item label="总交易笔数">{execSummary.total_trades}</Descriptions.Item>
                <Descriptions.Item label="裸交易">{execSummary.naked_trades}</Descriptions.Item>
              </Descriptions>
            </Card>
          )}

          {/* 报告状态 */}
          {report && (
            <div className="mb-4">
              <Tag color={report.report_status === 'published' ? 'green' : 'orange'}>
                {report.report_status === 'published' ? '已发布' : '草稿'}
              </Tag>
              {report.report_status === 'published' && (
                <Text type="secondary" className="ml-2">
                  报告已发布，修改后需重新发布
                </Text>
              )}
            </div>
          )}

          {/* 统计指标编辑 */}
          {report && (
            <Card size="small" title="统计指标" className="mb-4">
              <Descriptions size="small" column={4}>
                <Descriptions.Item label="总交易笔数">{report.total_trade_count ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="按计划完成">{report.complete_by_plan_count ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="执行率(%)">{report.execution_rate ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="胜率(%)">{report.win_rate ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="盈亏比">{report.profit_loss_ratio ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="平均进场得分">{report.avg_entry_score ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="平均出场得分">{report.avg_exit_score ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="平均交易得分">{report.avg_trade_score ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="最大回撤(%)">{report.max_drawdown ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="违规次数">{report.violation_total ?? '-'}</Descriptions.Item>
              </Descriptions>
            </Card>
          )}

          {/* 复盘内容编辑 */}
          <Card size="small" title="复盘内容" className="mb-4">
            <TextArea
              rows={12}
              value={reportContent}
              onChange={e => setReportContent(e.target.value)}
              placeholder="写下你的复盘分析...

可以从以下维度展开：
1. 交易执行情况回顾
2. 遵守/违反交易计划的情况
3. 情绪管理评估
4. 市场环境分析
5. 改进方向总结"
            />
          </Card>

          {/* 操作按钮 */}
          <div className="flex justify-end gap-3">
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={() => handleSave(false)}
            >
              保存草稿
            </Button>
            {(!report || report.report_status !== 'published') && (
              <Button
                type="primary"
                icon={<SendOutlined />}
                loading={saving}
                onClick={() => handleSave(true)}
              >
                发布报告
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default CheckModule;