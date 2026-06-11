export default function StatusBar() {
  return (
    <div className="h-12 bg-bg-secondary border-b border-border-color flex items-center justify-between px-4">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-text-primary font-semibold text-lg">🚀 量化交易系统</span>
        </div>
      </div>
      <div className="flex items-center gap-6 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-text-muted">📊 数据状态:</span>
          <span className="text-up-green">已加载</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-text-muted">⚡ 策略:</span>
          <span className="text-text-primary">就绪</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-text-muted">📅 最后更新:</span>
          <span className="text-text-primary">{new Date().toLocaleString("zh-CN")}</span>
        </div>
        <button className="text-text-secondary hover:text-text-primary transition-colors">
          ❓ 帮助
        </button>
      </div>
    </div>
  );
}
