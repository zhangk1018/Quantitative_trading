import React from 'react'
import { ConfigProvider } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { antdThemeConfig } from '@/styles/antd-theme'
import { router } from '@/app/router'
import { SettingsProvider } from '@/shared/contexts/SettingsContext'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

const App: React.FC = () => {
  return (
    <ConfigProvider theme={antdThemeConfig}>
      <SettingsProvider>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </SettingsProvider>
    </ConfigProvider>
  )
}

export default App
