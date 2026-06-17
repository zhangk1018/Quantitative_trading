# CustomIndicatorList 自编指标列表组件测试文档

> **模块路径**：`quant-trading-frontend/src/features/stock-picker/components/CustomIndicatorList.tsx`
> **测试路径**：`quant-trading-frontend/tests/components/CustomIndicatorList.test.tsx`
> **阶段**：P3.3（编辑模式功能完善）
> **生成日期**：2026-06-17
> **测试结果**：✅ 13/13 通过（100%）

---

## 一、模块概述

`CustomIndicatorList` 展示当前用户的全部自编指标，提供：
- 列表视图（名称 + 分类 Tag + 运算符 + 阈值 + 公式预览）
- 编辑入口（点击行尾编辑按钮 → 父组件 onEdit 回调）
- 删除入口（点击行尾删除按钮 → Popconfirm 二次确认 → 父组件 onDelete 回调）
- 引用感知删除（二次确认文案区分"未引用"和"被方案引用"两种场景）

**K 2026-06-17 决策**：
- 列表位置：ConditionBuilder 现有"已有 N 条"位置下方，独立区域
- 列表项交互：每行末尾"编辑" + "删除"两个图标按钮
- 删除二次确认：基于 `isIndicatorReferenced(id)` 区分未引用/已引用提示文案

---

## 二、测试覆盖矩阵

| 分类 | 用例数 | 关键场景 |
|------|--------|----------|
| 空状态 | 2 | "暂无自编指标"提示 + 不渲染列表容器 |
| 列表渲染 | 3 | 名称/分类/运算符/阈值/公式预览 + 分类 Tag + 分类中文标签 |
| 公式预览截断 | 2 | 公式 > 40 字符截断 + ≤ 40 字符不截断 |
| 编辑按钮 | 1 | 点击触发 onEdit，传入指标对象 |
| 删除未引用 | 2 | Popconfirm 文案 + 确认调用 onDelete + 取消不调用 |
| 删除已引用 | 1 | Popconfirm 文案区分"被方案引用" |
| 阈值显示 | 2 | 单值 + 双值区间 |
| **合计** | **13** | — |

---

## 三、关键设计决策

### 3.1 引用感知删除

K 决策"不允许掩盖数据问题"——删除一个被方案引用的指标，会导致引用该指标的条件失效（标记为 invalid），用户应该知情：
- 未引用：Popconfirm title "确认删除该自编指标？"，description "此操作不可撤销（仅标记软删除）"
- 已引用：Popconfirm title "该指标被方案引用"，description "删除后引用该指标的条件将自动标记为失效（invalid），是否继续？"

引用检测实时调用 `isIndicatorReferenced(id, userId)` 读取 localStorage 中的 plans。

### 3.2 删除软删除架构

实际删除通过 `removeCustomIndicator(id, userId)` 标记 `deleted: true + deletedAt`（P2 决策），不物理清除。reducer `REMOVE_CUSTOM_INDICATOR` 同步：
- 从 state.customIndicators 过滤掉
- 扫描 filterTree 中所有 conditions，对 sourceId === id 的条件标记 `invalid: true, invalidReason: '指标已删除'`

### 3.3 公式预览截断

公式按 40 字符截断，超出部分用 `...` 替代。完整公式通过 Tooltip（hover 触发）查看。

### 3.4 阈值格式化

- 单值（`number`）：直接显示数字
- 双值（`[number, number]`）：显示为 `[low, high]` 区间格式

### 3.5 分类 Tag 颜色

通过 `getCategoryMeta(category)` 查表显示：
- `trend` → "趋势类"（蓝色）
- `oscillator` → "震荡类"（橙色）
- `volume` → "成交量类"（绿色）
- `volatility` → "波动率类"（紫色）
- `custom` → "自定义"（灰色）

---

## 四、测试运行

```bash
cd quant-trading-frontend
npx vitest run tests/components/CustomIndicatorList.test.tsx
```

**结果**：13 passed (13) / 0 failed

---

## 五、与 P2 设计的对齐检查

| P2 设计要求 | 实施情况 |
|-------------|----------|
| 复用 P1.2 storage API | ✅ 仅消费 `isIndicatorReferenced` + `MOCK_USER_ID` |
| 软删除架构 | ✅ 不物理清除，符合 P1.2 决策 |
| 引用检测实时 | ✅ 每次渲染调 `isIndicatorReferenced` |
| REMOVE_CUSTOM_INDICATOR reducer 联动 | ✅ 父组件 dispatch（见 ConditionBuilder.handleDeleteClick） |
| RESOLVE_MISSING_INDICATORS P5.2 启用 | ✅ V1.0 noop，无需本组件处理 |
| 不修改 types/customIndicator.ts | ✅ 仅消费既有 `CustomIndicator` + `INDICATOR_OPERATORS` + `getCategoryMeta` |

---

## 六、配套规范遵守

- ✅ **不修改 storage / reducer / types**：仅消费既有 API + 父组件 dispatch
- ✅ **明确错误分类**：删除二次确认文案按"未引用 / 被引用"区分（K 偏好：清晰显示覆盖率异常及原因）
- ✅ **不掩盖数据问题**：被引用时明确告知用户引用条件将失效
- ✅ **数据流单向**：组件不直接 dispatch，由父组件在 onDelete 回调中 dispatch

---

## 七、集成位置

`ConditionBuilder.tsx`：
- L99：state 扩展 `editingIndicator`（P3.3 新增）
- L129-148：新增 `handleEditClick` / `handleUpdateCustomIndicator` / `handleDeleteClick` 3 个回调
- L289-294：组件渲染位置
  ```tsx
  {/* P3.3：自编指标列表（编辑 / 删除入口） */}
  <CustomIndicatorList
    indicators={customIndicators}
    onEdit={handleEditClick}
    onDelete={handleDeleteClick}
  />
  ```
- L320-336：CustomIndicatorModal 集成点扩展
  ```tsx
  <CustomIndicatorModal
    title={editingIndicator ? '编辑自编指标' : '新建自编指标'}
    editing={editingIndicator}
    onConfirm={editingIndicator ? handleUpdateCustomIndicator : handleSaveCustomIndicator}
    onCancel={() => { setShowCustomModal(false); setEditingIndicator(null); }}
  />
  ```

---

## 八、待 K 审阅项

| 编号 | 议题 | 现状 | 建议 |
|------|------|------|------|
| 1 | Popconfirm 文案区分引用状态 | 已实施 | 满足 K 偏好 |
| 2 | 公式截断阈值 40 字符 | 硬编码 40 | V2.0 可配置化 |
| 3 | 列表项密度（间距 / 字号） | 当前偏紧凑 | 满足 P3.3 阶段需求 |
| 4 | 引用检测实时性 | 每次渲染调 storage | V1.0 接受 |

---

## 九、与 P3.2 集成

P3.2 `ImportExportButtons` 完成后，导入的自编指标进入 `state.customIndicators`，**自动在 P3.3 `CustomIndicatorList` 显示**。导入的指标也支持编辑/删除（id 由 storage 重新生成，dispatch IMPORT_CUSTOM_INDICATORS reducer 按 id 去重）。
