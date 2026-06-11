import { useState } from 'react';
import { KLineChart } from './components/KLineChart';
import { StockHeader } from './components/StockHeader';
import { useStockData } from './hooks/useStockData';
import type { TimePeriod } from './types';

function App() {
  const [code, setCode] = useState('000001');
  const [period, setPeriod] = useState<TimePeriod>('1d');
  
  const { data, loading, error, stockInfo, refetch } = useStockData(code, period);

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <h1 className="text-2xl font-bold text-white">股票K线展示系统</h1>
          <p className="text-gray-400 text-sm mt-1">基于 React + TypeScript + KLineCharts</p>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        {/* Stock Info and Controls */}
        <StockHeader
          stockInfo={stockInfo}
          currentCode={code}
          onCodeChange={setCode}
          currentPeriod={period}
          onPeriodChange={setPeriod}
          onRefresh={refetch}
        />

        {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="bg-yellow-900/50 border border-yellow-600 text-yellow-300 px-4 py-3 rounded-lg mb-4">
            ⚠️ {error}
          </div>
        )}

        {/* Chart Container */}
        {!loading && data.length > 0 && (
          <div className="mt-4 rounded-lg overflow-hidden shadow-2xl border border-gray-800">
            <KLineChart data={data} height={600} />
          </div>
        )}

        {/* Empty State */}
        {!loading && data.length === 0 && !error && (
          <div className="text-center py-20 text-gray-500">
            暂无数据，请输入股票代码查询
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-gray-900 border-t border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 text-center text-gray-500 text-sm">
          © 2024 股票K线展示系统 | 数据来源: Tushare / Baostock
        </div>
      </footer>
    </div>
  );
}

export default App;
