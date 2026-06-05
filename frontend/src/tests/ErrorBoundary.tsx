import React, { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Chart error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <div className="w-full h-full flex items-center justify-center bg-white p-8">
          <div className="text-center">
            <div className="text-5xl mb-4">⚠️</div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">图表加载失败</h3>
            <p className="text-sm text-gray-600 mb-4">{this.state.error?.message}</p>
            <button
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              onClick={() => this.setState({ hasError: false, error: null })}
            >
              重试
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
