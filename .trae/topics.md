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
