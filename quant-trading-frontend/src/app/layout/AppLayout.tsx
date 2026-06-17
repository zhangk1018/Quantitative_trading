import React from 'react';
import { Layout, Typography, Space } from 'antd';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { DashboardOutlined, StockOutlined, StarOutlined, LineChartOutlined, SettingOutlined } from '@ant-design/icons';
import { ScreenerProvider } from '@/features/stock-picker/context/ScreenerContext';

const { Header, Content } = Layout;
const { Text } = Typography;

const AppLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    { key: '/picker', icon: <StockOutlined />, label: '选股视图' },
    { key: '/watchlist', icon: <StarOutlined />, label: '自选股' },
    { key: '/backtest', icon: <LineChartOutlined />, label: '回测分析' },
    { key: '/config', icon: <SettingOutlined />, label: '系统配置' },
  ];

  const selectedKey = location.pathname;

  return (
    // K 2026-06-17 决策：ScreenerProvider 上移到 AppLayout 层，让 /config 和 /picker
    // 共享同一份 screener state（customIndicators 跨页面同步 + 不再需要事件桥接）
    <ScreenerProvider>
    <Layout style={{ minHeight: '100vh', background: '#131722' }}>
      {/* 顶部通栏：Logo + 菜单栏 */}
      <Header className="h-14 px-6 flex items-center justify-between bg-bg-panel border-b border-border-color !leading-none">
        {/* 左侧：Logo */}
        <div className="flex items-center h-full gap-8">
          <div 
            className="flex items-center gap-2 flex-shrink-0 cursor-pointer" 
            onClick={() => navigate('/picker')}
          >
            <DashboardOutlined className="text-xl text-color-accent" />
            <Text strong className="text-text-primary text-base whitespace-nowrap">
              QuantPro
            </Text>
          </div>

          {/* 水平导航菜单 */}
          <div className="flex items-center h-full gap-1">
            {menuItems.map((item) => {
              const isActive = selectedKey === item.key;
              return (
                <div
                  key={item.key}
                  onClick={() => navigate(item.key)}
                  className={`
                    flex items-center gap-2 px-4 h-full cursor-pointer transition-all text-sm font-medium
                    ${isActive
                      ? 'text-color-accent border-b-2 border-color-accent bg-bg-base/30'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-card/50'
                    }
                  `}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* 右侧：系统状态 */}
        <Space size="middle" className="text-text-secondary text-sm flex-shrink-0">
        </Space>
      </Header>

      {/* 主工作区（全宽，无侧边栏） */}
      <Content className="flex-1 bg-bg-base">
        <div className="h-full min-h-[calc(100vh-56px)]">
          <Outlet />
        </div>
      </Content>
    </Layout>
    </ScreenerProvider>
  );
};

export default AppLayout;
