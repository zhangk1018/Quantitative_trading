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

## 今日通知记录（2026-09-29）

[方舟→量量 2026-09-29 08:15] 协作单 [43.0-SNAPSHOT-MARKET-DATE-20260929] 状态变更: 提单（NEW）——**快照缓存按单一全局最新交易日加载，致最新快照日滞后的市场整市缺失，自编指标选股恒 0 只（P0）**。K 反馈「沪深 + 自编指标全部选不出股票」，复现定位到后端：`snapshot_service.py` `_query_meta` L184-188 取全表 `MAX(trade_date)`（无市场维度）+ `_load_from_db` L383-394 `WHERE trade_date = 该单一日期` → 只有全局最新日的行进缓存。实测：DB `us` 最新 9/25、`cn/hk` 9/28，`snapshot.pkl` 仅 7379 条（cn 5210 + hk 2169，**无美股**），live `GET /api/snapshot/all?codes=AAPL,MU,TSLA&market=us` → `total=0`（cn/hk 正常）。历史同类事故即本次反馈：9/25 A股中秋休市、港美股开市 → 全局 latest 落在 hk/us，cn 被整市剔除，日志 9/26 20:51 / 9/28 09:32 / 9/28 15:15 三次启动均「缓存加载完成：205 条快照」、9/28 全天 326 次「全量快照请求：0只股票」，9/28 21:23 缓存重建后才恢复。请量量按单修复（快照按市场维度取各市场最新日 + `row_hash` 快照维度同步多市场口径）。方舟已加前端守卫：候选股全部无 K 线时显式弹窗报错，不再静默 0 只（`CustomIndicatorService.computeAndFilter` + 6 例单测）。

[量量→方舟 2026-09-29 10:05] 协作单 [43.0-SNAPSHOT-MARKET-DATE-20260929] 状态变更: NEW→ASSIGNED（量量认领，开始修复）。已确认根因：快照维度的日期口径缺市场维度——`_query_meta` 取全表单一 `MAX(trade_date)`，`_load_from_db` 用等值日期加载，故最新快照日与全局 latest 不一致的市场（美股次日 08:30 跑天然滞后、A股遇节假日休市滞后）被整市剔除。按单内 4 项预期修复推进（①按市场维度取各自最新日加载 ②`_query_meta` 计数与 `row_hash` 同步多市场口径 ③`_latest_trade_date` 语义确认 ④指定 market 命中 0 时 WARN 日志）。

[量量→方舟 2026-09-29 11:00] 协作单 [43.0-SNAPSHOT-MARKET-DATE-20260929] 状态变更: ASSIGNED→**VERIFY**（P0 已修，待方舟验证）。4 项预期修复全部落地（均在 `backend/core/service/snapshot_service.py`）：①`_load_from_db`/`_load_raw_data` 快照查询改 CTE join 各市场各自 `MAX(trade_date)`（`WITH m AS (SELECT market, MAX(trade_date) d … GROUP BY market) … JOIN m ON m.market=s.market AND m.d=s.trade_date`），SELECT 增 `s.market`；②`_query_meta` 改单条 CTE 取「各市场最新日 + 该日 `COUNT(DISTINCT code)`」，`_compute_row_hash` 增第 3 参 `market_latest`（签名 = 排序后 `market=date` 的 `|`-join），计数刻意用 `COUNT(DISTINCT code)` 与 `_snapshot_cache`(dict 按 code 去重) 口径对齐，杜绝「哈希恒定不匹配→无限重建」；③`_latest_trade_date` 保持「各市场最新日最大值」（= 旧全局 MAX，不被滞后市场拉低），新增 `_market_latest` 承载各市场各自最新日、由 `_derive_market_latest(rows)` 从已加载行反推；④`get_all_snapshot` 指定 market 且候选 codes 非空但命中 0 时输出 WARN（含各市场最新日）。配套 `CACHE_VERSION` 6→7 强制重建 + `cache_meta.json` 持久化 `market_latest`。自测：`GET /api/snapshot/all?codes=AAPL,MU,TSLA&market=us` → **total=3**（修复前 0）、各 206 根 K 线；`snapshot.pkl` = **7599 条 = cn 5210 + hk 2184 + us 205**（修复前 7379 缺美股）；`cache_meta.json` 哈希与对活库实测 `_query_meta` 哈希逐位相同（不振荡）；cn/hk 零回归。单测新增 `backend/tests/test_snapshot_market_date.py`（11 例）并增补 rowhash/refresh/range 适配，全量 **205 passed / 2 failed**（2 项既存失败与本单无关）。**验收提示**：活库三市场日期当前已对齐（均 9/28），「market=us→total=0」现场症状已不复现（bug 潜伏态），正确性由单测构造「各市场最新日不一致」场景证明，请勿以「现场未复现」判未修复；验收项③（浏览器美股 + 自编指标）属前端侧，请一并复核。

## 会话信息（2026-09-29）
- 日期：2026-09-29
- 负责角色：方舟
- 修改范围：自编指标选股「一只都不中」排查——复现（沪深 科创板/全市场 + 「10条件选股」均能出结果 3/33 只，证明前端管道正常）→ 定位根因为后端快照缓存缺市场维度（协作单 43.0 提单给量量）+ 前端加缺 K 线守卫与单测

## 会话信息（2026-10-01）
- 日期：2026-10-01
- 负责角色：量量
- 修改范围：**美股日线清洗僵死事故（P0）**排查与修复（K 反馈看板美股「日线清洗 ○ 待执行」告警，查证属实）——根因链：①08:30 计划触发时机器处于 Deep Idle 睡眠（pmset 07:59:40 睡 → 09:59:41 DarkWake），launchd 错过触发点、唤醒瞬间才补跑；②补跑后机器进 Maintenance Sleep 循环（每次 DarkWake 仅 40~50 秒），子进程被反复冻结；③10:50:21 入睡瞬间进行中的 `ak.stock_us_daily` HTTPS 请求被冻结，唤醒后 socket 半死 + **AkShare 不暴露 timeout（requests 默认无限等待）→ 永久阻塞在 `SSL_read`**（`sample` 抓栈 + `lsof` + CPU 时间 0:00.00 三证据）。处置：终止僵死进程（PID 91954/91973）→ `task_run_log` 僵死 running 记录标记 failed 并注明原因 → `caffeinate -i -s` 包裹断点续跑（游标 `DTE` 与已落 61 只末位严格一致，复用安全）→ 补齐美股 9/30 全链（quotes 205 / indicators 202 / snapshot 204 / signals 182 / parquet 204×93）。**修复 A**：`backend/collector/datasource/akshare.py` 新增 `network_deadline`（SIGALRM 硬超时，单标的 60s / 全市场快照 180s，仅主线程生效、非主线程退化）+ 为原先静默 `return None` 的 except 补 WARNING 日志；**修复 C**：9 个 ETL 定时任务 plist 前置 `caffeinate -i -s --` 并逐个重载（未动 postgresql/backend），`pmset repeat wakeorpoweron TWRFS 08:25:00` 已生效，并实测 caffeinate 如实转发退出码与 stdout/stderr；**修复 D**：`backend/clean/enrich/export_parquet.py` 四个失败分支改为返回 False、`__main__` 以 `sys.exit(1)` 上报（原静默退 0 被 runner 误判成功）。新增测试 7（超时）+ 4（退出码）例，相关测试集 68 passed。**重要澄清**：本次那次 `Cross-device link` 失败实为**本地 Trae sandbox 拦截备份轮转 rename/unlink** 的假象（报错原文含 `TRAE Sandbox Error: hit restricted`），生产 launchd 环境无此问题，非 sandbox 下重跑退出码 0、轮转正常。`ETL_PIPELINE.md` → v1.14
- 待办：①核验 **10-02 08:30** 美股任务准点触发与日线覆盖度（加固闭环验证）；②`backend/tests/test_trade_signals_table.py` 收集报错（引用已不存在的 `save_trade_signals`，阻断 `pytest backend/tests/` 全量收集，属既有问题，与本次无关）；③`stock_fundamental_pit` 空表（延续项）；④本次提交一并携带 09-29 以来积压的前后端未提交改动

## 会话信息（2026-10-03）
- 日期：2026-10-03
- 负责角色：量量
- 修改范围：**港/美股周线"未生成"结构性缺陷修复（P0）**（K 周六晨报「港股和美股周线现在还没生成」并询问调度安排）——根因：周/月K 聚合只有一条 A 股日历驱动路径（`trade_calendar` 判「本周最后交易日」+ 聚合无 market 过滤 + 周期区间取 A 股日历），港/美股只是被顺带写出，由此产生①孤儿日永久丢（A 股休市而港美开市的交易日既不触发聚合、也落在任何区间外，2025-10 以来 hk 12 天/us 19 天；（code,ISO周）缺失对 hk 2,986/us 616）②美股末日缺收盘（US T+1 08:30 落库 vs 旧触发点周五 18:30）③打标与看板新鲜度错位。**改造**：`compute_bar_aggregation.py` 新增 `--market`（默认 cn）/`--lookback-periods`/`--rebuild --from/--to`，拆 cn（逻辑零改动，仅加 `market IN ('cn','index')`）与 hk/us（按各自数据源日历 HSI/.IXIC 划分 ISO 周/自然月、结算判据「周=该 ISO 周周六已到 / 月=自然月末已到」、齐备门禁、先删后插幂等自愈、日历不可用则跳过不猜）**两条分支**；新增 `com.quant.bar_aggregation.overseas.{weekly,monthly}.plist`（**周二~六 09:30 / 10:00**，caffeinate 包裹）并已安装加载；`load_launchd_plists.sh` 补加载行；`pipeline_health_check.py` 拆出 `_period_range` 按市场区分周期口径；**看板判据修复**：`monitor.py` 新增 `_expected_period_label`（cycle 任务期望日=该周期应产出的最后一个交易日，未结算则回退上一周期）+ 统一入口 `_expected_date_for_task`，抽出 `_is_trade_day`/`_last_trade_day_on_or_before` 复用（`_get_last_trade_date` 行为不变），消除「每月 1 号到月末三市场月K 恒 pending、每周一~四周K 恒 pending」的假告警；清理 31 行错标脏数据。**回填**：hk 1w 92 周期/227,294 行、hk 1m 21/54,214、us 1w 3,379/36,610、us 1m 777/8,392，全 0 跳过，缺失对归零（备份 `stock_quotes_bak_1w1m_hkus_20261003` 565,317 行 / `stock_quotes_bak_mislabel_20261003` 31 行）。**验证**：港美周线打标 10-02、09-25 孤儿日归位、cn 完全未变；0700.HK 周线 OHLCV 与日线逐字段一致；健康检查全绿；看板 hk/us/cn 周K月K 全 success（hk 基本面 pending 属既定设计）。新增测试 15+11=26 例；全量 242 passed / 2 failed（既存）。`ETL_PIPELINE.md` → v1.15
- 待办：①核验海外周K首个自动触发（**周二 10-06 09:30**）与日志落盘；②观察 **10-31（周六）** 港/美月K首次自动结算（月桶判据上线后首个自然月末）；③`test_trade_signals_table.py` 收集报错 + `stock_fundamental_pit` 空表（延续项）；④待 K 决策：hk 历史 2025-01-01 之前仍为旧口径打标（本次按确认范围未重建）

## 会话信息（2026-10-08）
- 日期：2026-10-08
- 负责角色：量量
- 修改范围：**美股基本面 ETL 失败修复（P0）**（K 晨报看板美股「基本面 ❌」）——根因：新浪美股列表接口（`ak.stock_us_spot()` 背后逐页抓取的 `US_CategoryService.getList`，当日 914 页）**个别分页偶发返回上游错误对象**（`{"__ERROR":"HY000","__ERRORMSG":"SQLSTATE[HY000]: General error: 2006 MySQL server has gone away",...}`，**无 `data` 字段**），AkShare 分页循环无容错（直接取 `data_json["data"]`）→ `KeyError: 'data'` → **单页异常即整任务失败**（10-08 三次重试 08:46/08:58/09:04 撞不同异常页全败；10-06/10-07 正常，属上游偶发抖动）。修复：`backend/collector/etl/sync_us_basic.py` 改**自实现分页**（复用官方签名/URL）——逐页重试 3 次、持续异常页跳过并累计、**跳过占比 >10% 放弃写入**（宁缺勿残）、单页 20s 超时、覆盖率 <90% 告警；live 补跑 **914/914 页**、写入 209 条，`stock_daily_basic`(us) **2026-10-07 已补齐**（total_mv/pe/close 全非空）。新增 `backend/tests/test_us_basic_sina_paging.py` **9 例全过**（含「无 `data` 不再抛 KeyError」关键回归）；相关回归 **77 passed / 1 failed**（`test_daily_job_runner.py::TestConstants::test_stage_definitions_have_expected_tasks` 断言 `len(STAGE2_TASKS)==1`、实际含 `index_sync`，为既存失败，与本改动无关）。另：**前端服务纳入 launchd 托管（P1）**——新增 `scripts/launchctl/com.quant.frontend.plist`（RunAtLoad+KeepAlive，vite 5173）、`load_launchd_plists.sh` 加前端加载段、`start.sh` 前端启停全面转 launchd（start 等拉起 / stop 提示 unload / restart 用 kickstart / status 标注 / fg 提示先卸载；`FRONTEND_START_TIMEOUT` 8→30）。验证：`launchctl list` 有 `com.quant.frontend`(PID 5827)、5173 返回 200 且 `<title>量化交易系统</title>`、`dev status` 前后端均 launchd 监督、**KeepAlive 实测 kill 后 3s 自动拉起新 PID**
- 待办：①核验 **10-09 08:30** 美股 ETL 全链（尤其「基本面」）在生产调度路径成功；②观察前端 launchd 服务稳定性（登录自启 + KeepAlive）；③修 `test_daily_job_runner.py` STAGE2 断言（既存）；④`us_job_runner._log_end` 失败时恒传 `error_message=None`（看板仅「执行失败」无原因），待评估；⑤`stock_fundamental_pit` 空表（延续项）

## 今日通知记录（2026-10-08）

[量量→方舟 2026-10-08] 本次提交**一并携带你 10-06 的未提交前端改动**（`useScreenerData.ts` 缓存键纳入 `selectedMarket` + `frontend/tests/functions/{screenerRangeHash,pinbarIndicatorImport}.test.ts` + `frontend/docs/自编指标-导入-Pinbar关键位反转.json`）。背景：`scripts/git_push.sh` 按设计一次性暂存「全部已跟踪变更 + 未忽略新文件」，无法只挑单侧文件，且项目既有惯例为「+ 补齐同期积压改动」（见 commit a8c2448）。**请补一份 10-06 的方舟日报**（`docs/daily_report/2026/10/` 下当前无 10-06 记录，`topics.md` 亦未登记该次会话），并按规范 5.1 交叉复核抽查本次量量日报的完成项。

[量量→方舟 2026-10-08] 前端服务已改由 launchd 托管（`com.quant.frontend`，RunAtLoad+KeepAlive）。**影响**：前端不再由 `start.sh` 用 nohup 拉起；`./start.sh dev stop` 不再停止前端，需 `launchctl unload ~/Library/LaunchAgents/com.quant.frontend.plist`；`./start.sh dev frontend fg` 调试前须先 unload 该服务，避免 5173 端口冲突。请复核「登录/重启后前端自启」与 KeepAlive 行为。

## 会话信息（2026-10-09）
- 日期：2026-10-09
- 负责角色：方舟
- 修改范围：**选股多选自编指标「交集为空」根因修复（P0）+ 执行效率优化（P1）**。根因：数据窗口全局共享——`useScreenerData.computeMaxLookback()` 对所有已选指标取公式最大数字 +5 只产出一个窗口、`sliceOhlcv` 全局切片后供每个指标复用，导致「再加一个指标会拉长另一个指标的输入窗口」，窗口敏感型公式（突破窗口前高/全窗极值/依赖 `len`）结果随之改变，组合结果不再是单独结果的交集（极端为 0）。修复：`CustomIndicatorService` 新增 `computeConditionLookback` 并**按各指标自身窗口切片**（接受完整 OHLCV）；`useScreenerData` 移除全局窗口/切片；`customIndicatorRunner` 移除**逐批前导 null 补齐**（改每只股票保持自身长度，避免 ADX 预热 `tr[:14]` 含 NaN 静默失效）。效率：**Pyodide Worker 池并行**（按核数 2~4，批次轮转，端到端 ~2.0–2.4×）、单批超时 30s→120s、批次 100→50、**按批进度透传 UI**（不再假死）、OHLCV 分批并发拉取。**浏览器真实公式回归**（Playwright+系统 Chrome、admin 登录、注入 localStorage 真实指标、沪深全市场 4978 只）：A=10条件选股(`>=8`) 100 只（425.6s→216.5s）、B=多因子蓄势突破(`>=9`) 58 只（449.7s→184.3s）、**A+B=2 只**（非 0，修复生效；321.0s→136.3s）；**优化前后命中数逐项一致**。测试：新增 `frontend/tests/functions/customIndicatorRunner.test.ts` + 扩展 `CustomIndicatorService.test.ts`；`tsc` 0 错误、前端全量 **1130 passed**。
- 待办：①浏览器复核「系统配置→自编指标」列表与选股联动无回归；②加载阶段（候选 ~24s+K线 ~50s）受后端 `/api/snapshot/all` 单请求耗时限制，前端并发无明显收益，如需提速评估给量量开协作单；③评估 Worker 池上限由 4 放宽（内存换速度）；④**10-06 方舟日报**仍需回填（缺该次会话细节，未凭空补写）。

## 会话信息（2026-10-10）
- 日期：2026-10-10
- 负责角色：方舟
- 修改范围：**港股/美股自编指标选股「加载慢 + 疑似 100% 通过」排查与修复（P0/P1）**。**实测结论**：用真实指标「8条件选股改进」(`>=6`) 走 Playwright+系统 Chrome：港股 2714 只有 K 线 → 命中 **236**；美股 201 只 → 命中 **57**；且港股与**离线逐位复刻管道完全一致（236=236）** → 前端筛选本身正确，**未复现「100% 通过」**。但仍定位并修复了 3 个真实缺陷：①**静默 100% 通过**——`filterGroup` 声明了自定义条件（`hasCustomIndicator`=true 走全量管道）但引用的指标已删除/未加载/公式为空时，`extractCustomConditions` 返回 `[]` → `computeAndFilter` 走「conditions 为空 → 全部通过」fail-open 分支 → **结果=候选全量**；修复：`runFullScreening` 增加声明条件必须可解析且公式非空的前置校验并抛错，`computeAndFilter` 对 conditions/公式为空改**显式抛错**。②`fetchOhlcvBatch` 只按 `codes[0]` 推断**整批**市场 → 混合市场候选（跨市场自选股）会整组丢 K 线；修复：改为**逐代码推断并分组**请求。③候选股无 K 线被**静默剔除**；修复：显式提示「N 只候选股缺少K线数据，已从结果中剔除」。**效率**：港股全市场自编指标选股 **406s → 86s（4.7×）**——候选分页并发（串行 84s→~7s）、OHLCV 并发 4→6（136s→~12s）、**移除「范围变化即 clearCache」**（K 线只与代码有关、与筛选范围无关，避免重复下载全市场）、计算 184s→~68s；**命中数不变（236）**。测试：`tsc` 0 错误。
- 待办：①**协作单 44.0 待量量处理**（后端 `/api/snapshot/all` OHLCV 窗口固定 300 自然日 ≈196~205 根 → `if n>=200` 在**沪深永不生效**、us/hk 生效 → **同一自编指标跨市场结果不可比**；详见 `docs/协作单.md`）；②本轮前端改动**未提交**，待 K 确认后随日报提交；③「100% 通过」如再出现，请提供**具体市场 + 指标名 + 期望/实际命中数**以便复现（当前环境已不能复现）；④10-06 方舟日报仍待回填。

## 今日通知记录（2026-10-10）

[方舟→量量 2026-10-10] 协作单 **[44.0-SNAPSHOT-OHLCV-WINDOW-20261010]** 状态变更: NEW（`/api/snapshot/all` OHLCV 历史窗口固定 300 自然日 → 各市场实际仅 196/201/205 根，导致含 `ema(...,200)` / `if n>=200` 的自编指标在**沪深永不生效**、港美股生效，同一指标跨市场结果不可比；请评估放宽窗口至稳定覆盖 ≥250 交易日或改按交易日条数截取，并按各市场 latest 计算）。我在选股页实测：港股 2714 只 → 236、美股 201 只 → 57，**前端管道与离线复刻逐位一致**，故根因不在前端；本轮前端另修了 3 个静默/丢数据缺陷 + 港股提速至 86s（详见协作单「方舟已做的前端侧配合」）。

[量量→方舟 2026-10-10 04:00] 协作单 [44.0-SNAPSHOT-OHLCV-WINDOW-20261010] 状态变更: NEW→**VERIFY**（已修复，待方舟复核）。修复 3 点（均在 `backend/core/service/snapshot_service.py`）：①新增 `OHLCV_HISTORY_DAYS=450` 自然日（缺省路径缓存窗口），原 `HISTORY_DAYS=300` 仅留给范围模式缺省回看、口径不变；②新增 `_ohlcv_window_bounds`——上界 `max(各市场 latest)`、**下界基准 `min(各市场 latest)`**（复用 43.0 `_market_latest`），滞后市场（us T+1 / A股节假日休市）不再被截短；三处查询点（`_query_meta` 计数 / `_load_from_db` / `_load_raw_data`）参数统一，保证 `row_hash` 与缓存内容一致；③`CACHE_VERSION` 7→8 强制重建。**实测**：`codes=600519`/`0813.HK`/`CMG` 的 `ohlcv.length` **196/201/205 → 299/307/312**（均 ≥250，`if n>=200` 三市场均可进入）；零回归——范围模式 `trade_dates=417`（同 40.0）、`market=cn/hk/us` 5210/2721/205 只不变；哈希一致（`_query_meta` 计数 2,288,470 与加载条数逐位相同，重启命中缓存未触发重建）。**成本对比**：`ohlcv.pkl` 119MB→209MB、冷启动延迟加载 25.60s→25.12s（无回归）、全量重建 219s。新增 `tests/test_snapshot_ohlcv_window.py` 13 例、快照相关 67 例全过、后端全量 264 passed / 2 既存 failed。**请方舟复核**：浏览器侧用含 `ema(close,200)` / `if n>=200:` 的同一自编指标在沪深/港股/美股三市场验证长周期分支均可进入（后端数据已就绪）。另：**43.0 仍为 VERIFY 待你复核**（10-01 起未见关闭），如需一并处理请告知。

## 会话信息（2026-10-10）
- 日期：2026-10-10
- 负责角色：量量
- 修改范围：**协作单 44.0 `/api/snapshot/all` OHLCV 历史窗口修复（P1）**——缺省路径窗口由「全局 latest 倒推 300 自然日」改为「**450 自然日 + 下界基准取 min(各市场 latest)**」：新增 `OHLCV_HISTORY_DAYS = 450`（原 `HISTORY_DAYS = 300` 仅保留给范围模式缺省回看，口径不变）；新增 `_ohlcv_window_bounds(latest, market_latest)`（上界 = max(各市场 latest)，下界基准 = min(各市场 latest)，复用 43.0 `_market_latest`），三处查询点 `_query_meta`（计数）/ `_load_from_db` / `_load_raw_data` 参数统一，保证 `row_hash` 与缓存内容口径一致；`CACHE_VERSION` 7→8 强制重建。**实测**（重启重建后 admin 会话直连）：三市场 `ohlcv.length` **196/201/205 → 299/307/312**（均 ≥250，`if n>=200:` 三市场均可进入）；零回归——范围模式 `trade_dates=417`、`market=cn/hk/us` 5210/2721/205 只均不变；`_query_meta` 计数 2,288,470 与加载条数逐位相同、重启命中缓存未触发重建（判据稳定）。**成本**：`ohlcv.pkl` 119MB→209MB、冷启动延迟加载 25.60s→25.12s（无回归）、全量重建 219s。新增 `backend/tests/test_snapshot_ohlcv_window.py`（13 例）；快照相关 6 文件 67 例全过；后端全量 264 passed / 2 既存 failed（`test_daily_job_runner` STAGE2 断言、`test_daily_snapshot_sync` 港股涨停阈值，均与本单无关）。工单已置 **VERIFY** 待方舟复核
- 待办：①等待方舟复核 44.0（重点：浏览器侧同一自编指标跨三市场 `n>=200` 分支均可进入）；②**协作单 43.0 自 09-29 起长期停留 VERIFY**，方舟未回复复核结论，本次已在 topics 提醒；③`test_trade_signals_table.py` 收集报错（既存，阻断全量收集）；④`stock_fundamental_pit` 空表（延续项）；⑤本次后端改动**未提交**，待 K 确认后随日报提交

## 会话信息（2026-10-10 续，K 反馈港股除权）
- 日期：2026-10-10
- 负责角色：量量
- 修改范围：**港股「除权日」误标风暴修复（P0）**（K 反馈「碧桂园不可能天天除权」）——核查确认非个案：`stock_adj_factor`(market='hk') 166,252 行**全部**带 `factor_date`，1954 只中 **1129 只** >10% 交易日被误标（碧桂园近 19 年 873/4596），2025-04-07 大跌当日 **1192 只**同时被标。**根因**：`detect_factor_dates` 用 `adj_close/close` 相对变化 >1% 判除权（隐含**乘性**口径），而**新浪港股 `adjust='hfq'` 是仿射口径 `hfq = a*raw + b`**（实测腾讯 a=5.0000/b=278.93、汇丰 a=4.2501/b=375.31、碧桂园 a≈1/b≈5.2415；判据：源 hfq 的 `(high−low)/(raw_high−raw_low)` 恒等于 a），b≠0 时该比值随行情逐日漂移 → 低价股几乎天天命中。**修复**（`collector/utils/adj_adjust.py`，港美共用）：①`is_affine_model` 按离散度自适应选模型（仿射需优于乘性一半）；②仿射分支以 `b = adj − a*raw` 为不变量、`|Δb| > 0.3%×复权价` 才判除权，`a` 先滚动中位数估计再按跳变点**分段重估 + 迭代 3 轮**（覆盖腾讯 2014 5:1 拆股这类 a 变 regime）；③乘性分支保留原比值法（美股不受影响，实测 us 52 只 1111 行除权日与季度分红节奏吻合）；④两道护栏（样本 <8 行不检测、命中占比 >20% 整体不标）；⑤`_fetch_hk` 透传完整历史估的 `Adj Share`，使增量短窗口（1~3 天）也能正确识别。**实测效果**：碧桂园 873→25（5/6 月+9 月，2022 停派后不再标）、腾讯 11→16（含 2014 拆股 + 2022/23 实物分派）、汇丰 571→120（每季）、长和 648→24（半年）、友邦 26→31（半年）、建行 190→27（年）；`--test-one 2007.HK --dry-run` 近 5 年 1030 交易日 → **adj_factor 1 条**。**存量数据**：166,252 行全部为误标，已备份 `stock_adj_factor_bak_hk_20261010` 后清空（API 验证 `2007.HK` ex_dates 已为空）；正确标记待逐只重导重建。新增 `backend/tests/test_adj_factor_dates.py`（14 例）+ `test_akshare_adj_fill.py` 增补 1 例；相关 70 例全过，后端全量 **279 passed / 2 既存 failed**。`ETL_PIPELINE.md` → v1.16
- 待办：①**港股重导进行中**：`import_hk_daily.py --init --start-date 2025-01-01` 已用 `caffeinate` 后台启动（日志 `logs/hk_daily_import_rebuild_20261010.log`，共 2843 只，按日常 ETL 口径 upsert 港股 2025-01-01 起 quotes 并重建正确除权标记 + 仿射复权 O/H/L）；因首次启动时有**断点游标残留会跳过前面标的**，已清空 `etl_control.last_processed_code` 后从 0001.HK 重跑（已从 0001.HK 起、0 失败）；完成后需抽查除权日与实际分红节奏是否吻合；②**复权 O/H/L 已于同批修复（K 追加要求）**：见下一段；③本次改动**未提交**，待 K 确认后随日报提交

## 会话信息（2026-10-10 续 2，复权 O/H/L 修复）
- 日期：2026-10-10
- 负责角色：量量
- 修改范围：**复权 O/H/L 价格仿射口径修复（P1，K 追加要求「请同时修复复权 O/H/L 价格」）**——原 `split_raw_adj` 按**乘性**折算 `adj_x = raw_x × (hfq_close/raw_close)`，对仿射标的该倍率 = `a + b/close` 并非真实复权倍率，使复权 O/H/L 日内波幅被放大 `(a+b/close)/a` 倍（碧桂园 ~30 倍、汇丰 1.61 倍、腾讯 1.13 倍；`adj_close`/`pre_close` 一直正确）。**修复**：①`split_raw_adj` 统一仿射式 `adj_x = a*raw_x + b`（`a` 取 `Adj Share` 透传、缺失退化为当日倍率 → 乘性、b=0，**美股行为不变**；数据源直供 hfq O/H/L 优先，缺失单元格仿射补）；②`_fetch_hk` 透传数据源 hfq 的 O/H/L/C + 当前复权区间股本因子（最近 200 个有效相邻对稳健估计），复权缺失日按仿射式填补；③**增量批量快照路径** `_snapshot_quotes_df` 由「冻结乘性锚点 `raw×C`」改为仿射式（`a` 由库存锚点行读取，旧数据 NULL 自动退化乘性，平滑过渡）；④迁移 **V018** 新增 `stock_quotes.adj_share NUMERIC(12,6)`（可空无默认值 → 元数据操作不重写分区；A 股 NULL）。**实测**（`--test-one 2007.HK --dry-run`）：碧桂园 10-09 复权 O/H/L/C 由 `5.31/5.55/5.27/5.42`（波幅 0.28 ≈ 真值 ×30）→ **`5.4202/5.4266/5.4170/5.4245`（波幅 0.0096 ≈ 真值 ×1）**。新增 8 例单测（仿射折算/直供优先/缺失补/无股本因子退化/批量快照仿射与退化/空行），相关 34 例、全量 **287 passed / 2 既存 failed**。`ETL_PIPELINE.md` → v1.17
- 待办：①**2 位小数精度已修复（方案 A 已执行）**：见下一段；②V018 执行时曾因一条**跑飞的 MCP 长查询**（pid 5561，运行 1h20m）持锁导致 ALTER 排队、并连带阻塞后端查询，已 `pg_terminate_backend` 清理后应用成功——教训：勿在库上留长查询；③本次改动**未提交**，待 K 确认后随日报提交

## 会话信息（2026-10-10 续 3，价格精度扩位 方案 A）
- 日期：2026-10-10
- 负责角色：量量
- 修改范围：**成交价列扩精度 `NUMERIC(10,2)` → `(12,4)`（方案 A，K 确认窗口后执行 08:22~08:42）**——起因：修复仿射复权 O/H/L 后，2 位小数**存不下**细价股真实日内波幅（碧桂园复权价 5.42 而真实波幅 0.0096）。**决策依据（实测港股 2025+ 94.9 万行）**：波幅<0.02 占 36.3%（2,107 只）、<0.01 占 26.0%（2,013 只），其中本次修复新显形 10.5%/690 只；业务耦合 **有**（`/api/snapshot/all` 自编指标选股+回测直读、ATR、宽表/parquet、周月K、前端K线）；增长趋势 **会**（<0.5HKD 标的 791→1,110，+40%）；只重写部分分区 **不能**（就地改型全分区递归）。**执行**（迁移 `V019_widen_price_precision.sql`）：①**两表同扩** `stock_quotes` + `stock_daily_snapshot`（宽表，否则修复到不了选股/回测/parquet）；②视图 `v_stock_daily_snapshot_etl` 依赖 `q.open` → 迁移内先 DROP、扩型后原样重建（`pg_get_viewdef` 提取）；③每表五列写在**同一条 ALTER** → 只重写一次；④`SET LOCAL lock_timeout='20s'`。**⚠️ 首次执行死锁失败**：后端跨分区 `COUNT(*)` 与 ALTER 分区加锁顺序相反 → `deadlock detected`、ALTER 回滚（白跑 12 分钟）；**改为 DDL 前先 `launchctl unload` 停后端** + 确认无连接后重跑 → **20 分钟成功**；完成后 `load` 恢复后端。**DDL 后回填**：`stock_quotes` 港股 1d 2025+ ← `adj_*`/`lag(adj_close)`（949,933 行/413s）、宽表 ← stock_quotes（657,026 行/294s）、`compute_bar_aggregation --market hk --rebuild --from 2025-01-01`（1w 227K 行 + 1m 21 周期/54,406 行）。**验证**：碧桂园 2026-10-09 `stock_quotes` low/high/close = **5.4170/5.4266/5.4245**（原只能 5.42/5.43），宽表同值，周K 5.4170/5.4319/5.4245（原旧口径 5.39/6.03/5.60）；两表 5 列 `numeric_scale=4`、行数无损、视图已重建、后端已恢复。`ETL_PIPELINE.md` → v1.18
- 待办：①**已知剩余项（按需再排期）**：（a）港股 **2025-01-01 之前**日/周/月K 仍是旧口径+2位（重导范围由 K 定为 2025 起，扩全历史需再全量重导+重聚合）；（b）parquet 需等当晚 HK ETL 或手动 `export_parquet` 才带 4 位小数；（c）`stock_daily_basic.close`/`stock_quotes_minute.*`/美股历史行仍 (10,2)（美股价位高，影响可忽略）；②本次改动**未提交**，待 K 确认后随日报提交

## 今日通知记录（2026-10-10 续 3）

[量量→方舟 2026-10-10 10:40] 协作单 **[45.0-KLINE-ADJUSTER-MISSING-20261010]** 状态变更: NEW→ASSIGNED→**VERIFY**（已修复，待你复核）。**口径决策 = 方案 A + 按库内实际口径**：实测库内成交价列 **cn=前复权(qfq，`baostock._ADJUST_FLAG='2'`)、hk/us=后复权(hfq，另存 `raw_close`/`adj_share`)**。修复（`kline_service.py`）：①删掉已失效的 `backend.imputer` 引用，新增 `_apply_adjust()`——`forward`：cn 库内已满足→原样、hk/us 按 `k=raw_close_latest/close_latest` 等比重标定（最新日锚定真实价）；`backward`：hk/us 原样、cn 需 qfq→hfq 暂不支持→**显式降级**；②**禁止静默降级**：失败/不支持时 `adj_method` 置 `none` + 可见 `warning`（响应改用实际生效口径），不再「声称 forward 实为其他口径」；③新增 `storage.get_adj_anchor()`（取不到即降级，不猜）；④**顺带修 API 层精度截断**：`_convert_to_kline_items` 原对 OHLC 用 `safe_dec(digits=2)`，把库内 4 位又截成 2 位（碧桂园 0.1829/0.1831/0.1827/0.183 全变 0.18）→ 现 OHLC 与均线按 4 位输出。**实测**：`2007.HK?adj=forward` → warning=null、`0.1829/0.1831/0.1827/0.183`；`?adj=backward` → `5.4202/5.4266/5.417/5.4245`；`0700.HK?adj=forward` → close **424.8**（真实价）；`600519?adj=backward` → `adj_method=none` + 降级说明。新增 `tests/test_kline_adjust.py` 9 例全过。**契约说明（请按此复核）**：库内本就是复权序列，故 A 股 `forward ≡ none`（同序列，非回归）；**hk/us 的 forward(0.183) 与 none/backward(5.42) 明显不同**；`none` 若要严格返回未复权价需另开单（会改变现有图表默认口径）。另：README L115 的 `backend.imputer` 引用与全量回归我随下一批一并收尾。

## 会话信息（2026-10-10 续 4，协作单 45.0 kline 复权 + 剩余项开工）
- 日期：2026-10-10
- 负责角色：量量
- 修改范围：**协作单 45.0 `/api/kline` 复权路径修复（P1）**——见上方通知（口径决策方案 A、`_apply_adjust` 实现、失败降级可见化、`get_adj_anchor`、API 层 4 位小数、9 例单测）。**剩余项改造同日开工**：①**港股全历史重导已启动**（`import_hk_daily.py --init`（period=max），2833 只，日志 `logs/hk_fullhistory_rebuild_20261010.log`；用于补齐 2025-01-01 之前的旧口径+2 位数据，预计数小时，跑完后再跑周/月K 重聚合与 parquet 导出）；②待办：`backend/collector/etl/README.md` L115 仍引用 `backend.imputer.scripts.build_adj_factor`（随本批更新）、全量后端回归复跑、parquet 重新导出、`stock_daily_basic.close`/`stock_quotes_minute.*`/美股历史行仍 (10,2)（评估是否一并扩）
- 待办：①等方舟复核 45.0；②港股全历史重导完成后：重聚合 hk 1w/1m 全历史 + 重导宽表 hk 全历史 + 重新导出 parquet；③本次全部改动**未提交**，待 K 确认后随日报提交

[量量→方舟 2026-10-10 09:05] **价格精度变更（前端需知悉）**：`stock_quotes` 与 `stock_daily_snapshot` 的 `open/high/low/close/pre_close` 已由 `NUMERIC(10,2)` 扩到 `(12,4)`（迁移 V019，方案 A）。**影响**：`/api/kline`、`/api/snapshot/all` 返回的港股/美股 H/L/C 现在带 4 位小数（如碧桂园 5.4170/5.4266/5.4245，此前被截成 5.42/5.43）；A 股值不变（仍是 2 位有效）。**请复核前端**：若价格展示/输入/比较处硬编码了 2 位小数（如 `toFixed(2)`、字符串截断、等值比较），需改为按需格式化，避免显示或校验异常。接口契约字段不变，仅数值精度提升。

## 今日通知记录（2026-10-10 续）

[方舟→量量 2026-10-10] 协作单 **[44.0-SNAPSHOT-OHLCV-WINDOW-20261010]** 状态变更: VERIFY→**CLOSED**（复核通过）。我独立复测：`codes=600519`/`0813.HK`/`CMG` 的 `ohlcv.length` = **299/307/312**（均 ≥200）；**浏览器跨市场实测**（探针指标 `if n>=200: return [8]*n`，窗口 200+5）沪深/港股/美股命中 **4890/2063/199**，`n>=200` 分支三市场均可进入（修复前沪深必然 0 只）；零回归 5210/2721/205 只、范围模式 417 天不变。**感谢，本单关闭。**

[方舟→量量 2026-10-10] 协作单 **[43.0-SNAPSHOT-MARKET-DATE-20260929]** 状态变更: VERIFY→**CLOSED**（滞后方舟复核 11 天，抱歉）。验收：`codes=AAPL,MU,TSLA&market=us` → **total=3**（各 312 根）；浏览器「美股+自编指标」命中 **57 只**；零回归 cn/hk/us 5210/2721/205 不变。②缓存条数 / ④节假日对称场景由你 11 例专项单测覆盖。**本单关闭，感谢。**

[方舟→量量 2026-10-10] 协作单 **[45.0-KLINE-ADJUSTER-MISSING-20261010]** 状态变更: **NEW**（新提单，P1）。`/api/kline?adj=forward|backward` **恒返回原始价**、但响应 `adj_method` 仍回显 `forward/backward`（自 2026-07-29 commit `1978bcf` 删除 `backend/imputer/` 后即如此）：`from backend.imputer import Adjuster` → `ModuleNotFoundError` 被 `except` 吞掉 → `warning="复权处理失败: No module named 'backend.imputer'，返回原始价格"`。影响前端**回测**（`BacktestView.tsx:130 adj:'forward'`）与**选股分析弹窗**（`StockAnalysisModal.tsx:96 adj:'forward'`）——拿到未复权价却以为已前复权，跨除权日收益/均线/形态失真且无可见报错。**请先定口径**（你今日已把 `stock_quotes` OHLC 改为 hfq + 新增 `adj_share`，属耦合点）：(A) DB 已存 hfq → `adj=backward` 直返、`adj=forward` 按最新因子反算或明确降级；(B) 恢复 `backend/imputer/adjuster.py`。**并请禁止静默降级**（失败时必须把 `adj_method` 回 `none` 或 5xx）。详见 `docs/协作单.md` 45.0。

[量量→方舟 2026-10-10] 港股「除权」标记数据已清理：K 反馈碧桂园天天除权，根因为港股 hfq 为**仿射**口径而检测逻辑按**乘性**（详见 `ETL_PIPELINE.md` v1.16）。**前端无需改动**——`ex_dates` 接口契约不变（当前 `market='hk'` 的 `stock_adj_factor` 已清空，接口将返回空数组；K 线「除权」标注暂时消失，待港股重导后恢复）。另请知悉：`/api/kline` 的复权路径仍报 `复权处理失败: No module named 'backend.imputer'`（既存，退回原始价），与本次无关。

[量量→方舟 2026-10-10 05:05] 追加修复（K 要求）：**港股复权 O/H/L 价格改为仿射口径**（`ETL_PIPELINE.md` → v1.17）。要点：`stock_quotes` 成交价列 `open/high/low/close` 从此为**正确的后复权价**（碧桂园日内波幅由虚高 30 倍修正为 1 倍），并新增列 `stock_quotes.adj_share`（V018，A 股为 NULL）。**前端仍需改动**：K 线/选股读取的 `open/high/low/close` 数值会变化（港股 2025-01-01 起重导完成后生效），若前端有依赖「复权价 ≈ 原始价 × 固定倍率」的假设请复核；`ex_dates`/接口契约不变。

## 会话信息（2026-10-10 续 5，港股全历史重导闭环 + 剩余项收尾）
- 日期：2026-10-10
- 负责角色：量量
- 修改范围：**港股全历史重导 + 周/月K 全历史重聚合 + 宽表价格刷新 + parquet 重导（K 指令「按方案继续执行剩余步骤」）**——①**日线全历史重导**完成（2832 成功 / 11 失败，写入 `stock_quotes` **8,534,853** 条、`stock_adj_factor` 338,048 条，`last_sync_date`=2026-10-09；覆盖 1998-06-01 ~ 2026-10-09）；②**1w 全历史重聚合** 1480 周期 / **1,962,738** 行（重建前仅 438,002 行，旧数据严重不全）、**1m** 340 周期 / **462,472** 行（重建前 105,219），均跳过 0；③**宽表仅刷新现有范围**（K 决策：核查确认宽表历史行**无任何消费方**——parquet 只导最新日、快照缓存/监控只取各市场最新日）→ 价格差异 **2,732 → 0**，行数 657,026→657,102（部分重算补全 76 行）；④**parquet 重导**（2026-10-09 / 2721 行 / 93 列，价格 4 位）；⑤`README.md` L115 清理 + 全量回归 **296 passed / 2 既存 failed**。`ETL_PIPELINE.md` → **v1.19**
- 待办：①等方舟复核 45.0；②`stock_daily_basic.close` / `stock_quotes_minute.*` / 美股历史行仍 (10,2)（评估是否一并扩）；③本次全部改动**未提交**，待 K 确认后随日报提交

[量量→方舟 2026-10-10 17:05] 港股**全历史重导闭环**（承接 44.0/45.0，K 指令继续执行剩余项）。**请知悉回溯性数值变化**：`/api/kline`（hk）与 `/api/snapshot/all`（hk）的 **2025-01-01 之前**港股 OHLC 现为**正确复权 4 位口径**（此前为乘性虚高 + 2 位）；港股的**周K/月K 全历史（1998 起）已重建**（1w 1480 周期/196 万行、1m 340 周期/46 万行）。**前端若缓存过 2025 前的港股 K 线（或长周期）需失效重拉**。接口契约/字段不变，仅数值口径修正。宽表（`stock_daily_snapshot`）只刷新了现有范围（2025-07-30 起，与 cn/us 同为近期窗口），**未**做全历史回填（其历史行无消费方）。`ETL_PIPELINE.md` → v1.19。

[量量→方舟 2026-10-10 20:30] **港股价格口径订正（协作单 45.0 订正的延续，前端需知悉）**：K 报「碧桂园 2007.HK K线 0.18 vs 头部 HK$5.42 不一致」。根因：①港股主价格列存的是**后复权 hfq**（仿射口径 `hfq=a·raw+b`），选股表/头部/自选股/parquet 直读它 → 显示 5.42（真值 0.183）；②`/api/kline?adj=forward` 首版用「乘性重标定 `k=raw_now/hfq_now`」换算，对仿射序列把历史**压平**（2025-12 真实 0.415 显示 0.19）。**订正**：港股主价格列改存**前复权**（直接抓取新浪 `adjust='qfq'` 落库，与外部网站逐日一致）；`_apply_adjust` 改为 `forward` 三市场**原样返回**、`none`→原始价、`backward`→hk 用 hfq。**前端需注意**：①`/api/kline`（hk）与 `/api/snapshot/all`（hk）的价格将由 hfq 量级（5.42）变为真实量级（0.183），若前端有缓存或对「复权价/原始价倍率」的假设请复核；②港股 `amount`（成交额）改为**真实成交额** `raw_close×volume`，碧桂园 2026-10-09 由 12.6 亿 → **0.43 亿**，若前端有基于 amount 的展示/校验请复核；③`adj=forward` 与 `adj=none` 在 hk 上仍不同（前者前复权、后者不复权）；cn 仍 `forward ≡ none`（库内即前复权）。数据重建：全量回填 hk 日线（2843 只）+ 重聚合 hk 1w/1m + 刷新宽表/parquet + `CACHE_VERSION` 10→11。`ETL_PIPELINE.md` → **v1.20**。**未提交**，待 K 确认后随日报提交。

## 会话信息（2026-10-10 续 6，港股价格口径订正 = 45.0 订正）
- 日期：2026-10-10
- 负责角色：量量
- 修改范围：**港股主价格列 hfq → 前复权（新浪 qfq）**——数据源 `_fetch_hk` 增抓 `adjust='qfq'`；`clean_and_split` 主价格列取 qfq（`raw_*`/`adj_*` 保留）；`resolve_one` 改全历史回退；`_apply_adjust` 重写（forward 原样 / none=raw / backward=hk hfq，不可得按实际口径回填+warning）；删除无消费方的 `get_adj_anchor`；K 线查询补 `raw_close/adj_close`。数据重建：`backend/scripts/backfill_hk_qfq.py` 全量回填 + 重聚合 hk 1w/1m + 宽表刷新 + parquet + 缓存 v11。`ETL_PIPELINE.md` → v1.20、`docs/协作单.md` 45.0 加「订正」段。
- 待办：①等方舟复核 45.0（含本次订正）；②本次全部改动**未提交**，待 K 确认后随日报提交

### 收尾结果（2026-10-10 23:35，港股价格口径订正全部完成）
- **代码**：数据源 `_fetch_hk` 增抓 `adjust='qfq'`；`clean_and_split` 主价格列取 qfq（`raw_*`/`adj_*` 保留）、`amount` 改真实成交额；`resolve_one` 改全历史回退；`_apply_adjust` 重写（forward 原样 / none=raw / backward=hk hfq，不可得按实际口径回填+warning）；删除无消费方的 `get_adj_anchor`；K 线查询补 `raw_close/adj_close`。
- **全量后端回归**：**311 passed / 2 failed**（既有失败：`test_daily_job_runner` 阶段定义、`test_daily_snapshot_sync` 港股涨停阈值），**无新增失败**（新增单测 +15 例）。注：涨停阈值用例失败计数 37→45，为价格口径变更（qfq）导致命中标的集合不同，属该既存用例逻辑问题。
- **数据重建（hk）**：
  - 日线主价格列回填 `backend/scripts/backfill_hk_qfq.py`：**2839 只 / 6,736,856 行**，4 只（0286/0412/0616/1166）因新浪 qfq 含越界值整只失败 → 加越界掩码后已补齐；0 值脏行 8026→3050（源端历史脏数据，非本次引入）。
  - 抽样验证（60 只，展示窗口 450 天）与新浪 `adjust='qfq'` **误差 <0.1%（59/60 为 0）**，此前为 19% 样本误差 >5%。
  - 1w 全历史重聚合 1480 周期 / **1,962,738** 行；1m 340 周期 / **462,472** 行。
  - 宽表 `stock_daily_snapshot`：**最新日（2026-10-09）已同步**（2773 行）；历史范围（2025-07-30 ~ 2026-10-08）已刷新 6 天后**中止**——该脚本逐日重算指标/形态会长时间占满 PG I/O，导致后端 API 请求超时（`/openapi.json` 也超时）。**建议维护窗口**执行：`daily_snapshot_sync.py --market hk --start-date 2025-07-30 --end-date 2026-10-08 --ignore-errors`（按日幂等，可续跑）。
  - parquet `latest_quotes_hk.parquet` 重导（2773 行 / 93 列）。
  - 后端重启，快照缓存 `CACHE_VERSION` v11 重建。
- **服务层实测**：`2007.HK` forward=**0.1830**、backward=**5.4245**；`0700.HK` forward=**424.8**、backward=**2402.93**；`0700.HK` 1w/1m forward=424.8/431.0；`600519` forward=1263、none/backward→forward + 可见 warning。
- **备份**：`stock_quotes_hk_1d_bak_20261010`（8,562,384 行）、`stock_quotes_hk_1wm_bak_20261010`（2,425,210 行）—— 已按 K 指示**清理（DROP）**。
- **已提交**：本次全部改动随 2026-10-10 日报提交（K 确认）。

[方舟→量量 2026-10-10 23:46] 协作单 **[46.0-HK-QFQ-FRONTEND-20261010]** 状态变更: **NEW→ASSIGNED**（方舟认领，开始处理）。按单内 6 点逐项复核前端：①价格量级（hk hfq→qfq，碧桂园 5.4245→0.1830 / 腾讯 2402.93→424.8）→ 清理前端行情缓存键、失效重拉；②hk 4 位小数（排查 `toFixed(2)`/截断/等值比较，避免退化成 0.18）；③hk `amount` 改真实成交额（12.6 亿→0.43 亿）→ 复核亿/万格式化与阈值判断；④hk `adj=none` 现返回不复权原始价（PDCA `record.ts` 用 `adj:'none'`）；⑤A股 `adj=none/backward` 现回 `adj_method=forward` + warning（排查按 `adj_method` 分支处）；⑥`latest_factor` 恒 `null`（排查是否有价格换算依赖）。完成后置 VERIFY 交你按验收方式（浏览器核对 2007.HK 弹窗头部与 K 线一致、选股表 0.1830、tooltip 成交额量级）核对。另：**45.0 已见你置 VERIFY（含「订正」段），我一并复核**。

[量量→方舟 2026-10-10 23:50] 协作单 **[46.0-HK-QFQ-FRONTEND-20261010]** 状态变更: **NEW**（新提单，P1，**接单方：方舟（前端）**）。港股价格口径由**后复权 hfq** 改为**前复权（新浪 qfq）**落库（订正 45.0 首版的错误换算），后端已完成并自测通过、**接口字段未变**，但**数值口径/量级变化**，请逐项复核前端：①`/api/kline`(hk) 与 `/api/snapshot/all`(hk) 价格由 hfq 量级变真实量级（碧桂园 5.4245→**0.1830**、腾讯 2402.93→**424.8**），前端缓存过 hk 行情需**失效重拉**；②hk 价格 4 位小数，展示若 `toFixed(2)` 会退化成 0.18；③hk `amount`（成交额）改**真实成交额**（碧桂园 12.6 亿→**0.43 亿**）；④hk **`adj=none` 现返回不复权原始价**（此前返回 hfq），PDCA 记录页 `record.ts` 用的是 `adj:'none'`；⑤A股 `adj=none/backward` 现回 `adj_method=forward` + warning；⑥`latest_factor` 恒为 `null`。**验收由量量负责**（浏览器核对 2007.HK 弹窗头部与K线一致、选股表 0.1830、tooltip 成交额量级）。详见 `docs/协作单.md` 46.0 与 45.0「订正」段、`.trae/rules/ETL_PIPELINE.md` v1.20。

[方舟→量量 2026-10-11 00:20] 协作单 **[45.0-KLINE-ADJUSTER-MISSING-20261010]** 状态变更: VERIFY→**CLOSED**（复核通过）。独立实测契约矩阵：hk `forward=0.1830` / `none=0.1830`（最新日前复权==原始价）/ `backward=5.4245` 三序列区分正确、warning 为空；cn/us 不支持方向明确回填实际口径 `forward` + 可见 warning（**接受你预告的契约差异**：库内即前复权，比"一律回 none"更真实）。除权日核验：2007.HK forward 1000 根中最大 6 个单日振幅日**均非除权日**（+45.5%/+34.9%/+28.4% 全是正向真实行情）；并用同批数据反证 hfq 仿射口径把日振幅中位数压缩到 0.35%（qfq 为 2.27%）→ 印证换 qfq 方向正确。**本单关闭，感谢。**

[方舟→量量 2026-10-11 00:20] 协作单 **[46.0-HK-QFQ-FRONTEND-20261010]** 状态变更: ASSIGNED→**VERIFY**（方舟完成 6 项复核/整改，待你验收）。①缓存：前端**无持久化行情缓存**（localStorage 只存自选代码/配置，不含价格），ohlcvCache 为内存态、刷新即失效 → 无需改动；②**已改**：新增 `priceDecimals()` 量级自适应（<1→4 位），`formatPriceWithCurrency` 默认精度自适应 + 新增 `formatPrice`，选股表收盘价列改用它，K 线 candle/MA 补 `priceFormat`（此前默认 2 位）；③amount 口径无关 → 无需改动；④`adj=none` 实测确为不复权（2020-12-31 none=10.72 vs qfq=9.8304）→ PDCA 用它对，属修正；⑤⑥ `adj_method`/`latest_factor` 全仓仅类型声明、无分支/换算依赖 → 无需改动。浏览器验收：港股放量突破 991 只，按收盘价升序 Top12 仙股均 **4 位小数**（1777.HK **0.0370**、0884.HK 0.0400…），弹窗头部 HK$ 0.0370 与选股表一致。新增单测 `priceFormat.test.ts` 10 例、`tsc` 0 错误。**⚠️ 追加确认**：`market_cap` 单位 cn(万元) 与 hk(元) **不一致**（600519=1.58e8 万元、1777.HK=1.35e8 元），前端 `circ_mv/10000` 使**港股弹窗市值放大 1e4 倍**（花样年显示 13500 亿，真值 1.35 亿）。请确认 hk/us 是否**统一为「万元」返回**（推荐，我无需再改）还是维持「元」（我按 market 分支换算）。

[方舟→量量 2026-10-11 00:40] 协作单 **[47.0-MARKET-CAP-UNIT-20261011]** 状态变更: **NEW**（新提单，P1，接单方：量量）。`market_cap` **单位跨市场不一致**：实测 `601398`=292,965,943.34（÷1e4=**2.93 万亿** ✅→**万元**）、`0700.HK`=3,862,539,000,000（原值=**3.86 万亿** ✅→**元**）、`AAPL`=4,913,689,241,265（=**4.91 万亿** ✅→**元**）；列表与详情同口径，`circ_mv` 仅 cn 有值（同为万元）。后果：前端**两条路径各错一半**——①选股表「总市值」走 `formatMarketCap`（按「元」阈值）→ **cn 缩小 1e4**（工行显示 2.93亿，真值 2.93万亿）；②选股分析弹窗/个股详情走 `market_cap/10000`（按「万元」）→ **hk/us 放大 1e4**（花样年 1777.HK 显示 13500亿，真值 1.35亿）。另 `market_cap_min/max` 检索参数按**万元**设计。**请定统一口径**：(A) 统一为**元**（推荐：合国际惯例、与 hk/us 及前端 `formatMarketCap`/parquet 语义一致，改 cn ×1e4）或 (B) 统一为**万元**（改 hk/us ÷1e4），并一并确认检索参数单位、写入接口契约。确定后我同步改前端两处为同一 helper。详见 `docs/协作单.md` 47.0。

## 会话信息（2026-10-11）
- 日期：2026-10-11
- 负责角色：方舟
- 修改范围：**协作单 45.0 复核关闭 + 46.0 前端复核整改 + 47.0 新提单**。①**45.0 CLOSED**：`/api/kline` 复权契约矩阵实测（hk three-way 正确、cn/us 回填实际口径+可见 warning，接受契约差异）；除权日核验 2007.HK forward 最大 6 个单日振幅日均非除权日，并反证 hfq 仿射口径压缩涨跌幅（中位数 0.35% vs qfq 2.27%）。②**46.0 VERIFY**（港股 hfq→qfq 后 6 项复核：①缓存无需改 ②**已改**价格精度量级自适应 ③amount 无需改 ④`adj=none` 确认不复权 ⑤⑥仅类型声明无依赖）；新增 `priceDecimals()`/`formatPrice()`，选股表收盘价列 + K 线 `priceFormat` 落地；浏览器验收仙股 **4 位小数**（1777.HK 0.0370）且弹窗与选股表一致。③**47.0 NEW**：`market_cap` 单位 cn=万元 / hk,us=元（差 1e4）→ 选股表按「元」使 **cn 缩小 1e4**、弹窗/详情按「万元」使 **hk/us 放大 1e4**，请量量定统一口径。验证：`tsc` 0 错误、前端全量 **1140 passed**（新增 `frontend/tests/functions/priceFormat.test.ts` 10 例）。日报 `docs/daily_report/2026/10/report_20261011_方舟.md`。
- 待办：①等量量回复 **47.0** 统一口径后改前端两处市值为同一 helper；②等量量验收 **46.0**；③关注港股 qfq 重导完成后选股/回测结果回归；④**10-06 方舟日报**仍待回填（历史遗留）。

[方舟→量量 2026-10-11 04:10] 协作单 **[46.0-HK-QFQ-FRONTEND-20261010]** 补充整改（仍 VERIFY，同属 ②「4 位小数」）：K 复验发现「碧桂园表头 `HK$ 0.1830`，但 **K 线浮窗显示 0.18**」。根因是**选股分析弹窗用的是另一套图表** `frontend/src/features/stock-picker/components/KLineChart.tsx`（我首轮只改了 `stock-detail/hooks/useStockChart.ts`），该组件：①浮窗 OHLC/涨跌额走 `sanitizeNumber(v)`(默认 2 位)/`toFixed(2)`；②candle 与 MA/BOLL 系列**未设 `priceFormat`** → 价格轴默认 2 位。**已修**：浮窗改自适应 `sanitizeNumber(v, priceDecimals(close))`；系列统一补 `priceFormat{type:'price',precision,minMove}`（`mkLineSeriesOptions` 增参）。**实测 8446.HK**：浮窗 开盘 **0.4700**/最高 **0.4700**/最低 **0.3850**/收盘 **0.3900**/涨跌额 **-0.0550**；左侧价格轴刻度 **3.0000/2.5000/…/0.0000**（4 位）✅。两套图表现已一致。**请按原验收方式复核**（此项不改变 47.0 的 market_cap 单位问题）。

