import React, { useState } from 'react'
import { Typography, Table } from 'antd'

const { Text } = Typography

interface StockData {
  key: string
  rank: number
  code: string
  name: string
  score: number
  turnover: number
  maTrend: number
  volume: number
}

const StockTable: React.FC = () => {
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])

  const mockData: StockData[] = [
    { key: '1', rank: 1, code: '000001', name: '平安银行', score: 92.5, turnover: 8.2, maTrend: 2.1, volume: 1.2 },
    { key: '2', rank: 2, code: '000002', name: '万科A', score: 86.2, turnover: 7.1, maTrend: 1.8, volume: 0.9 },
    { key: '3', rank: 3, code: '600000', name: '浦发银行', score: 82.8, turnover: 6.5, maTrend: 1.5, volume: 1.1 },
    { key: '4', rank: 4, code: '600519', name: '贵州茅台', score: 78.5, turnover: 5.2, maTrend: 2.3, volume: 0.8 },
    { key: '5', rank: 5, code: '000858', name: '五粮液', score: 76.3, turnover: 4.8, maTrend: 1.9, volume: 0.7 },
    { key: '6', rank: 6, code: '002594', name: '比亚迪', score: 74.1, turnover: 9.5, maTrend: 2.5, volume: 1.5 },
    { key: '7', rank: 7, code: '601318', name: '中国平安', score: 72.8, turnover: 6.1, maTrend: 1.6, volume: 1.0 },
    { key: '8', rank: 8, code: '300750', name: '宁德时代', score: 71.2, turnover: 8.8, maTrend: 2.2, volume: 1.3 },
    { key: '9', rank: 9, code: '600036', name: '招商银行', score: 69.5, turnover: 5.8, maTrend: 1.7, volume: 0.9 },
    { key: '10', rank: 10, code: '000651', name: '格力电器', score: 68.2, turnover: 4.5, maTrend: 1.4, volume: 0.8 },
    { key: '11', rank: 11, code: '601899', name: '紫金矿业', score: 66.8, turnover: 7.2, maTrend: 2.0, volume: 1.2 },
    { key: '12', rank: 12, code: '000333', name: '美的集团', score: 65.5, turnover: 5.1, maTrend: 1.6, volume: 0.7 },
    { key: '13', rank: 13, code: '600030', name: '中信证券', score: 64.2, turnover: 6.8, maTrend: 1.8, volume: 1.1 },
    { key: '14', rank: 14, code: '002555', name: '三七互娱', score: 62.8, turnover: 8.1, maTrend: 2.1, volume: 1.0 },
    { key: '15', rank: 15, code: '300059', name: '东方财富', score: 61.5, turnover: 7.5, maTrend: 1.9, volume: 1.4 },
    { key: '16', rank: 16, code: '600887', name: '伊利股份', score: 60.2, turnover: 4.2, maTrend: 1.5, volume: 0.6 },
    { key: '17', rank: 17, code: '000063', name: '中兴通讯', score: 58.8, turnover: 6.3, maTrend: 1.7, volume: 0.9 },
    { key: '18', rank: 18, code: '601668', name: '中国建筑', score: 57.5, turnover: 3.8, maTrend: 1.3, volume: 0.8 },
    { key: '19', rank: 19, code: '300124', name: '汇川技术', score: 56.2, turnover: 5.6, maTrend: 2.0, volume: 0.7 },
    { key: '20', rank: 20, code: '600703', name: '三安光电', score: 54.8, turnover: 7.8, maTrend: 2.2, volume: 1.1 },
  ]

  const columns = [
    {
      title: '排名',
      dataIndex: 'rank',
      key: 'rank',
      width: 60,
      align: 'center' as const,
      render: (rank: number) => (
        <Text className={`font-bold ${rank <= 3 ? 'text-yellow-400' : 'text-text-secondary'}`}>
          {rank}
        </Text>
      ),
    },
    {
      title: '代码',
      dataIndex: 'code',
      key: 'code',
      width: 80,
      render: (code: string) => (
        <Text className="text-color-up font-mono">{code}</Text>
      ),
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 100,
      render: (name: string) => (
        <Text className="text-text-primary">{name}</Text>
      ),
    },
    {
      title: '综合得分',
      dataIndex: 'score',
      key: 'score',
      width: 100,
      align: 'right' as const,
      render: (score: number) => (
        <Text className="text-color-up font-semibold">{score}</Text>
      ),
    },
    {
      title: '换手率',
      dataIndex: 'turnover',
      key: 'turnover',
      width: 80,
      align: 'right' as const,
      render: (value: number) => (
        <Text className="text-text-secondary">{value}</Text>
      ),
    },
    {
      title: 'MA趋势',
      dataIndex: 'maTrend',
      key: 'maTrend',
      width: 80,
      align: 'right' as const,
      render: (value: number) => (
        <Text className="text-text-secondary">{value}</Text>
      ),
    },
    {
      title: '成交量',
      dataIndex: 'volume',
      key: 'volume',
      width: 80,
      align: 'right' as const,
      render: (value: number) => (
        <Text className="text-text-secondary">{value}</Text>
      ),
    },
  ]

  const rowSelection = {
    selectedRowKeys: selectedKeys,
    onChange: (keys: React.Key[]) => setSelectedKeys(keys as string[]),
  }

  return (
    <div className="bg-bg-base rounded-lg overflow-hidden">
      <Table
        dataSource={mockData}
        columns={columns}
        rowSelection={rowSelection}
        pagination={false}
        bordered={false}
        className="text-sm"
        style={{ background: '#131722' }}
      />
    </div>
  )
}

export default StockTable
