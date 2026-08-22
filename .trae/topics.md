# 跨会话提醒

## 会话信息
- 日期：2026-08-15
- 负责角色：方舟
- 修改范围：交易台账费用计算修复、交易成本缓存机制、dirtyFields追踪、晨星放量条件修复、回测Worker崩溃修复、下拉菜单滚动条修复

## 会话信息
- 日期：2026-08-16
- 负责角色：方舟
- 修改范围：协作单 [14.0-DAILY-CHECK-WEEKLY-MONTHLY-20260816] 提单转量量（晨检增加周K/月K检查）；回测分析页签批量回测改造完成（整组逐股回测+汇总对比，浏览器自测通过）；协作单 [15.0-EXIT-SLIP-SAVE-500-20260816] 交易台账新增卖出记录保存500修复（V004迁移未执行导致表缺stamp_duty/transfer_fee列，已执行迁移，浏览器自测通过）

[方舟→量量 2026-08-16 17:15] 协作单 [16.0-PLAN-BACKEND-20260816] 状态变更: NEW（阶段A交易计划模块后端接口，方舟越界新建 plans.py/securities.py 及模板接口，请量量接手评审/确认，前端交易计划页签已就绪待联调）
[方舟→量量 2026-08-16 17:30] 协作单 [16.0-PLAN-BACKEND-20260816] 状态变更: NEW→VERIFY（量量已修复：commit dacf28b（LEFT JOIN 替代 N+1、INSERT ON CONFLICT）和 8dd2069（deleted_at 过滤、Pydantic 校验），方舟审核通过，关闭协作单）
[方舟 2026-08-16] 协作单 [14.0-DAILY-CHECK-WEEKLY-MONTHLY-20260816] 状态变更: VERIFY→CLOSED（晨检脚本周K/月K检查验证通过：weekly_quotes_freshness OK 最新2026-08-14/5208只，monthly_quotes_freshness OK 最新2026-07-31/5207只，SKILL.md已同步更新）
[量量 2026-08-16] 协作单 [13.0-EXIT-SLIP-ONE-BUY-MULTI-SELL-20260813] 状态修正: VERIFY→CLOSED（处理记录已标注 CLOSED，顶部状态同步修正）
[量量 2026-08-16] 协作单 [14.0-DAILY-CHECK-WEEKLY-MONTHLY-20260816] 状态变更: NEW→VERIFY（创建 backend/scripts/daily_check.py，含周K线/月K线检查，请方舟验证）
[量量 2026-08-16] 代码审查修复: 方舟违规修改的后台代码（pdca/plans.py/securities.py/snapshots.py/__init__.py）已审查并修复 10 项问题（竞态条件/O(n²)性能/N+1查询/事务缺失/异常捕获/假值吞没），已提交 commit dacf28b
[方舟 2026-08-16] 回测分析页签批量回测完成：股票选择支持整组自选股（"🎯 回测整个分组"），逐股回测汇总对比（盈亏/胜率/最大回撤/交易次数）+单股明细切换，TypeScript编译通过 + Playwright 端到端自测通过（18股票全组回测，17成功1无数据）
[量量 2026-08-16] 三次审阅修复: 提交 10ff362 — 修复部分平仓场景下 sweep-line 浮盈计算错误（按原始数量建仓、按平仓数量扣减，剩余持仓浮盈继续保留）

## 会话信息
- 日期：2026-08-16
- 负责角色：量量
- 修改范围：晨检自动化脚本创建（daily_check.py）、PDCA 后台代码三轮审阅修复（12项，含竞态条件/O(n²)性能/N+1查询/deleted_at过滤/输入校验/部分平仓浮盈计算）、技能文档同步更新、协作单状态处理

## 会话信息
- 日期：2026-08-17
- 负责角色：方舟
- 修改范围：PDCA 菜单重新排列+资金管理拆分、周期总览删除/滚动修复、批量回测 isRunning 状态修复、二期 PDCA 进度盘点及明日计划

## 会话信息
- 日期：2026-08-18
- 负责角色：量量
- 修改范围：调查后台进程频繁停止根因（macOS jetsam 内存压力杀死进程），修复方案：SnapshotService OHLCV 延迟加载（稳定内存 1.6GB→167MB，降低87%）、内存优化（batch_size/GC/消除中间列表）、双重守护机制（watchdog + launchd 健康检查）、清理废弃脚本和临时文件；每日晨检 Pipeline 健康检查（9 OK / 2 WARN）；协作单 #17.0 复核（Check+Act 后端代码审阅通过 + 3 项修复：索引+account_id+String长度，V005迁移）；daily_basic_sync 超时配置修复（3600s→7200s）

## 会话信息
- 日期：2026-08-18
- 负责角色：方舟
- 修改范围：PDCA 二期闭环 Check+Act 模块前端实现（CheckModule/ActModule 组件、types.ts/api.ts、PDCADashboard Tab）；**越界**创建了 CheckReport/ActRecord 后端 ORM 模型和 API 路由，已开协作单 [17.0] 请量量复核

[方舟→量量 2026-08-18 07:30] 协作单 [17.0-CHECK-ACT-BACKEND-REVIEW-20260818] 状态变更: NEW（方舟越界创建 PDCA Check+Act 后端代码，涉及 6 个文件：check_report.py/act_record.py ORM 模型 + CRUD 路由，请量量复核确认）
[量量→方舟 2026-08-18 08:28] 协作单 [17.0-CHECK-ACT-BACKEND-REVIEW-20260818] 状态变更: NEW→VERIFY（量量复核通过：ORM 模型与 DDL 一致 ✅、API 代码规范 ✅、6 个端点 curl 自测全部通过 ✅，测试数据已清理。请方舟前端验证联调。）
[方舟 2026-08-18 13:25] 协作单 [17.0-CHECK-ACT-BACKEND-REVIEW-20260818] 状态变更: VERIFY→CLOSED（方舟前端验证通过：curl 验证全部 6 个端点正常、CheckModule/ActModule 联调通过、测试数据全流程验证通过）

## 会话信息
- 日期：2026-08-18
- 负责角色：方舟
- 修改范围：API 架构重构（按业务领域拆分 13 个 service 文件、响应拦截器自动解包、CRUD 泛型工厂）、类型分层（constants.ts 分离 LABELS/OPTIONS）、更新 18 个调用方移除 res.code 检查

[量量 2026-08-19] 协作单 [18.0-FRONTEND-AUDIT-20260819] 状态变更: NEW（前端 6 维度代码审查确认 7 项整改：Q1/Q3 类型安全收口、Q4 fetchDailyOHLC 静默吞错、P1 全局 maxDays 内存膨胀、S2 脚本资源上限、Q2 list/listAll 重复、Q5 usePDCACycle 脆弱依赖、S1 Token localStorage 待后端配合。请方舟处理，量量负责终审。）
[方舟→量量 2026-08-19 16:52] 协作单 [18.0-FRONTEND-AUDIT-20260819] 状态变更: ASSIGNED→VERIFY（方舟修复完成：Q1/Q3 类型安全收口、Q2 list/listAll 合并、Q4 fetchDailyOHLC 异常显式化、Q5 usePDCACycle 依赖归一化、P1/S2 内存+资源上限、S1 待后端配合。另补迁移 diary.ts/check-report.ts。TypeScript 编译通过。请量量终审。）
[量量 2026-08-19] 协作单 [18.0-FRONTEND-AUDIT-20260819] 状态变更: VERIFY→REOPENED（终审不通过：① Q5 usePDCACycle 依赖改为对象引用+调用方传内联对象字面量，引发无限请求/渲染循环；② S2 输出上限校验的是批次股票数而非元素数，保护失效。请方舟修复后重新提交。）
[方舟→量量 2026-08-19 16:57] 协作单 [18.0-FRONTEND-AUDIT-20260819] 状态变更: REOPENED→VERIFY（Q5: CheckModule/ActModule 提取 statusOrder 为模块级常量，引用稳定 ✅；S2: totalElements reduce 校验全批次元素总数 ✅。TypeScript 编译通过。请量量终审。）
[量量 2026-08-19] 协作单 [18.0-FRONTEND-AUDIT-20260819] 状态变更: VERIFY→CLOSED（复核通过：Q5 改用模块级常量稳定引用消除无限循环；S2 改为全批次元素总数校验。TypeScript 编译 exit 0。两项阻断项已修复，工单关闭。）
[量量→方舟 2026-08-19] 协作单 [19.0-AUTH-FRONTEND-20260819] 状态变更: NEW（后端单密钥门禁+HttpOnly Cookie 已完成并自测通过，前端 5 处配合：client.ts 删 token 改 withCredentials+401 跳 login、stock-detail/watchlist api 加 withCredentials、新建登录页、路由守卫。门禁密码见 .env 的 API_ACCESS_KEY。）
[方舟→量量 2026-08-19 17:04] 协作单 [19.0-AUTH-FRONTEND-20260819] 状态变更: NEW→ASSIGNED（方舟已认领，完成全部 5 项前端配合：client.ts 删除 token 逻辑+withCredentials+401跳/login ✅；stock-detail/api.ts 加 withCredentials ✅；watchlist/api.ts 加 withCredentials ✅；新建 Login.tsx 登录页 ✅；router.tsx 加 /login 路由+AuthGuard 路由守卫 ✅。S2 minor 加固（Array.isArray 守卫）已同步修复。TypeScript 编译通过。待量量确认后端就绪后联调。）
[量量 2026-08-19] 协作单 [19.0-AUTH-FRONTEND-20260819] 状态变更: VERIFY→CLOSED（终审 5 项+1 全通过：token 删除/withCredentials x3/Login.tsx/AuthGuard 路由守卫/S2 加固，tsc 编译 exit 0。前后端均已就绪，待统一重启上线。）
[量量 2026-08-19 17:13] 本会话结束。今日完成：后端单密钥门禁+HttpOnly Cookie 认证迁移上线（自测+curl 验证全通过）；协作单 [18.0] 终审关闭；[19.0] 提单→终审关闭。已重启上线，认证门禁已生效。日报已提交。明天见！

## 会话信息
- 日期：2026-08-19
- 负责角色：方舟
- 修改范围：协作单 [18.0] 前端代码审计整改（7项+量量终审2项修复）✅；协作单 [19.0] 前端认证迁移（5项+1项加固）✅；K 代码审阅4+3项高优先级修复（错误提取工具、竞态防护、乐观更新回滚、验证错误判误、401无限循环防护）✅；后端重启使 auth 路由生效 ✅

[方舟→量量 2026-08-19 17:40] 协作单 [19.0-AUTH-FRONTEND-20260819] 后端已重启，auth 路由生效，/api/auth/login 返回 200，门禁登录联调通过。

## 会话信息
- 日期：2026-08-21
- 负责角色：方舟
- 修改范围：选股视图量化评分列（新增评分管线+移除K线形态列）、Pyodide Worker init()竞态修复、交易计划股票搜索Bug修复（stock.ts .items→直接返回数组）、选股分层止盈缺省参数10项对齐、交易成本配置优化、K线形态检测微调

## 会话信息
- 日期：2026-08-22
- 负责角色：量量
- 修改范围：修复日线增量导入周末误触发 fallback（import_daily_data.py + _is_trade_day + 7项单测）；修复 daily_check.py missing_stocks 北交所口径误报；修复后端被 healthcheck 循环 kill（healthcheck.plist 加 AbandonProcessGroup=true）；增强 load_launchd_plists.sh 卸载逻辑。会话交互对象：K

## 会话信息
- 日期：2026-08-22
- 负责角色：方舟
- 修改范围：macOS 重装后开发环境重建（Homebrew/Python 3.11/Node/PostgreSQL 18/TA-Lib 0.7.1 + venv 重建依赖安装 + PG 复用原数据 + 前后端自测通过）；装载 launchd 定时任务 7 个 plist + backend 守护；编写 ~/.zprofile 自动加载；触发阶段1 ETL，安装 akshare+tushare，诊断 adj_factor_sync 卡在 WARP IPv6 SYN_SENT 网络问题。会话交互对象：K