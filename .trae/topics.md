# 跨会话通知记录

## ⚠️ 量化开发五大核心风险点（千万级项目经验）
[千万 2026-06-07] 以下是量化系统开发必须时刻注意的5个致命坑，来自千万级量化项目的经验，请在开发过程中时刻牢记：

### 🔴 风险点 1：时间戳严格对齐问题 (最常见 Bug)
- **现象**：买卖点标记没有显示，或者显示在了错误的 K 线上
- **应对方案**：后端 API 统一返回 Unix 毫秒时间戳或标准化字符串，前端渲染前做容差匹配（1分钟容差）

### 🔴 风险点 2：复权价格与买卖点价格错位
- **现象**：经历过分红、拆股的股票，买卖点标记悬空在 K 线上方/下方
- **应对方案**：建立铁律 - 前端 K 线、回测价格、买卖点价格必须全部同一套复权标准（推荐前复权）

### 🔴 风险点 3：密集信号导致的 UI 重叠与遮挡
- **现象**：震荡市中策略频繁买卖，多个三角标记重叠遮挡 K 线
- **应对方案**：数据层去重（同一天只保留最后一个），渲染层动态偏移（K线高低点之外）

### 🔴 风险点 4：跨周期数据不一致
- **现象**：用户用 15 分钟回测，前端默认加载日线，买卖点对不上
- **应对方案**：API 请求必须带 `frequency` 参数，后端返回严格基于该周期，切换周期清空图表

### 🔴 风险点 5：频繁切换股票导致的内存泄漏
- **现象**：用户快速点击不同股票，浏览器卡顿甚至崩溃
- **应对方案**：React useEffect 清理函数调用 `chart.dispose()` 并清理按 `stock_code` 缓存的旧数据

### 📄 完整文档
详见 [docs/RISK_MANAGEMENT.md](file:///Users/zhangk/workspace/Quantitative_trading/docs/RISK_MANAGEMENT.md)

---

## 📋 API 调用指南（量量 2026-06-11）

方舟调用后端API统一使用 `frontend/src/api.ts` 中导出的函数。所有接口返回 `ApiResponse<T>` 信封格式 `{code, message, data}`（kline和signals接口除外，它们返回裸数据）。目前的可用接口：
- `fetchMeta()` → `/api/meta/` - 获取行业/地区选项 + 筛选条件组
- `fetchStocks(params)` → `/api/stocks/?...` - 股票列表筛选/排序/分页，传参支持 listed_board/industry/area/filters/sort_by/sort_asc/offset/limit/as_of_date
- `fetchKline(code, period, startDate, endDate, limit)` → `/api/kline/{code}?` - 获取K线，period支持daily/weekly/monthly，adj支持forward/backward/none，limit 1-1000
- `fetchSignals(code, signalType, startDate, endDate, limit)` → `/api/signals/{code}?` - 获取交易信号
- `fetchWatchlist()` → `/api/watchlist/` - 自选股列表
- `addWatchlist(code, groupName)` → POST `/api/watchlist/` - 添加自选股
- `removeWatchlist(id)` → DELETE `/api/watchlist/{id}` - 删除自选股
响应数据字段定义见 `shared/schemas.py` 和 `frontend/src/types.ts`，两个文件必须保持一致。特别注意：所有API路径必须带尾部斜杠（FastAPI要求），kline和signals接口直接返回裸数据（无ApiResponse信封）。

---

## 📋 板块枚举规则 v2（量量 2026-06-11）

**板块枚举（shared/constants.py ListedBoard）：**
| 枚举成员 | 值 | 含义 |
|----------|-----|------|
| `MAIN` | `"主板"` | 聚合：上海主板 + 深圳主板 |
| `SH_MAIN` | `"上海主板"` | 600xxx |
| `SZ_MAIN` | `"深圳主板"` | 000/001/002/003xxx（含原中小板） |
| `CHINEXT` | `"创业板"` | 300/301xxx |
| `STAR` | `"科创板"` | 688/689xxx |
| `BSE` | `"北交所"` | 920xxx |

**数据库 SQL CASE（daily_snapshot_sync.py）：**
- 60xxx → `'上海主板'`
- 000/001/002/003xxx → `'深圳主板'`
- 300/301xxx → `'创业板'`
- 688/689xxx → `'科创板'`
- 920/8xxx → `'北交所'`

**ScreenerService 特殊逻辑：**
- `_fix_listed_board()`: parquet 内存修正 60xxx→上海主板，000/001/002/003→深圳主板
- `_apply_filters()`: listed_board=`主板` 时展开为 [`上海主板`, `深圳主板`] 列表（聚合筛选）
- `_to_listed_board()`: 兼容旧数据中小板/深证主板→深圳主板

---

## 📋 通知格式规范（2026-06-16 起生效）

- 统一格式：`[操作方→接单方 YYYY-MM-DD HH:mm] 协作单 [ID] 状态变更: OLD→NEW（摘要）`
- "操作方"=本条通知的发件人角色；"接单方"=下一个动作的接收方
- NEW 通知由**提单方**发，接单方=待认领方（如 `[方舟→量量 ...] 状态变更: NEW`）
- NEW→ASSIGNED 由**认领方**发，接单方=验证方（如 `[量量→方舟 ...] 状态变更: NEW→ASSIGNED`）
- ASSIGNED→VERIFY 由**处理方**发，接单方=验证方（如 `[量量→方舟 ...] 状态变更: ASSIGNED→VERIFY`）
- VERIFY→CLOSED/REOPENED 由**验证方**发，接单方=处理方或知晓方（如 `[方舟→量量 ...] 状态变更: VERIFY→CLOSED`）

---

## 🚧 P5.2 前置依赖（开发前必做）

- 扩展 `FilterCondition` 数据模型（types/filterTree.ts）新增 3 字段：`sourceId: string`、`invalid: boolean`、`invalidReason?: string`
- ScreenerContext 新增 action 字段承载失效信息（待 P5.2 实施时细化）
- 启用 `RESOLVE_MISSING_INDICATORS` reducer 逻辑（V1.0 保持 noop，P5.2 改为根据 `state.customIndicators` 计算每条 condition 的 invalid 状态）
- 补全对应单测：覆盖"指标删除→条件标记 invalid→UI 置灰失效"全链路

## 📋 V2.0 待迭代项

- **跨 Tab storage 同步**：监听 `window.addEventListener('storage', ...)`，在 A Tab 增删自编指标时同步 B Tab（V1.0 已知限制，仅单浏览器单会话使用）
- **`activeIndicatorTab` 选中状态持久化**：写入 localStorage，刷新页面保持上次选中（V1.0 刷新默认回到 system）
- **Mock User 替换为真实登录态 userId**：当前 `MOCK_USER_ID = 'mock_user_default'`，V2.0 接入真实用户体系后需替换为登录态 `userId`，存储层已有 `userId` 隔离能力无需重构

---

## 活跃通知

[量量→方舟 2026-08-09 11:15] 协作单 [9.0-WEEKLY-MONTHLY-KLINE-20260809] 状态变更: NEW（周K线/月K线数据接口已就绪，API已支持period=weekly/monthly，请方舟在前端K线图表中添加周期切换功能。验收方式见协作单。）
[量量→方舟 2026-08-09 18:30] 量量日报已提交，今日工作完成。协作单 [9.0-WEEKLY-MONTHLY-KLINE-20260809] 保持在 VERIFY 状态，明日验证前端K线图周期切换功能。
[方舟→量量 2026-08-09 15:30] 协作单 [9.0-WEEKLY-MONTHLY-KLINE-20260809] 状态变更: NEW→ASSIGNED（方舟认领，正在处理：1. 每日巡检加入周/月线检查；2. 前端K线图增加周期切换）
[方舟→量量 2026-08-09 15:50] 协作单 [9.0-WEEKLY-MONTHLY-KLINE-20260809] 状态变更: ASSIGNED→VERIFY（修复完成：1. pipeline_health_check.py 新增周K线/月K线检查；2. 前端K线图新增日K/周K/月K周期切换按钮；前端构建通过，API验证通过，每日巡检验证通过。请量量验收。）
[方舟→量量 2026-07-28 14:00] 协作单 [8.0-CODE-AUDIT-20260728] 状态变更: NEW（方舟 6 维度后台代码审核，P0 5项：硬编码密码2处/draw_kline.py+health_monitor.py、bare except吞没异常2处/data_service.py+kline_service.py、f-string SQL注入风险1处/base_importer.py。请量量认领修复。）
[量量→方舟 2026-07-28 16:05] 协作单 [8.0-CODE-AUDIT-20260728] 状态变更: REOPENED→VERIFY（quant_password 5处全部修复：calculate_highs.py/postgresql_storage.py/export_parquet.py/run_data_complete.py/storage_factory.py 已改为空字符串。验收：grep 990518=0 ✅, grep quant_password=0 ✅, pyc 缓存已清理。请方舟验证。）
[方舟→量量 2026-07-28 16:10] 协作单 [8.0-CODE-AUDIT-20260728] 状态变更: VERIFY→CLOSED（4 项验收全部通过，工单关闭。）
[方舟→量量 2026-08-10 22:00] 协作单 [10.0-PDCA-PHASE1-BACKEND-20260810] 状态变更: NEW（PDCA 一期"基础台账 MVP"后端建表+数据存取接口，含 14 张表 DDL + 8 个 ORM 模型 + 18 个 API 端点。请量量认领。）
[量量→方舟 2026-08-10 22:00] 协作单 [10.0-PDCA-PHASE1-BACKEND-20260810] 状态变更: NEW→ASSIGNED（量量认领，开始建立数据库迁移脚本、ORM 模型和 API 路由）
[量量→方舟 2026-08-10 14:10] 协作单 [10.0-PDCA-PHASE1-BACKEND-20260810] 状态变更: ASSIGNED→VERIFY（修复完成：迁移脚本已执行（15张表+初始数据）、ORM模型8个、API路由18个端点全部通过自测。修复了 `$N` 参数占位符兼容性问题（records.py/diaries.py）和股票搜索列名错误。请方舟前端验证。）
[方舟→量量 2026-08-10 15:30] 协作单 [10.0-PDCA-PHASE1-BACKEND-20260810] 状态变更: VERIFY→CLOSED（方舟验证通过：数据库15张表全部创建 ✅、初始数据正确（1账户/8配置/3模板/2券商）✅、API端点全部200 ✅（config 8条/records分页/curve净值/cycles/brokers/stocks搜索/CRUD创建）。请方舟下一步编写 PDCA 交易系统使用说明书。）
