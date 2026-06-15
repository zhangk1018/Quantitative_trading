import React from 'react'
import { Layout, Typography, Space, Tooltip, Divider } from 'antd'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { 
  RocketOutlined, 
  LineChartOutlined, 
  StarOutlined, 
  SettingOutlined,
  DatabaseOutlined,
  ThunderboltOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons'

const { Header, Content } = Layout
const { Text } = Typography

const MainLayout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()

  // 菜单项配置
  const menuItems = [
    { key: '/', label: '选股视图', icon: <RocketOutlined /> },
    { key: '/watchlist', label: '自选股', icon: <StarOutlined /> },
    { key: '/backtest', label: '回测视图', icon: <LineChartOutlined /> },
    { key: '/config', label: '参数配置', icon: <SettingOutlined /> },
  ]

  const handleMenuClick = (key: string) => {
    navigate(key)
  }

  const selectedKey = location.pathname

  return (
    <Layout className="h-screen w-screen overflow-hidden bg-bg-base">
      {/* ================= 顶部通栏 (导航 + 状态) ================= */}
      <Header className="h-14 px-6 flex items-center justify-between bg-bg-panel border-b border-border-color !leading-none">
        
        {/* 左侧：Logo 与 自定义导航菜单 */}
        <div className="flex items-center h-full gap-8">
          {/* Logo */}
          <div 
            className="flex items-center gap-2 flex-shrink-0 cursor-pointer" 
            onClick={() => navigate('/')}
          >
            <RocketOutlined className="text-xl text-color-accent" />
            <Text strong className="text-text-primary text-base whitespace-nowrap">
              量化交易系统
            </Text>
          </div>

          {/* 水平导航菜单 - 使用 Flex 布局，彻底解决折叠问题 */}
          <div className="flex items-center h-full gap-1">
            {menuItems.map((item) => {
              const isActive = selectedKey === item.key
              return (
                <div
                  key={item.key}
                  onClick={() => handleMenuClick(item.key)}
                  className={`
                    flex items-center gap-2 px-4 h-full cursor-pointer transition-all text-sm font-medium
                    ${isActive 
                      ? 'text-color-up border-b-2 border-color-up bg-bg-base/30' 
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-card/50'
                    }
                  `}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* 右侧：系统状态指示器 (紧凑布局) */}
        <Space size="middle" className="text-text-secondary text-sm flex-shrink-0">
          <Tooltip title="数据源连接正常">
            <Space size={4}>
              <DatabaseOutlined className="text-color-up" />
              <Text className="text-text-secondary">数据状态:</Text>
              <Text className="text-color-up">已加载</Text>
            </Space>
          </Tooltip>
          
          <Divider type="vertical" className="bg-border-color h-4 my-0" />

          <Tooltip title="策略引擎就绪">
            <Space size={4}>
              <ThunderboltOutlined className="text-[#FFD700]" />
              <Text className="text-text-secondary">策略:</Text>
              <Text className="text-[#FFD700]">就绪</Text>
            </Space>
          </Tooltip>

          <Divider type="vertical" className="bg-border-color h-4 my-0" />

          <QuestionCircleOutlined className="text-lg cursor-pointer hover:text-text-primary transition-colors" />
        </Space>
      </Header>

      {/* ================= 主工作区 (全宽) ================= */}
      <Content className="flex-1 overflow-auto bg-bg-base">
        <Outlet />
      </Content>
    </Layout>
  )
}

export default MainLayout