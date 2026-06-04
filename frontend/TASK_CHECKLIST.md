# 前端开发任务清单 - Lingma-FE

**工作目录**：`/Users/zhangk/workspace/Quantitative_trading/src/frontend`  
**创建日期**：2026-05-31  

---

## 📋 Phase 1.3：前端基础组件迁移

### 任务 1：创建 StockTable.tsx

**文件路径**：`src/components/StockTable.tsx`  
**参考源**：`/Users/zhangk/workspace/stock_screener/frontend/src/components/StockTable.tsx`  
**预计行数**：~210 行  
**难度**：★★（中）

#### 功能清单
- [ ] **F1.1** 显示股票列表（12个默认列）
  - 代码、名称、行业、涨跌幅、收盘价、PE、PB、总市值、成交额、换手率、量比、净流入
- [ ] **F1.2** 支持展开/收起额外字段
  - 开盘、最高、最低、昨收、涨跌额、成交量等 25+ 字段
  - 动态显示激活的 pattern_* 形态字段
- [ ] **F1.3** 点击列头排序
  - 支持升序/降序切换
  - 可排序字段：pct_chg, close, total_mv, amount, turnover_rate, volume_ratio, net_mf_amount, pe, pb, vol_ratio_5
  - 排序图标显示（↑↓）
- [ ] **F1.4** 分页功能
  - 上一页/下一页按钮
  - 显示当前页/总页数
  - 显示总记录数
  - 边界处理：第一页禁用"上一页"，最后一页禁用"下一页"
- [ ] **F1.5** 颜色标记
  - 涨跌幅 > 0：红色（text-red-400）
  - 涨跌幅 < 0：绿色（text-green-400）
  - 净流入 > 0：红色
  - 净流入 < 0：绿色
- [ ] **F1.6** 股票代码链接
  - 点击跳转到同花顺个股页面
  - 使用 `target="_blank" rel="noopener noreferrer"`
  - 点击链接不触发行点击事件
- [ ] **F1.7** onRowClick 回调
  - 可选属性：`onRowClick?: (code: string) => void`
  - 点击行时触发（为后续 K线联动预留）
  - 点击链接时不触发

#### 技术实现要点
- [ ] **T1.1** 使用 `StockRow` 类型定义
- [ ] **T1.2** 实现 fmt() 函数格式化数值
  - 涨跌幅：`+X.XX%` 或 `-X.XX%`
  - 换手率：`X.XX%`
  - 总市值/流通市值：万元转亿（除以 10000）
  - 成交额：万元转亿
  - 净流入：元转万（除以 1000）
  - 形态字段：1 显示 ●，0 显示 ○
  - 其他数值：保留两位小数
  - null/undefined 显示 `-`
- [ ] **T1.3** 实现 cellColor() 函数确定颜色
- [ ] **T1.4** 使用 useState 管理展开状态
- [ ] **T1.5** 表格使用 sticky header（滚动时表头固定）
- [ ] **T1.6** 偶数行和奇数行背景色交替
- [ ] **T1.7** 空数据提示："暂无匹配数据"

#### 代码审查（6维度）
- [ ] **逻辑正确性**：排序、分页、状态管理正确
- [ ] **安全性**：无 XSS 风险，外部链接安全
- [ ] **性能**：使用 key、避免不必要的重渲染
- [ ] **健壮性**：空值处理、异常捕获
- [ ] **可维护性**：命名规范、注释完备、结构清晰
- [ ] **合规性**：符合数据范围规定、limit ≤ 200

#### 验收标准
- [ ] TypeScript 编译无错误
- [ ] 与 types.ts 完全兼容
- [ ] 支持 100+ 条数据流畅渲染
- [ ] 分页边界条件正确
- [ ] 排序功能正常
- [ ] 颜色标记正确
- [ ] 代码审查全部通过

---

### 任务 2：创建 App.tsx

**文件路径**：`src/App.tsx`  
**参考源**：`/Users/zhangk/workspace/stock_screener/frontend/src/App.tsx`  
**预计行数**：~170 行  
**难度**：★★（中）

#### 功能清单
- [ ] **F2.1** 整合三大组件
  - StatusBar（状态栏）
  - FilterPanel（筛选面板）
  - StockTable（股票表格）
- [ ] **F2.2** 状态管理
  - activeFilters：选中的筛选条件数组
  - activeIndustries：选中的行业数组
  - activeAreas：选中的地区数组
  - sortBy：排序字段（默认 'pct_chg'）
  - sortAsc：排序方向（默认 false，降序）
  - offset：分页偏移（默认 0）
  - LIMIT：每页数量（常量 100）
- [ ] **F2.3** 数据加载
  - 组件挂载时加载元数据（fetchMeta）
  - 筛选/排序/分页变化时加载股票列表（fetchStocks）
  - 使用 AbortController 取消过期请求
- [ ] **F2.4** 筛选条件管理
  - toggleFilter：切换筛选条件
  - toggleIndustry：切换行业
  - toggleArea：切换地区
  - clearAll：清空所有条件
  - removeFilter：从 StatusBar 删除单个条件（支持 __industry__ 和 __area__ 前缀）
- [ ] **F2.5** 排序管理
  - handleSort：点击列头排序
  - 同一字段再次点击切换升降序
  - 不同字段点击默认降序
- [ ] **F2.6** 分页管理
  - 筛选/排序变化时重置 offset 为 0
  - 上一页：offset - LIMIT
  - 下一页：offset + LIMIT
- [ ] **F2.7** 加载状态
  - 查询中显示"查询中…"提示
  - 使用 animate-pulse 动画
- [ ] **F2.8** 错误处理
  - 显示错误信息
  - 全屏居中显示

#### 技术实现要点
- [ ] **T2.1** 使用 useState 管理所有状态
- [ ] **T2.2** 使用 useCallback 优化事件处理函数
  - toggleFilter、toggleIndustry、toggleArea、clearAll、removeFilter、handleSort
- [ ] **T2.3** 使用 useEffect 处理副作用
  - useEffect 1：挂载时加载元数据（仅执行一次）
  - useEffect 2：筛选/排序/分页变化时加载股票列表
- [ ] **T2.4** 使用 AbortController 取消请求
  - 每次请求创建新的 controller
  - cleanup 函数中 abort 前一次请求
  - 捕获 AbortError 不显示错误
- [ ] **T2.5** 构建 filterLabels 映射
  - 从 meta.groups 中提取字段标签
  - 用于 StatusBar 显示
- [ ] **T2.6** 布局结构
  - 外层：flex flex-col h-screen bg-gray-900 text-gray-200
  - 顶部：StatusBar
  - 主体：flex flex-1 overflow-hidden
    - 左侧：FilterPanel（固定宽度 56）
    - 右侧：main（flex-1，相对定位）
      - 加载提示：absolute top-2 right-4
      - StockTable：flex-1

#### 代码审查（6维度）
- [ ] **逻辑正确性**：状态流转、副作用处理正确
- [ ] **安全性**：无敏感信息泄露
- [ ] **性能**：useCallback 优化、请求取消机制
- [ ] **健壮性**：错误处理、加载状态
- [ ] **可维护性**：状态管理清晰、函数职责单一
- [ ] **合规性**：LIMIT=100 ≤ 200

#### 验收标准
- [ ] TypeScript 编译无错误
- [ ] 与现有组件无缝集成
- [ ] 筛选、排序、分页功能正常
- [ ] 并发请求正确处理
- [ ] 错误提示友好
- [ ] 代码审查全部通过

---

### 任务 3：编译验证

**执行时机**：任务 1 和任务 2 完成后  
**难度**：★（易）

#### 验证清单
- [ ] **V1** 运行 `npm run build` 无错误
- [ ] **V2** 运行 `tsc --noEmit` 无类型错误
- [ ] **V3** 检查控制台无警告
- [ ] **V4** 手动启动开发服务器测试基本功能
  ```bash
  cd /Users/zhangk/workspace/Quantitative_trading/src/frontend
  npm run dev
  ```

#### 常见问题处理
- [ ] **P1** 类型不匹配：检查 types.ts 定义
- [ ] **P2** 导入路径错误：检查相对路径
- [ ] **P3** 缺少依赖：检查 package.json
- [ ] **P4** CSS 类名错误：检查 TailwindCSS 类名

---

### 任务 4：提交验收

**执行时机**：编译验证通过后  
**难度**：★（易）

#### 验收准备
- [ ] **A1** 整理代码变更清单
- [ ] **A2** 编写提交说明（commit message）
- [ ] **A3** 准备功能演示截图或录屏
- [ ] **A4** 更新 WORK_PLAN.md 进度

#### 提交内容
```
feat(frontend): 完成 Phase 1.3 前端基础组件迁移

- 新增 StockTable.tsx：股票表格组件，支持排序、分页、字段展开
- 新增 App.tsx：主应用组件，整合筛选、表格功能
- 保持与现有 types.ts、api.ts、FilterPanel、StatusBar 兼容
- 遵循项目规范和代码审查要求

待办事项：
- 待 schemas.py 完成后适配统一响应信封格式
- 待 schemas.py 确认后严格对齐 types.ts
- Phase 4 开发 KLineChart.tsx
```

---

## 📊 进度跟踪

### 当前状态
| 任务 | 状态 | 开始时间 | 完成时间 | 备注 |
|------|------|---------|---------|------|
| 任务 1：StockTable.tsx | ✅ 已完成 | 2026-05-31 | 2026-05-31 | 224行，含onRowClick支持 |
| 任务 2：App.tsx | ✅ 已完成 | 2026-05-31 | 2026-05-31 | 165行，整合三大组件 |
| 任务 3：编译验证 | ✅ 已完成 | 2026-05-31 | 2026-05-31 | TypeScript编译通过 |
| 任务 4：提交验收 | ✅ 已完成 | 2026-05-31 | 2026-05-31 | 验收报告已生成 |

### 完成统计
- **总任务数**：4
- **已完成**：4
- **完成率**：100%

---

## 📝 问题记录

### 问题 1：响应信封格式未适配
**发现时间**：计划阶段  
**影响**：api.ts 直接返回 JSON，未解析 `{"code", "message", "data"}`  
**解决方案**：待 schemas.py 完成后，在 api.ts 中增加解包逻辑  
**优先级**：P0（高）  
**状态**：⏳ 待处理

### 问题 2：types.ts 未严格对齐 schemas.py
**发现时间**：计划阶段  
**影响**：当前 types.ts 是临时版本，可能与最终 schema 不一致  
**解决方案**：待 schemas.py 确认后，重新生成 types.ts  
**优先级**：P0（高）  
**状态**：⏳ 待处理

### 问题 3：K线功能缺失
**发现时间**：计划阶段  
**影响**：App.tsx 不包含 KLineChart 区域  
**解决方案**：Phase 4 开发 KLineChart.tsx 并集成到 App.tsx  
**优先级**：P1（中）  
**状态**：🚫 暂不处理

---

## ✅ 负责人确认

**请逐项勾选确认**：

### 计划确认
- [ ] 我已阅读并理解任务清单
- [ ] 我同意任务分解和实施顺序
- [ ] 我对验收标准无异议

### 开始执行
- [ ] 我可以开始执行任务 1（回复"开始任务1"）

**确认人**：_______________  
**确认日期**：_______________

---

**备注**：每个任务完成后，我会向您汇报并进行 Check（检查）阶段。请您及时验收，如有问题立即反馈。
