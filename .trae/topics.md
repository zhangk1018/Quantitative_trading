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
- 修改范围：调查后台进程频繁停止根因（macOS jetsam 内存压力杀死进程），修复方案：SnapshotService OHLCV 延迟加载（稳定内存 1.6GB→167MB，降低87%）、内存优化（batch_size/GC/消除中间列表）、双重守护机制（watchdog + launchd 健康检查）、清理废弃脚本和临时文件

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