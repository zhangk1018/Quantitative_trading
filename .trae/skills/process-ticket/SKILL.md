---
name: "process-ticket"
description: "查看 .trae/topics.md 获取新协作单，认领并处理，更新状态后通知对方验证。Invoke when 启动会话发现 NEW/REOPENED 工单，或用户要求处理某个协作单。"
---

# 处理协作单（Process Ticket）

按规范处理协作单，完成修复后通知方舟验证。

## 触发条件

- 启动会话检查 topics.md 发现有 NEW 或 REOPENED 工单
- 用户明确说"处理工单"/"处理协作单"
- 用户说认领某个具体工单

## 完整流程

### 阶段 1：查看（Discover）

```
1. Read .trae/topics.md — 查看是否有新的状态变更
2. Read docs/协作单.md — 查看所有非 CLOSED 工单
```

### 阶段 2：认领（Assign）

找到自己职责范围内的 NEW/REOPENED 工单：

1. 在 **协作单.md** 中更新状态：`NEW` → `ASSIGNED`
2. 在 **处理记录** 追加一行：`- YYYY-MM-DD 量量: 认领，开始修复（ASSIGNED）`
3. 在 **.trae/topics.md** 追加通知：
   ```
   [量量 YYYY-MM-DD HH:mm] 协作单 [ID] 状态变更: NEW→ASSIGNED（摘要）
   ```

### 阶段 3：处理（Fix）

1. 分析根因（不要只修表象）
2. 实施修复
3. 自测验证修复有效
4. 在 **协作单.md** 的"修复记录"中记录修复细节
5. 更新状态：`ASSIGNED` → `VERIFY`
6. 在 **处理记录** 追加：`- YYYY-MM-DD 量量: 修复完成，待验证（VERIFY）`
7. 在 **.trae/topics.md** 追加通知：
   ```
   [量量 YYYY-MM-DD HH:mm] 协作单 [ID] 状态变更: ASSIGNED→VERIFY（修复摘要）
   ```

### 阶段 4：等待验证（Wait）

方舟会在下次启动时看到 topics.md 通知，进行验证：
- **验证通过** → 方舟改为 CLOSED
- **验证不通过** → 方舟改为 REOPENED，注明原因

### 阶段 5：跟进 REOPENED（Follow-up）

如果工单被 REOPENED：
1. 查看方舟附注的不通过原因
2. 补充修复
3. 再次提交 VERIFY

一个工单最多 REOPENED 2 次，第 3 次需 K 介入。

## 状态更新模板

在 协作单.md 中更新状态时，同时更新 status table：

```markdown
| **状态** | NEW | → | ASSIGNED |
```

每次修改后追加处理记录：
```markdown
**处理记录**:
- 2026-06-10 方舟: 提单（NEW）
- 2026-06-10 量量: 认领，开始修复（ASSIGNED）
- 2026-06-10 量量: 修复完成，待验证（VERIFY）
- 2026-06-10 方舟: 验证通过，关闭（CLOSED）
```

## topics.md 通知格式

每次状态变更都追加一行：
```
[量量 YYYY-MM-DD HH:mm] 协作单 [ID] 状态变更: OLD→NEW（简短摘要）
```

## 示例

处理工单 `[4.4-STOCKS-20260610]`：

1. **认领**：改状态 NEW→ASSIGNED，topics.md 追加
2. **修复**：改代码 + 自测 200 OK
3. **提交验证**：改状态 ASSIGNED→VERIFY，topics.md 追加
4. **关闭**：方舟验证后改 VERIFY→CLOSED