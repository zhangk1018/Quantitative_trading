# 前端编程规范 - Lingma-FE

**适用范围**：`/Users/zhangk/workspace/Quantitative_trading/src/frontend`  
**创建日期**：2026-05-31  
**基于**：project_rules.md + CODE_QUALITY_GUIDE.md  

---

## 📐 一、代码风格规范

### 1.1 TypeScript 规范

#### ✅ 必须遵守
```typescript
// 1. 严格类型定义，禁止使用 any
interface StockRow {
  ts_code: string
  name: string
  pct_chg: number
  // ... 其他字段
}

// 2. 函数参数和返回值必须标注类型
function fmt(key: string, val: unknown): string {
  // ...
}

// 3. 可选属性使用 ?
interface Props {
  onRowClick?: (code: string) => void
}

// 4. 联合类型明确标注
type SignalType = 'buy' | 'sell'

// 5. 泛型使用规范
const [stocks, setStocks] = useState<StocksResponse | null>(null)
```

#### ❌ 禁止使用
```typescript
// 禁止 any
const data: any = fetchData() // ❌

// 禁止隐式 any
function process(data) { // ❌ 参数未标注类型
  return data.value
}

// 禁止类型断言滥用
const code = row.ts_code as string // ❌ 除非必要
```

---

### 1.2 React 组件规范

#### ✅ 推荐写法
```typescript
// 1. 使用函数式组件 + TypeScript
interface Props {
  rows: StockRow[]
  total: number
  onSort: (key: string) => void
}

export default function StockTable({ rows, total, onSort }: Props) {
  const [expanded, setExpanded] = useState(false)
  
  const handleExpand = useCallback(() => {
    setExpanded(prev => !prev)
  }, [])
  
  return (
    <div className="...">
      {/* JSX */}
    </div>
  )
}
```

#### ❌ 避免写法
```typescript
// 禁止类组件
class StockTable extends Component { // ❌
  // ...
}

// 禁止箭头函数组件（不利于调试）
const StockTable = (props: Props) => { // ⚠️ 不推荐
  // ...
}

// 禁止默认导出匿名函数
export default function({ rows }: Props) { // ❌ 缺少函数名
  // ...
}
```

---

### 1.3 Hooks 使用规范

#### ✅ 正确使用
```typescript
// 1. useEffect 依赖项完整
useEffect(() => {
  fetchStocks(params)
}, [activeFilters, sortBy, offset]) // ✅ 所有依赖项都列出

// 2. useCallback 优化事件处理
const toggleFilter = useCallback((key: string) => {
  setActiveFilters(prev => 
    prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
  )
}, []) // ✅ 无外部依赖

// 3. useState 初始化
const [loading, setLoading] = useState(false) // ✅ 明确初始值
```

#### ❌ 常见错误
```typescript
// 1. 缺少依赖项
useEffect(() => {
  fetchStocks({ filters: activeFilters }) // ❌ activeFilters 未在依赖项中
}, [])

// 2. 不必要的 useCallback
const value = useCallback(complexCalculation(), []) // ❌ 计算结果不需要缓存

// 3. 状态初始化不明确
const [count, setCount] = useState() // ❌ 应明确初始值
```

---

### 1.4 命名规范

#### 变量命名
```typescript
// ✅ camelCase
const stockList: StockRow[] = []
const isLoading = false
const totalPages = 10

// ❌ 避免
const stock_list = [] // snake_case
const StockList = [] // PascalCase（仅用于组件/类）
```

#### 常量命名
```typescript
// ✅ UPPER_SNAKE_CASE
const LIMIT = 100
const BASE_URL = '/api'
const SORTABLE_KEYS = new Set([...])

// ❌ 避免
const limit = 100 // 应与普通变量区分
```

#### 组件命名
```typescript
// ✅ PascalCase
export default function StockTable() { }
export default function FilterPanel() { }

// 文件名与组件名一致
// StockTable.tsx → StockTable 组件
```

#### 函数命名
```typescript
// ✅ 动词开头，描述行为
function fetchMeta() { }
function toggleFilter() { }
function handleSort() { }
function formatDate() { }

// ❌ 避免
function meta() { } // 不清楚是获取还是处理
function filter() { } // 不清楚是切换还是应用
```

---

## 🎨 二、样式规范（TailwindCSS）

### 2.1 类名组织顺序

```typescript
// ✅ 推荐顺序：布局 → 尺寸 → 间距 → 颜色 → 其他
<div className="
  flex flex-col           // 布局
  w-full h-screen         // 尺寸
  px-4 py-2 gap-2         // 间距
  bg-gray-900 text-white  // 颜色
  overflow-hidden         // 其他
">
```

### 2.2 响应式设计

```typescript
// ✅ 移动端优先
<div className="
  text-sm                 // 默认（移动端）
  md:text-base            // 中等屏幕
  lg:text-lg              // 大屏幕
">
```

### 2.3 状态样式

```typescript
// ✅ 使用条件类名
<button className={[
  'px-4 py-2 rounded',
  isActive 
    ? 'bg-red-600 text-white' 
    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
].join(' ')}>
```

### 2.4 禁止自定义 CSS

```typescript
// ❌ 禁止内联样式
<div style={{ color: 'red' }}> // ❌

// ❌ 禁止自定义 CSS 文件（除非必要）
// 优先使用 TailwindCSS utility classes
```

---

## 🏗️ 三、组件结构规范

### 3.1 文件结构

```typescript
// 1. 导入语句
import { useState, useCallback } from 'react'
import type { StockRow } from '../types'

// 2. 常量定义
const LIMIT = 100
const DEFAULT_COLS = [...]

// 3. 工具函数
function fmt(key: string, val: unknown): string {
  // ...
}

// 4. 子组件（如果有）
function SubComponent() {
  // ...
}

// 5. 主组件
interface Props {
  // ...
}

export default function MainComponent({ prop1, prop2 }: Props) {
  // 状态
  const [state, setState] = useState()
  
  // 回调函数
  const handler = useCallback(() => {
    // ...
  }, [])
  
  // 副作用
  useEffect(() => {
    // ...
  }, [])
  
  // 渲染
  return (
    <div>...</div>
  )
}
```

### 3.2 组件拆分原则

```typescript
// ✅ 单一职责：每个组件只做一件事
function StockTable() { /* 只负责表格渲染 */ }
function FilterPanel() { /* 只负责筛选条件 */ }

// ✅ 可复用性：通用逻辑提取为自定义 Hook
function useStockData() {
  const [stocks, setStocks] = useState<StocksResponse | null>(null)
  const [loading, setLoading] = useState(false)
  
  useEffect(() => {
    // 加载逻辑
  }, [])
  
  return { stocks, loading }
}

// ❌ 避免巨型组件（超过 300 行考虑拆分）
```

---

## 🔒 四、安全性规范

### 4.1 XSS 防护

```typescript
// ❌ 禁止 dangerouslySetInnerHTML
<div dangerouslySetInnerHTML={{ __html: htmlContent }} /> // ❌

// ✅ 使用文本内容
<div>{textContent}</div> // ✅
```

### 4.2 外部链接安全

```typescript
// ✅ 必须添加 rel="noopener noreferrer"
<a 
  href={url} 
  target="_blank" 
  rel="noopener noreferrer"
>
  链接文本
</a>
```

### 4.3 敏感信息保护

```typescript
// ❌ 禁止硬编码密钥
const API_KEY = 'sk-123456789' // ❌

// ✅ 使用环境变量
const API_KEY = import.meta.env.VITE_API_KEY // ✅
```

### 4.4 URL 参数编码

```typescript
// ✅ 使用 URLSearchParams
const params = new URLSearchParams()
params.set('filters', filters.join(','))
params.set('sort_by', sortBy)

// ❌ 禁止手动拼接
const url = `/api/stocks?filters=${filters}&sort_by=${sortBy}` // ❌
```

---

## ⚡ 五、性能优化规范

### 5.1 列表渲染

```typescript
// ✅ 使用唯一 key
{rows.map(row => (
  <tr key={row.ts_code}> // ✅ 使用唯一标识
    {/* ... */}
  </tr>
))}

// ❌ 禁止使用 index 作为 key
{rows.map((row, index) => (
  <tr key={index}> // ❌ 可能导致渲染问题
    {/* ... */}
  </tr>
))}
```

### 5.2 事件处理优化

```typescript
// ✅ 使用 useCallback
const handleClick = useCallback(() => {
  // ...
}, [dependency])

// ✅ 小函数可以直接内联
<button onClick={() => setExpanded(!expanded)}>
```

### 5.3 避免不必要的重渲染

```typescript
// ✅ 使用 React.memo（纯展示组件）
const PureComponent = React.memo(function PureComponent(props) {
  return <div>{props.value}</div>
})

// ✅ 状态提升，避免重复状态
// ❌ 避免在子组件中维护与父组件同步的状态
```

### 5.4 大数据量处理

```typescript
// ✅ 分页加载，避免一次性渲染大量数据
const LIMIT = 100
const [offset, setOffset] = useState(0)

// ⚠️ 如果数据量超过 1000，考虑虚拟滚动（Phase 5 优化）
```

---

## 🛡️ 六、健壮性规范

### 6.1 空值处理

```typescript
// ✅ 明确处理 null/undefined
function fmt(val: unknown): string {
  if (val === null || val === undefined) return '-'
  return String(val)
}

// ✅ 可选链操作符
const name = stock?.name ?? '-'

// ❌ 避免隐式转换
const value = stock.name || '-' // ❌ 空字符串也会被替换
```

### 6.2 错误处理

```typescript
// ✅ API 调用必须有错误处理
fetchStocks(params)
  .then(setStocks)
  .catch(e => {
    if (e.name !== 'AbortError') {
      setError(e.message)
    }
  })

// ✅ 显示友好错误提示
if (error) {
  return <div className="text-red-400">错误：{error}</div>
}
```

### 6.3 加载状态

```typescript
// ✅ 显示加载状态
{loading && (
  <div className="animate-pulse">加载中…</div>
)}

// ✅ 禁用按钮防止重复提交
<button disabled={loading}>提交</button>
```

### 6.4 边界条件

```typescript
// ✅ 分页边界处理
<button 
  disabled={offset === 0} 
  onClick={() => onPageChange(offset - limit)}
>
  上一页
</button>

<button 
  disabled={offset + limit >= total} 
  onClick={() => onPageChange(offset + limit)}
>
  下一页
</button>
```

---

## 📊 七、数据流规范

### 7.1 单向数据流

```typescript
// ✅ 父组件 → 子组件（通过 props）
function App() {
  const [stocks, setStocks] = useState<StocksResponse | null>(null)
  
  return <StockTable rows={stocks?.rows ?? []} />
}

// ❌ 禁止子组件直接修改父组件状态
```

### 7.2 状态提升

```typescript
// ✅ 共享状态提升到最近的共同父组件
function App() {
  const [activeFilters, setActiveFilters] = useState<string[]>([])
  
  return (
    <>
      <FilterPanel activeFilters={activeFilters} onToggle={setActiveFilters} />
      <StockTable activeFilters={activeFilters} />
    </>
  )
}
```

### 7.3 API 调用规范

```typescript
// ✅ 统一通过 api.ts 调用
import { fetchStocks } from './api'

// ❌ 禁止在组件中直接使用 fetch
fetch('/api/stocks') // ❌
```

---

## 🧪 八、测试规范（预留）

### 8.1 单元测试（Phase 5）

```typescript
// 待实现
import { render, screen } from '@testing-library/react'
import StockTable from './StockTable'

test('renders stock list', () => {
  render(<StockTable rows={[]} total={0} offset={0} limit={100} />)
  expect(screen.getByText('暂无匹配数据')).toBeInTheDocument()
})
```

---

## 📝 九、注释规范

### 9.1 函数注释

```typescript
/**
 * 格式化数值显示
 * @param key - 字段名
 * @param val - 原始值
 * @returns 格式化后的字符串
 */
function fmt(key: string, val: unknown): string {
  // ...
}
```

### 9.2 复杂逻辑注释

```typescript
// 计算总页数，至少为 1
const totalPages = Math.max(1, Math.ceil(total / limit))

// 隐式追加 ts_code 作为第二排序键（后端处理）
// 前端只需传递 sortBy 字段
```

### 9.3 TODO 注释

```typescript
// TODO: 待 schemas.py 完成后适配统一响应信封格式
// TODO: Phase 4 集成 KLineChart 组件
```

---

## ✅ 十、代码审查清单

每次提交代码前，必须自检以下项目：

### 10.1 逻辑正确性
- [ ] 算法实现正确
- [ ] 边界条件处理完整
- [ ] 状态流转清晰
- [ ] 无死循环或内存泄漏

### 10.2 安全性
- [ ] 无 XSS 风险
- [ ] 外部链接安全
- [ ] 无敏感信息泄露
- [ ] URL 参数正确编码

### 10.3 性能
- [ ] 列表使用唯一 key
- [ ] 事件处理使用 useCallback
- [ ] 避免不必要的重渲染
- [ ] 大数据量有分页或虚拟滚动

### 10.4 健壮性
- [ ] 空值处理完整
- [ ] 错误处理友好
- [ ] 加载状态显示
- [ ] 边界条件覆盖

### 10.5 可维护性
- [ ] 命名规范清晰
- [ ] 函数职责单一
- [ ] 关键逻辑有注释
- [ ] 代码结构合理

### 10.6 合规性
- [ ] 符合数据范围规定
- [ ] limit ≤ 200
- [ ] 无未来函数
- [ ] 遵循项目规范

---

## 🔄 十一、持续改进

### 11.1 发现问题
- 代码审查中发现的问题立即记录
- 用户反馈的问题及时修复
- 性能瓶颈持续优化

### 11.2 更新规范
- 新发现的最佳实践及时补充
- 过时的规范及时删除
- 定期回顾和更新本文档

### 11.3 经验分享
- 典型问题的解决方案记录到文档
- 优秀代码示例分享给团队
- 经验教训纳入下一轮 PDCA

---

**最后更新**：2026-05-31  
**维护人**：Lingma-FE
