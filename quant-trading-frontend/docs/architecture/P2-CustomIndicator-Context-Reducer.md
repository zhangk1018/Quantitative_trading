# P2 状态层设计文档：自编指标 Context+Reducer

> **适用范围**：V1.0 自编指标模块（条件构建器扩展）
> **基座依赖**：[P1.1 数据模型](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/types/customIndicator.ts) + [P1.2 存储层](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/utils/customIndicatorStorage.ts)（K 评审通过）
> **被审稿方**：K
> **审查状态**：⏳ 待 K 评审
> **生成日期**：2026-06-16

---

## 一、设计目标

为 V1.0 自编指标模块提供全局状态管理：
1. **集中管理**：在 ScreenerContext 中统一管理自编指标列表 + 当前 Tab，避免散落在多个组件的 useState
2. **数据流单向**：UI → dispatch(action) → reducer → state → UI，禁止直接修改 state
3. **存储层解耦**：Context 不直接读写 localStorage，所有持久化操作通过 `customIndicatorStorage` API
4. **启动自动加载**：`ScreenerProvider` 挂载时自动从 localStorage 加载自编指标，组件无需关心初始化逻辑
5. **过渡期兼容**：V1.0 阶段失效检测由 UI 层判断（FilterCondition 不扩展 invalid 字段），但 reducer 层预留 `RESOLVE_MISSING_INDICATORS` action 供未来扩展

---

## 二、State 扩展（V1.0 新增 2 字段）

`ScreenerState` 在原有 15 字段基础上新增：

| 字段 | 类型 | 初值 | 作用 |
|------|------|------|------|
| `customIndicators` | `CustomIndicator[]` | `[]` | 当前用户的自编指标列表（**仅未软删除的**，UI 层通过 `listCustomIndicators` 加载） |
| `activeIndicatorTab` | `IndicatorTab` (`'system' \| 'custom'`) | `'system'` | 条件构建器当前激活的 Tab（系统预设 / 我的自编） |

**关键决策**：
- `customIndicators` 存在 Context 而非组件局部 state：跨组件共享（如 ConditionBuilder、ConditionPicker、CustomIndicatorModal 都需访问）
- 启动时 `useEffect` 自动加载，确保打开页面后立即可见
- 不存储软删除的指标（由 storage API 过滤），保持 Context 内存最小化
- 软删除检测需要时调 `listAllCustomIndicators()` 获取全量

**未引入**（V1.0 过渡）：
- `FilterCondition` 未扩展 `sourceId / invalid / invalidReason` 字段（K 评审认可设计，UI 层自行判断失效）
- `tempParams / tempThreshold / tempOperator` 三层临时参数暂未挂到 state（**保留** 在 `PlanCondition` 数据模型中，**P5.1** 才进入 reducer）

---

## 三、Action 扩展（V1.0 新增 7 个）

| Action | Payload | 行为 | 测试用例 |
|--------|---------|------|---------|
| `LOAD_CUSTOM_INDICATORS` | `CustomIndicator[]` | 整体替换 `customIndicators`（启动加载用） | `LOAD_CUSTOM_INDICATORS 加载 3 个` |
| `ADD_CUSTOM_INDICATOR` | `CustomIndicator` | 插入到列表头部（按 updatedAt 倒序） | `ADD_CUSTOM_INDICATOR 插入到列表头部` |
| `UPDATE_CUSTOM_INDICATOR` | `CustomIndicator` | 按 id 替换（未找到 id 则列表不变） | `UPDATE_CUSTOM_INDICATOR 替换指定 id` / `未匹配 id 列表不变` |
| `REMOVE_CUSTOM_INDICATOR` | `string`（id） | 从列表过滤 | `REMOVE_CUSTOM_INDICATOR 从列表移除` |
| `SET_INDICATOR_TAB` | `IndicatorTab` | 切换 Tab | `SET_INDICATOR_TAB 切换到 custom` / `切回 system` |
| `RESOLVE_MISSING_INDICATORS` | （无） | **V1.0 过渡：noop**，保留 action 供未来扩展 | `RESOLVE_MISSING_INDICATORS 为 noop` |
| `IMPORT_CUSTOM_INDICATORS` | `CustomIndicator[]` | 按 id 去重合并（已存在 id 跳过） | `IMPORT_CUSTOM_INDICATORS 合并新指标（去重 id）` |

**关键决策**：

### 3.1 启动加载不感知 storage
- `LOAD_CUSTOM_INDICATORS` 只接收 `CustomIndicator[]`，不直接调 storage API
- 由 `ScreenerProvider` 的 `useEffect` 在挂载时调 `loadFromStorage()` 后 dispatch
- **理由**：reducer 保持纯函数特性，不含副作用（不直接读 localStorage / 调 fetch）
- 副作用隔离：`ScreenerProvider` 是唯一持有"读 storage"逻辑的地方，reducer 仅做数据转换

### 3.2 ADD/UPDATE 都直接替换，不走 storage
- reducer 不调 `saveCustomIndicator()`，不读 localStorage
- 组件层先调 storage API 持久化，成功后 dispatch action 更新 Context
- **理由**：保持 reducer 纯函数；storage 失败时（如 localStorage 不可用）Context 与 storage 可能短暂不一致，但 UI 层可通过 reload 重新同步
- **典型流程**（P3.1 CustomIndicatorModal）：
  ```ts
  const created = saveCustomIndicator(formValues);  // 1) 持久化
  dispatch({ type: 'ADD_CUSTOM_INDICATOR', payload: created });  // 2) 更新 state
  ```

### 3.3 IMPORT 按 id 去重（不按 name）
- 导入文件来源可能是其他用户的导出（虽然 V1.0 限定 mock_user，但 V2.0 会按 userId 隔离）
- 按 `id` 去重是**幂等导入**的安全选择
- **name 唯一性**由 storage 层的 `isNameTaken` 校验保证（导入时已存在的 name 会被计入 name_duplicate 错误并跳过）
- **为什么不在 reducer 层做 name 去重**：reducer 是纯函数，无法读取"当前 storage 中存在的 name 列表"（要读 storage 就是副作用）；name 校验应在 storage 层的 `importCustomIndicators` 中完成

### 3.4 RESOLVE_MISSING_INDICATORS 设计为 noop
- V1.0 阶段 `FilterCondition` 不含 `sourceId / invalid` 字段
- 失效检测由 UI 层（`ConditionBuilder.tsx`）在渲染时通过 `state.customIndicators.some()` 自行判断
- reducer 保留 action 是**架构对称性**：未来若 `FilterCondition` 扩展 `invalid` 字段，reducer 层只需填充该逻辑，UI 层调用方式不变
- **示例**（P5.2 实施时）：
  ```ts
  case 'RESOLVE_MISSING_INDICATORS': {
    if (!state.filterTree) return state;
    const validIds = new Set(state.customIndicators.map(i => i.id));
    return {
      ...state,
      filterTree: {
        conditions: state.filterTree.conditions.map(c => ({
          ...c,
          // 假设 c 增加 sourceId 字段
          invalid: c.sourceId ? !validIds.has(c.sourceId) : false,
        })),
      },
    };
  }
  ```

### 3.5 SET_MARKET / RESET_ALL 不清空 customIndicators
- 自编指标属于"用户长期数据资产"，与"当前选股会话状态"语义正交
- 切换市场 / 重置时保留 `customIndicators` 和 `activeIndicatorTab`，符合用户预期
- 单独重置用 `clearAllCustomIndicators()` 工具函数（V1.0 限定测试/调试用）
- **测试保障**：
  - `SET_MARKET 不影响 customIndicators`（reducer 验证）
  - `RESET_ALL 清空 customIndicators`（⚠️ **但当前实现 `RESET_ALL = initialState` 会清空**！这是**已知问题**，需要后续决策是否修复）

---

## 四、关键边界场景处理

### 4.1 SET_MARKET / RESET_ALL 对 customIndicators 的影响
**当前行为**（K 需决策）：
- `SET_MARKET` ✅ **不**清空 `customIndicators`（合理）
- `RESET_ALL` ⚠️ **清空** `customIndicators`（`return initialState` 整体重置）— **可能不合理**，自编指标应保留

**建议修复**（P3 阶段前）：
```ts
case 'RESET_ALL':
  return {
    ...initialState,
    customIndicators: state.customIndicators,  // 保留自编指标
    activeIndicatorTab: state.activeIndicatorTab,  // 保留 Tab
  };
```

### 4.2 启动加载失败的容错
- `ScreenerProvider` 的 `useEffect` 包裹 `try/catch`
- localStorage 不可用 / 解析失败时 `customIndicators` 保持 `[]`，UI 显示空列表（降级）
- 不抛错到 UI（避免整个 App 崩溃）
- `console.error` 记录到控制台，方便排查

### 4.3 autoLoad 参数的可关闭能力
- `ScreenerProvider({ autoLoad = true })` 暴露 `autoLoad` 参数
- 测试场景可显式传 `false` 跳过启动加载，纯净测试 reducer 行为
- 生产环境始终传 `true`（默认）

### 4.4 并发 dispatch 安全
- reducer 是纯函数，同一 action + state 永远得到相同结果，React 自动处理
- storage 写操作（saveCustomIndicator）是同步的，dispatch 紧随其后，无 race condition
- **未处理**：如果用户在 P3.1 弹窗打开时其他 Tab 修改 localStorage（跨 Tab 同步），当前未监听 storage 事件 — **V1.0 已知限制**

---

## 五、API 接口清单

### 5.1 Context 公开 API
```ts
// 组件消费
const { state, dispatch } = useScreener();

// state 关键字段
state.customIndicators       // CustomIndicator[]
state.activeIndicatorTab    // 'system' | 'custom'

// dispatch 关键 action
dispatch({ type: 'LOAD_CUSTOM_INDICATORS', payload: [...] });
dispatch({ type: 'ADD_CUSTOM_INDICATOR', payload: indicator });
dispatch({ type: 'UPDATE_CUSTOM_INDICATOR', payload: indicator });
dispatch({ type: 'REMOVE_CUSTOM_INDICATOR', payload: id });
dispatch({ type: 'SET_INDICATOR_TAB', payload: 'custom' });
dispatch({ type: 'RESOLVE_MISSING_INDICATORS' });  // noop
dispatch({ type: 'IMPORT_CUSTOM_INDICATORS', payload: [...] });
```

### 5.2 Provider 初始化 API
```tsx
// 生产用法
<ScreenerProvider>{children}</ScreenerProvider>  // autoLoad=true（默认）

// 测试用法
<ScreenerProvider autoLoad={false}>{children}</ScreenerProvider>  // 纯净 reducer 测试
```

### 5.3 工具函数（re-export for tests）
```ts
export { EXPORT_FORMAT_VERSION };  // 让 tests 可以断言导出文件版本号
```

---

## 六、测试覆盖

### 6.1 ScreenerContext.test.tsx
- **用例数**：40（V1.0 新增 12 + V1.0 之前 28）
- **新增用例分组**（V1.0）：
  1. LOAD_CUSTOM_INDICATORS 加载 3 个
  2. ADD_CUSTOM_INDICATOR 插入到列表头部
  3. UPDATE_CUSTOM_INDICATOR 替换指定 id
  4. UPDATE_CUSTOM_INDICATOR 未匹配 id 列表不变
  5. REMOVE_CUSTOM_INDICATOR 从列表移除
  6. SET_INDICATOR_TAB 切换到 custom
  7. SET_INDICATOR_TAB 切回 system
  8. RESOLVE_MISSING_INDICATORS 为 noop
  9. IMPORT_CUSTOM_INDICATORS 合并新指标（去重 id）
  10. SET_MARKET 不影响 customIndicators
  11. RESET_ALL 清空 customIndicators（**待 K 决策**：是否应保留）
  12. 初始 state 自带空 customIndicators 和 system Tab
- **autoLoad Provider 用例**：3 个
- **覆盖率**：88.48% / 88.88% / 100%

### 6.2 customIndicatorStorage.test.ts
- **用例数**：33
- **覆盖场景**：MOCK_USER_ID / CRUD / 软删除 / 硬删除 / 引用检测 / 导入导出（成功+部分失败+版本校验+字段非法+重名）/ localStorage 降级
- **关键边界**：seed 写错、JSON 解析失败、Array 根对象、版本过高

---

## 七、文件清单

| 文件 | 行数 | 说明 |
|------|------|------|
| [ScreenerContext.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/context/ScreenerContext.tsx) | 389 | 状态层主文件（V1.0 新增 ~60 行） |
| [tests/context/ScreenerContext.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/context/ScreenerContext.test.tsx) | ~400 | reducer + autoLoad Provider 用例（V1.0 新增 12 + 3） |
| [tests/utils/customIndicatorStorage.test.ts](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/utils/customIndicatorStorage.test.ts) | 358 | 存储层单测 33 用例 |
| [src/.../types/customIndicator.ts](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/types/customIndicator.ts) | ~250 | P1.1 数据模型（K 已评审通过） |
| [src/.../utils/customIndicatorStorage.ts](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/utils/customIndicatorStorage.ts) | 419 | P1.2 存储层（K 已评审通过，本阶段微调 re-export） |

---

## 八、待 K 决策项

| 编号 | 议题 | 现状 | 建议 |
|------|------|------|------|
| 1 | `RESET_ALL` 是否清空 `customIndicators`？ | 当前清空（`return initialState`） | 改为保留（更符合"自编指标是用户资产"预期） |
| 2 | `RESOLVE_MISSING_INDICATORS` 何时启用？ | V1.0 过渡为 noop | P5.2 阶段启用，需先扩展 `FilterCondition` 增加 `sourceId/invalid/invalidReason` 字段 |
| 3 | V1.0 阶段自编指标导入是否做跨 Tab 同步？ | 不做（V1.0 已知限制） | V2.0 监听 `window.addEventListener('storage', ...)` 处理 |
| 4 | `activeIndicatorTab` 是否需要持久化？ | 不持久化（刷新回到 system） | V1.0 保持现状，V2.0 可加 localStorage 记忆 |

---

## 九、配套约束遵守检查

- ✅ **严格复用 P1 定义的类型**：state 字段类型直接用 `CustomIndicator` / `IndicatorTab`，无新定义
- ✅ **不修改 storage API**：仅在 storage 文件中 re-export `EXPORT_FORMAT_VERSION` 供 tests 使用（未改业务逻辑）
- ✅ **临时参数独立**：`PlanCondition.tempParams/tempThreshold/tempOperator` 未侵入 state（保留在数据模型层）
- ✅ **失效标记设计**：`invalid/invalidReason` 字段已在数据模型预留，P5.2 启用
- ✅ **集成测试核心规则**：storage 33 用例覆盖名称唯一性、临时参数不覆盖模板（P5.1 验证）、指标删除失效检测（P5.2 验证）、导入导出去重、本地存储降级

---

## 十、下一步（P3 启动前提）

P2 通过 K 评审后，按顺序推进：
- **P3.1** CustomIndicatorModal 8 字段表单（依赖：P2 state + P1.1 类型 + P1.2 storage）
- **P3.2** ImportExportButtons + JSON 格式校验（依赖：P2 IMPORT action + P1.2 importCustomIndicators）
- **P4.1/4.2** ConditionBuilder 集成 Tab + 下拉分组（依赖：P3 + P2 activeIndicatorTab）
- **P5.1/5.2/5.3** 临时参数 + 失效检测 + 删除二次确认（依赖：P1.1 PlanCondition + P2 state）
- **P6.1/6.2/6.3/6.4** 集成测试 + Playwright + 文档 + 后端协作单

> P2 评审未通过前，**禁止**启动 P3 编码，避免返工。
