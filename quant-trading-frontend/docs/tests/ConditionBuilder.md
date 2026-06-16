# 条件构建器组件测试

> **测试模块**：[`tests/components/ConditionBuilder.test.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/ConditionBuilder.test.tsx)
> **被测源码**：[`src/features/stock-picker/components/ConditionBuilder.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/components/ConditionBuilder.tsx)
> **关联数据模型**：[`src/features/stock-picker/types/filterTree.ts`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/types/filterTree.ts)
> **关联 Context**：[`src/features/stock-picker/context/ScreenerContext.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/context/ScreenerContext.tsx)
> **用例数**：15　**覆盖率**：100% / 96.29% / 100%　**v8 provider**

---

## 1. 模块职责

`ConditionBuilder` 是选股侧边栏的"条件构建器"面板，让用户通过**预设 + 关系（AND/OR/NOT）+ 手动添加**三种方式组合出任意复合选股条件。

**核心设计**：
- **扁平无嵌套** `FilterTree.conditions[]` 是有序列表（K 偏好）
- **关系（op）由"下一个待添加"决定**，已添加条件的关系不会随后续选择改变（K 偏好）
- **6 个预设 + 自定义**（custom），其中"底部放量+MACD金叉"是 2 条件组合预设
- **3 个互斥单选按钮 [AND] [OR] [NOT]** 控制"下一个待添加条件"的关系
- **已添加条件的 op 标签可点击循环切换**（AND → OR → NOT → AND）
- **重置 / 市场切换**联动清空

**关联状态**（[`ScreenerContext.tsx`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/src/features/stock-picker/context/ScreenerContext.tsx)）：
- `state.filterTree: FilterTree | null` — 当前选股条件树
- `state.nextConditionOp: FilterOp` — 下一个待添加条件的关系
- 6 个 action：`SET_NEXT_CONDITION_OP` / `ADD_CONDITION` / `REMOVE_CONDITION` / `UPDATE_CONDITION_OP` / `CLEAR_CONDITIONS` / `APPLY_PRESET`

---

## 2. 测试用例清单

按 `describe` 块组织。

### 2.1 基础渲染（2 用例）

| # | 标题 | 说明 |
|---|------|------|
| 1 | 渲染 header、count 徽标、reset 按钮 | 默认折叠时仍可见 |
| 2 | 默认折叠时不显示 6 个预设按钮 | `destroyOnHidden` 真正卸载 Panel 内容 |

### 2.2 折叠面板（1 用例）

| # | 标题 | 说明 |
|---|------|------|
| 3 | 点击 header 展开后，6 个预设按钮全部可见 | + 3 关系 + 添加按钮 |

### 2.3 预设应用（3 用例）

| # | 标题 | 说明 |
|---|------|------|
| 4 | 点击 RSI超卖 预设后，state 中添加 1 个 condition | 单条件预设 |
| 5 | 点击"底部放量+MACD金叉"组合预设后，添加 2 个 AND 条件 | 组合预设 |
| 6 | 应用预设会替换已有 conditions（典型"应用"语义） | `APPLY_PRESET` 替换而非追加 |

### 2.4 关系选择器 AND/OR/NOT（4 用例）

| # | 标题 | 说明 |
|---|------|------|
| 7 | 初始默认选中 AND | `nextConditionOp: 'AND'` |
| 8 | 点击 OR 后 nextConditionOp 变为 OR | |
| 9 | 点击 NOT 后 nextConditionOp 变为 NOT | |
| 10 | 关系选择仅影响下一个添加的条件，已添加的不变 | **K 偏好核心** |

### 2.5 添加 / 删除 / 循环切换 op（3 用例）

| # | 标题 | 说明 |
|---|------|------|
| 11 | 点击"+ 条件"添加一个自定义 condition，count=1 | + 空状态消失 |
| 12 | 点击删除按钮移除对应 condition | + filterTree 变 null（删完最后一个） |
| 13 | 点击 op 标签循环切换 AND → OR → NOT → AND | **K 偏好交互** |

### 2.6 重置（1 用例）

| # | 标题 | 说明 |
|---|------|------|
| 14 | 点击重置清空所有 conditions 并重置 nextConditionOp | `CLEAR_CONDITIONS` action |

### 2.7 市场切换联动（1 用例）

| # | 标题 | 说明 |
|---|------|------|
| 15 | 切换市场后 conditions 清空，nextConditionOp 回到 AND | **SET_MARKET 联动**（与 IndicatorFilter / FinancialFilter 一致） |

---

## 3. 关键 helper

```ts
/** 暴露 state 的小工具（在 DOM 中嵌入当前 filterTree + nextConditionOp） */
function StateInspector({ testId = 'state-condition' }) {
  const { state } = useScreener();
  return <div data-testid={testId}>{JSON.stringify({ filterTree: state.filterTree, nextConditionOp: state.nextConditionOp })}</div>;
}

/** 读取 state JSON */
function readState() {
  const text = screen.getByTestId('state-condition').textContent || '{}';
  return JSON.parse(text);
}

/** 渲染组件 + Inspector */
function renderBuilder() {
  return render(<ScreenerProvider><ConditionBuilder /><StateInspector /></ScreenerProvider>);
}

/** 展开折叠面板 */
async function expandPanel(user) {
  await user.click(screen.getByTestId('condition-builder-header'));
}
```

**data-testid 约定**：
- `condition-builder-collapse` / `condition-builder-header` / `condition-builder-count` / `condition-builder-reset`
- `condition-preset-<fieldKey>`（6 个预设）
- `condition-op-and` / `condition-op-or` / `condition-op-not`
- `condition-add`（+ 条件按钮）
- `condition-empty`（空状态文案）
- `condition-list`（条件列表容器）
- `condition-item-<id>` / `condition-item-op-<id>` / `condition-item-remove-<id>`（每个条件）
- `condition-op-help`（关系说明图标）

---

## 4. 维护要点

### 4.1 折叠 / 销毁语义
使用 `destroyOnHidden`（Antd 5.x 推荐），`destroyInactivePanel` 已被弃用。折叠时**内容不渲染**到 DOM，因此测试可以用 `queryByTestId(...).not.toBeInTheDocument()`。

### 4.2 图标选择
`PuzzleOutlined` 在当前 `@ant-design/icons` 版本中**不存在**。条件构建器头图标使用 `ControlOutlined`（语义最贴"条件构建器"）。其他图标（`BookOutlined` / `ReloadOutlined` / `PlusOutlined` / `EyeOutlined` / `CloseOutlined`）均可用。

### 4.3 关系切换不追溯
**核心不变量**：已添加条件的 op 永远不变。修改 op 的唯一方式是：
- 点击该条件前的 op 标签（循环切换）
- 应用预设（替换整个列表）

新加条件的 op 由 `nextConditionOp` 决定，且 `nextConditionOp` 在添加后**不会自动重置**——用户连续加 3 个都是 OR 是允许的。

### 4.4 K 偏好对照
- ✅ "每个条件独立携带关系操作符（AND/OR/NOT）" — 满足
- ✅ "先选择关系再添加条件" — 满足
- ✅ "已添加条件的关系不会随后续选择改变" — 满足
- ✅ "扁平无嵌套" — 满足（FilterTree.conditions[] 一维数组）

---

## 5. 关联 Playwright 浏览器自测

[`temp/browser_test/test_condition_builder.py`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/temp/browser_test/test_condition_builder.py)（9 场景全过）

覆盖：
1. 默认折叠
2. 展开面板（6 预设 + 3 关系 + 添加）
3. RSI超卖预设
4. 组合预设替换
5. 关系切换 + 添加
6. URL 序列化（`cond_<fieldKey>=<op>`）
7. op 循环切换
8. 删除条件
9. 重置

---

## 6. 变更记录

| 日期 | 变更 | 触发 |
|------|------|------|
| 2026-06-16 | 首次提交 15 用例（K 截图要求开发条件构建器） | K："按照图片开发条件构建器模块" |
| 2026-06-16 | 修复 `genConditionId is not defined`（ScreenerContext 缺 import） | vitest 跑测发现 |
| 2026-06-16 | 修复 `PuzzleOutlined is not defined` → 换 `ControlOutlined` | vitest 跑测发现 |
| 2026-06-16 | 修复 activeKey 折叠逻辑反了（condition: true 应折叠而非展开） | vitest 跑测发现 |
| 2026-06-16 | initialState 缺 `nextConditionOp: 'AND'` | TypeScript 字段缺漏 |
| 2026-06-16 | `destroyInactivePanel` → `destroyOnHidden`（Antd 5.x 弃用清理） | K 偏好 |
