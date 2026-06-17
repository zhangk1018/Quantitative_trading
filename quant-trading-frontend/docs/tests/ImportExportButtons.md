# ImportExportButtons 自编指标导入导出按钮测试文档

> **模块路径**：`quant-trading-frontend/src/features/stock-picker/components/ImportExportButtons.tsx`
> **测试路径**：`quant-trading-frontend/tests/components/ImportExportButtons.test.tsx`
> **阶段**：P3.2（依托 P2 已落地方案 + P1.2 导入导出 API）
> **生成日期**：2026-06-17
> **测试结果**：✅ 16/16 通过（100%）

---

## 一、模块概述

`ImportExportButtons` 提供两个并排按钮：
- **导入**：触发文件选择 → 解析 JSON → Preview 弹窗确认 → 写入 localStorage + 通知父组件 dispatch `IMPORT_CUSTOM_INDICATORS`
- **导出**：从 localStorage 读取全部自编指标 → 创建 Blob → 触发下载（文件名带日期）

**K 2026-06-17 决策**：
- 按钮位置：ConditionBuilder "新建" 按钮下方并列两个图标按钮
- 导入流程：Preview 弹窗确认制（按错误类型分组展示明细）
- 导出文件名：`custom-indicators-YYYY-MM-DD.json`

---

## 二、测试覆盖矩阵

| 分类 | 用例数 | 关键场景 |
|------|--------|----------|
| 基础渲染 | 4 | 导入/导出按钮 + 隐藏 file input + 数量显示 + disabled 状态 |
| 导出 | 2 | 触发 Blob 下载 + 空列表 disabled 不触发 |
| 导入 - file-level 错误 | 4 | 版本不支持 / 格式无效 / 根对象缺失 / indicators 非数组 |
| 导入 - indicator-level 错误 | 3 | name_duplicate / field_invalid / 全部合法 |
| 确认导入 | 1 | 写入 localStorage + 回调 onImportSuccess |
| 取消导入 | 1 | 关闭弹窗不写入 |
| 文件大小超限 | 1 | > 5MB 拒绝导入 |
| **合计** | **16** | — |

---

## 三、关键设计决策

### 3.1 导入流程（Preview 弹窗确认制）

K 2026-06-17 决策，避免误导入导致数据污染：

```
1) 触发 file input → 用户选择 .json
2) FileReader 读取为文本
3) parseImportFile 校验 → file-level 错误（版本/格式/根对象/indicators类型）
   → message.error + 不进入 Preview
4) 进入 Preview 弹窗：
   - 展示文件元信息（导出时间/来源用户/版本/数量）
   - 展示预计结果：新增 X 条 / 跳过 Y 条 / 错误 Z 条
   - 展示错误明细（按 4 类错误类型分组：name_invalid / name_duplicate / field_invalid / parse_error）
5) 用户点击"确认导入"
   → importCustomIndicators 写入 localStorage
   → 从 storage 取出刚写入的指标列表（带新 id/timestamps）
   → 回调 onImportSuccess 通知父组件 dispatch IMPORT_CUSTOM_INDICATORS
   → 弹窗关闭 + message.success
```

### 3.2 重名检测用 prop 而非 storage

Preview 阶段用 `customIndicators` prop 检测重名（不直接读 localStorage），原因：
- 父组件维护 state 单一数据源
- 避免 storage 与 UI 不一致时的歧义
- 测试时只需传 prop 即可模拟已有指标

**已知限制**：若父组件 prop 与 localStorage 不一致，preview 会按 prop 显示，可能与导出/写入后的状态有差异。V1.0 接受此限制，V2.0 计划优化为"以 storage 为权威源"。

### 3.3 导入成功回调数据流

`importCustomIndicators` 会重新生成 id/createdAt/updatedAt，无法从 importCustomIndicators 返回值直接拿到"新写入的子集"。当前实现：
1. 调用 importCustomIndicators 写入 storage
2. 从 localStorage 读出全部
3. 按 updatedAt 倒序
4. 取前 result.added 条（即刚导入的）
5. 通过 onImportSuccess(payload) 回调

**风险**：若用户在导入过程中并发写入其他指标，可能取错。V1.0 单用户单 Tab，接受此限制。

### 3.4 文件大小硬限制 5MB

与 localStorage 5MB 限制对齐，防止 OOM + 写入失败。文件名长度也影响 JSON 体积（5 个指标 + 8 字段 ≈ 1-2KB）。

### 3.5 错误类型分组展示

4 类 indicator-level 错误分别用不同颜色 Tag：
- `name_invalid`（红）：名称格式错误（长度/字符集）
- `name_duplicate`（橙）：当前用户已存在同名
- `field_invalid`（火山红）：必填字段缺失/类型错误
- `parse_error`（品红）：写入时异常

---

## 四、测试运行

```bash
cd quant-trading-frontend
npx vitest run tests/components/ImportExportButtons.test.tsx
```

**结果**：16 passed (16) / 0 failed

---

## 五、与 P2 设计的对齐检查

| P2 设计要求 | 实施情况 |
|-------------|----------|
| 复用 P1.2 storage API | ✅ 不修改 `customIndicatorStorage.ts` |
| IMPORT_CUSTOM_INDICATORS reducer | ✅ 父组件 dispatch 由 onImportSuccess 回调 |
| 按 id 去重 | ✅ 导入写入用新 id，reducer 端按 id 去重 |
| 错误分类（file-level vs indicator-level） | ✅ 严格按 P1.2 分类 |
| name 唯一性校验 | ✅ 用 prop `customIndicators` 检测（V1.0 限制） |
| 不修改 types/customIndicator.ts | ✅ IndicatorExportFile + ImportResult 已落地 |

---

## 六、配套规范遵守

- ✅ **不修改 storage API**：仅消费 `exportCustomIndicators` / `parseImportFile` / `importCustomIndicators` / `MOCK_USER_ID`
- ✅ **不修改 types**：仅消费既有 `IndicatorExportFile` / `EXPORT_FORMAT_VERSION` / `ImportErrorType` / `ImportErrorDetail`
- ✅ **数据流单向**：组件不直接 dispatch，由父组件在 onImportSuccess 回调中 dispatch
- ✅ **明确错误分类**：预览弹窗按 4 类 indicator-level 错误分组展示（K 偏好：清晰显示异常原因）
- ✅ **不掩盖数据问题**：5MB 文件大小硬限制 + 3 类 file-level 错误独立提示

---

## 七、集成位置

`ConditionBuilder.tsx` L226-238：

```tsx
{/* P3.2：导入/导出按钮（K 2026-06-17 决策：新建按钮下方并列） */}
<div className="flex items-center justify-between gap-2">
  <ImportExportButtons
    customIndicators={customIndicators}
    onImportSuccess={handleImportSuccess}
  />
  <Text
    className="text-text-secondary text-xs"
    data-testid="condition-builder-custom-count"
  >
    已有 {customIndicators.length} 条
  </Text>
</div>
```

`handleImportSuccess` 回调（L63-65）：
```ts
const handleImportSuccess = (newIndicators: CustomIndicator[]) => {
  dispatch({ type: 'IMPORT_CUSTOM_INDICATORS', payload: newIndicators });
};
```

---

## 八、待 K 审阅项

| 编号 | 议题 | 现状 | 建议 |
|------|------|------|------|
| 1 | Preview 阶段重名检测用 prop vs storage | 用 prop（避免双源） | 接受 V1.0 限制 |
| 2 | 导入回调数据流（从 storage 取新写入子集） | 按 updatedAt 倒序取前 N 条 | 单用户单 Tab 接受 |
| 3 | 文件大小 5MB 硬限制 | 与 localStorage 一致 | 满足 V1.0 需求 |
| 4 | 错误分组展示 | 4 类 indicator-level 错误 | 满足 K 偏好 |
