export default function BacktestView() {
  const trades = [
    { date: "2026-06-03", direction: "买入", price: 10.65, quantity: 1000, fee: 8.20, pnl: 0.00, holding: 1000 },
    { date: "2026-06-09", direction: "平仓", price: 11.15, quantity: 1000, fee: 9.10, pnl: 4720.70, holding: 0 },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* 上部：主图表区 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="p-3 border-b border-border-color bg-bg-secondary flex items-center gap-4">
          <div className="flex items-center gap-1">
            <button className="bg-bg-card border border-border-color text-text-secondary px-3 py-1 text-sm rounded hover:bg-bg-primary transition-colors">
              ◀ 前复权
            </button>
            <button className="bg-bg-card border border-border-color text-text-secondary px-3 py-1 text-sm rounded hover:bg-bg-primary transition-colors">
              ▶ 后复权
            </button>
            <button className="bg-up-green text-white px-3 py-1 text-sm rounded">
              ● 不复权
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-text-muted text-sm">周期:</span>
            <select className="bg-bg-card border border-border-color text-text-primary text-sm px-2 py-1 rounded">
              <option>日线</option>
              <option>周线</option>
              <option>月线</option>
            </select>
          </div>
        </div>

        <div className="flex-1 flex flex-col">
          {/* 主 K 线图区域 */}
          <div className="flex-1 flex items-center justify-center bg-bg-primary border-b border-border-color">
            <div className="text-center text-text-muted">
              <div className="text-5xl mb-4">📊</div>
              <div className="text-lg mb-2">K线图表区域</div>
              <div className="text-sm">K线蜡烛图 + MA均线 + 买卖信号标记</div>
            </div>
          </div>

          {/* 成交量图 */}
          <div className="h-24 flex items-center justify-center bg-bg-secondary border-b border-border-color">
            <div className="text-center text-text-muted">
              <div className="text-sm">副图1: 成交量</div>
            </div>
          </div>

          {/* MACD 图 */}
          <div className="h-24 flex items-center justify-center bg-bg-primary">
            <div className="text-center text-text-muted">
              <div className="text-sm">副图2: MACD [可切换RSI/KDJ/BOLL]</div>
            </div>
          </div>
        </div>
      </div>

      {/* 下部：绩效卡片 + 交易明细 */}
      <div className="h-[220px] border-t border-border-color bg-bg-secondary flex flex-col">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-color">
          <h3 className="text-text-primary font-medium">绩效分析</h3>
          <button className="text-text-muted text-sm">▼</button>
        </div>

        <div className="grid grid-cols-4 gap-4 p-3 border-b border-border-color">
          <div className="bg-bg-card p-3 rounded">
            <div className="text-text-muted text-xs mb-1">总收益率</div>
            <div className="text-up-green text-xl font-semibold">4.28%</div>
          </div>
          <div className="bg-bg-card p-3 rounded">
            <div className="text-text-muted text-xs mb-1">年化收益</div>
            <div className="text-up-green text-xl font-semibold">15.23%</div>
          </div>
          <div className="bg-bg-card p-3 rounded">
            <div className="text-text-muted text-xs mb-1">最大回撤</div>
            <div className="text-down-red text-xl font-semibold">-2.85%</div>
          </div>
          <div className="bg-bg-card p-3 rounded">
            <div className="text-text-muted text-xs mb-1">胜率</div>
            <div className="text-text-primary text-xl font-semibold">58.6%</div>
          </div>
          <div className="bg-bg-card p-3 rounded">
            <div className="text-text-muted text-xs mb-1">夏普比率</div>
            <div className="text-text-primary text-xl font-semibold">1.21</div>
          </div>
          <div className="bg-bg-card p-3 rounded">
            <div className="text-text-muted text-xs mb-1">盈亏比</div>
            <div className="text-text-primary text-xl font-semibold">1.45</div>
          </div>
        </div>

        <div className="flex-1 overflow-hidden flex flex-col">
          <div className="px-4 py-2">
            <h4 className="text-text-primary font-medium text-sm">交易明细</h4>
          </div>
          <div className="flex-1 overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-card sticky top-0">
                <tr>
                  <th className="text-left px-4 py-2 text-text-muted font-medium">日期</th>
                  <th className="text-left px-4 py-2 text-text-muted font-medium">方向</th>
                  <th className="text-right px-4 py-2 text-text-muted font-medium">价格</th>
                  <th className="text-right px-4 py-2 text-text-muted font-medium">数量</th>
                  <th className="text-right px-4 py-2 text-text-muted font-medium">费用</th>
                  <th className="text-right px-4 py-2 text-text-muted font-medium">盈亏</th>
                  <th className="text-right px-4 py-2 text-text-muted font-medium">持仓</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-color/50">
                {trades.map((trade, index) => (
                  <tr key={index} className="hover:bg-bg-card transition-colors">
                    <td className="px-4 py-2 text-text-primary">{trade.date}</td>
                    <td className={`px-4 py-2 ${trade.direction === "买入" ? "text-up-green" : "text-down-red"} font-medium`}>
                      {trade.direction}
                    </td>
                    <td className="px-4 py-2 text-text-primary font-mono text-right">{trade.price.toFixed(2)}</td>
                    <td className="px-4 py-2 text-text-primary font-mono text-right">{trade.quantity.toLocaleString()}</td>
                    <td className="px-4 py-2 text-text-muted font-mono text-right">{trade.fee.toFixed(2)}</td>
                    <td className={`px-4 py-2 font-mono text-right ${trade.pnl > 0 ? "text-up-green" : trade.pnl < 0 ? "text-down-red" : "text-text-muted"}`}>
                      {trade.pnl >= 0 ? "+" : ""}{trade.pnl.toFixed(2)}
                    </td>
                    <td className="px-4 py-2 text-text-primary font-mono text-right">{trade.holding.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
