import { useState } from 'react';
import type { StockInfo, TimePeriod } from '../types';

interface StockHeaderProps {
  stockInfo: StockInfo | null;
  currentCode: string;
  onCodeChange: (code: string) => void;
  currentPeriod: TimePeriod;
  onPeriodChange: (period: TimePeriod) => void;
  onRefresh: () => void;
}

export const StockHeader = ({
  stockInfo,
  currentCode,
  onCodeChange,
  currentPeriod,
  onPeriodChange,
  onRefresh,
}: StockHeaderProps) => {
  const [inputCode, setInputCode] = useState(currentCode);

  const handleCodeSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputCode.trim()) {
      onCodeChange(inputCode.trim());
    }
  };

  const isPositive = (stockInfo?.change ?? 0) >= 0;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 shadow-lg">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        {/* Controls */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <form onSubmit={handleCodeSubmit} className="flex items-center gap-2">
            <input
              type="text"
              value={inputCode}
              onChange={(e) => setInputCode(e.target.value)}
              placeholder="输入股票代码"
              className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
            />
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-all font-medium shadow-md hover:shadow-lg"
            >
              查询
            </button>
          </form>
          
          <div className="flex items-center gap-2">
            <span className="text-gray-400 text-sm">周期:</span>
            {(['1d', '1w', '1m'] as TimePeriod[]).map((period) => (
              <button
                key={period}
                onClick={() => onPeriodChange(period)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  currentPeriod === period
                    ? 'bg-blue-600 text-white shadow-md'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'
                }`}
              >
                {period === '1d' ? '日线' : period === '1w' ? '周线' : '月线'}
              </button>
            ))}
          </div>
        </div>

        {/* Stock Info */}
        {stockInfo && (
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="text-left">
              <span className="text-xl font-bold text-white">{stockInfo.name}</span>
              <span className="text-gray-500 ml-2 font-mono">{stockInfo.code}</span>
            </div>
            <div className="text-left sm:text-right">
              <div className={`text-2xl font-bold ${isPositive ? 'text-red-500' : 'text-green-500'}`}>
                ¥{stockInfo.price.toFixed(2)}
              </div>
              <div className={`text-sm font-medium ${isPositive ? 'text-red-500' : 'text-green-500'}`}>
                {isPositive ? '+' : ''}{stockInfo.change.toFixed(2)} ({isPositive ? '+' : ''}{stockInfo.changePercent.toFixed(2)}%)
              </div>
            </div>
            <button
              onClick={onRefresh}
              className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg transition-all font-medium flex items-center gap-2 shadow-md hover:shadow-lg"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              刷新
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
