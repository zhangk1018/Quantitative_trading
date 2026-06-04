# 前端运行指南

## 🚀 快速开始

### 方式一：使用启动脚本（推荐）

```bash
cd /Users/zhangk/workspace
./start_system.sh
```

这会自动启动后端和前端服务。

---

### 方式二：手动启动

#### 第一步：启动后端服务

打开终端 1：

```bash
cd /Users/zhangk/workspace/stock_screener/backend

# 首次运行需要安装依赖
pip install -r requirements.txt

# 启动后端（端口 8000）
python main.py
```

或使用 uvicorn：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**验证后端**：访问 http://localhost:8000/api/meta

---

#### 第二步：启动前端服务

打开终端 2：

```bash
cd /Users/zhangk/workspace/Quantitative_trading/src/frontend

# 首次运行需要安装依赖
npm install

# 启动前端开发服务器（端口 5173）
npm run dev
```

**访问前端**：在浏览器中打开 http://localhost:5173

---

## 📋 可用命令

### 前端命令

```bash
# 开发模式（支持热更新）
npm run dev

# 生产构建
npm run build

# 预览生产版本
npm run preview
```

### 后端命令

```bash
# 启动服务
python main.py

# 或使用 uvicorn
uvicorn main:app --reload --port 8000

# 查看 API 文档
# 访问 http://localhost:8000/docs
```

---

## 🔧 配置说明

### 前端代理配置

文件：`vite.config.ts`

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',  // 后端地址
      changeOrigin: true,
    },
  },
}
```

所有 `/api/*` 请求会自动转发到后端。

### 后端 CORS 配置

文件：`stock_screener/backend/main.py`

已配置允许来自 `http://localhost:5173` 的跨域请求。

---

## ⚠️ 常见问题

### 1. 前端无法连接后端

**症状**：页面显示 "failed to fetch" 或网络错误

**检查步骤**：
```bash
# 1. 确认后端是否运行
curl http://localhost:8000/api/meta

# 2. 检查端口占用
lsof -i :8000

# 3. 查看后端日志
# 在后端终端查看是否有错误信息
```

**解决方法**：
- 确保后端服务正在运行
- 检查防火墙设置
- 确认端口未被占用

---

### 2. 端口被占用

**症状**：启动时提示 "Port XXXX is already in use"

**解决方法**：
```bash
# 查找占用端口的进程
lsof -i :8000  # 后端
lsof -i :5173  # 前端

# 杀死进程（替换 PID）
kill -9 <PID>

# 或者更改端口
# 前端：修改 vite.config.ts 中的 port
# 后端：启动时指定不同端口 uvicorn main:app --port 8001
```

---

### 3. 依赖未安装

**前端依赖缺失**：
```bash
cd /Users/zhangk/workspace/Quantitative_trading/src/frontend
npm install
```

**后端依赖缺失**：
```bash
cd /Users/zhangk/workspace/stock_screener/backend
pip install -r requirements.txt
```

---

### 4. TypeScript 编译错误

**症状**：运行 `npm run dev` 时出现类型错误

**解决方法**：
```bash
# 检查类型定义
npx tsc --noEmit

# 如果有错误，根据提示修复
# 常见原因：types.ts 与后端 schema 不一致
```

---

### 5. 数据文件缺失

**症状**：后端启动失败，提示找不到 data.parquet

**解决方法**：
```bash
# 检查数据文件是否存在
ls -lh /Users/zhangk/workspace/stock_screener/data.parquet

# 如果不存在，需要从源项目复制或重新生成
cp /path/to/source/data.parquet /Users/zhangk/workspace/stock_screener/
```

---

## 🌐 访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端应用 | http://localhost:5173 | 主界面 |
| 后端 API | http://localhost:8000 | API 根路径 |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| 元数据接口 | http://localhost:8000/api/meta | 测试后端是否正常 |
| 股票列表 | http://localhost:8000/api/stocks | 测试股票数据 |

---

## 🛑 停止服务

### 使用启动脚本
按 `Ctrl + C` 停止所有服务

### 手动启动
- **前端**：在前端终端按 `Ctrl + C`
- **后端**：在后端终端按 `Ctrl + C`

---

## 📊 系统架构

```
用户浏览器
    ↓
http://localhost:5173 (Vite 开发服务器)
    ↓ (代理 /api 请求)
http://localhost:8000 (FastAPI 后端)
    ↓
读取 data.parquet 文件
    ↓
返回 JSON 数据
```

---

## 🔍 调试技巧

### 前端调试

1. **浏览器开发者工具**
   - F12 打开开发者工具
   - Console 标签查看 JavaScript 错误
   - Network 标签查看 API 请求

2. **Vite 日志**
   - 前端终端会显示编译错误和警告
   - 热更新状态也会显示在这里

### 后端调试

1. **API 测试**
   ```bash
   # 测试元数据接口
   curl http://localhost:8000/api/meta
   
   # 测试股票列表
   curl "http://localhost:8000/api/stocks?limit=5"
   ```

2. **Swagger UI**
   - 访问 http://localhost:8000/docs
   - 可以在线测试所有 API 接口

3. **后端日志**
   - 后端终端会显示请求日志和错误信息

---

## 📝 开发建议

1. **保持两个终端窗口**
   - 一个用于后端
   - 一个用于前端
   - 方便查看各自的日志

2. **先启动后端，再启动前端**
   - 确保后端正常运行后再启动前端
   - 避免前端启动后找不到后端

3. **修改代码后自动刷新**
   - 前端支持热更新，保存文件后自动刷新
   - 后端使用 `--reload` 参数也会自动重启

4. **定期清理缓存**
   ```bash
   # 如果遇到问题，可以尝试清理
   rm -rf node_modules/.vite
   npm run dev
   ```

---

## 🎯 下一步

成功启动后，您可以：

1. ✅ 浏览股票列表
2. ✅ 使用筛选条件过滤股票
3. ✅ 点击列头排序
4. ✅ 翻页浏览更多数据
5. ⏳ Phase 4：查看 K 线图（待开发）

祝您使用愉快！🎉
