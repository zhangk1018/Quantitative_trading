import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import KLinePage from './KLinePage.tsx'
import TestSimpleChart from './components/TestSimpleChart.tsx'
import './index.css'

// 简短的路由检测：
// - /?kline=CODE → 独立 K 线页面
// - /?test → 简化版测试
const params = new URLSearchParams(window.location.search)
let RootComponent: React.ReactElement;
if (params.has('test')) {
  RootComponent = <TestSimpleChart />
} else if (params.has('kline')) {
  RootComponent = <KLinePage />
} else {
  RootComponent = <App />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  RootComponent
)
