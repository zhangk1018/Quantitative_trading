# 跨会话提醒

## 会话信息
- 日期：2026-09-16
- 负责角色：方舟
- 修改范围：① 回测分析股票名称反查优化——`BacktestConfigPanel`/`tradeExport` 的 `watchlistNames` 按市场（cn/hk/us）分桶并行请求，解决跨市场名称查不到；下拉/整组回测不再用 `|| code` 冒充名称（改 `?? ''`）；② 导入/导出升级——买/卖策略导出改为「选择 Modal + Checkbox 列表」（`ImportExportButtons` + 新增 `SellImportExportButtons`/`SellStrategyModal`），存储层 `exportCustomIndicators`/`exportCustomSellStrategies` 加 ids 过滤；③ **Safari 股票名称显示异常已定位为非代码问题**——后端 34 只 code 实测全返回中文名、前端逻辑/vite 源码正确，是 Safari 对 vite dev server 的 JS 强缓存，无痕窗口+清理网站数据后正常，未改代码
- 待办：跟进控制台 IndexedDB `backtestStorage` object store 未初始化告警；财务指标库 `stock_fundamental_pit` 为空表（净利润/营收/ROE 无数据），如需展示需接入财务数据采集

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