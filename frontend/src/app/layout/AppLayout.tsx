import React from 'react';
import { Layout, Typography, Space, Dropdown, Avatar, Tag, Modal, message } from 'antd';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { DashboardOutlined, StockOutlined, StarOutlined, LineChartOutlined, SettingOutlined, ExperimentOutlined, CheckCircleOutlined, UserOutlined, LogoutOutlined, SafetyOutlined, TeamOutlined, DownOutlined } from '@ant-design/icons';
import { ScreenerProvider } from '@/features/stock-picker/context/ScreenerContext';
import { WatchlistProvider } from '@/features/watchlist/store';
import { useAuth } from '@/features/auth/AuthContext';

const { Header, Content } = Layout;
const { Text } = Typography;

const AppLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isAdmin, authDisabled, logout } = useAuth();

  const menuItems = [
    { key: '/picker', icon: <StockOutlined />, label: '选股视图' },
    { key: '/watchlist', icon: <StarOutlined />, label: '自选股' },
    { key: '/backtest', icon: <LineChartOutlined />, label: '回测分析' },
    { key: '/strategy-backtest', icon: <ExperimentOutlined />, label: '策略回测' },
    { key: '/pdca', icon: <CheckCircleOutlined />, label: '交易室' },
    { key: '/config', icon: <SettingOutlined />, label: '系统配置' },
    // 管理员页入口按 role 控制（非 admin 不显示）
    ...(isAdmin ? [{ key: '/users', icon: <TeamOutlined />, label: '用户管理' }] : []),
  ];

  const selectedKey = location.pathname;

  const displayName = user?.display_name || user?.username || (authDisabled ? '认证未启用' : '未登录');

  const handleLogout = () => {
    Modal.confirm({
      title: '退出登录',
      content: '确认退出当前账号？',
      okText: '退出',
      cancelText: '取消',
      onOk: async () => {
        await logout();
        message.success('已退出登录');
        navigate('/login', { replace: true });
      },
    });
  };

  const userMenuItems = [
    { key: 'change-password', icon: <SafetyOutlined />, label: '修改密码' },
    ...(isAdmin ? [{ key: 'users', icon: <TeamOutlined />, label: '用户管理' }] : []),
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ];

  const onUserMenuClick = ({ key }: { key: string }) => {
    if (key === 'logout') {
      handleLogout();
      return;
    }
    navigate(`/${key}`);
  };

  return (
    // K 2026-06-17 决策：ScreenerProvider 上移到 AppLayout 层，让 /config 和 /picker
    // 共享同一份 screener state（customIndicators 跨页面同步 + 不再需要事件桥接）
    // K 2026-06-22 反馈 #1：WatchlistProvider 也必须包裹 Outlet，否则 StockPickerView
    // 中 useWatchlist() 拿不到 Context（React 只向下查找）
    <ScreenerProvider>
    <WatchlistProvider>
    <Layout style={{ height: '100vh', overflow: 'hidden', background: '#131722' }}>
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

        {/* 右侧：当前用户 + role + 账号操作 */}
        <Space size="middle" className="text-text-secondary text-sm flex-shrink-0">
          <Dropdown menu={{ items: userMenuItems, onClick: onUserMenuClick }} trigger={['click']}>
            <div className="flex items-center gap-2 cursor-pointer px-2 py-1 rounded hover:bg-bg-card/60" data-testid="topbar-user">
              <Avatar size={24} icon={<UserOutlined />} className="bg-bg-card" />
              <Text className="text-text-primary">{displayName}</Text>
              {user && (
                <Tag color={isAdmin ? 'blue' : 'default'} className="!mr-0">
                  {isAdmin ? '管理员' : '普通用户'}
                </Tag>
              )}
              <DownOutlined className="text-xs" />
            </div>
          </Dropdown>
        </Space>
      </Header>

      {/* 主工作区（全宽，无侧边栏） */}
      <Content className="flex-1 flex flex-col min-h-0 bg-bg-base">
        <div className="flex-1 min-h-0">
          <Outlet />
        </div>
      </Content>
    </Layout>
    </WatchlistProvider>
    </ScreenerProvider>
  );
};

export default AppLayout;
