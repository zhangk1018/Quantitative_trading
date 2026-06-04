import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

// 暂时移除 StrictMode 以避免开发环境中 useEffect 双重调用导致请求中止
// TODO: 后续需要修复 App.tsx 中的请求逻辑以支持 StrictMode
ReactDOM.createRoot(document.getElementById('root')!).render(
  <App />
)