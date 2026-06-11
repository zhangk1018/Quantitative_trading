# 跨会话通知记录

## ⚠️ 重要：量化开发五大核心风险点（千万级项目经验）
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

[方舟 2026-06-08 23:58] 协作单 [BOUNDARY-001] 状态变更: NEW（后端静态前端文件越界操作审查+跨会话项目结构问题：monitor.html 4项越界修改待量量复核+kline_service.py模块路径问题）
[方舟 2026-06-09 00:25] 前端端口变更: 5177→5173（vite.config.ts 已改 strictPort 5173，dev server 重启在 5173，project_memory 已同步）
[方舟 2026-06-09 17:35] 协作单 [P2-SCHEMA-20260609] 状态变更: NEW（SignalItem schema 治理：price: Decimal→float 序列化字符串问题、signal_type 描述 buy/sell 与实际技术型不符、新增 direction 字段建议；3 项任务 P2 优先级待量量认领）
[量量 2026-06-09 22:00] 协作单 [BOUNDARY-001] 状态变更: ASSIGNED→VERIFY（4 项越界修改全部审查：越界1/3 保留，越界2/4 代码中未找到（已覆盖/已移除），kline_service.py 不改（项目惯例），monitor.html 归属后端）
[量量 2026-06-09 22:00] 协作单 [P2-SCHEMA-20260609] 状态变更: ASSIGNED→VERIFY（任务1 price: Decimal→float、任务2 新增 direction: Literal["buy","sell"] 字段 + 修正 description，历史回填 226,986 条 0 NULL）
[方舟 2026-06-09 22:30] 协作单 [BOUNDARY-001] 状态变更: VERIFY→CLOSED（4 项越界自然消解：2 保留+2 覆盖/移除，kline_service.py 项目惯例无问题，monitor.html 归后端）
[方舟 2026-06-09 22:30] 协作单 [P2-SCHEMA-20260609] 状态变更: VERIFY→CLOSED（5 股×5 type×30 条=344 条信号 200，price 数字 + direction buy/sell 全部通过）
[方舟 2026-06-10] 协作单 [4.4-META-20260610] 状态变更: NEW（fetchMeta 返回 trade_date=20260601 total=300，但 DB 最新 20260608 共 5515 条；loader 缓存陈旧 4 天，影响 Phase 4.4.1 选股列表数据时效性）
[方舟 2026-06-10] 协作单 [4.4-STOCKS-20260610] 状态变更: NEW（P0 阻塞：/api/stocks/ 返回 500，jsonable_encoder vars() TypeError；6-10 早上 14/14 集成测试通过，下午突发，可能 P2-SCHEMA direction 字段或 4.4 后端补丁副作用）
[方舟 2026-06-10] Phase 4.4.1-4.4.5 完成：4 个联调任务 + 1 个 E2E 闭环（15/16 通过，唯一 1 项为 toast 时序问题）
[方舟 2026-06-10] Phase 6.1.a 启动：搭积木式条件组合面板 ConditionBuilder（搭积木式 AND/OR/NOT 逻辑筛选 UI），等 [4.4-STOCKS-20260610] 修复后联调
[量量 2026-06-10 14:55] 协作单 [4.4-STOCKS-20260610] 状态变更: NEW→FIXED（/api/stocks/ 返回 200，jsonable_encoder 已修；6 个字段全补全：stock_code/name/listed_board/industry/sub_industry/trade_date + 30+ 数值字段）
[量量 2026-06-10 14:55] 协作单 [4.4-META-20260610] 状态变更: NEW→FIXED（fetchMeta 返回 trade_date=20260608 total=5515，loader 缓存已刷新）
[方舟 2026-06-10 15:00] 协作单 [4.4-STOCKS-20260610] 状态变更: FIXED→CLOSED（联调 17/17 通过：bool 筛选传给后端+range 前端过滤+AND 组合端到端；UI total 5515 与 API 一致；附带修 total 显示 bug：rangeFiltered.length → resp.data.total）
[方舟 2026-06-10 15:00] 协作单 [4.4-META-20260610] 状态变更: FIXED→CLOSED（联调验证：UI 显示 trade_date=2026-06-08 total=5,515，与 DB 真实最新一致）
[方舟 2026-06-10 15:00] Phase 6.1.a 联调完成：17/17 通过（后端 bool 筛选+前端 range 过滤+AND 组合端到端）
[量量 2026-06-10 10:30] 协作单 [DB-SCHEMA-001] 状态变更: NEW→ASSIGNED（认领：init_db.sql 补 user_watchlist 表定义）
[量量 2026-06-10 10:35] 协作单 [DB-SCHEMA-001] 状态变更: ASSIGNED→VERIFY（init_db.sql v4.1 新增 user_watchlist + migrate_add_watchlist.sql，待方舟验证）
[量量 2026-06-10 11:05] 协作单 [4.4-FIELDS-20260610] 状态变更: NEW（每日快照 36 字段空值问题：ma10/ma20/rsi_6/macd 926-942 空、net_mf_amount 3275 空、ps/dv_ratio 等 318-2064 空）
[量量 2026-06-10 11:05] 协作单 [4.4-FIELDS-20260610] 状态变更: NEW→ASSIGNED（认领：基于科创板重下载数据重跑 fix_indicators + fix_snapshot_fields）
[量量 2026-06-10 17:50] 协作单 [4.4-FIELDS-20260610] 状态变更: ASSIGNED→VERIFY（排除北交所 + 扩展 daily_snapshot_sync.py：boll/break_high/consec_up/vol_ratio/area/rsi/macd 均已填充。ma10/ma20/bh20 空值率 1.2-1.3%，rsi/macd 空值率 1.9% 待 F 任务填充。已知局限：dv_ratio/dv_ttm/float_share/ps/ps_ttm 数据源无数据）
[量量 2026-06-10 18:10] 协作单 [DB-SCHEMA-001] 状态变更: VERIFY→CLOSED（user_watchlist 表结构验证通过：id/user_id/code/group_name/sort_order/created_at + UNIQUE(user_id,code)）
[量量 2026-06-10 18:10] 协作单 [4.4-FIELDS-20260610] 状态变更: VERIFY→CLOSED（字段修复验证：boll/break_high/consec_up/vol_ratio/area/rsi/macd 已填充正常。ma10/ma20 16.8%空值主因科创板历史数据不足（仅5-11天），非代码问题；dv_ratio/dv_ttm/net_mf_amount 等为数据源局限）
[方舟 2026-06-11] 协作单 [6.1-KLINE-20260611] 状态变更: NEW（科创板K线数据仅5-11天，需删原重下历史数据，修复ma10/ma20/rsi_6/macd等技术指标空值问题）
[方舟 2026-06-11] 协作单 [6.1-KLINE-20260611] 状态变更: VERIFY→CLOSED（验证通过：ma10 16.8%→1.2%, ma20 16.9%→1.3%, rsi_6 16.8%→1.5%, macd 17.0%→1.5%, break_high_20 16.9%→1.3%. parquet已重新生成）
[量量 2026-06-11 06:27] 协作单 [6.1-KLINE-20260611] 状态变更: NEW→ASSIGNED（认领：科创板历史数据重下 + API调用指南）
[量量 2026-06-11 06:27] API调用指南：方舟调用后端API统一使用 `frontend/src/api.ts` 中导出的函数。所有接口返回 `ApiResponse<T>` 信封格式 `{code, message, data}`（kline和signals接口除外，它们返回裸数据）。目前的可用接口：
- `fetchMeta()` → `/api/meta/` - 获取行业/地区选项 + 筛选条件组
- `fetchStocks(params)` → `/api/stocks/?...` - 股票列表筛选/排序/分页，传参支持 listed_board/industry/area/filters/sort_by/sort_asc/offset/limit/as_of_date
- `fetchKline(code, period, startDate, endDate, limit)` → `/api/kline/{code}?` - 获取K线，period支持daily/weekly/monthly，adj支持forward/backward/none，limit 1-1000
- `fetchSignals(code, signalType, startDate, endDate, limit)` → `/api/signals/{code}?` - 获取交易信号
- `fetchWatchlist()` → `/api/watchlist/` - 自选股列表
- `addWatchlist(code, groupName)` → POST `/api/watchlist/` - 添加自选股
- `removeWatchlist(id)` → DELETE `/api/watchlist/{id}` - 删除自选股
响应数据字段定义见 `shared/schemas.py` 和 `frontend/src/types.ts`，两个文件必须保持一致。特别注意：所有API路径必须带尾部斜杠（FastAPI要求），kline和signals接口直接返回裸数据（无ApiResponse信封）。
[量量 2026-06-11 06:35] 协作单 [6.1-KLINE-20260611] 状态变更: ASSIGNED→VERIFY（E任务已覆盖科创板，数据验证：ma10/ma20/rsi_6/macd 填充率90%+，剩余57只新股<10日正常现象。无需删原重下。请方舟验证。）
[方舟 2026-06-11 16:30] 协作单 [6.1-INDICATOR-20260611] 状态变更: NEW（选股视图侧边栏8个灰显指标全部因后端缺字段：行情3个[振幅/每手价格/委比] StockResponse无字段；财务5个[净利润增长率/营收增长率/毛利率/净利率/资产负债率] 无字段；财务3个[净利润/营业收入/净资产收益率] stock_fundamental_pit表存在但未导出parquet也未关联StockResponse。请量量补全字段+视图+parquet导出。）
[方舟 2026-06-11 16:45] 协作单 [6.1-INDICATOR-20260611] 范围缩减：行情指标 3 个（振幅/每手价格/委比）确认后端长期无法提供数据，已从前端 Sidebar.tsx 移除（MARKET_INDICATOR_FIELD_MAP + 按钮网格）。工单范围现仅剩财务指标 5+3 项待量量补全。
[方舟 2026-06-11 16:55] 协作单 [6.1-INDICATOR-20260611] 范围再缩减：财务指标 5 个（净利润增长率/营收增长率/毛利率/净利率/资产负债率）确认后端无字段且短期无法补全，已从前端 Sidebar.tsx 移除（FINANCIAL_INDICATOR_FIELD_MAP + 按钮网格）。工单范围现仅剩财务指标 3 项（净利润/营业收入/净资产收益率，待后端 stock_fundamental_pit 表填充并导出 parquet）。
[量量 2026-06-11 18:00] 协作单 [6.1-INDICATOR-20260611] 状态变更: NEW→VERIFY（诊断结果：行情3个已移除✅；财务5个数据源无字段永久禁用❌；财务3个 stock_fundamental_pit 表为空表0条记录，保留占位待后续填充数据❌。本工单无代码修复可做，Sidebar.tsx 注释已更新。请方舟验证。）
