export type ViewType = "stock-picker" | "watchlist" | "backtest" | "settings";

interface ViewTabsProps {
  currentView: ViewType;
  onViewChange: (view: ViewType) => void;
}

export default function ViewTabs({ currentView, onViewChange }: ViewTabsProps) {
  const views = [
    { id: "stock-picker", label: "选股视图", icon: "🔍" },
    { id: "watchlist", label: "自选股", icon: "⭐" },
    { id: "backtest", label: "回测视图", icon: "📈" },
    { id: "settings", label: "参数配置", icon: "⚙️" },
  ];

  return (
    <div className="flex items-center gap-1 bg-bg-secondary border-b border-border-color px-2">
      {views.map(({ id, label, icon }) => {
        const isActive = currentView === id;
        return (
          <button
            key={id}
            onClick={() => onViewChange(id as ViewType)}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-medium transition-all border-b-2 ${
              isActive
                ? "text-text-primary border-btn-primary bg-bg-primary text-sm"
                : "text-text-secondary border-transparent hover:text-text-primary hover:bg-bg-card"
            }`}
          >
            <span>{icon}</span>
            <span>{label}</span>
          </button>
        );
      })}
    </div>
  );
}
