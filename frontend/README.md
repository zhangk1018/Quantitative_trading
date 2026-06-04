# 前端开发工作区 - 方舟

**工作目录**：`/Users/zhangk/workspace/Quantitative_trading/frontend`  
**负责人**：方舟（前端 AI 工程师）  
**创建日期**：2026-05-31  
**最后更新**：2026-06-04

---

## 📚 文档导航

### 核心文档
| 文档 | 说明 | 状态 |
|------|------|------|
| [PROJECT_DESIGN.md](./PROJECT_DESIGN.md) | **项目设计文档** | 包含 Day 3 工作总结 + 缓存架构 |
| [WORK_PLAN.md](./WORK_PLAN.md) | **工作计划** | 任务跟踪、进度、待办 |
| [TASK_CHECKLIST.md](./TASK_CHECKLIST.md) | **任务清单** | 逐项任务分解 |
| [RUNNING_GUIDE.md](./RUNNING_GUIDE.md) | **运行指南** | 启动、调试、构建 |
| [CODING_STANDARDS.md](./CODING_STANDARDS.md) | **编程规范** | TypeScript、React、TailwindCSS |

### 上级文档
| 文档 | 路径 |
|------|------|
| 项目工作规则 | `../../.trae/rules/project_rules.md` |
| AI 协作记录 | `../../docs/AI_COLLABORATION.md` |
| 量化系统融合 - 实施规划方案 | `../../docs/量化系统融合开发 - 实施规划方案.md` |

---

## 🎯 当前进度（2026-06-04）

| 阶段 | 状态 | 备注 |
|------|------|------|
| Phase 1.3 - 基础组件迁移 | ✅ | StockTable/App/FilterPanel/StatusBar |
| Phase 2 - 巡检问题修复 | ✅ | KDJ/RSI 越界、.env 保护、依赖补齐 |
| Day 2 - K线图组件 | ✅ | lightweight-charts 集成 |
| **Day 3 - 形态识别 + 三级缓存** | ✅ | 详见 PROJECT_DESIGN.md Day 3 工作总结 |
| Day 4+ - 待规划 | ⏳ | K线叠加指标线 / 单元测试 |

---

## 🚀 快速开始

```bash
# 安装依赖
npm install

# 启动开发服务器（默认 5173）
npm run dev

# 构建生产版本
npm run build

# 类型检查
npx tsc --noEmit
```

**前后端启动**（推荐）：
```bash
bash ../start_service.sh start    # 启动
bash ../start_service.sh restart  # 重启
bash ../start_service.sh status   # 状态
```

---

## 📁 目录结构（精简版）

```
frontend/
├── PROJECT_DESIGN.md         # 项目设计文档 ⭐
├── WORK_PLAN.md              # 工作计划
├── TASK_CHECKLIST.md         # 任务清单
├── RUNNING_GUIDE.md          # 运行指南
├── CODING_STANDARDS.md       # 编码规范
├── README.md                 # 本文件
├── package.json
├── vite.config.ts            # 含 /api 代理
├── tailwind.config.js
└── src/
    ├── main.tsx              # 应用入口
    ├── App.tsx               # 主应用组件 ⭐
    ├── api.ts                # API 封装
    ├── types.ts              # TypeScript 类型
    ├── index.css
    ├── components/
    │   ├── StockTable.tsx    # 股票表格 ⭐
    │   ├── FilterPanel.tsx   # 筛选面板
    │   ├── StatusBar.tsx     # 状态栏
    │   └── KLineChart.tsx    # K线 + 成交量 (Day 2) ⭐
    ├── hooks/                # 自定义 Hooks (Day 3)
    │   ├── useKLineData.ts   # 单股 K线 + 缓存 + 增量
    │   └── useBatchKLine.ts  # 批量形态 + 三级缓存
    ├── utils/                # 工具模块 (Day 3)
    │   ├── patternDetector.ts    # 5 个高胜率形态算法
    │   ├── patternCache.ts       # 形态结果缓存
    │   ├── klineCache.ts         # K线 LRU 缓存
    │   └── indicators.ts         # 技术指标计算
    └── mocks/
        └── meta.ts           # 字段元数据 Mock
```

---

## 🔗 相关链接

- [React 官方文档](https://react.dev)
- [TypeScript 手册](https://www.typescriptlang.org/docs)
- [TailwindCSS 文档](https://tailwindcss.com/docs)
- [Vite 指南](https://vitejs.dev/guide/)
- [lightweight-charts 文档](https://tradingview.github.io/lightweight-charts/)

---

## 📝 变更记录

| 日期 | 版本 | 变更内容 | 维护人 |
|------|------|---------|--------|
| 2026-05-31 | v1.0 | 初始版本 | Lingma-FE |
| 2026-06-04 | v1.4 | 精简文档导航，标记 Day 3 工作，移除已废弃文档引用 | 方舟 |

---

**最后更新**：2026-06-04  
**维护人**：方舟（前端 AI 工程师）
