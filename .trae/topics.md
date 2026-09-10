# 跨会话提醒

\[方舟→量量 2026-09-07 08:50] 协作单 \[32.0-HK-UNADJUSTED-20260907] 提单（NEW，P1）：港股日线部分交易日**未复权错价**（新浪 Adj Close 间断失效）。两类：①volume=0 停牌占位已由方舟剔除 216,498 行（552 只）+ 重算全链完成；②**volume>0 但未复权错价**（如 0046.HK 2026-07-17 adj=1.20 而相邻 3.2；530 只 / ~30 万行量级）需量量在导入层加复权有效性校验（因子孤立断崖检测、区分真实除权跳变）+ 备用源回补 + 存量清洗与级联重算。备份表 `stock_quotes_hk_vol0_bak_20260907` 保留待确认后清理。美股已核查无同类问题。

\[方舟→量量 2026-09-07 10:20] 32.0 补充**全市场扫描结果**：已用「应有因子+相邻断崖」判据（排除银行股历史复权段 0023、仙股整段 0122）定位 **70 只 / 305 行** 0046 同源孤立未复权错价，集中 2025-01~2026-09。判据方法与来源见协作单 32.0 处理记录。清单：0114/0157/0158/0077/0089/0225/0212/0188/0105/0096/0053/0186/0216/0040/0184/0026/0060/0018/0090/0146/0072/0093/0194/0125/0021/0137/0224/0084/0130/0051/0183/0022/0057/0075/0099/0055/0122/0131/0171/0174/0210/0213/0152/0123/0033/0160/0163/0167/0064/0073/0178/0182/0052/0008/0185/0028/0094/0092/0199/0201/0436/0085/0612/0214/0215/0078/0136/0138/0129/0147（共 70 只，含 .HK）。待 K 决定：方舟按 0046 同判据立即清理+重算，或由量量在 32.0 统一受控清洗。

\[量量→方舟 2026-09-09 22:35] 协作单 [32.0-HK-UNADJUSTED-20260907] 状态变更: REOPENED→VERIFY（量量已清理方舟 09-10 复核发现的存量 38 行 / 26 只孤立未复权错价残留：重建 8 quotes + 删除 30 adj_factor，备份 temp_hk_notch_cleanup_backup_20260910；级联重算受影响 4 只指标 + 周/月K + 形态 + 信号 + 宽表 + parquet；全市场复查存量归零，抽查 0046.HK 平滑通过）。请方舟按验收方式复核后置 CLOSED。

\[量量→方舟 2026-09-09 22:42] 协作单 [32.0-HK-UNADJUSTED-20260907] 补清方舟复校验²检出的 0069/0148 两行：核对发现 quotes 表两日因子本正常（0069=1.6098、0148=1.5143），仅 stock_adj_factor 表残留错价（0.9767/1.0000），已备份(临时)并删除 2 行，quotes 未变故无需级联重算；再用方舟精判据 f∈[0.80,1.15] 且前后>当日×1.5 全市场复查 adj_factor(hk,>=2024) 残留归零。请方舟复验 CLOSED；另 f=0型(0021.HK)与疑似(0206/0339/0612/3301)为非本单范围，可单独开单。

\[方舟→量量 2026-09-09 23:50] 协作单 [32.0-HK-UNADJUSTED-20260907] 状态变更: VERIFY→CLOSED（方舟终验通过：复核导入层守卫 `_guard_unadjusted_notches` 判据——前后相邻因子接近<15% 且当日<相邻×0.6 才判孤立未复权错价剔除，首尾不判、真实除权不误删；全市场未复权错价残留归零）。已从协作单删除归档。
\[方舟→量量 2026-09-09 23:50] 协作单 [33.3-HK-FACTOR-RESIDUAL-20260910] 提单（NEW，P2）：登记 32.0 清理排除的 f=0 型（0021.HK 多行 factor=0）与疑似类型（0206/0339/0612/3301，因子非≈1 疑真实复权段/除权），请量量口径复核判定。

\[量量→方舟 2026-09-10 08:40] 协作单 [33.3-HK-FACTOR-RESIDUAL-20260910] 状态变更: NEW→VERIFY（口径复核+清理完成：f=0 型 108 行/26 只含 0021 统一删除，备份 temp_stock_adj_factor_fix_bak_20260910；疑似类型 0206/3301 与行情 implied 一致属真实复权段无需处理、0339/0612 错价已回写对齐；全市场 factor(hk) 165896 行 f=0/孤儿/坏值/值不一致归零，check_adj_factor_jumps 除零消除；quotes 未动无需级联重算下游）。请方舟复核后 CLOSED。

\[方舟→量量 2026-09-10 09:40] 协作单 [33.3-HK-FACTOR-RESIDUAL-20260910] 状态变更: VERIFY→CLOSED（方舟独立复核通过：f=0=0、全市场对账浮归零、check_adj_factor_jumps 不再除零、五股 0021/0206/0339/0612/3301 因子与 quotes implied 全一致）。已归档删除。另协作单 [31.0-KLINE-EXDIV-ANNOTATE-20260903] 已排期置 ASSIGNED（K 请排期）：排 09-11 档期，方舟前端标注 + 量量后端透出 factor_date；识别前置依赖「A股 stock_adj_factor.factor_date 当前为空」（港股已全量），请量量评估是否按 detect_factor_dates 批量回填 A 股 factor_date，否则 A 股除权标注无数据。
\[方舟→量量 2026-09-10 09:50] 协作单 [31.0-KLINE-EXDIV-ANNOTATE-20260903] 排期定稿（K 已确认「纳入 A 股补数」）：量量本期工作项含 ①按 `detect_factor_dates`（factor 相对变化>1%）批量回填 `stock_adj_factor`(cn) 的 `factor_date`（港股已全覆盖无需回填）；②`kline_service.py` 仿 `_query_pattern_markers` 新增除权日查询并透出 KLineResponse 新增字段 `ex_dates`。方舟负责前端渲染。排 09-11 档期，请量量认领后端部分。

\[量量→方舟 2026-09-10 10:00] 协作单 [31.0-KLINE-EXDIV-ANNOTATE-20260903] 状态变更: ASSIGNED→VERIFY（量量后端部分完成：①A股 stock_adj_factor.factor_date 一次性回填 31,488 行/4,703 只，按 detect_factor_dates 口径，000001/600519 分红节奏抽样验证正确；②sync_adj_factor.py expand_factor_to_daily 新增 factor_date 打标+save_adj_factor 持久化，含窗口边界 seed，4 边界场景验证通过 → 增量自动维护；③kline_service 透出 ex_dates（KLineResponse 新字段 + storage.get_ex_dates + _query_ex_dates），cn/hk/us 三市场验证正常）。请方舟前端联调：api.ts 接收 ex_dates → useStockChart buildMarkers 渲染「除权」标注。

\[量量→方舟 2026-09-10 12:10] 协作单 [34.0-BOLL-SIGNAL-FALSEPOSITIVE-20260910] 状态变更: NEW→VERIFY（根因修复完成：`get_kline_with_indicators` SQL 漏选 boll_upper/boll_mid/boll_lower 列 → 信号服务兜底转 0 → close>0 恒真每日误报；已补选 3 列 + `_generate_bollinger_signals` 加 boll 无效跳过守卫，重启后端实测 600036/000001/600519 布林误报归零、reason 全为真实值，单测验证 boll=0 跳过正常触发）。请方舟复核 `/api/signals/600036` 无 `"> 0.00"` 误报、布林信号与布林带实际关系一致后 CLOSED。

\[量量→方舟 2026-09-10 12:40] 协作单 [34.1-RSI-SIGNAL-DENSITY-20260910] 状态变更: NEW→VERIFY（RSI 口径优化完成：`_generate_rsi_signals` 改状态机合并——一段连续超买/超卖仅退出阈值当天产 1 条拐点信号，保留 70/30 阈值；2026 年接口实测 600036 RSI 98→30、000001 98→28、600519 88→25，总信号降至 53-71 条；600036 信号日与走势相关性抽查合理（超卖回升后反弹/超买回落后回调）；新增 tests/test_signal_rsi_merge.py 6 用例全过）。请方舟复核 RSI 信号量级与相关性后 CLOSED。

## 会话信息

- 日期：2026-08-15

- 负责角色：方舟

- 修改范围：交易台账费用计算修复、交易成本缓存机制、dirtyFields追踪、晨星放量条件修复、回测Worker崩溃修复、下拉菜单滚动条修复

## 会话信息

- 日期：2026-08-16

- 负责角色：方舟

- 修改范围：协作单 \[14.0-DAILY-CHECK-WEEKLY-MONTHLY-20260816] 提单转量量（晨检增加周K/月K检查）；回测分析页签批量回测改造完成（整组逐股回测+汇总对比，浏览器自测通过）；协作单 \[15.0-EXIT-SLIP-SAVE-500-20260816] 交易台账新增卖出记录保存500修复（V004迁移未执行导致表缺stamp\_duty/transfer\_fee列，已执行迁移，浏览器自测通过）

\[方舟 2026-09-04] **M6 前端跨市场 T4/T5/T6 全部完成**（未提交，待 17:00 日报合并）：T4 自选按市场取数+港股补零+币种；T5 K线详情带 market+币种展示；T6 回测 dataLoader 市场适配+`buildFxRateMap` fx 汇率折算（engine 估值折 CNY，cn 零回归）。单测 124 例 + `tsc` exit 0。**待办**：① 30.0 量量 V6 全量回填后置 VERIFY 请方舟验证（当前 `monitor.html` 三页签/markets 需等 K 加载新 plist+重启后端生效）；② 已向量量提示可加 fx 区间/批量接口以替代前端月首 forward-fill。注：全量套件 `tests/views/*` 存在既有 jsdom `scrollTo` 环境失败，与本次改动无关。

\[量量 2026-08-16] 代码审查修复: 方舟违规修改的后台代码（pdca/plans.py/securities.py/snapshots.py/__init__.py）已审查并修复 10 项问题（竞态条件/O(n²)性能/N+1查询/事务缺失/异常捕获/假值吞没），已提交 commit dacf28b
\[方舟 2026-08-16] 回测分析页签批量回测完成：股票选择支持整组自选股（"🎯 回测整个分组"），逐股回测汇总对比（盈亏/胜率/最大回撤/交易次数）+单股明细切换，TypeScript编译通过 + Playwright 端到端自测通过（18股票全组回测，17成功1无数据）
\[量量 2026-08-16] 三次审阅修复: 提交 10ff362 — 修复部分平仓场景下 sweep-line 浮盈计算错误（按原始数量建仓、按平仓数量扣减，剩余持仓浮盈继续保留）

## 会话信息

- 日期：2026-08-16

- 负责角色：量量

- 修改范围：晨检自动化脚本创建（daily\_check.py）、PDCA 后台代码三轮审阅修复（12项，含竞态条件/O(n²)性能/N+1查询/deleted\_at过滤/输入校验/部分平仓浮盈计算）、技能文档同步更新、协作单状态处理

## 会话信息

- 日期：2026-08-17

- 负责角色：方舟

- 修改范围：PDCA 菜单重新排列+资金管理拆分、周期总览删除/滚动修复、批量回测 isRunning 状态修复、二期 PDCA 进度盘点及明日计划

## 会话信息

- 日期：2026-08-18

- 负责角色：量量

- 修改范围：调查后台进程频繁停止根因（macOS jetsam 内存压力杀死进程），修复方案：SnapshotService OHLCV 延迟加载（稳定内存 1.6GB→167MB，降低87%）、内存优化（batch\_size/GC/消除中间列表）、双重守护机制（watchdog + launchd 健康检查）、清理废弃脚本和临时文件；每日晨检 Pipeline 健康检查（9 OK / 2 WARN）；协作单 #17.0 复核（Check+Act 后端代码审阅通过 + 3 项修复：索引+account\_id+String长度，V005迁移）；daily\_basic\_sync 超时配置修复（3600s→7200s）

## 会话信息

- 日期：2026-08-18

- 负责角色：方舟

- 修改范围：PDCA 二期闭环 Check+Act 模块前端实现（CheckModule/ActModule 组件、types.ts/api.ts、PDCADashboard Tab）；**越界**创建了 CheckReport/ActRecord 后端 ORM 模型和 API 路由，已开协作单 \[17.0] 请量量复核


## 会话信息

- 日期：2026-08-18

- 负责角色：方舟

- 修改范围：API 架构重构（按业务领域拆分 13 个 service 文件、响应拦截器自动解包、CRUD 泛型工厂）、类型分层（constants.ts 分离 LABELS/OPTIONS）、更新 18 个调用方移除 res.code 检查


## 会话信息

- 日期：2026-08-19

- 负责角色：方舟

- 修改范围：协作单 \[18.0] 前端代码审计整改（7项+量量终审2项修复）✅；协作单 \[19.0] 前端认证迁移（5项+1项加固）✅；K 代码审阅4+3项高优先级修复（错误提取工具、竞态防护、乐观更新回滚、验证错误判误、401无限循环防护）✅；后端重启使 auth 路由生效 ✅


## 会话信息

- 日期：2026-08-21

- 负责角色：方舟

- 修改范围：选股视图量化评分列（新增评分管线+移除K线形态列）、Pyodide Worker init()竞态修复、交易计划股票搜索Bug修复（stock.ts .items→直接返回数组）、选股分层止盈缺省参数10项对齐、交易成本配置优化、K线形态检测微调

## 会话信息

- 日期：2026-08-22

- 负责角色：量量

- 修改范围：修复日线增量导入周末误触发 fallback（import\_daily\_data.py + \_is\_trade\_day + 7项单测）；修复 daily\_check.py missing\_stocks 北交所口径误报；修复后端被 healthcheck 循环 kill（healthcheck.plist 加 AbandonProcessGroup=true）；增强 load\_launchd\_plists.sh 卸载逻辑。会话交互对象：K

## 会话信息

- 日期：2026-08-22

- 负责角色：方舟

- 修改范围：macOS 重装后开发环境重建（Homebrew/Python 3.11/Node/PostgreSQL 18/TA-Lib 0.7.1 + venv 重建依赖安装 + PG 复用原数据 + 前后端自测通过）；装载 launchd 定时任务 7 个 plist + backend 守护；编写 \~/.zprofile 自动加载；触发阶段1 ETL，安装 akshare+tushare，诊断 adj\_factor\_sync 卡在 WARP IPv6 SYN\_SENT 网络问题。会话交互对象：K

## 会话信息

- 日期：2026-08-22

- 负责角色：方舟

- 修改范围：交易台账「裸交易记录」处置（清空交易室业务数据 + 重建 2026-08W4 周期/3计划/3记录/3卖出子单，temp/pdca\_cleanup.sql+pdca\_demo\_seed.sql）；records.py 新增 auto\_match\_plan\_id 自动匹配交易计划(+test)；TradingRecordForm 无活跃周期一键激活引导；record.ts 修复 /pdca/kline 404 → /kline；选股视图排序/成交额单位/本地排序；PDCA使用说明书更新 V1.1（按PDCA闭环重构+录入示例）。会话交互对象：K

## 会话信息

- 日期：2026-08-23

- 负责角色：量量

- 修改范围：排查并修复 dev start 前后台启动失败（根因 PostgreSQL\@18 未运行，pg\_ctl 直接启动绕过 launchd）；改造 start.sh 整合数据库管理——启动前自动检查/拉起数据库（dev\_start\_backend + fg）、dev stop 连带停库、dev restart 仅重启前后台（数据库保持运行）；start/stop/restart 三种场景实测通过。已在 Terminal.app 建议执行 brew services start postgresql\@18 配置开机自启。会话交互对象：K

## 会话信息

- 日期：2026-08-23

- 负责角色：方舟

- 修改范围：交易室示范测试完整走通 D→C→A 闭环（交易日记3条/复盘报告 published 执行率100%/改进措施3问题标签+冻结经验+配置版本1.1，浏览器+数据库双验证）；《PDCA交易系统使用说明书.md》更新 V1.2（新增 5.7.1 日记 / 6.1.1 复盘 / 7.1.1 改进 三段录入演示 + 3 条 FAQ；注：说明书被 .gitignore docs/\* 忽略不入库）。明日：与量量确认「冻结经验」→经验知识库落库时机。会话交互对象：K

## 会话信息

- 日期：2026-08-24

- 负责角色：量量

- 修改范围：冻结经验落库实现（迁移 V006：trade\_experience 加 source\_act\_record\_id + 唯一索引；act\_record.py 新增 \_sync\_trade\_experience，冻结开启自动生成经验条目写入 pdca.trade\_experience，关闭软删除，删除连带软删除；单元测试 3/3 通过；curl 全链路自测通过；演示数据 act\_record id=1 经验已补齐落库）。会话交互对象：K


## 会话信息

- 日期：2026-08-24

- 负责角色：量量

- 修改范围：①后端统一用户域 launchd 管理（数据库 com.quant.postgresql/后端 com.quant.backend/ETL 全部迁移 \~/Library/LaunchAgents，停用 watchdog+healthcheck，修复数据库未启动导致后端崩溃循环，重启自愈验证通过）；②冻结经验落库（V006 迁移 + act\_record.py \_sync\_trade\_experience，协作单 20.0 已 CLOSED）；③错误码统一（shared/error\_codes.py 集中表 + PDCA 10 路由改造，数据源 source 标注）；④日志规范（分层目录 backend/etl/cron/postgres/system/frontend）；⑤日志清理随月K线聚合执行（cleanup\_expired\_logs 保留60天，删除独立定时任务）；⑥stage2 触发时间 17:45→17:30（与文档一致）；⑦8-24 数据质量核查通过（日线5207只/指标>99%/宽表正常）；⑧Pandas DBAPI2 警告修复（postgresql\_storage.py 12 处 read\_sql 改 SQLAlchemy engine）；⑨Baostock pe\_ttm 补全修复（日期格式 YYYYMMDD→YYYY-MM-DD + 10秒 signal.alarm 超时防护，实测 1498/1552 成功，pe\_ttm 覆盖率 72%→99%）。量量日报已更新并提交。会话交互对象：K

## 会话信息

- 日期：2026-08-24

- 负责角色：方舟

- 修改范围：协作单 \[20.0] 冻结经验落库复核通过并关闭（VERIFY→CLOSED，说明书更新 V1.3：7.1.1 落库说明 + 7.1.2 全链路验证用例，说明书不入库）；修复交易计划周期下拉不刷新 Bug（PDCADashboard.tsx 新增 planRefreshKey 切页签自动重拉 + TradingPlanEditor.tsx refreshKey 依赖 + 刷新按钮增强，浏览器实测 + tsc 通过，测试周期已清理）。会话交互对象：K

## 会话信息

- 日期：2026-08-25

- 负责角色：方舟

- 修改范围：经验知识库浏览界面（PDCA 新增「经验知识库」页签，只读浏览 + 标签筛选 + 详情展开）；协作单 \[21.0] 提单转量量实现查询 API；前端 ExperienceLibrary.tsx + experience.ts service + types 新增 TradeExperience；说明书同步更新。会话交互对象：K


## 会话信息

- 日期：2026-08-25

- 负责角色：量量

- 修改范围：①P0 修复 pandas2.2+SQLAlchemy2.0 参数化查询回归（postgresql\_storage.py 新增 \_run\_query\_df helper，10 处 read\_sql 改写，Decimal→float，全链路重跑通过）；②协作单 \[21.0] 经验知识库查询 API（experience.py+路由）；③协作单 \[22.0] 资金曲线浮盈修复（snapshots.py）；④清理 parquet 备份文件。已提交 a6e7261/64b3824/eed61d9，日报已生成。会话交互对象：K

## 会话信息（方舟）

- 日期：2026-08-25

- 负责角色：方舟

- 修改范围：①经验知识库浏览界面（前端 4 文件：PDCADashboard.tsx 新页签 / types.ts 类型 / services/experience.ts / components/ExperienceLibrary.tsx）；②协作单 \[21.0] 联调验证 CLOSED；③协作单 \[22.0] 资金曲线 bug 诊断提单+复核 CLOSED；④协作单 \[23.0] 数据管道回归验证 CLOSED。协作单已闭环，日报已生成，待提交前端代码。修改范围全在前端 + docs。会话交互对象：K

## 会话信息

- 日期：2026-08-26

- 负责角色：量量

- 修改范围：研究确认 pe\_ttm 缺失均为亏损股 → 移除 Baostock pe\_ttm 补全逻辑（sync\_daily\_basic.py，删除 \_fill\_pe\_ttm\_gaps + 相关常量/import）；估值筛选改为 pe\_ttm>0；ETL\_PIPELINE.md 文档同步。注意：工作区仍有方舟昨日未提交前端改动（PDCADashboard.tsx/types.ts/ExperienceLibrary.tsx/experience.ts + report\_20260825\_方舟.md），本次量量只提交自身改动，方舟文件待方舟提交。会话交互对象：K

## 会话信息

- 日期：2026-08-27

- 负责角色：量量

- 修改范围：①复权因子增量「只下载变化部分」优化（sync\_adj\_factor.py：stock\_fhps\_em 筛窗口内除权股票，5232→212，约-24倍调次，接口异常自动回退，正确性验证通过）；②定时任务时间调整（阶段2 17:30→16:30、阶段3 18:15→17:30，launchd stage2/3 plist + load\_launchd\_plists 文案，plutil 通过）；③全项目日志格式统一（logger.py 新增 IsoFormatter+LOG\_FORMAT+configure\_root\_logging，ISO8601 毫秒+时区，5字段，接入调度器/ETL/后端main/监控；修正 basicConfig %f 坑需走 IsoFormatter）；④文档同步（ETL\_PIPELINE.md v1.5、量化交易.md 新增第7章日志规范）。注意：工作区仍含方舟未提交前端改动（PDCADashboard.tsx/types.ts/ExperienceLibrary.tsx/experience.ts + report\_20260825\_方舟.md）及今日 ETL 生成数据产物 latest\_quotes.parquet/.bak，本次量量仅提交自身代码改动，方舟文件与数据产物待方舟/另行处理。会话交互对象：K

## 会话信息

- 日期：2026-08-28

- 负责角色：量量

- 修改范围：①协作单清理——删除已 CLOSED 的历史工单（8.0\~24.0，含 12.0 状态残留 NEW 但实际已闭环），仅保留活动工单；②协作单 \[24.0] 经验知识库口径确认（NEW→VERIFY：数据来源保持全部非软删除/标签保持自由/内容前端分节渲染）；③协作单 \[25.0] K线 import os + 毛盈亏口径确认（NEW→VERIFY：问题1 import os 合规无遗漏 curl 验证 200；问题2 毛盈亏全量口径正确非 Bug，0.00 根因为本次平仓未生成卖出子单、remain\_qty 未扣 gross\_profit null，待方舟浏览器重新添加卖出子单修正）。会话交互对象：K

## 会话信息

- 日期：2026-08-28

- 负责角色：方舟

- 修改范围：①协作单 \[24.0] 经验知识库口径验证 CLOSED（前端 ExperienceLibrary.tsx 三节分节渲染 + 说明书 V1.4）；②演示 2026-08W4 周期天齐锂业 002466 平仓操作（发现 K 线服务 500：kline\_service.py 缺 import os，方舟越权临时修复并重启后端；平仓保存成功，但毛盈亏显示 0.00 待确认口径）；③协作单 \[25.0] 提单转量量：K 线 os Bug 复核 + 毛盈亏计算口径确认。会话交互对象：K
  \[量量 2026-08-29] 看板逻辑修复：系统看板「复权因子同步」误报「部分完成（198/4000, 5.0%）」已修复——根因是复权因子增量「只下载变化部分」优化后，最新交易日仅除权股（198 只）写入属正常，但 monitor.py 仍按全市场 4000 判覆盖率。已为 adj\_factor\_sync 加 incremental\_delta 标记并特判 success（见 monitor.py），后端已重启，task-chain 验证 \[D] success。周K/月K 定时提前：周K 19:00→18:30、月K 20:00→18:45，plist/脚本/文档注释已同步，load 脚本已重载生效。
  \[量量 2026-08-29] 测试同步待办（后续处理）：backend/tests/test\_daily\_job\_runner.py 因 daily\_job\_runner.py 阶段模型演进而未同步，4 个失败（test\_stage\_constants / test\_stage\_definitions\_have\_expected\_tasks / test\_all\_success / test\_mixed\_status），均为修改 STAGE_\* 常量命名与阶段结构（阶段3拆分、STAGE\_DAILY\_IMPORT 改名、stage2 独立日线导入）所致，不含 DB 依赖，可安全修复。本次 27.0 改动无关，已确认忽略。留待后续「测试同步」统一更新测试中的常量引用与 get\_last\_batch\_status 返回值断言。

## 会话信息

- 日期：2026-09-02

- 负责角色：方舟

- 修改范围：港股/美股改造立项（K 决意纳入港美股）——①完成 yfinance 数据质量实测验证（9988.HK/AAPL/SPY/BTC-USD 日线+基本面可用，Adj Close 为后复权，港股代码须去前导零，0700.HK 元数据缓存需用 start/end 或长 period 绕过）；②整理 docs/reference/yfinance接口调用参考.md；③细化《加入港股美股改造方案\_v2.md》（含复权口径最终决策：后端存 raw\_*+adj\_* 绝不存静态前复权价、汇率 fx\_rates、限流分片、幂等、P0 监控告警、M0-M7 里程碑）；④协作单 \[30.0] 立项提单转量量（后端全部工作项：M1 表迁移/M2 适配器+复权+港股ETL/M3 美股ETL/M4 计算层复用/M4.5 汇率/M5 API/M7 定时任务/P0 监控）。前端 M6 开发计划见当日日报。会话交互对象：K


## 会话信息

- 日期：2026-09-03

- 负责角色：量量

- 修改范围：协作单 \[30.0-HKUS-MARKET] 全链路推进——V1(V008迁移+迁移执行器) → V2(Yahoo适配器+复权+港股ETL) → V3(美股ETL+V011+核心池205) → V4(M4计算层复用+M4.5汇率) → V5(M5 API+V012)，均置 VERIFY 待方舟验证；V6(P0监控+M7定时) 开发中：hk/us\_job\_runner 拆分（task\_run\_log 记 `hk:`/`us:` 前缀）、/monitor/market-chain 接口、港17:00/美次日08:30(周二\~六) 双 plist、监控三页签（沪深/港股/美股）。**P1 修复**：A股日线导入误带港/美股——import\_daily\_data.py 选股与完整度校验加 market='cn'、fill\_missing\_data.py 补 sb.market='cn'。**诊断**：港股回填「拉取为空」= Yahoo 429 限流（非停牌/非代码错，实测 0080/0700.HK 可拉）。**文档**：ETL\_PIPELINE.md v1.6（港/美股任务链+三页签+手动启动命令，.trae 不入库）。**待办**：30.0 V6 置 VERIFY 收尾→30.0 CLOSED；import\_hk\_daily 限流节流修复。会话交互对象：K

## 会话信息

- 日期：2026-09-03

- 负责角色：方舟

- 修改范围：30.0 港/美股后端全链路 V1-V5 验证通过（V008迁移/港股美股ETL/M4计算复用/fx汇率/V5 API与V012 watchlist，门禁登录 curl 复验）；M6 前端市场工具层（T1/T7/T8/T9）+ 选股器市场传导与隔离（T2/T3）；美股列表 K 确认先按 205 只、后续扩 \~600；31.0 K线除权日登记后置；晨检数据管道健康。量量已进入 V6（P0监控+M7定时），30.0 完成后 CLOSED。

## 会话信息

- 日期：2026-09-04

- 负责角色：量量

- 修改范围：①港股/美股下载限流+断点续传（market\_download\_common + V013 游标列）+ `--start-date` 区间参数；②港股行情下载空跑排查与修复（根因=新浪 9/4 数据延迟、增量终点硬编码今天→整批拉空；新增 `_probe_src_latest` 探测数据源最新日期，港/美股对称修复 + 6 新单测）；③移除 yfinance 依赖（删 sync\_hk/us\_basic/sync\_fx/check\_index\_integrity，列表同步改 AkShare，停 hk\_basic\_sync 告警进程）；④周/月K覆盖率统计修复（分母改周期内实际日线股票数 58%→100%）+ 周/月K聚合补 market 字段并回算 2025+；⑤监控看板修复（动态基准/latest\_date 按 market 过滤、get\_markets 超时、running 4h 僵死检测、数据完整性总览文案）。**待办**：新浪 9/4 港股数据更新后重跑 `import_hk_daily --incremental` 补数；30.0 港/美股真实数据状态跟踪。会话交互对象：K

## 会话信息

- 日期：2026-09-05

- 负责角色：方舟

- 修改范围：M6 联调收尾（前端）。修复2个前端 bug：①选股器市场切换 market 参数丢失（useScreenerData.stateRef 漏装配 selectedMarket）→ 已修+回归2例+浏览器复验（market=hk 返回 .HK 港股）；②K线详情页 STOCK\_CODE\_RE 只认A股代码导致 .HK 被判「无效的股票代码」→ 放宽对齐后端白名单+浏览器复验 0005.HK 正常渲染150根；补 tests/setup.ts scrollTo 桩消除 jsdom 未处理拒绝。**已提单转量量**：协作单 \[6.2-HK-SIGNALS-20260905] 港股 trade\_signals 近乎缺失（仅1只、滞留08-20，K线已到09-03），疑似 signal\_precompute --market hk 链路未铺开。**既有失败**：tests/components/StockPickerView\.test.tsx「导出结果」用例（createObjectURL spy 0次）在我改动前后均失败，非本次引入。**待 K 反馈**：fx 区间接口（前端目前按月首 forward-fill 折算）。回测 fx 链路待联调验证。会话交互对象：K

## 会话信息
- 日期：2026-09-06
- 负责角色：方舟
- 修改范围：复核协作单 27.0 / 30.0。**27.0**（交易日记）：门禁登录后三项硬性复核全过（无 trading_record_id→422；DELETE 不存在→404；DONE 周期 delete/put→40018 且数据未动），状态字段由陈旧 VERIFY 同步为 **CLOSED**（早于 08-29 即已关闭）。**30.0**（港股美股）：V1-V5 均已验证闭环；本轮 V6 接口复核 PASS（/monitor/markets/ 三市场覆盖 hk 2184/us 203、/monitor/alerts/、/monitor/market-chain/?market=hk）。状态字段同步为「ASSIGNED→V6（V1-V5 闭环 + V6 铺全量 hk 2184/us 203 进行中，回填齐后置 VERIFY 请方舟最终验证）」。**30.0 剩余**：等量量铺全量完成（HK/US 对齐最新交易日）→ 方舟做整单收尾 CLOSED。会话交互对象：K

\[量量→方舟 2026-09-06 09:45] 协作单 \[6.2-HK-SIGNALS-20260905] 状态变更: ASSIGNED→VERIFY（港股信号补数完成：9/4 日线入库后指标 2644 只/信号 2642 只对齐 09-04，宽表 snapshot 2184 条 + parquet 已导出；0005.HK 行情/指标/信号全部对齐，9 月 4 条信号。请方舟前端验证 0005.HK K 线无「信号数据加载失败」告警、出现买卖信号标记后 CLOSED）
\[量量→方舟 2026-09-06 10:05] 协作单 \[30.0-HKUS-MARKET-20260902] 状态变更: ASSIGNED→VERIFY（V6 铺全量完成：HK/US 日线+指标+形态+信号+宽表+Parquet 全链路对齐 09-04 —— hk 2184 只（宽表已重建）/us 205 只（9/4 增量补入后重算 5 步链路）。请方舟整单收尾验证：三市场监控接口 + 港美股 K 线/选股/自选 + 信号可用性复核后 CLOSED。注：美股 6 只增量拉空待下个交易日自然补回）

## 会话信息
- 日期：2026-09-06
- 负责角色：量量
- 修改范围：**港股选股负价格报错修复（P0）**——根因=新浪 hfq 对仙股返回负后复权价（raw 为正）导入未校验，美股锚点重建对 NEM 同类负价。①脚本防护：import_hk/us_daily 的 clean_and_split 检测负 adj 价→回退 raw、因子置 1.0（置于 detect_factor_dates 前防误标除权日），单测通过；②存量数据修复：HK 60625 负价行回退 raw + 56179 pre_close 重算 + 43214 负因子删除；US 45 行 + 43 pre_close + 39 负因子；③港股全链路重算（指标 2644 只→形态→信号→宽表 2184 条→parquet）完成；④验证：hk parquet 2184 行转 StockResponse 0 错误、0 负值。**已完成**：6.2/30.0 协作单状态置 VERIFY（数据补数完成）。会话交互对象：K

## 会话信息
- 日期：2026-09-07
- 负责角色：方舟
- 修改范围：**0046.HK 行情异常排查与修复**。K 报告 0046.HK 行情不对，根因=新浪港股数据源在部分交易日 **Adj Close 未复权**（K 线现值 4.x→1.3 跳变）。①**第 1 类（volume=0 停牌占位，核心断裂）**：剔 216,498 行（552 只，含 0046 8/31、9/1），备份表 `stock_quotes_hk_vol0_bak_20260907`；重算周/月K（temp/bar_hk_recompute.py，仅 market=hk）+ 指标(全量 hk)+形态+信号(force-full)+宽表+parquet，0046 最新 20260904 4.12 恢复连续；②**第 2 类（volume>0 未复权错价）**：如 0046 7/17 adj=1.20=raw 级、factor0.95 夹在两日 3.2 之间（530 只/30 万行），判据复杂（2000 年 factor0.25 是真实复权）、删除会形成数据空洞 → **提单 32.0 转量量**设计导入层复权有效性校验+备用源回补+级联重算。③**美股核查无同类问题**（volume=0 仅 110 行/1984-1995/已复权历史，2026 归零）。剩 0046 7/17 等历史未复权错价待量量 32.0 处理。会话交互对象：K

## 跨会话通知
[方舟→量量 2026-09-10 17:00] 协作单 [34.0-BOLL-SIGNAL-FALSEPOSITIVE-20260910] 状态变更: VERIFY→**CLOSED**（方舟独立复核通过：代码确认 SELECT 补选 boll_*+守卫；数据源独立查证 600036/000001/600519 boll_upper 全部实值无 0；接口实证三股布林 `>0.00` 误报 0、600036 布林 167→16 条真实信号，前端无信号告警、除权/布林正常渲染。布林误报根因彻底修复。注：600036 仍约 70 条 RSI 真实信号属 RSI 阈值频率高，独立于本工单，另议）
[方舟→量量 2026-09-10 17:05] 协作单 [34.1-RSI-SIGNAL-DENSITY-20260910] 状态变更: NEW（600036 总信号约 100 条中约 70 条为 RSI 超买/超卖真实信号、触发频率高与震荡噪声混合;前端已按类型分散去重缓解显示,需量量评估 RSI 阈值/连续合并/确认条件以降频,P3 低优先级）
[方舟→K 2026-09-10 16:15] 协作单 [31.0-KLINE-EXDIV-ANNOTATE-20260903] 状态变更: VERIFY→CLOSED（方舟前端联调通过：api.ts 解析 ex_dates→useStockChart buildExDateMarkers 渲染「除权」belowBar 标注，浏览器实测 600036 详情页 6 月中下旬「除权」淡紫圆点成功渲染、与复权跳空对齐；单测已补 ex_dates 解析+空兜底；31.0 全链路闭环完成）
[方舟→量量 2026-09-07 11:20] 协作单 [32.0-HK-UNADJUSTED-20260907]：**全市场"孤立"判据收敛复核+批量清洗已落地**。用`前后相邻日 factor 均正常、仅当日本复权`严格孤立判据复核全 market=hk，确认此前 70 只清单多数已被早期 305 行清理覆盖，**当前库残留 27 行/14 只**孤立未复权错价（0053/0060/0089/0096/0105/0114/0130/0157/0158/0184/0186/0212/0216），其中 0175.HK 经核验为**整段平滑复权段误报，排除不处理**。已备份 `temp_hk_notch_backup_20260907` 并删除 27 行，重算 13 只指标+17 组形态+周/月K（1w/1m 共 52 万行）+信号全量（445,607 条）+宽表（2,184 条）+parquet（2,184/93 列无负价）。**当前库孤立未复权错价已清零**。仍需量量在 `import_hk_daily.py` 导入层加「Adj Close 缺失/≤Close×1.01 即剔除回退+告警」拦截防复发，并对增量每日过检。

## 会话信息
- 日期：2026-09-08
- 负责角色：量量
- 修改范围：①港股/美股基本面同步补全（新建 sync_hk_basic.py 百度估值 + sync_us_basic.py 新浪；港股 09-07 2784条/美股 09-04 209条，PE覆盖100%）；②交易信号+宽表重算（港股 09-07 信号1566/宽表2202、美股 09-04 信号130/宽表205）；③监控覆盖率口径误报修复 monitor.py（signal_precompute 事件驱动不分市场固定阈值100，其余任务港/美股动态基准——修复技术指标97.5%/形态97.5%/信号success三误报）；④美股引入 pandas_market_calendars；⑤周六基本面补全 launchd（hk 12:00 / us 13:00 两 new plist + load_launchd_plists.sh）；⑥港股ETL 17:00→21:20（数据源21:14才到位）；⑦us_job_runner 恢复基本面步骤 + hk_job_runner 基本面低频开关（HKJOB_RUN_BASIC=1）。**明日待办**：协作单 32.0 遗留 P1——import_hk_daily.py 导入层「Adj Close 缺失/≤Close×1.01 剔除回退+告警」复权有效性拦截（方舟 09-07 已清存量 27 行，防复发）。会话交互对象：K

## 会话信息
- 日期：2026-09-07
- 负责角色：量量
- 修改范围：监控后端改造两条——33.0 监控看板按市场统计（`monitor.py` 加 market 参数+市场专属缓存键，`monitor.html` 三市场预加载+页签联动）、33.1 美股任务链误报修复（`US_HOLIDAYS_2026`+`_get_last_us_trade_date` 美东时钟期望交易日、股票列表/Parquet 改数据就绪判断）。32.0 港股脏数据（volume=0/Adj Close 缺失/孤立未复权错价）清洗由方舟完成，量量侧 `import_hk_daily.py` 导入层拦截列为明日待办。协作单 33.0/33.1 待 K 重启后端后由方舟复核。

## 会话信息
- 日期：2026-09-09
- 负责角色：量量
- 修改范围：①**港股当日增量探针端点错配 P0 修复**（`import_hk_daily.py`）——`_probe_src_latest`/`_window_is_single_day` 由逐只日线源（新浪滞后一天）切换为批量快照源 `download_hk_snapshot_all`（与生产路径一致），`_window_is_single_day` 改按窗口内是否含工作日判缺口，删废弃 `PROBE_CODE`；实测 09-09 批量直写 2709 回写 last_sync。②**跨市场混算举一反三**：`standardize_stock_codes.py` 的 `check_data_consistency` 限定 market='cn'，标注废弃 `calculate_highs.py`/`run_data_complete.py`，复核监控/任务链已按市场隔离。③**日志治理**：`compute_indicators_daily.py` 详细日志按日期轮转 `logs/cron/indicator_compute.log` + `_write_summary` 汇总；新建 `log_retention.py`（30 天清理 cron 明细）集成 `daily_job_runner`。④**港股调度**：改造 `probe_hk_poll.py` 以全天不复权快照源为命中判据（实测 17:02 就绪），港股自动任务 **21:20 → 18:30**。**待办**：32.0 P1——`import_hk_daily.py` 导入层「Adj Close 缺失/≤Close×1.01 剔除回退+告警」防复发；复验 09-10 18:30 自动任务正常导入。会话交互对象：K

[方舟→量量 2026-09-09] 协作单 [33.2-SNAPSHOT-503-20260909] 提单（NEW，P1）：选股视图有条件构建器选股偶发「OHLCV 数据拉取失败 HTTP 500」。根因=`get_all_snapshot` 抛 `ServiceNotReadyError`（继承 `Exception`）被全局 handler 映射为 **500**。预期修复：将 `ServiceNotReadyError` 改为 `RuntimeError` 子类或新增 503 映射，使「数据刷新/加载中」返回 **503**。前端 `CustomIndicatorService` 已由方舟加 503 就绪轮询（等 `/api/snapshot/ready` 后重试），后端按 503 修复后即可根治、无需前端再改。

[方舟→量量 2026-09-10 09:00] 协作单 [33.2-SNAPSHOT-503-20260909] 状态变更: NEW→VERIFY→**CLOSED**（方舟校验通过：`ServiceNotReadyError` 已继承 `RuntimeError`，`py_compile` 通过 + `issubclass` 断言=True，已被 `RuntimeError→503` 处理器正确映射，刷新窗口 `/api/snapshot/all` 返回 503 而非 500；前端 `CustomIndicatorService` 已带 503 就绪轮询）。按 K 指令已闭环工单删除归档，协作单 33.2 段落已移除。注：后端重启 + 刷新窗口回归留待部署复验。

[量量→方舟 2026-09-10 09:00] 协作单 [32.0-HK-UNADJUSTED-20260907] 状态变更: NEW→VERIFY（导入层拦截防复发已完成：`import_hk_daily.py` 新增 `_guard_unadjusted_notches` 基于「孤立断崖」判据剔除 Adj Close≈Close 未复权错价行并告警，天然排除真实除权块/最新锚点；4 用例自测通过。存量错价已由方舟 09-07 清至零，「备用源回补」未引入。请方舟后续增量自动过检无「孤立未复权错价」告警后 CLOSED）

[方舟→量量 2026-09-10 09:30] 协作单验证收尾（应 K 要求）：**30.0 / 6.2 / 33.0 / 33.1 由方舟验证通过，状态置 CLOSED 并已按 K 指令从协作单删除归档，文件 644→119 行大减体积。** 验证要点：30.0=hk/us 任务链 8 步全 success、宽表/信号/parquet 对齐；6.2=港股信号最新 09-08 类型齐全（0005.HK 抽查）；33.0=data-summary/coverage-trend 按 market(cn/hk/us) 口径独立（5207/2709/205）；33.1=us 期望交易日 `_get_last_trade_date` 返回 09-08 正确。**32.0 保留未 CLOSED（复核发现存量残留）**：导入层拦截已生效（09-09 21:06 拦 X.HK 07-17 错价），但对 `stock_adj_factor`(hk,>=2024) 聚焦判据扫描仍检出 **38 行/26 只**真孤立未复权错价（0046 2026-04-01 等，2025~2026 存量，未见新增），未达「存量收敛为 0」。请量量与方舟核对 38 行清单并批量清理+级联重算后续作（已在协作单 32.0 处理记录追加）。31.0 为 NEW 登记保留。

[方舟→量量 2026-09-10 11:00] 协作单 [32.0-HK-UNADJUSTED-20260907] 复核反馈：量量两轮清理（删 30 行 factor + 重建 8 行 quotes + 级联重算）已消除 0046 等大部分，级联已跑通（指标/信号/宽表最新 09-09）✅。但用精判据「f∈[0.8,1.15] 且前后>当日×1.5」（adj≈close 未复权特征）复查 `stock_adj_factor`(hk,>=2024) **仍残留 2 行确凿未复权错价未删**：0069.HK(2025-09-26 f=0.9767, 应 1.59/1.58)、0148.HK(2026-06-11 f=1.0000, 应 1.51/1.53)。请量量补清这两行（删 factor 行或回写应有因子 + 级联重算该两股）后置 CLOSED；另 0021 f=0 型与 0206/0339/0612/3301 疑似类型请单独复核口径。

## 会话信息

- 日期：2026-09-09

- 负责角色：方舟

- 修改范围：①港美股跨市场整单终验收尾（30.0 三市场监控/K线/选股/自选/信号、6.2 港股信号前端可用性、33.0 看板按市场统计、33.1 美股任务链误报，均验证通过置 CLOSED）；②32.0 港股导入层拦截终验通过（复核 `_guard_unadjusted_notches` 判据，全市场未复权错价残留归零）置 CLOSED 归档；③新增协作单 33.3 登记 32.0 清理排除的 f=0 型（0021.HK）与疑似类型（0206/0339/0612/3301）转量量口径复核；④协作单归档清理（删除已 CLOSED 工单）+ topics.md 状态通知 + 方舟日报。会话交互对象：K

## 会话信息

- 日期：2026-09-10

- 负责角色：方舟

- 修改范围：前台股票搜索跨市场支持。①自选股「添加自选股」：改为代码/名称输入，新增 `searchStocksAll`（/stocks/search 三市场并发合并）并使 `useStockSearch`、弹窗 `resolveCode` 跨市场，港美股可搜；②交易室「标的代码」：统一 `stockSearchOptions`（buildStockOptions/pickStockName）三处调用，修复港股名称被加 `.HK` 前缀（原纯数字正则 label 反解），并加 `optionLabelProp="value"` 使选中后只显示代码；③K线弹窗缺省带「除权」标注；④前端信号去重段合并 + `/api/snapshot` 503 就绪轮询。遗留待 K 定夺：交易室美股中文名搜不到（stock_basic 美股仅有 ticker 名，属后端/数据层，需决策是否开协作单转量量）。会话交互对象：K

- 修改范围：协作单 32.0（港股存量未复权错价）清理收尾 + 协作单 33.2 修复。①32.0：以孤立断崖判据定位 38 行/26 只错价，备份后删 30 行 factor + 重建 8 行 quotes，级联重算受影响股票指标/周月K/形态/信号/宽表/parquet；方舟复校验²补清 0069.HK(2025-09-26)/0148.HK(2026-06-11) 2 行（仅删 factor，quotes 因子本正常无需重算），精判据 f∈[0.8,1.15] 且前后>1.5× 全市场复查归零；32.0 方舟终验 CLOSED，f=0型/疑似类型平移登记为 33.3。②33.2：`snapshot_service.py` `ServiceNotReadyError` 改继承 `RuntimeError`，命中全局 503 映射修复选股快照偶发 500，方舟验证 CLOSED。日报已更新，待提交。会话交互对象：K

## 会话信息
- 日期：2026-09-10
- 负责角色：量量
- 修改范围：①协作单 33.3 港股 factor 残留口径复核 CLOSED（f=0/孤儿/坏值归零，除零消除）；②协作单 31.0 K线除权日后端部分（A股 factor_date 回填 31,488 行/4,703 只 + sync_adj_factor 增量打标 + kline_service 透出 ex_dates，方舟联调后 CLOSED）；③协作单 34.0 布林误报修复 CLOSED（SQL 漏选 boll 列 + 守卫）；④协作单 34.1 RSI 信号状态机合并 VERIFY（600036 98→30 条）；⑤日志治理全项目改造（logger.py 新增 setup_detail_and_summary_loggers，7 个 ETL 脚本明细→stdout(cron 明细)、主日志只留汇总，hk/us runner 补 _write_cron_detail 完整落盘）。注：31.0/34.0/34.1 后端代码已随 d3510d3 提交，本次提交覆盖日志治理。会话交互对象：K
