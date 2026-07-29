// BacktestWarningBar.tsx — 三级警告面板

import React from 'react';
import { Alert, Space } from 'antd';

interface WarningBarProps {
  warnings: string[];
  /** 价格收益口径提示 */
  showPriceReturnNote?: boolean;
  /** 不含手续费提示 */
  showFeeFreeNote?: boolean;
}

const BacktestWarningBar: React.FC<WarningBarProps> = ({
  warnings,
  showPriceReturnNote = false,
  showFeeFreeNote = false,
}) => {
  if (warnings.length === 0 && !showPriceReturnNote && !showFeeFreeNote) {
    return null;
  }

  return (
    <Space direction="vertical" style={{ width: '100%', marginBottom: 12 }}>
      {warnings.map((w, i) => (
        <Alert
          key={`warn-${i}`}
          message={w}
          type="warning"
          showIcon
          style={{ padding: '4px 12px' }}
        />
      ))}
      {showPriceReturnNote && (
        <Alert
          message="收益口径：价格收益（基于前复权价格，不含分红送转）"
          type="info"
          showIcon
          style={{ padding: '4px 12px' }}
        />
      )}
      {showFeeFreeNote && (
        <Alert
          message="V1 回测不含手续费和滑点，回测收益可能高估"
          type="info"
          showIcon
          style={{ padding: '4px 12px' }}
        />
      )}
    </Space>
  );
};

export default BacktestWarningBar;