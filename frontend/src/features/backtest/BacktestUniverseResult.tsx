// BacktestUniverseResult.tsx — 批量回测结果：整组汇总对比 + 单股明细
//
// 顶部为汇总对比表格（每只股票一行，可点击行切换查看明细），
// 底部为当前选中股票的详细回测结果（指标卡片 / K线图 / 资金曲线 / 交易明细 / 诊断）。

import React, { useMemo } from 'react';
import { Card, Table, Tabs, Tag, Collapse, Empty, Button, Typography } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, SwapOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { BacktestUniverseResult as UniverseResult, BacktestSummary } from './backtestTypes';
import BacktestWarningBar from './BacktestWarningBar';
import BacktestMetrics from './BacktestMetrics';
import BacktestChart from './BacktestChart';
import BacktestEquityCurve from './BacktestEquityCurve';
import BacktestTradeLog from './BacktestTradeLog';
import BacktestDiagnostics from './BacktestDiagnostics';

const { Text } = Typography;

interface Props {
  results: UniverseResult[];
  activeIndex: number;
  onSelectStock: (index: number) => void;
  /** 初始资金（用于资金曲线计算收益率） */
  initialCapital: number;
}

function pct(val: number): string {
  return `${(val * 100).toFixed(2)}%`;
}

function fmt(val: number, decimals = 2): string {
  return val.toFixed(decimals);
}

/** 单行汇总数据（源自 BacktestSummary，取表格展示所需字段） */
interface RowData {
  index: number;
  stockCode: string;
  stockName: string;
  error?: string;
  summary: BacktestSummary | null;
  tradeCount: number;
}

const BacktestUniverseResult: React.FC<Props> = ({
  results,
  activeIndex,
  onSelectStock,
  initialCapital,
}) => {
  const rows: RowData[] = useMemo(() => {
    return results.map((r, index) => ({
      index,
      stockCode: r.stockCode,
      stockName: r.stockName,
      error: r.error,
      summary: r.output?.summary ?? null,
      tradeCount: r.output?.trades?.length ?? 0,
    }));
  }, [results]);

  // 成功股票数量（用于顶部统计展示）
  const successCount = useMemo(() => rows.filter((r) => !r.error).length, [rows]);

  // 全组平均收益率（仅统计成功的股票）
  const avgReturn = useMemo(() => {
    const ok = rows.filter((r) => r.summary);
    if (ok.length === 0) return null;
    return ok.reduce((acc, r) => acc + (r.summary?.totalReturn ?? 0), 0) / ok.length;
  }, [rows]);

  const columns: ColumnsType<RowData> = [
    {
      title: '股票',
      key: 'stock',
      width: 140,
      render: (_, r) => (
        <div className="flex items-center gap-2">
          <Text strong style={{ fontSize: 13 }}>{r.stockCode}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.stockName}</Text>
        </div>
      ),
    },
    {
      title: '总收益率',
      dataIndex: 'summary',
      key: 'totalReturn',
      width: 110,
      align: 'right',
      sorter: (a, b) => (a.summary?.totalReturn ?? -1) - (b.summary?.totalReturn ?? -1),
      render: (_, r) => {
        if (r.error) return <Text type="danger">失败</Text>;
        const v = r.summary?.totalReturn ?? 0;
        const positive = v >= 0;
        return (
          <span style={{ color: positive ? '#3f8600' : '#cf1322' }}>
            {positive ? <ArrowUpOutlined /> : <ArrowDownOutlined />} {pct(v)}
          </span>
        );
      },
    },
    {
      title: '年化',
      key: 'annualized',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.summary?.annualizedReturn ?? -1) - (b.summary?.annualizedReturn ?? -1),
      render: (_, r) => (r.summary ? pct(r.summary.annualizedReturn) : '-'),
    },
    {
      title: '胜率',
      key: 'winRate',
      width: 90,
      align: 'right',
      sorter: (a, b) => (a.summary?.winRate ?? -1) - (b.summary?.winRate ?? -1),
      render: (_, r) => (r.summary ? pct(r.summary.winRate) : '-'),
    },
    {
      title: '盈亏比',
      key: 'profitLossRatio',
      width: 90,
      align: 'right',
      sorter: (a, b) => (a.summary?.profitLossRatio ?? -1) - (b.summary?.profitLossRatio ?? -1),
      render: (_, r) => (r.summary ? fmt(r.summary.profitLossRatio) : '-'),
    },
    {
      title: '最大回撤',
      key: 'maxDrawdown',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.summary?.maxDrawdown ?? -1) - (b.summary?.maxDrawdown ?? -1),
      render: (_, r) => (r.summary ? <span style={{ color: '#cf1322' }}>{pct(r.summary.maxDrawdown)}</span> : '-'),
    },
    {
      title: '交易次数',
      key: 'tradeCount',
      width: 90,
      align: 'right',
      sorter: (a, b) => a.tradeCount - b.tradeCount,
      render: (_, r) => (r.summary ? r.summary.totalTrades : '-'),
    },
    {
      title: '状态',
      key: 'status',
      width: 80,
      render: (_, r) => (r.error ? <Tag color="red">失败</Tag> : <Tag color="green">成功</Tag>),
    },
    {
      title: '明细',
      key: 'action',
      width: 70,
      align: 'center',
      render: (_, r) => (
        <Button
          type="link"
          size="small"
          icon={<SwapOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            onSelectStock(r.index);
          }}
        >
          查看
        </Button>
      ),
    },
  ];

  // 当前选中股票的详细数据
  const active = results[activeIndex];
  const activeSummary = active?.output?.summary ?? null;
  const activeError = active?.error;

  return (
    <div>
      {/* 顶部统计 + 汇总对比表格 */}
      <Card size="small" style={{ marginBottom: 12 }}>
        <div className="flex items-center gap-3 mb-2" style={{ marginBottom: 8 }}>
          <Text strong style={{ fontSize: 14 }}>批量回测汇总</Text>
          <Tag color="blue">{rows.length} 只</Tag>
          <Tag color={successCount > 0 ? 'green' : 'default'}>{successCount} 成功</Tag>
          {avgReturn !== null && (
            <Tag color={avgReturn >= 0 ? 'green' : 'red'}>
              平均总收益 {avgReturn >= 0 ? '+' : ''}{pct(avgReturn)}
            </Tag>
          )}
        </div>
        <Table<RowData>
          rowKey="index"
          size="small"
          columns={columns}
          dataSource={rows}
          pagination={false}
          rowClassName={(r) => (r.index === activeIndex ? '!bg-color-accent/10' : '')}
          onRow={(r) => ({
            onClick: () => onSelectStock(r.index),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>

      {/* 单股明细 */}
      <Card
        size="small"
        title={
          active
            ? `明细：${active.stockCode} ${active.stockName}`
            : '明细'
        }
      >
        {!active ? (
          <Empty description="无结果" />
        ) : activeError ? (
          <Empty description={activeError || '该股票回测失败，无明细数据'} />
        ) : (
          <>
            <BacktestWarningBar warnings={active.output?.warnings ?? []} />
            {activeSummary && <BacktestMetrics summary={activeSummary} />}

            <Card size="small" style={{ marginBottom: 12 }}>
              <Tabs
                defaultActiveKey="kline"
                items={[
                  {
                    key: 'kline',
                    label: 'K线图',
                    children: (
                      <BacktestChart
                        bars={active.bars}
                        trades={active.output?.trades ?? []}
                        height={400}
                      />
                    ),
                  },
                  {
                    key: 'equity',
                    label: '资金曲线',
                    children: (
                      <>
                        <BacktestEquityCurve
                          equityCurve={active.output?.equityCurve ?? []}
                          initialCapital={initialCapital}
                          height={300}
                        />
                        <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
                          左轴：净值金额 &nbsp;|&nbsp; 右轴：收益率%
                        </Text>
                      </>
                    ),
                  },
                ]}
              />
            </Card>

            <Collapse
              ghost
              size="small"
              items={[
                {
                  key: 'trades',
                  label: `交易明细 (${(active.output?.trades ?? []).filter((t) => t.direction !== 'buy').length} 笔)`,
                  children: (
                    <BacktestTradeLog trades={active.output?.trades ?? []} />
                  ),
                },
                {
                  key: 'diagnostics',
                  label: `诊断报告 (${active.output?.diagnostics?.length ?? 0} 条)`,
                  children: <BacktestDiagnostics diagnostics={active.output?.diagnostics ?? []} />,
                },
              ]}
            />
          </>
        )}
      </Card>
    </div>
  );
};

export default BacktestUniverseResult;
