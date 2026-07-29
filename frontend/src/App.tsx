import React from 'react'
import { ConfigProvider, App as AntdApp } from 'antd'
import { RouterProvider } from 'react-router-dom'
import { antdThemeConfig } from '@/styles/antd-theme'
import { router } from '@/app/router'
import { SettingsProvider } from '@/shared/contexts/SettingsContext'

const App: React.FC = () => {
  return (
    <ConfigProvider theme={antdThemeConfig}>
      <AntdApp>
        <SettingsProvider>
          <RouterProvider router={router} />
        </SettingsProvider>
      </AntdApp>
    </ConfigProvider>
  )
}

export default App
