# 1. 生成 package.json 文件（项目的身份证）
npm init -y

# 2. 安装核心业务依赖（React、路由、UI库、状态管理、图表等）
npm install react react-dom react-router-dom antd @ant-design/icons zustand @tanstack/react-query axios lightweight-charts dayjs

# 3. 安装开发工具依赖（Vite构建工具、TypeScript、Tailwind CSS等）
npm install -D vite @vitejs/plugin-react typescript @types/react @types/react-dom tailwindcss postcss autoprefixer

# 4. 初始化 Tailwind CSS 配置文件
npx tailwindcss init -p