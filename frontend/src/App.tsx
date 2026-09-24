import React from 'react'
import { ConfigProvider, App as AntdApp } from 'antd'
import { RouterProvider } from 'react-router-dom'
import { antdThemeConfig } from '@/styles/antd-theme'
import { router } from '@/app/router'
import { SettingsProvider } from '@/shared/contexts/SettingsContext'
import { AuthProvider } from '@/features/auth/AuthContext'

const App: React.FC = () => {
  return (
    <ConfigProvider theme={antdThemeConfig}>
      <AntdApp>
        <SettingsProvider>
          {/* AuthProvider 挂在 Router 之上：/auth/me 结果跨路由复用，导航不重复请求 */}
          <AuthProvider>
            <RouterProvider router={router} />
          </AuthProvider>
        </SettingsProvider>
      </AntdApp>
    </ConfigProvider>
  )
}

export default App
