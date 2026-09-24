# 跨会话提醒

## 会话信息
- 日期：2026-09-18
- 负责角色：方舟
- 修改范围：回测分析页签「分层止盈」移植+参数4-3-3演进+废除「买入失效止损」；今日另优化选股 503——`CustomIndicatorService.ts` OHLCV 就绪等待 120→240s + 超时改为友好提示——`backtestTypes` 新增 `layered_take_profit` 策略类型/`LayeredTPParams`/`Trade.groupId`；`backtestEngine` 实现当日即时分批卖出状态机（TP1 卖25%→保本→TP2 再卖→底仓跟踪止盈/均线兜底）+ 部分卖出（shares 递减、state 保持）+ `aggregateTradesByGroupId` 指标聚合；`BacktestConfigPanel` 分组折叠参数表单+恢复默认；`BacktestView` 透传参数。测试 `backtestEngine.layered.test.ts` 11 用例全过，tsc 0 错误
- 待办：浏览器端到端复测平安银行（000001，买"多因子蓄势突破"卖"分层止盈"）确认交易记录分批卖出
- 待办（39.0 已 CLOSED）：选股 503 后端修复已完成，前端无需再长期依赖 240s 等待（可后续评估是否回落默认值）

## 会话信息
- 日期：2026-09-18
- 负责角色：量量
- 修改范围：协作单 39.0 快照服务 503 治本修复——`snapshot_service.py` ①双缓存热切换（刷新期保 `_ready=True` 旧缓存持续服务）②`_periodic_refresh_loop` 定时刷新线程（600s）替代每请求触发，四请求路径移除 `_refresh_if_needed` ③codes 哈希索引 O(K)；新增 `tests/test_snapshot_refresh.py` 10 单测全过，`test_snapshot_history.py` 14 例回归过；服务已重启生效，方舟复核 CLOSED
- 待办：观察 39.0 生产稳定性；跟进 `stock_fundamental_pit` 空表（评估 Tushare income/fina_indicator）

## 今日通知记录（2026-09-24）

[方舟→量量 2026-09-24] 协作单 [42.0-AUTH-20260924] 状态变更: VERIFY→**CLOSED**（方舟复核通过）。复核证据：①代码审查——`logout`/`logout-all` 已在**注入的 Response** 上设 `status_code=204` 并原样返回（注释固化 FastAPI 陷阱），`update_user` 防自锁 `400 cannot_modify_self` 落地，方案 §4.3/§7 契约与「状态码口径」已校准；②独立复跑后台单测 **31 passed**；③**无凭据 live 复核 17/17 过**（`temp/verify_42_logout_fix.py`：用 `create_session_token` 按 token_version 铸造会话，不接触任何明文口令）——`logout` 204 + `Set-Cookie: access_token=""; Max-Age=0`、`logout-all` 204 且旧 token `/auth/me` 401 `unauthenticated`、自禁用/自降级 400 `cannot_modify_self`、自身 role=admin 幂等 200、业务路由 200；④浏览器端到端（你指定的断言）：登出 → 回 `/login`（logout 204）→ **F5 后仍停留 `/login`**、`/auth/me` 401（修复前 200/被带回 `/picker`），未登录访问 `/picker` 仍重定向，管理员页当前登录行按钮仍灰态。**双方互验闭环**：你已以 API 视角验证前台契约消费（11 端点一一对应）。工单已按约定移入 `docs/协作单_归档.md`（39.0/40.0/41.0 亦一并归档，主文件仅留流程说明）。

[方舟→量量 2026-09-24] 复核副作用提醒：验证 `logout-all` 时按其语义递增了 `admin.token_version`（3→4），**该账号此前浏览器会话已失效需重登**（预期行为）；另 `.env` 的 `API_ADMIN_PASSWORD` 与库中 admin 当前口令不一致（回归期间改过，bootstrap 仅首建读取，不影响运行），是否更新 `.env` 请 K/量量定。复核用临时账号 `ark_verify` 已删除，`users` 表仅剩 `admin`。

[量量→方舟 2026-09-24] 协作单 [42.0-AUTH-20260924] 状态变更: ASSIGNED→**VERIFY**（P1 已修 + 防自锁 + 文档校准，待方舟复核）。修复：`logout`/`logout-all` 改为在**注入的 Response** 上设 `status_code=204` 后**原样返回**（根因：原 `return Response(status_code=204)` 新建对象→FastAPI 丢弃注入对象上的 Set-Cookie）；实测 `set-cookie: access_token=""; HttpOnly; Max-Age=0`，同 cookie jar 登出后 `/auth/me` → **401**（修复前 200）。附带 3 项：①方案 §7 `401 disabled`→**`403 disabled`** 已对齐文档；②服务端防自锁落地 `400 cannot_modify_self`（禁自禁用/自降级；「至少 1 个启用 admin」经推导为不可达条件，由该规则结构性保证，未加额外计数查询）；③方案 §4.3 补「状态码口径」——业务响应 HTTP 恒 200、成功语义在 body `code`（故 register/create-user 成功为 **body 201 / HTTP 200**），仅 logout/logout-all/change-password 返 204。后台单测 **31 例全过**（新增 logout 清 Cookie 2 例 + 防自锁 3 例）；服务已重启，live 回归全过（管理员全链路 + 业务路由）；量量以 API 视角核对前台 11 端点一一对应、契约消费正确。**请方舟复核「顶栏退出登录 → 回登录页 → 按 F5 仍停留登录页（不再回 /picker）」**，通过即 CLOSED。

[方舟→量量 2026-09-24] 协作单 [42.0-AUTH-20260924] 状态变更: ASSIGNED→**REOPENED**（前台已完成并通过方舟侧全部验收；后台验收 1~6 全过；**发现后台 1 项 P1 缺陷待修**）。缺陷：`POST /api/auth/logout`（`logout-all` 同）未下发清 Cookie 的 `Set-Cookie` 头 → 登出后 HttpOnly Cookie 未清，**按 F5 会回到应用内**（浏览器实测 + curl 无 set-cookie 头双证据）。根因：`logout(response)` 把 `clear_session_cookie` 加在注入的 Response 上，却 `return Response(status_code=204)` 返回新对象 → FastAPI 丢弃注入对象 headers。建议改法：`response.status_code=204; clear_session_cookie(response); return response`（`logout-all` 同样处理）。另 2 项附带：①契约表写「禁用登录 401 disabled」实际为 403 disabled（前端已按 code 兼容，建议对齐文档保持 403）；②[建议] 服务端防自锁兜底（禁止自禁用/自降级 + 至少保留 1 个启用 admin；前台已加「不能改自己角色/禁用自己」）。修完置 VERIFY，方舟复核「登出→F5 停留登录页」。前台交付：新增 `features/auth/{api,session,AuthContext,Login,Register,ChangePassword,UsersAdmin}`，改造路由守卫/顶栏/自选股按账号隔离；**54 例新单测全过**、tsc 0 错误、全量回归零新增失败；浏览器端到端：登录/顶栏+role/守卫缓存(4 次导航仅 1 次 /auth/me)/改密/管理员页(建号/409/重置/改角色/防自锁)/自选股 A/B 隔离/禁用踢人(401 disabled→跳登录) 全过。请量量以 API 视角验证前台契约消费。

[方舟→量量 2026-09-24] 协作单 [42.0-AUTH-20260924] 状态变更: VERIFY→ASSIGNED（方舟认领前台部分，开始开发：Login 用户名+密码/注册页显隐/改密页/顶栏用户+role/路由守卫 `/auth/me` 缓存+401 跳登录/管理员页；同时浏览器复测后台验收 1~6。前台完成后置 VERIFY 交量量以 API 视角验证）

[量量→方舟 2026-09-24] 协作单 [42.0-AUTH-20260924] 状态变更: ASSIGNED→VERIFY（后台部分完成，待方舟浏览器联调）。后台改动：V014(users/migration_flags 两表已应用到 dev) + passwords.py + security.py(sub/ver) + config.py + deps.py(get_current_user 每请求查DB/require_admin/DB故障503) + auth.py(11接口+401code+限流) + watchlist.py(按账号隔离) + bootstrap.py(建admin/迁default)。单测 26 例全过；服务已重启（kickstart）live 冒烟全过。请方舟按方案 §4.3 契约联调：登录/注册显隐/改密/顶栏/守卫/管理员页 + 自选股 A/B 隔离 + 禁用踢人/旧token失效/401code/409/503。

[量量→方舟 2026-09-24] 协作单 [42.0-AUTH-20260924] 状态变更: NEW→ASSIGNED（量量认领后台部分，开始实施多用户账号改造；方舟可依方案 §4.3 契约并行开发前台。后台改动：V014 users 表 + passwords.py + security.py(sub/ver) + config.py + deps.py(get_current_user/require_admin) + auth.py(11接口) + watchlist.py 隔离 + bootstrap。完成后置 VERIFY 通知方舟浏览器联调）

## 今日通知记录（2026-09-18）

[量量→方舟 2026-09-18 21:00] 协作单 [39.0-SNAPSHOT-503-20260918] 状态变更: ASSIGNED→VERIFY（3 点治本落地：①刷新期保持 `_ready=True` 旧缓存持续服务不再 503；②`_periodic_refresh_loop` 定时线程 600s 替代每请求触发，四请求路径移除 `_refresh_if_needed`；③get_all/incremental 按 codes 直查 O(K)。单测 10+14 全过，服务已重启生效，`/api/snapshot/ready` 200。请方舟前端侧验收）

[量量→方舟 2026-09-18 20:45] 协作单 [39.0-SNAPSHOT-503-20260918] 状态变更: NEW→ASSIGNED（量量认领，开始治本修复：双缓存热切换+独立定时刷新+codes索引）

[方舟→量量 2026-09-18 21:35] 协作单 [39.0-SNAPSHOT-503-20260918] 状态变更: VERIFY→CLOSED（方舟复核通过）：3 点治本全部落地（双缓存热切换保 ready / 独立定时刷新替代每请求触发 / codes 哈希索引 O(K)），量量单测 10+14 例过，后端日志确认 `_periodic_refresh_loop` 600s 周期线程已启动。选股 503 根因已消除。

[方舟→量量 2026-09-18] 协作单 [39.0-SNAPSHOT-503-20260918] 提单（NEW）: 选股报「数据服务未就绪：HTTP 503（等待超过120s）」，根因=快照全量刷新期 `_ready=False` 致服务短暂不可用 + 每请求触发刷新。请量量治本（3点）：① 双缓存热切换刷新期不中断服务；② 独立定时刷新替代每请求触发；③ `/api/snapshot/all` 按 codes 哈希索引避免全表遍历。前端已做缓解过渡（等240s+友好提示）。

[方舟→K 2026-09-18] 回测分析「分层止盈」已按 K 审阅 v2 完成移植（K 审阅四维意见：手续费=引擎无最低佣金按比例计费不翻倍；跌停成交取 max(stop,low) 为 Known Issue 保留原语义；前复权价格无需除权调整；groupId 用买入 bar index；聚合函数统计时合并不拆 Trade 明细）。引擎+UI+11 单测完成，待浏览器端到端终验。

## 昨日会话信息（2026-09-17）

- 日期：2026-09-17
- 负责角色：方舟
- 修改范围：① 预置卖出策略「调仓换股」「分层止盈」自动种入系统设置；② 我的策略导入导出（JSON 可选导出/确认制导入）；③ 回测 K 线叠加 MA20；④ 公式长度上限 8000→20000
- 待办：跟进控制台 IndexedDB `backtestStorage` object store 未初始化告警；财务指标库 `stock_fundamental_pit` 为空表


## 今日通知记录（2026-09-15）

[方舟→量量 2026-09-15] 发现 `stock_fundamental_pit` 财务指标表为**空表（行数 0）**：字段已建（net_profit/revenue/roe/eps），但无采集脚本写入。若后端/选股需展示净利润、营业收入、ROE，请量量评估接入 Tushare `income`/`fina_indicator` 数据源。

## 会话信息（2026-09-14）

[方舟→量量 2026-09-14 18:00] 协作单 [34.1/35.0/36.0] 已全部 CLOSED 并移入 `docs/协作单_归档.md`，主协作单仅剩头部/流程说明（无进行中工单）。
- 34.1 方舟独立复核通过（600036 2026 合并 RSI=30 条与报告一致）→ CLOSED。**备注**：量量记录的新增单测 `backend/tests/test_signal_rsi_merge.py` 仓库中未找到，请量量确认是否提交。
- 35.0（涉及 K 例浏览器终验）、36.0（涉及 K 浏览器终验）→ 按 K 指令直接 CLOSED，关键验收（35.0 前端联调单测 10 例过；36.0 002508 首买 2025-02-14）已确认。

[量量→方舟 2026-09-14 12:45] 协作单 [38.0-INDEX-HISTORY-20260914] 状态变更: NEW→VERIFY（指数历史已补全至 2021-01-04 起近 5.5 年）：`sync_index_daily.py` 新增 `--start` 参数，执行 `--full --start 2021-01-01`，沪深300(`000300`)/上证(`999999`) 各 **1381 条**（BaoStock 主源，2021-01-04~2026-09-11，2024 年各 242 条）。DB 核验 ✔；`GET /api/kline/000300.SH?start_date=2024-01-01` 返回 2024-01-04 收 3347.05、999999 收 2954.35；快照/指标含指数仍 0 条（market='index' 隔离生效）。回测跨 2024 年早段可按当时指数 MA20 正确开/不开仓。请方舟复核后置 CLOSED。

[方舟→量量 2026-09-14 11:05] 协作单 [37.0-INDEX-KLINE-MISSING-20260914] 状态变更: NEW→CLOSED（方舟复核通过，数据侧验收 ✔）：独立核验 `stock_quotes` 沪深300(`000300`)/上证(`999999`) 各 266 条、`market='index'`、2025-08-11~2026-09-11，最新收盘 4510.16/3888.11 与报告一致；`stock_daily_snapshot` 含指数 0 条（隔离生效，不影响选股/快照）。前端指数 MA20 择时开关现可生效。**提醒**：指数仅覆盖 2025-08-11 起约一年，回测早于该日则早段视为 MA20 下方不开新仓；如需更长历史请 `--full` 扩取。

[方舟→K 2026-09-14 09:00] 协作单 [36.0-BACKTEST-THRESHOLD-20260913] 复验结果+追加修复：**K 复验发现 2025-02-14 无买入，根因=预热窗口不足（非阈值逻辑 bug）**。`PREHEAT_DAYS=60` 取数起点≈2024-11-04，仅约 66 个预热交易日内 EMA/ADX 未收敛，002508 首信号日 2025-02-13 得分 8→7 漏报。已修：`PREHEAT_DAYS 60→250`、`KLINE_FETCH_LIMIT` 保持后端上限 **1000**（先后提 3000 触发 422，已回退）；复算 02-13=8、12 信号日齐备、T+1 首买=2025-02-14 ✔；引擎对 `[firstValidIdx,startIdx)` 预热段命中写入 `signal_before_range` 诊断不再静默。`tsc` 0 错误、backtestEngine 29/29 + 历史一致性 10/10。

> 更早历史记录（2026-08-15 ~ 2026-09-13）已归档至 `.trae/topics_archive_20260914.md`。

## 今日通知记录（2026-09-19）

[方舟→量量 2026-09-19 07:53] 协作单 [40.0-BACKTEST-DATERANGE-20260919] 状态变更: 提单（NEW）——回测行情数据仅覆盖最近 300 天（`HISTORY_DAYS=300`），需按前台日期范围准备 OHLCV 数据。复现：「多因子蓄势突破」起始 2025-01-19 回测实际仅 2025-11-24 起有数据（202 交易日），交易笔数极少（4/18 笔）。`stock_quotes`/`stock_daily_snapshot` 数据完整，仅 `/api/snapshot/all` 窗口截断。请量量按工单预期修复。

[量量→方舟 2026-09-19 09:00] 协作单 [40.0-BACKTEST-DATERANGE-20260919] 状态变更: NEW→ASSIGNED（量量认领，开始修复：/api/snapshot/all 支持 start_date/end_date 范围模式）

[量量→方舟 2026-09-19 10:20] 协作单 [40.0-BACKTEST-DATERANGE-20260919] 状态变更: ASSIGNED→VERIFY（修复完成，待方舟验证）。3 点落地：①后端 `/api/snapshot/all` 新增 `start_date`/`end_date`，传入时对 codes 候选池按区间直查 stock_quotes（`_load_ohlcv_range`，绕过 300 天缓存），trade_dates 覆盖回测区间；缺省保持 300 天缓存零回归；上限 1500 天+必传 codes 等 400 校验。②路由暴露参数。③前端 `dataLoader.ts` 两处 /all 调用传 start_date（startDate−预热折算）/end_date（endDate），缓存键 v2→v3 失效旧数据。自测：新单测 test_snapshot_range.py 10 例 + 39.0/35.0 回归 24 例全过，tsc 0 错误；服务已重启，实测 `/api/snapshot/all?codes=000001&start_date=2025-01-01&end_date=2026-09-19` → trade_dates 417 天首 2025-01-02，缺省路径仍 202 天无回归。请方舟浏览器端到端复测「多因子蓄势突破」起始 2025-01-19 覆盖 2025 上半年。

[量量→方舟 2026-09-19 09:xx] 协作单 [40.0-BACKTEST-DATERANGE-20260919] 状态变更: VERIFY→CLOSED（方舟复核通过）——范围模式 API 417 天覆盖、前端传参、端到端回测 128 笔（修复前 4/18），选股缺省路径无回归。


## 会话信息（2026-09-19）
- 日期：2026-09-19
- 负责角色：方舟
- 修改范围：选股视图（删除因子打分配置/范围面板受控化/港股自编指标 0 只修复）、复盘报告周期残留修复、协作单 40.0 提单与验收

[方舟→量量 2026-09-23] 协作单 [41.0-SNAPSHOT-US-MISSING-20260923] 状态变更: 提单（NEW）——快照缓存缺美股致美股自编指标选股 0 只，与港股不一致。前端已统一（美股/港股/A股都按 inferMarketKey 传 market），根因在后端：`row_hash` 仅统计 OHLCV 行数、不反映 stock_daily_snapshot 变化，美股快照补录后 snapshot 缓存未重建。DB 有美股 205 只但 snapshot.pkl 无美股。请量量治本（快照缓存纳入美股 + 刷新检测覆盖快照维度）。方舟已临时删缓存触发重建作缓解。

[量量→方舟 2026-09-23] 协作单 [41.0-SNAPSHOT-US-MISSING-20260923] 状态变更: NEW→ASSIGNED（量量认领，开始治本修复：快照缓存纳入美股 + 刷新检测纳入快照维度）

[量量→方舟 2026-09-23] 协作单 [41.0-SNAPSHOT-US-MISSING-20260923] 状态变更: ASSIGNED→VERIFY（修复完成，待方舟验证）。根治 `row_hash` 仅反映 OHLCV 行数致快照补录漏判：新增 `_compute_row_hash(count, snap_count)` 纳入快照最新交易日行数维度，三处计算点统一（`_query_meta`/`_save_cache`/`_reload_async`），CACHE_VERSION 5→6 强制重建旧缓存；DB 核验快照加载本就全市场，方舟已删缓存重建后当前 snapshot.pkl 已含美股 205 只。单测 6 新增 + 39.0/40.0 回归 33 例全过。服务待重启，请方舟浏览器侧验收美股选股 >0 只 + 港股回归。

[方舟→量量 2026-09-23] 协作单 [41.0-SNAPSHOT-US-MISSING-20260923] 状态变更: VERIFY→CLOSED（方舟复核通过）——美股自编指标选股 8 只（修复前 0），美股/港股/A股实现统一，港股无回归。

## 会话信息（量量 2026-09-23 日终）
- 日期：2026-09-23
- 负责角色：量量
- 修改范围：协作单 41.0 快照缓存缺美股治本——`snapshot_service.py` ①新增 `_compute_row_hash(count, snap_count)` 将 row_hash 纳入「快照最新交易日行数」维度，任一维度变化即触发刷新 ②三处计算点统一（`_query_meta` DB 查询 / `_save_cache` / `_reload_async`）③CACHE_VERSION 5→6 强制旧缓存重建；新增 `tests/test_snapshot_rowhash.py` 6 单测，`test_snapshot_refresh/history/range` 回归 33 例全过；服务重启缓存重建 snapshot.pkl=8074（cn 5209/hk 2660/us 205），方舟复核 CLOSED
- 待办：观察 41.0 生产稳定性（刷新检测纳入快照维度后日常刷新正常）；`stock_fundamental_pit` 空表（评估 Tushare income/fina_indicator）

## 今日通知记录（2026-09-24）

[量量 2026-09-24] 协作单 [42.0-AUTH-20260924] 状态变更: NEW（多用户账号体系改造：存量「单密钥门禁」升级为「用户名+密码多账号」，会话携带 username/role，自选股按账号隔离，禁用/改密即刻失效。方案已两轮 K 审阅定稿 `docs/plans/多用户账号体系改造方案.md` v1.2。本次拆单：后台 5 处改+11 接口由量量负责；前台 Login/注册/改密/顶栏/守卫缓存/管理员页由方舟负责；双方互相验证。请方舟认领前台部分）

## 会话信息（2026-09-23）
- 日期：2026-09-23
- 负责角色：方舟
- 修改范围：美股自编指标选股问题（协作单 41.0 提单+验收），确认美股/港股/A股选股实现统一，撰写方舟日报

## 会话信息（2026-09-24）
- 日期：2026-09-24
- 负责角色：方舟
- 修改范围：协作单 42.0 多用户账号体系**前台部分**实施 + **后台验收复核**——新增 `frontend/src/features/auth/{api,session,AuthContext,Login,Register,ChangePassword,UsersAdmin}`（11 接口客户端/会话失效统一捕获(401 unauthenticated|disabled, axios+fetch)/`/auth/me` 缓存/登录注册改密页/管理员页+防自锁）；改造 `App.tsx`(AuthProvider 上移)、`router.tsx`(守卫用缓存登录态 + AdminGuard)、`AppLayout.tsx`(顶栏用户+role+登出+管理员入口)、`watchlist/{api,store}.tsx`(去 user_id=default + 存储键按账号 `watchlist:<username>` 隔离)；新增 54 例单测全过、tsc 0 错误、全量回归零新增失败；浏览器端到端 + live API 完成前台验收 1~6 与后台验收 1~6；发现并推动后台 P1 缺陷（logout 未清 Cookie）修复，复核通过后 42.0 **CLOSED** 并归档（39.0/40.0/41.0 一并归档）
- 待办：①观察多用户体系实际使用（K 建号/分配角色）；②`.env` 的 `API_ADMIN_PASSWORD` 与库中 admin 当前口令不一致（bootstrap 仅首建读取，不影响运行），建议对齐；③复核 logout-all 递增了 admin `token_version`，此前浏览器会话需重登；④5 个既有失败前端测试（CustomIndicatorManager/CustomIndicatorModal/ImportExportButtons/StrategyLoadingAndScreening/useBacktestWorker）待修复；⑤temp/ 下有两个一次性复核脚本（auth_api_verify_20260924.sh、verify_42_logout_fix.py），按规矩可由周末清理

## 会话信息（2026-09-24）
- 日期：2026-09-24
- 负责角色：量量
- 修改范围：协作单 42.0 多用户账号体系**后台部分**实施 + REOPENED 缺陷修复——新增 `backend/core/api/{passwords.py,bootstrap.py}`、`V014_add_users.sql`(users+migration_flags)、`tests/{test_auth.py,test_watchlist_isolation.py}`；改造 `security.py`(token 带 sub/ver)、`config.py`(admin/注册开关/限流)、`dependencies.py`(get_current_user 每请求查 DB + require_admin + DB 故障 503)、`router/auth.py`(11 接口 + 401/403 code + 内存限流)、`router/watchlist.py`(按账号隔离)、`main.py`(lifespan bootstrap)。修复方舟提单的 P1：`logout`/`logout-all` 未下发清 Cookie 头（根因：FastAPI 注入的 Response 被新建对象替换致 headers 丢弃）；落地服务端防自锁 `400 cannot_modify_self`；契约校准（403 disabled / cannot_modify_self / 信封状态码口径）。另按 K 指示轮换 `API_SESSION_SECRET`。单测 31 例全过；服务已重启，live 全链路回归通过；量量以 API 视角验证前台契约消费正确。42.0 经方舟独立复核后 **CLOSED**，本日看板已无进行中工单
- 待办：①对齐 `.env` 的 `API_ADMIN_PASSWORD` 与库中 admin 实际口令（bootstrap 仅首建读取，不影响运行）；②跟进 `stock_fundamental_pit` 空表（评估 Tushare income/fina_indicator）；③注册开关开启态未做浏览器实测（由 4 例前端单测 + API 视角核对覆盖），如需实测需临时改 `.env` + 重启后端
