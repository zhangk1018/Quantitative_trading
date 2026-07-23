// ErrorBoundary.tsx — 回测结果区域错误边界
// 捕获子组件渲染异常，展示友好错误信息并提供重试/重置按钮

import React, { Component, type ReactNode } from 'react';
import { Button, Result } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

interface Props {
  children: ReactNode;
  /** 重置回调（清空回测结果并重置表单） */
  onReset?: () => void;
  /** 自定义错误标题 */
  errorTitle?: string;
}

interface State {
  hasError: boolean;
  errorMessage: string;
}

export class BacktestErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, errorMessage: '' };
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      errorMessage: error.message || '未知渲染错误',
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('[BacktestErrorBoundary] 捕获到渲染异常:', error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, errorMessage: '' });
    this.props.onReset?.();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <Result
          status="error"
          title={this.props.errorTitle || '回测结果渲染失败'}
          subTitle={this.state.errorMessage}
          extra={
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={this.handleReset}
            >
              重置并重试
            </Button>
          }
        />
      );
    }

    return this.props.children;
  }
}

export default BacktestErrorBoundary;