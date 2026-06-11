# 选股策略保存/加载 设计方案

**作者**：方舟
**日期**：2026-06-08
**状态**：实施中（Phase 1）
**关联需求**：
- 需求 2：选股策略可保存/加载
- 需求 1（自编指标）已放一放，本文档不展开；后续单独立项

---

## 一、背景与目标

### 现状
- [StockPickerView.tsx](file:///Users/zhangk/workspace/Quantitative_trading/frontend/src/components/StockPickerView.tsx) 是 5 条 mock 数据的占位页面
- 当前筛选条件完全硬编码，刷新即丢失
- 团队内调试策略只能截图或口述，无法直接传递

### 目标
1. 选股视图的**筛选 + 排序**可保存为命名策略
2. 一键加载已保存策略，恢复所有状态
3. 支持**导入他人策略**做测试，零摩擦分享
4. 未来可无缝升级到后端 DB 存储（接口已抽象）

---

## 二、数据结构

### 2.1 TypeScript 类型定义

新增于 [frontend/src/types.ts](file:///Users/zhangk/workspace/Quantitative_trading/frontend/src/types.ts)：

```typescript
/**
 * 选股筛选条件（不含自编指标，Phase 1 范围）
 */
export interface ScreenerFilters {
  /** 上市地筛选：['main_sh', 'main_sz', 'chinext', 'star', 'bse', 'kjj'] */
  boards: string[];
  /** 行业筛选：['银行', '地产', ...] */
  industries: string[];
  /** 形态/动量字段：['pattern_morning_star', 'break_high_20', 'vol_ratio_5', ...] */
  patterns: string[];
  /** 排序字段 */
  sortBy: string;
  /** 排序方向 */
  sortOrder: 'asc' | 'desc';
  /** 取前 N 名 */
  topN: number;
}

/**
 * 选股策略
 */
export interface Strategy {
  id: string;                    // UUID，本地生成
  name: string;                  // 策略名
  description?: string;          // 策略描述
  author?: string;               // 策略作者（导入时记录来源）
  filters: ScreenerFilters;
  createdAt: string;             // ISO 8601
  updatedAt: string;
}
```

### 2.2 localStorage 存储格式

**Key**: `quant_trading:strategies`（命名空间隔离，便于未来多模块共存）

**Value**: `Strategy[]` JSON 数组

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "价值低估",
    "description": "低 PE + 高 PB 安全边际",
    "author": "K",
    "filters": {
      "boards": ["main_sh", "main_sz"],
      "industries": ["银行", "地产"],
      "patterns": ["break_high_20"],
      "sortBy": "pe",
      "sortOrder": "asc",
      "topN": 20
    },
    "createdAt": "2026-06-08T10:30:00.000Z",
    "updatedAt": "2026-06-08T10:30:00.000Z"
  }
]
```

---

## 三、组件设计

### 3.1 存储抽象层

新增 [frontend/src/utils/strategyStorage.ts](file:///Users/zhangk/workspace/Quantitative_trading/frontend/src/utils/strategyStorage.ts)（约 200 行）：

```typescript
export interface StrategyStorage {
  list(): Strategy[];
  get(id: string): Strategy | null;
  save(strategy: Strategy): void;
  delete(id: string): void;
  /** 导出为短码（Base64） */
  exportShortCode(id: string): string;
  /** 导出为 JSON 字符串 */
  exportJSON(id: string): string;
  /** 从短码或 JSON 字符串导入 */
  import(raw: string): { strategy: Strategy; warnings: string[] };
  /** 触发浏览器下载 .json 文件 */
  downloadAsFile(id: string): void;
}

class LocalStorageStrategyStorage implements StrategyStorage { ... }
export const strategyStorage: StrategyStorage = new LocalStorageStrategyStorage();
```

**关键方法实现要点**：

```typescript
// 字段白名单（与 mocks/meta.ts + 后端 meta.py 对齐）
const VALID_PATTERN_KEYS = new Set([
  'pattern_morning_star', 'pattern_evening_star', 'pattern_bullish_engulfing',
  'pattern_bearish_engulfing', 'pattern_hammer',
  'break_high_20', 'break_high_60',
  'vol_ratio_5', 'consec_up_3', 'consec_up_5',
  // ...后续按 meta.ts 扩充
]);

// 导入时校验，失效字段降级而非拒绝
validateStrategy(s: Strategy): { warnings: string[] } {
  const warnings: string[] = [];
  s.filters.patterns = s.filters.patterns.filter(p => {
    if (!VALID_PATTERN_KEYS.has(p)) {
      warnings.push(`字段 ${p} 在当前版本不存在，已忽略`);
      return false;
    }
    return true;
  });
  return { warnings };
}

// ID 冲突处理
resolveIdConflict(s: Strategy): Strategy {
  const existing = this.list();
  if (!existing.some(e => e.id === s.id)) return s;
  return {
    ...s,
    id: crypto.randomUUID(),
    name: `${s.name} (导入)`,
    createdAt: new Date().toISOString(),
  };
}

// 短码编解码（URL 安全 Base64）
exportShortCode(id: string): string {
  const strategy = this.get(id);
  if (!strategy) throw new Error('Strategy not found');
  const json = JSON.stringify(strategy);
  return btoa(unescape(encodeURIComponent(json)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

importShortCode(code: string): Strategy {
  const padded = code + '='.repeat((4 - code.length % 4) % 4);
  const b64 = padded.replace(/-/g, '+').replace(/_/g, '/');
  const json = decodeURIComponent(escape(atob(b64)));
  return JSON.parse(json);
}
```

### 3.2 UI 组件

新增 [frontend/src/components/StrategyManager.tsx](file:///Users/zhangk/workspace/Quantitative_trading/frontend/src/components/StrategyManager.tsx)（约 280 行）：

**Props 接口**：
```typescript
interface StrategyManagerProps {
  isOpen: boolean;
  onClose: () => void;
  onLoad: (strategy: Strategy) => void;       // 加载策略回调
  currentFilters: ScreenerFilters;           // 当前筛选条件（用于"保存当前"）
  onSaveCurrent: (name: string) => void;     // 保存当前条件回调
}
```

**UI 结构**：
```
┌─ 我的策略 ────────────────────────────[×]─┐
│ [💾保存当前]  [📥导入]                    │
│ ──────────────────────────────────────── │
│ 价值低估           K · 2026-06-08 10:30  │
│ 2板块 · 2行业 · 1形态 · Top 20           │
│ [▶加载] [✏重命名] [📋复制] [📤导出] [🗑]  │
│ ──────────────────────────────────────── │
│ 早盘异动           量量 · 06-07 09:15    │
│ 1板块 · 0行业 · 3形态 · Top 50           │
│ [▶加载] [✏重命名] [📋复制] [📤导出] [🗑]  │
│ ──────────────────────────────────────── │
│            共 2 条策略                      │
└──────────────────────────────────────────┘
```

**导入预览 Modal**（导入时弹出）：
```
┌─ 导入策略 ─────────────────────────────────┐
│                                              │
│  检测到外部策略 "早盘异动"                  │
│  作者: 量量 · 2026-06-07                     │
│  ────────────────────────────────────────  │
│  ✅ 上市地: 创业板                           │
│  ✅ 行业: （无）                            │
│  ✅ 排序: change_pct DESC · Top 50          │
│  ⚠️  pattern_super_v2 字段不存在，已忽略    │
│  ────────────────────────────────────────  │
│  策略名: [早盘异动 (导入)________________]   │
│                                              │
│              [取消]      [导入并使用]        │
└──────────────────────────────────────────────┘
```

### 3.3 StockPickerView 集成

修改 [frontend/src/components/StockPickerView.tsx](file:///Users/zhangk/workspace/Quantitative_trading/frontend/src/components/StockPickerView.tsx)：

1. **顶部工具栏**新增两个按钮：
   ```
   [排名方式▼] [排序▼] [TopN▼] │ 筛选: 8 │ [💾保存策略] [📂我的策略]
   ```

2. **state 化筛选条件**（替换硬编码）：
   ```typescript
   const [filters, setFilters] = useState<ScreenerFilters>({
     boards: ['all'],
     industries: [],
     patterns: [],
     sortBy: 'score',
     sortOrder: 'desc',
     topN: 20,
   });
   const [managerOpen, setManagerOpen] = useState(false);
   ```

3. **集成 StrategyManager**：
   ```tsx
   <StrategyManager
     isOpen={managerOpen}
     onClose={() => setManagerOpen(false)}
     onLoad={(s) => { setFilters(s.filters); setManagerOpen(false); }}
     currentFilters={filters}
     onSaveCurrent={(name) => {
       const strategy: Strategy = {
         id: crypto.randomUUID(),
         name,
         filters,
         createdAt: new Date().toISOString(),
         updatedAt: new Date().toISOString(),
       };
       strategyStorage.save(strategy);
     }}
   />
   ```

---

## 四、导入/分享能力矩阵

| 渠道 | 实现 | 工时 |
|------|------|------|
| **JSON 字符串** | 粘贴到文本框 → 解析 → 预览 → 导入 | 已包含 |
| **.json 文件** | `<input type="file" accept=".json">` → FileReader 读取 | +15 min |
| **短码（Base64）** | 文本框粘贴 → Base64 解码 → 同上 | 已包含 |
| **剪贴板** | `navigator.clipboard.writeText()` 一键复制 | +5 min |
| **浏览器下载** | `Blob` + `URL.createObjectURL` + `<a download>` | +10 min |
| **分享链接** | `?import=<shortCode>` URL 参数，页面打开自动检测 | +30 min |
| **二维码** | `qrcode` 库（~15KB），生成 PNG + 下载 | +30 min |

**Phase 1 范围**：JSON 字符串 + 短码 + 剪贴板 + 浏览器下载 + 文件导入
**Phase 2 范围**：分享链接 + 二维码（如果用户反馈需要再上）

---

## 五、字段白名单维护

| 来源 | 文件 | 同步方式 |
|------|------|----------|
| 后端 meta.py | `backend/collector/db/meta.py` | 后端权威源 |
| 前端 mocks/meta.ts | `frontend/src/mocks/meta.ts` | 手工同步 |
| 前端白名单 | `frontend/src/utils/strategyStorage.ts:VALID_PATTERN_KEYS` | 从 mocks/meta.ts 提取 |

**风险**：三处定义不同步时，导入策略会失效。**缓解**：
- 短期：每次发版前 grep 校验
- 长期（Phase 2）：后端 `/api/meta` 返回最新白名单，前端拉取后构建 `VALID_PATTERN_KEYS`

---

## 六、用户交互流程

### 6.1 保存策略

```
用户在选股视图设置好筛选条件（板块/行业/形态/排序/TopN）
        ↓
点击 [💾保存策略] 按钮
        ↓
弹输入框："请输入策略名" [价值低估] [取消] [保存]
        ↓
strategyStorage.save(strategy) 写入 localStorage
        ↓
顶部 toast: "✅ 已保存：价值低估"
```

### 6.2 加载策略

```
点击 [📂我的策略] 按钮
        ↓
StrategyManager 抽屉打开，列出所有策略
        ↓
点击某条策略的 [▶加载]
        ↓
抽屉关闭，filters state 更新
        ↓
触发数据重新拉取（TopN 变更、排序变更等）
        ↓
列表区显示新结果
```

### 6.3 导入他人策略（4 种方式任选）

```
方式 A：分享短码
  1. 发送方点击 [📋复制短码] → 短码入剪贴板
  2. 微信/钉钉粘贴发送
  3. 接收方点击 [📥导入] → 粘贴短码 → 弹预览 → 确认

方式 B：JSON 文件
  1. 发送方点击 [📤导出] → 浏览器下载 strategy.json
  2. 邮件附件发送
  3. 接收方点击 [📥导入] → 选择文件 → 弹预览 → 确认

方式 C：URL 链接（Phase 2）
  1. 发送方点击 [🔗分享链接] → 复制 https://app.xxx.com/strategy?import=xxx
  2. 接收方打开链接 → 自动检测 → 弹预览 → 确认

方式 D：二维码（Phase 2）
  1. 发送方点击 [📱生成二维码] → 弹二维码图片
  2. 接收方扫码 → 同方式 C
```

---

## 七、关键技术决策

### 决策 1：存储位置

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| localStorage | 零后端依赖，即时可用 | 换设备丢数据 | ✅ Phase 1 |
| 后端 DB | 多端同步 | 需建表/接口 | Phase 2 |
| 云端多用户 | 团队共享 | 需用户系统 | 未来 |

**接口已抽象**（`StrategyStorage` interface），未来切换零成本。

### 决策 2：字段失效处理

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| 拒绝整个导入 | 严格 | 1 个字段失效就废 | ❌ |
| 忽略失效字段 + 警告 | 容错好 | 用户可能漏看警告 | ✅ |
| 自动映射到最接近字段 | 智能 | 可能误判 | ❌ |

### 决策 3：ID 冲突处理

| 方案 | 选择 |
|------|------|
| 覆盖本地 | ❌ 危险 |
| 生成新 UUID + 名字加 "(导入)" | ✅ 推荐 |
| 弹窗让用户选 | 太繁琐 |

### 决策 4：分享格式

| 方案 | 优点 | 选择 |
|------|------|------|
| 纯 JSON | 完整可读 | 短方案可行 |
| Base64 短码 | 紧凑、可放链接 | ✅ 推荐 |
| 压缩 JSON（gzip） | 更短 | 浏览器支持差，复杂 |

**最终**：同时支持 JSON 文件和短码，用户按需选择。

---

## 八、风险与限制

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| localStorage 容量限制（~5MB） | 策略过多可能溢出 | 单策略 < 2KB，限制 50 条；超出时弹警告 |
| 字段白名单不同步 | 导入策略失效 | 短期：发版前 grep 校验；长期：从后端 meta API 拉取 |
| 浏览器禁用 localStorage | 保存/加载全失效 | 启动时检测，禁用时弹"请启用浏览器存储"提示 |
| 已知浏览器缓存问题 | 旧版本代码不生效 | Vite 已配 `Cache-Control: no-cache`，需强制刷新 |
| 导入 JSON 来源不可信 | 理论上可注入恶意字段 | 纯数据无代码执行风险；只接受白名单字段 |

---

## 九、实施计划（Phase 1: 1.5 天）

| 步骤 | 内容 | 估时 | 依赖 |
|------|------|------|------|
| Step 1 | `types.ts` 加 `Strategy` / `ScreenerFilters` 类型 | 10 min | - |
| Step 2 | `utils/strategyStorage.ts` 完整实现（含短码/校验/冲突） | 60 min | Step 1 |
| Step 3 | `StockPickerView.tsx` state 化（filters + handlers） | 60 min | - |
| Step 4 | `components/StrategyManager.tsx` 抽屉 + 列表 + 操作 | 90 min | Step 2 |
| Step 5 | StrategyManager 加导入预览 Modal | 45 min | Step 2, 4 |
| Step 6 | 联调：保存 → 列表 → 加载 → 导入 | 30 min | Step 3, 4, 5 |
| Step 7 | 浏览器下载 .json / 复制短码 / 导入文件 | 30 min | Step 4 |
| Step 8 | Playwright 端到端测试 | 30 min | Step 6, 7 |
| Step 9 | TypeScript 编译零错误验证 | 10 min | 全部 |

**总计**：~6 小时（1.5 个工作日）

---

## 十、待确认事项（K 评审）

1. **抽屉位置**：右侧滑出（推荐） vs 居中弹窗 vs 底部弹起？
2. **localStorage 上限**：50 条（推荐） vs 100 条 vs 无限制？
3. **"我的策略"按钮位置**：选股视图顶部工具栏（推荐） vs Sidebar 列表里？
4. **作者字段**：`author?` 可选，导入时从策略 JSON 读取还是手动填？
5. **是否需要 Phase 2 的分享链接/二维码**：要做就 +1 小时，不要就只做 Phase 1

---

## 十一、后续可扩展（暂不做）

- 后端 DB 同步（替换 `LocalStorageStrategyStorage` 为 `HttpStrategyStorage`）
- 分享链接、二维码
- 策略分享市场（浏览/复制其他用户策略）
- 定时运行（每日 15:30 自动跑策略推送结果）
- **自编指标**（需求 1，单独立项）

---

**评审完成后**，按 Step 1→9 顺序开工，每个 Step 完成后做 TypeScript 编译检查。
