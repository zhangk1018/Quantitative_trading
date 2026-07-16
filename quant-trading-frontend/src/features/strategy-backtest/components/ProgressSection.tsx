// src/features/strategy-backtest/components/ProgressSection.tsx
// 运行进度条 + 阶段提示 + 取消按钮

import React from 'react';
import { Progress, Button } from 'antd';
import { CloseOutlined } from '@ant-design/icons';

export interface ProgressInfo {
  stage: 'data' | 'indicators' | 'simulation' | 'done';
  percent: number;
  message: string;
}

interface ProgressSectionProps {
  progress: ProgressInfo;
  onCancel: () => void;
  disabled?: boolean;
}

const stageLabels: Record<string, string> = {
  data: '数据加载',
  indicators: '指标计算',
  simulation: '回测模拟',
  done: '完成',
};

const ProgressSection: React.FC<ProgressSectionProps> = ({ progress, onCancel, disabled }) => {
  return (
    <div className="bg-bg-panel rounded-lg border border-border-color p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium">
          {stageLabels[progress.stage] ?? progress.stage}
        </span>
        <Button
          size="small"
          danger
          icon={<CloseOutlined />}
          onClick={onCancel}
          disabled={disabled}
          data-testid="cancel-backtest-btn"
        >
          取消
        </Button>
      </div>
      <Progress
        percent={Math.round(progress.percent * 100)}
        status={progress.stage === 'done' ? 'success' : 'active'}
        strokeColor="#1677ff"
        format={(pct) => `${pct}%`}
      />
      <div className="text-text-disabled text-xs mt-1">
        {progress.message}
      </div>
    </div>
  );
};

export default ProgressSection;