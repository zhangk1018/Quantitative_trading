# 前端依赖快速参考卡

**项目**: Quantitative Trading Frontend  
**最后更新**: 2026-05-31

---

## 🚀 核心依赖（您需要了解的）

### 1️⃣ React (v18.3.1)
```typescript
// 常用 API
import { useState, useEffect, useCallback } from 'react'

// 示例
const [count, setCount] = useState(0)
```
📖 **学习**: https://zh-hans.react.dev/learn

---

### 2️⃣ TypeScript (v5.4.5)
```typescript
// 类型标注
const name: string = "张三"
const age: number = 25
const items: string[] = ["a", "b"]

// 接口定义
interface User {
  id: number
  name: string
}
```
📖 **学习**: https://www.typescriptlang.org/zh/docs/

---

### 3️⃣ TailwindCSS (v3.4.3)
```tsx
// 直接用类名写样式
<div className="flex items-center justify-between p-4 bg-white rounded-lg shadow">
  <span className="text-lg font-bold text-gray-900">标题</span>
</div>
```

**常用类名速查**:
- 布局: `flex`, `grid`, `block`, `inline`
- 间距: `p-4` (内边距), `m-2` (外边距), `gap-2` (间隙)
- 尺寸: `w-full`, `h-screen`, `max-w-md`
- 颜色: `bg-blue-500`, `text-white`, `border-gray-300`
- 字体: `text-sm`, `font-bold`, `text-center`
- 响应式: `md:flex`, `lg:grid-cols-3`

📖 **学习**: https://tailwindcss.com/docs

---

## 🛠️ 工具链（自动工作，无需关心）

| 工具 | 版本 | 作用 | 命令 |
|------|------|------|------|
| **Vite** | 5.2.11 | 开发服务器 + 构建工具 | `npm run dev` |
| **tsc** | 5.4.5 | TypeScript 编译器 | `npx tsc --noEmit` |
| **tailwindcss** | 3.4.3 | CSS 框架 | 自动运行 |
| **autoprefixer** | 10.4.19 | 浏览器前缀 | 自动运行 |

---

## 📦 完整依赖列表

### 生产依赖（会打包到最终代码）
```json
{
  "react": "^18.3.1",              // React 核心库
  "react-dom": "^18.3.1",          // React DOM 渲染器
  "lightweight-charts": "^4.1.0"   // K线图表库（Phase 4 使用）
}
```

### 开发依赖（仅开发时使用）
```json
{
  "@types/react": "^18.3.1",       // React 类型定义
  "@types/react-dom": "^18.3.0",   // ReactDOM 类型定义
  "@vitejs/plugin-react": "^4.3.0",// Vite React 插件
  "autoprefixer": "^10.4.19",      // CSS 浏览器前缀
  "postcss": "^8.4.38",            // CSS 后处理器
  "tailwindcss": "^3.4.3",         // CSS 框架
  "typescript": "^5.4.5",          // TypeScript 编译器
  "vite": "^5.2.11"                // 构建工具
}
```

---

## 💻 常用命令

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 类型检查
npx tsc --noEmit

# 构建生产版本
npm run build

# 预览生产构建
npm run preview

# 查看依赖树
npm list --depth=0

# 更新依赖
npm update
```

---

## ❓ 常见问题

### Q: node_modules 太大怎么办？
**A**: 这是正常的！不要删除，不要提交到 Git。

### Q: 依赖冲突怎么办？
**A**: 
```bash
rm -rf node_modules package-lock.json
npm install
```

### Q: 如何查看某个包的文档？
**A**: 
```bash
npm info [包名]
# 或访问 https://www.npmjs.com/package/[包名]
```

### Q: 需要学习所有包吗？
**A**: **不需要！** 只需掌握 React + TypeScript + TailwindCSS 即可。

---

## 🎯 学习优先级

### 🔴 必须掌握
1. React 基础（组件、props、state）
2. React Hooks（useState, useEffect, useCallback）
3. TypeScript 基础类型（string, number, boolean, interface）
4. TailwindCSS 常用类名

### 🟡 建议了解
5. Vite 配置（如果需要自定义）
6. TypeScript 高级类型（泛型、联合类型）
7. React 性能优化（memo, useMemo）

### 🟢 无需深入
8. PostCSS 工作原理
9. Autoprefixer 配置
10. Vite 插件开发

---

## 📚 推荐学习路径

**第 1 周**: React 基础 + JSX 语法  
**第 2 周**: React Hooks + 组件通信  
**第 3 周**: TypeScript 基础 + 类型标注  
**第 4 周**: TailwindCSS 布局 + 样式  
**第 5 周**: 实战项目练习  

---

## 🔗 快速链接

- **详细依赖文档**: [DEPENDENCIES_GUIDE.md](./DEPENDENCIES_GUIDE.md)
- **工作计划**: [WORK_PLAN.md](./WORK_PLAN.md)
- **任务清单**: [TASK_CHECKLIST.md](./TASK_CHECKLIST.md)
- **编码规范**: [CODING_STANDARDS.md](./CODING_STANDARDS.md)

---

**提示**: 将此文件加入书签，随时查阅！⭐
