export default function SettingsView() {
  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto p-6">
        {/* 账户基本设置 */}
        <div className="mb-8">
          <h3 className="text-text-primary font-medium text-lg mb-4">💰 账户基础设置</h3>
          <div className="bg-bg-card p-4 rounded-lg border border-border-color">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-text-secondary text-sm mb-2">初始资金</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="100000.00"
                    className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">元</span>
                </div>
              </div>
              <div>
                <label className="block text-text-secondary text-sm mb-2">持仓上限</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="5"
                    className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">只股票</span>
                </div>
              </div>
              <div>
                <label className="block text-text-secondary text-sm mb-2">单笔仓位</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="20"
                    className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 交易费率设置 */}
        <div className="mb-8">
          <h3 className="text-text-primary font-medium text-lg mb-4">💸 交易费率设置（A股标准）</h3>
          <div className="bg-bg-card p-4 rounded-lg border border-border-color">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-text-secondary text-sm mb-2">佣金（买卖双向）</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="0.03"
                    className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">‰</span>
                </div>
              </div>
              <div>
                <label className="block text-text-secondary text-sm mb-2">印花税（仅卖出）</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="0.1"
                    className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">%</span>
                </div>
              </div>
              <div>
                <label className="block text-text-secondary text-sm mb-2">过户费（买卖双向）</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="0.001"
                    className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">‰</span>
                </div>
              </div>
              <div>
                <label className="block text-text-secondary text-sm mb-2">滑点设置</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="0.01"
                    className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">元/股</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 技术指标参数设置 */}
        <div className="mb-8">
          <h3 className="text-text-primary font-medium text-lg mb-4">📈 技术指标参数设置</h3>
          <div className="bg-bg-card p-4 rounded-lg border border-border-color">
            <div className="grid grid-cols-2 gap-6">
              <div className="flex items-center gap-4">
                <span className="text-text-secondary text-sm w-24">MA均线:</span>
                <div className="flex items-center gap-3">
                  <span className="text-text-muted text-sm">短期</span>
                  <input
                    type="text"
                    defaultValue="5"
                    className="w-20 bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green text-center"
                  />
                  <span className="text-text-muted text-sm">长期</span>
                  <input
                    type="text"
                    defaultValue="20"
                    className="w-20 bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green text-center"
                  />
                </div>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-text-secondary text-sm w-24">MACD:</span>
                <div className="flex items-center gap-2">
                  <span className="text-text-muted text-sm">SHORT</span>
                  <input
                    type="text"
                    defaultValue="12"
                    className="w-16 bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green text-center"
                  />
                  <span className="text-text-muted text-sm">LONG</span>
                  <input
                    type="text"
                    defaultValue="26"
                    className="w-16 bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green text-center"
                  />
                  <span className="text-text-muted text-sm">SIG</span>
                  <input
                    type="text"
                    defaultValue="9"
                    className="w-16 bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green text-center"
                  />
                </div>
              </div>
              <div>
                <label className="block text-text-secondary text-sm mb-2">RSI周期</label>
                <input
                  type="text"
                  defaultValue="14"
                  className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                />
              </div>
              <div>
                <label className="block text-text-secondary text-sm mb-2">成交量阈值</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="10000"
                    className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">手</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 回测风控规则 */}
        <div className="mb-8">
          <h3 className="text-text-primary font-medium text-lg mb-4">🛡️ 回测风控规则</h3>
          <div className="bg-bg-card p-4 rounded-lg border border-border-color">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-text-secondary text-sm mb-2">最大回撤限制</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="15"
                    className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">%</span>
                </div>
              </div>
              <div>
                <label className="block text-text-secondary text-sm mb-2">单日最大亏损</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="3"
                    className="w-full bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">%</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" className="accent-up-green" />
                <span className="text-text-secondary text-sm">禁止隔夜持仓</span>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" defaultChecked className="accent-up-green" />
                <span className="text-text-secondary text-sm">涨跌停/停牌自动跳过</span>
              </div>
            </div>
          </div>
        </div>

        {/* 高级回测选项 */}
        <div className="mb-8">
          <h3 className="text-text-primary font-medium text-lg mb-4">🧩 高级回测选项</h3>
          <div className="bg-bg-card p-4 rounded-lg border border-border-color">
            <div className="mb-4">
              <label className="block text-text-secondary text-sm mb-2">复权方式</label>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2">
                  <input type="radio" name="adjType" defaultChecked className="accent-up-green" />
                  <span className="text-text-primary text-sm">前复权</span>
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="adjType" className="accent-up-green" />
                  <span className="text-text-primary text-sm">后复权</span>
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="adjType" className="accent-up-green" />
                  <span className="text-text-primary text-sm">不复权</span>
                </label>
              </div>
            </div>

            <div className="mb-4">
              <label className="block text-text-secondary text-sm mb-2">交易时机</label>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2">
                  <input type="radio" name="tradeTime" defaultChecked className="accent-up-green" />
                  <span className="text-text-primary text-sm">次日开盘</span>
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="tradeTime" className="accent-up-green" />
                  <span className="text-text-primary text-sm">当日收盘</span>
                </label>
              </div>
            </div>

            <div>
              <label className="block text-text-secondary text-sm mb-2">数据区间</label>
              <div className="flex items-center gap-2">
                <span className="text-text-secondary text-sm">近</span>
                <input
                  type="text"
                  defaultValue="180"
                  className="w-24 bg-bg-primary border border-border-color text-text-primary px-3 py-2 rounded focus:outline-none focus:border-up-green text-center"
                />
                <span className="text-text-secondary text-sm">天数据</span>
              </div>
            </div>
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-3">
          <button className="bg-up-green text-white px-6 py-2 rounded hover:opacity-90 transition-opacity font-medium">
            保存配置
          </button>
          <button className="bg-bg-card border border-border-color text-text-primary px-6 py-2 rounded hover:bg-bg-secondary transition-colors">
            恢复默认
          </button>
          <button className="bg-bg-card border border-border-color text-text-primary px-6 py-2 rounded hover:bg-bg-secondary transition-colors">
            导出配置
          </button>
        </div>
      </div>
    </div>
  );
}
