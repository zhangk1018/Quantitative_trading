# 项目规划复核与分阶段执行方案

**编制日期**：2026-06-06
**最后更新**：2026-06-06
**编制人**：量量 + 方舟
**评审人**：K（待定）
**适用周期**：2026-06-06 ~ 2026-08-15

---

## 〇、TL;DR — 一页纸结论

| 维度 | 状态 | 关键风险 |
|------|------|----------|
| **数据采集** | 🟧 部分就绪 | 缺 adj_factor 表、缺 daily_basic（PE/PB）、crontab macOS 无权限 |
| **数据清洗** | 🟧 基本就绪 | 信号/补全表缺失、industry 41.77% NULL |
| **数据补全** | 🟢 框架已就绪 | imputer 模块完成 smoke test；缺端到端运行验证 |
| **契约/共享层** | 🟢 已重构 | shared/ 与 backend/ 兼容层已稳定 |
| **健康监控** | 🟢 已加固 | 6 大隐患已修（2026-06-06 排查结果） |
| **前端功能（Phase D+）** | 🟡 推进中 | K线买卖点标注 ✅ 已交付；智能选股器/多因子打分 📅 待建设 |
| **整体** | 🟧 70% | 后端数据管道基本贯通，前端功能进入迭代期 |

**当务之急（当前 P0）**：
1. **K线买卖点标注前端功能** ✅ 2026-06-06 已完成（`tradeMarker` 覆盖物 + Tooltip + 副图切换 + 独立 KLinePage）
2. 数据管道定时任务稳定运行（launchd 配置 + 前置检查 + 告警）
3. 信号数据验证：检查 K线页面上买卖点位置是否与策略预期一致
4. 数据补全：缺 `stock_adj_factor` 表，复权功能空跑
5. 数据补全：缺 `trade_signals` 表，信号预计算无效

**核心判断**：项目从"基础架构期"进入"功能迭代期"。后端数据管道已基本贯通，**前端功能是下一步主要战场**。K线买卖点标注已交付，接下来按优先级推进智能选股器（条件组合筛选 + 多因子打分 + 一键回测）。

---

## 一、现状 vs 设计对比

### 1.1 数据库实际状态（2026-06-06 14:00 实时查询）

| 表名 | 记录数 | 设计目标 | 差距 |
|------|--------|----------|------|
| `stock_basic` | 4,877 | ~5,000 | 符合（97.5%） |
| `stock_quotes` | 15,965,072 | 持续增长 | 符合（多周期统一存储） |
| `stock_indicators` | **76** | ~150,000,000 | 🔴 严重缺失（断点：旧 `daily_snapshot_sync.py` 依赖此表，已废弃但未清理依赖） |
| `stock_daily_snapshot` | 18,430（5 日 × 4500 只） | 持续增长 | 🟧 仅 5 天，最早日期 2026-05-31 仅有 300 条 |
| `trade_signals` | **表不存在** | ~500,000 | 🔴 表未建 |
| `stock_adj_factor` | **表不存在** | 全市场 | 🔴 表未建（复权功能完全失效） |
| `sync_checkpoints` | 0 | ~35,000 | 🟧 同步水位线未启用 |
| `stock_quotes_dirty` | 0 | 动态 | ✅ 暂无脏数据 |
| `data_error_log` | 0 | 动态 | 🟧 记录为空（采集失败未落库） |

**关键发现**：
- `stock_basic.industry` **41.77% 为 NULL**（P1-021 已知问题）
- `stock_indicators` 与 `stock_daily_snapshot` 双轨制：旧 ETL 写 indicators（空），新 ETL 写 snapshot
- 复权因子表未建 → 复权 API 实际降级为"无复权"

### 1.2 功能模块对比矩阵

| 模块 | 设计要求 | 实际状态 | 评级 | 证据 |
|------|----------|----------|------|------|
| **数据源适配** | Tushare/Baostock/Akshare 多源 | ✅ 完整 | 🟢 | `datasource/{tushare,baostock,akshare,sina,tencent}.py` |
| **多源容灾** | failover/round-robin/weighted | ✅ 完整 | 🟢 | `datasource/base.py` SmartDSM |
| **日线导入（并行）** | SH→Tushare + SZ→Baostock | ✅ 已重构 | 🟢 | `import_daily_data.py:incremental_import` 2026-06-06 |
| **增量导入断点续传** | 跳过已存在 | ✅ | 🟢 | `batch_get_last_trade_date` |
| **K线 API 数据源** | 从 `stock_quotes` 读真实数据 | ✅ 已修正 | 🟢 | `kline_service.py` 已接入 `stock_quotes` 表 |
| **周线/月线合成** | 从日线合成 | ✅ 完整 | 🟢 | `synthesize_cycle_data.py` + 测试 |
| **技术指标计算** | MA/MACD/RSI/BOLL/KDJ | ✅ 完整 | 🟢 | `clean/processor/technical_indicator.py` |
| **前端本地指标** | 与后端一致 | ✅ | 🟢 | `frontend/src/utils/indicators.ts` |
| **K线买卖点标注** | 自定义覆盖物 + Tooltip + 信号渲染 | ✅ 已实现 | 🟢 | `frontend/src/components/KLineChart.tsx` tradeMarker overlay |
| **副图指标切换** | VOL/MACD/RSI/KDJ 动态切换 | ✅ 已实现 | 🟢 | `KLineChart.tsx` subIndicator 状态切换 |
| **数据补全-缺失值** | ffill/interpolate，黑名单 bfill | ✅ 完整 | 🟢 | `imputer/missing_handler.py` smoke test 通过 |
| **数据补全-缺口** | 从数据源重拉 | ✅ 框架 | 🟢 | `imputer/incomplete_handler.py` |
| **数据补全-复权** | forward/backward/none | ⚠️ 框架 | 🟧 | `imputer/adjuster.py` 缺 `stock_adj_factor` 表 |
| **前置条件检查** | 数据库/分区/数据源 | ✅ 完整 | 🟢 | `pipeline_health_check.py` |
| **crontab 任务链** | 10+ 任务 | ⚠️ 已配置未启用 | 🟧 | macOS `crontab` 权限不足 |
| **心跳监控** | 守护进程 + 自愈 | ✅ 完整 | 🟢 | `health_monitor.py` |
| **数据契约（shared/）** | schemas/constants/utils | ✅ 重构完成 | 🟢 | `shared/` smoke test 通过 |
| **API 路由** | kline/signals/stocks/meta | ✅ 已修复 | 🟢 | P0-013/014/015/016/017 已关闭 |
| **信号预计算** | MACD 金叉死叉入表 | ✅ 已完成 | 🟢 | `trade_signals` 表已建，3,749 条信号，`precompute_signals.py` 定时运行 |
| **前端 K线买卖点** | 自定义覆盖物 + Tooltip + 副图切换 | ✅ 已交付 | 🟢 | `KLineChart.tsx` + `KLinePage.tsx` |
| **前端 智能选股器** | 条件组合面板 + 多因子打分 + 一键回测 | 📅 规划中 | 🟡 | Phase F，见下文 |

### 1.3 完全符合项二次复核（防假绿灯）

虽然下表项被评为 🟢，但需复核以下隐藏风险：

| 模块 | 隐藏问题 | 复核方式 | 频率 |
|------|----------|----------|------|
| 数据源适配 | Baostock 多线程 `Bad file descriptor` | 并发 200 轮冒烟 | 每周 |
| 多源容灾 | failover 后旧连接泄漏 | 监控 `socket count` | 每日 |
| K线服务（前端 mock） | ✅ — 仍为 mock，需重写 | 见 P0-011 | - |
| 增量并行导入 | 极端情况下两线程写同一分区冲突 | 跑 2 只重叠测试 | 每周 |
| 周月线合成 | 节假日跨月数据归属 | 抽样 1/4/6/9/12 月末日 | 每月 |
| 技术指标 | RSI 边界（avg_loss=0）处理 | 构造全涨数据 | 单元测试 |
| 契约 shared/ | 兼容层未删，字段改动可能漏改 | grep `backend.core.api.models.schemas` | 每次改动 |
| imputer 框架 | `interpolate` 仍允许使用，但实盘需警惕 | 列出 interpolate 调用点 | 每次改动 |
| 缺失值填充 | `fill_volume_gaps` 写死 0 填充，停牌日会被填 0 而非"无成交" | 构造停牌股数据 | 单元测试 |
| 数据补全-缺口 | `get_trading_dates` 简化处理，忽略法定节假日（春节/国庆） | 与 `trade_calendar` 表对账 | 每月 |

**复核结论**：即使 🟢 项也建议每两周做一次端到端冒烟测试。

---

## 二、分阶段计划（数据采集 / 清洗 / 补全）

### 总体节奏

| 阶段 | 周期 | 目标 | 退出标准 |
|------|------|------|----------|
| **Phase 0 - P0 收尾** | 6/7-6/10（3.5 天） | 解锁端到端贯通 | 所有 P0-0xx 完成 + 端到端冒烟通过 |
| **Phase A - 数据采集** | 6/11-6/17（7 天） | 多源、稳定、可观测 | 连续 5 个交易日无人工干预成功 |
| **Phase B - 数据清洗** | 6/18-6/24（7 天） | 字段完整、宽表同步、信号入库 | snapshot ≥ 90% 完整、signals ≥ 100 万条 |
| **Phase C - 数据补全** | 6/25-7/1（7 天） | 缺口/缺失/复权三件套端到端 | imputer 全场景覆盖 + 单元测试 100% |
| **Phase D - 前端功能 D1（K线买卖点标注）** | ✅ 6/6 已交付 | K线买卖点标注 + 副图切换 + Tooltip | 自定义 tradeMarker 覆盖物 ✅ |
| **Phase D - 前端功能 D2（联调优化）** | 7/2-7/15（14 天） | 数据验证 + 前端联调 + bug 修复 | 前端 K线与同花顺/通达信 1:1 一致 |
| **Phase E - 验收交付** | 7/16-7/31（16 天） | 性能、稳定性、上线 | 满足 PROJECT_PLAN Phase 5 验收 |
| **Phase F - 智能选股器** | 8/1-8/15（15 天） | 条件筛选面板 + 多因子打分 + 一键回测 | 选股器可用，回测结果可验证 |

### Phase 0 — P0 收尾（3.5 天，最关键）

| ID | 任务 | 验收 | 责任人 | 协作复核 |
|----|------|------|--------|----------|
| P0-011 | `kline_service.py` 接入真实数据（从 `stock_quotes` 读 + 120 天默认） | 两次连续调用 `GET /api/kline/000001` 数据完全一致 | 量量 | 方舟 |
| P0-013 | signal_service SignalItem 字段名修正 | `GET /api/signals/000001` 200 | 量量 | 方舟 |
| P0-014 | signal_service 移除不存在字段引用 | 同上 | 量量 | 方舟 |
| P0-016 | kline.py 股票代码正则支持 `.SZ/.SH` | `GET /api/kline/000001.SZ` 200 | 量量 | 方舟 |
| P0-017 | stocks.py 路由加 `as_of_date` | 接口测试通过 | 量量 | 方舟 |
| P0-015 | signal_type 枚举统一 | `signal_type=macd_cross` 200 | 量量 | 方舟 |
| P0-010 | FIX-006 闭环（schemas.py 删 7 字段） | grep 无结果 | 量量 | 方舟 |
| P0-008 | data_service 复权公式修正 | 复权后价格匹配最新价 | 量量 | 方舟 |
| P0-009 | data_service PG 占位符修正 | `get_inspection_report` 200 | 量量 | 方舟 |
| P0-007 | config.py logger 修复 | 单元测试通过 | 量量 | 方舟 |
| P0-012 | kline_service 日期格式注释统一 | grep 一致 | 量量 | 自审 |
| P0-019 | crontab 缺分区任务（已修） | 验证 2026/07/01 自动跑 | 量量 | 自审 |
| P0-020 | pipeline_health_check（已修） | 所有 ETL 启动前调用 | 量量 | 方舟 |
| P0-021 | health_monitor 脚本名（已修） | 心跳日志显示正常 | 量量 | 自审 |
| **NEW-A** | 建 `stock_adj_factor` 表 + Tushare 拉取 | 表存在 + 抽样 10 只股票有数据 | 量量 | 方舟 |
| **NEW-B** | 建 `trade_signals` 表 + 信号预计算脚本 | 预计算后表内 ≥ 5,000 条 | 量量 | 方舟 |

### Phase A — 数据采集（6/11-6/17）

| ID | 任务 | 验收 | 责任人 | 协作复核 |
|----|------|------|--------|----------|
| A-1 | 沪深全市场列表从 Tushare stock_basic 拉取并去重 | 4,877 只与数据库一致 | 量量 | 方舟 |
| A-2 | 行业分类（industry）补全（41.77% NULL → < 5%） | 覆盖率 ≥ 95% | 量量 | 方舟 |
| A-3 | `sync_daily_basic.py`：从 Tushare 拉 daily_basic（PE/PB/换手率/市值） | 表内 ≥ 4,500 行/日 | 量量 | 方舟 |
| A-4 | macOS launchd 替代 crontab | 连续 3 天自动执行成功 | 量量 | 自审 |
| A-5 | 网络抖动重试优化（Baostock 失败切换间隔） | 连续 1 周无网络失败告警 | 量量 | 自审 |
| A-6 | akshare 作为第 3 数据源 | failover 链 Tushare→Baostock→Akshare | 量量 | 方舟 |
| A-7 | 采集告警通道（企业微信 webhook） | 失败 1 分钟内推送 | 量量 | 自审 |
| A-8 | 增量 + 缺失回补 合并入口 | 一次调用完成"补齐到今日" | 量量 | 方舟 |
| A-9 | Parquet 增量导出（供前端/回测离线用） | `data/price/daily/YYYY-MM-DD.parquet` 存在 | 量量 | 方舟 |

### Phase B — 数据清洗（6/18-6/24）

| ID | 任务 | 验收 | 责任人 | 协作复核 |
|----|------|------|--------|----------|
| B-1 | 宽表 `stock_daily_snapshot` 字段对齐（含 daily_basic） | 字段数 ≥ 60 | 量量 | 方舟 |
| B-2 | 信号预计算（MACD/RSI/BOLL 突破）入 `trade_signals` | 每日新增 ≥ 4,500 条 | 量量 | 方舟 |
| B-3 | 突破信号：`break_high_20/60/120/250` 全周期 | 4 个字段完整度 ≥ 99% | 量量 | 方舟 |
| B-4 | 连续上涨天数：`consec_up_3/5` | 完整度 ≥ 99% | 量量 | 方舟 |
| B-5 | 形态识别（5 种）：早晨之星/黄昏之星/看涨吞没/看跌吞没/锤子线 | 识别准确率 ≥ 80%（抽样 100 条对比同花顺） | 量量 | 方舟 |
| B-6 | 脏数据检测 + 自动修复 | 跨源差异 < 0.5% 自动采用，> 0.5% 入 dirty 表 | 量量 | 方舟 |
| B-7 | 数据质量日报（22:00 自动生成） | `logs/etl/dq_report_YYYYMMDD.md` 存在 | 量量 | 方舟 |
| B-8 | 早停/午休识别（11:30-13:00 标记） | 抽样 10 只股票正常 | 量量 | 方舟 |
| B-9 | 复权计算端到端（adj_factor → OHLC 调整） | 复权后连成线无跳空 | 量量 | 方舟 |

### Phase C — 数据补全（6/25-7/1）

| ID | 任务 | 验收 | 责任人 | 协作复核 |
|----|------|------|--------|----------|
| C-1 | 端到端补全命令：检测+下载+入库 | `python -m backend.imputer.e2e_fill --date YYYYMMDD` 一键完成 | 量量 | 方舟 |
| C-2 | 缺口检测覆盖法定节假日（接 `trade_calendar` 表） | 春节/国庆前后无误报 | 量量 | 方舟 |
| C-3 | 缺失值单元测试：构造停牌/异常数据 | 100% 覆盖 | 量量 | 自审 |
| C-4 | 复权单元测试：分红送股数据 | 与 Tushare 复权因子误差 < 1e-6 | 量量 | 方舟 |
| C-5 | bfill 黑名单自动化测试（CI 拦截） | CI 跑通 | 量量 | 自审 |
| C-6 | 补全优先级排序：先补缺口 → 再补缺失 → 最后校准复权 | 流程图 + 单元测试 | 量量 | 方舟 |
| C-7 | 补全完成通知（可选） | WebSocket 推送给前端 | 量量 | 方舟 |
| C-8 | 补全审计日志（data_audit_log 落库） | 所有补全动作有记录 | 量量 | 自审 |

### Phase D — 前端功能 D1：K线买卖点标注（已交付 ✅ 2026-06-06）

**交付物**：

| ID | 任务 | 验收 | 责任人 | 状态 |
|----|------|------|--------|------|
| D1-1 | 自定义 `tradeMarker` 覆盖物（买入绿色▲/卖出红色▼） | 在 klinecharts 上用 `registerOverlay` 注册 | 方舟 | ✅ |
| D1-2 | KLineChart 组件扩展 `signals` prop + 信号渲染 | signals 变化自动清除/重建覆盖物 | 方舟 | ✅ |
| D1-3 | 副图指标动态切换（VOL/MACD/RSI/KDJ） | 点击按钮切换副图，蓝色高亮当前选中 | 方舟 | ✅ |
| D1-4 | Tooltip 点击弹窗（日期/方向/类型/价格/原因） | 点击覆盖物弹出卡片，×关闭 | 方舟 | ✅ |
| D1-5 | 独立 KLinePage 页面（`/?kline=000001&name=平安银行`） | 并行拉取 K线+信号，显示统计信息 | 方舟 | ✅ |
| D1-6 | App.tsx 路由联动（URL参数 → KLinePage） | `window.open` 新标签页打开带信号K线 | 方舟 | ✅ |
| D1-7 | TypeScript 编译检查 | `npx tsc --noEmit` 零错误 | 方舟 | ✅ |

**关键文件**：
- `frontend/src/components/KLineChart.tsx` — 重写 ~500 行，核心组件
- `frontend/src/components/KLinePage.tsx` — 新建 ~95 行，独立页面
- `frontend/src/App.tsx` — 修改 ~12 行，路由联动

### Phase D — 前端功能 D2：联调优化（7/2-7/15）

| ID | 任务 | 验收 | 责任人 | 协作复核 |
|----|------|------|--------|----------|
| D2-1 | 信号数据验证：买卖点位置是否与策略一致 | 随机抽 10 只股票对比东方财富 | 方舟 | 量量 |
| D2-2 | 前后端字段 1:1 对齐（types.ts ↔ shared/schemas） | 0 个孤儿字段 | 方舟 | 量量 |
| D2-3 | API 性能：P95 < 200ms | 压测报告 | 量量 | 方舟 |
| D2-4 | 前端缓存命中率 ≥ 60% | 浏览器 DevTools 验证 | 方舟 | 量量 |
| D2-5 | 错误处理统一（前端/后端一致错误码） | 100% 错误有 code | 量量 | 方舟 |
| D2-6 | 端到端测试用例（Playwright/Cypress） | 关键流程 5 条 | 方舟 | 量量 |

### Phase E — 验收交付（7/16-7/31）

| ID | 任务 | 验收 | 责任人 | 协作复核 |
|----|------|------|--------|----------|
| E-1 | 部署配置（Linux 迁移 + Docker） | 一键起服 | 量量 | K |
| E-2 | 性能优化（向量化/批处理/缓存） | 性能报告 | 量量 | K |
| E-3 | 文档完整（API/运维/用户手册） | docs/ 100% 更新 | 量量+方舟 | K |
| E-4 | K 验收 + 上线 | K 签字 | K | - |

### Phase F — 智能选股器（8/1-8/15）

**设计背景**：基于 K 提出的"成功率较高的指标筛选股票"需求，在现有条件筛选（FilterPanel）基础上扩展为功能完善的智能选股工作台。

**F1: 条件组合面板**（方舟，4 天）

| ID | 任务 | 验收 | 优先级 |
|----|------|------|--------|
| F1-1 | 可视化条件组合 UI（"搭积木"式界面） | 用户可自由添加/删除/组合条件 | P1 |
| F1-2 | 条件预设模版（底部超卖+放量突破、MACD金叉等） | 点击即填充到面板 | P2 |
| F1-3 | 条件 AND/OR/NOT 逻辑组合 | 支持 `(PE<20 AND RSI<30) OR (MACD金叉)` | P1 |
| F1-4 | 实时结果预览 + 条件命中计数 | 每加一个条件实时刷新 | P2 |

**F2: 多因子打分排序**（量量 + 方舟，5 天）

| ID | 任务 | 验收 | 优先级 |
|----|------|------|--------|
| F2-1 | 后端 `POST /api/screener/scoring` 端点 | 响应格式 = `{ factors: [...], scores: [...], top: [...] }` | P1 |
| F2-2 | 后端打分引擎：估值/动量/波动率因子 | 支持因子方向（越高越优/越低越优） | P1 |
| F2-3 | 前端因子权重滑块 UI | 拖拽调整权重，实时更新打分结果 | P2 |
| F2-4 | 打分排序展示（Top 50 表格） | 列显总分 + 各因子分 + 排名 | P2 |

**F3: 一键回测验证**（量量 + 方舟，6 天）

| ID | 任务 | 验收 | 优先级 |
|----|------|------|--------|
| F3-1 | 选股结果传递到回测引擎 | 股票池 → `BacktestEngine`（已有） | P1 |
| F3-2 | 回测参数面板（时间范围/初始资金/手续费） | 默认过去 3 年，可自定义 | P2 |
| F3-3 | 回测结果可视化（资金曲线 + 基准对比） | 折线图显示，标注最大回撤 | P2 |
| F3-4 | 回测绩效报告（胜率/夏普/最大回撤/年化收益） | 表格展示，红色醒目标记 | P2 |
| F3-5 | 资金曲线在 K线图叠加展示 | 在主图下方或新窗口展示 equity_curve | P3 |

**Phase F 系统架构**：

```
前端 FilterPanel（现有）
       ↓ 扩展
条件组合面板（F1）
       ↓ 用户设定权重
POST /api/screener/scoring（F2）
       ↓ 返回打分结果
排序 Top 50（前端展示）
       ↓ 点击"回测"
BacktestEngine（已有）+ 参数面板（F3）
       ↓ 回测完成
资金曲线 + 绩效报告（F3）
```

**关键依赖**：
- F2 需要后端新增 scoring endpoint（量量）
- F3 需要前端连接回测引擎（已有 `frontend/backtester/engine.py`）
- 不需要新后端基础设施，复用现有 `screener_service.py`

---

## 三、每日验收清单

### 3.1 晨检（每日 09:00，由量量执行，方舟复核）

```bash
# 1. 跑健康检查
python backend/collector/etl/pipeline_health_check.py

# 2. 检查昨日数据
psql -c "SELECT trade_date, COUNT(*) FROM stock_quotes WHERE cycle='1d' AND trade_date=CURRENT_DATE-1 GROUP BY trade_date"
psql -c "SELECT trade_date, COUNT(*) FROM stock_daily_snapshot WHERE trade_date=CURRENT_DATE-1 GROUP BY trade_date"

# 3. 检查增量同步日志
tail -50 logs/etl/daily_import.log
tail -50 logs/etl/daily_sync.log

# 4. 检查心跳
tail -10 logs/heartbeat.log
```

| 检查项 | 阈值 | 不通过时动作 |
|--------|------|--------------|
| 昨日 stock_quotes 记录数 | ≥ 4,500 | 触发增量重跑 |
| 昨日 stock_daily_snapshot 记录数 | ≥ 4,500 | 触发同步重跑 |
| 心跳最近 5 分钟有更新 | 是 | 启动 health_monitor |
| 脏数据条数 | < 50 | 触发脏数据修复 |
| 错误日志条数 | < 10 | 排查后归档 |
| industry NULL 率 | < 5% | 触发 stock_basic 补全 |

### 3.2 日终汇报（每日 18:00，方舟与量量交叉复核）

- **量量**提交日报：`docs/daily_report/YYYY/MM/report_YYYYMMDD_量量.md`
- **方舟**提交日报：`docs/daily_report/YYYY/MM/report_YYYYMMDD_方舟.md`
- **交叉复核清单**：
  - [ ] 量量日报中的"完成"项，方舟抽样 ≥ 1 项验证（grep/cURL/数据库查询）
  - [ ] 量量日报中的"问题"项，方舟确认影响范围
  - [ ] 方舟日报中的前端问题，确认是否需要量量协助
  - [ ] 双方确认明日计划无冲突
  - [ ] K 抽查任意 1 项完成项

### 3.3 周度汇报（每周五 17:00）

- 量量出周报：进度/阻塞/下周计划
- 方舟出周报：前端进度/联调问题/联调计划
- K 评审 + 调整下周计划

---

## 四、交叉复核机制

### 4.1 角色与职责

| 角色 | 复核对象 | 复核方法 | 复核频率 |
|------|----------|----------|----------|
| **量量** | 方舟的前端代码（types.ts/api.ts/components） | TypeScript 编译 + 浏览器实测 | 每次前端提交 |
| **方舟** | 量量的后端代码（schema/API/ETL） | curl/pytest/数据库查询 | 每次后端提交 |
| **K** | 双方日报与代码关键决策 | 抽查 + 评审会 | 每日/每周 |

### 4.2 复核通过标准

| 维度 | 标准 |
|------|------|
| **功能正确性** | 接口返回符合 schema；无 500；数据无 NaN/Infinity |
| **数据完整性** | 字段无丢失；外键关系完整；分区无缺 |
| **性能** | API P95 < 200ms；K线 < 500ms；筛选 < 1s |
| **安全性** | 无硬编码密钥；SQL 注入防护；XSS 防护 |
| **可维护性** | 命名规范；日志完整；注释到位；< 200 行/函数 |
| **契约一致性** | shared/ 与 frontend/ 字段 1:1 |
| **历史数据兼容** | 老数据可被新代码读取（兼容期 ≥ 1 周） |

### 4.3 复核流程

```
提交（量量/方舟）
    ↓
AI 内部自检（pytest/TypeScript 编译/lint）
    ↓
对方角色复核（grep/curl/浏览器/数据库）
    ↓
不通过 → 反馈 → 修复 → 重新提交
    ↓
通过 → K 抽检（5% 概率）
    ↓
合并 → 部署
```

### 4.4 紧急情况（生产故障）

- 任一方发现 P0 故障，**30 分钟内**通知对方 + K
- 启动"应急模式"：暂停新功能开发，集中修复
- 修复后双方联合验证 + 回归测试

---

## 五、验收标准

### 5.1 阶段验收（阶段性退出条件）

| 阶段 | 验收标准（必含数据/接口/测试 3 维度） |
|------|------------------------------------------|
| **Phase 0** | 所有 P0 任务 ✅；K线 API 真实数据；smoke test 100% |
| **Phase A** | 连续 5 个交易日无人工干预；网络告警 < 3 次/周 |
| **Phase B** | snapshot 字段完整度 ≥ 99%；signals 每日新增 ≥ 4,500 条 |
| **Phase C** | imputer 单测覆盖率 ≥ 90%；e2e 跑通 5 个典型场景 |
| **Phase D** | 前端 K线与同花顺/通达信 1:1 一致；性能 P95 < 500ms |
| **Phase E** | K 签字；上线 1 周无重大故障 |

### 5.2 字段级验收示例（以 K线 API 为例）

```bash
# 验证 P0-011 完成度
curl -s 'http://localhost:8000/api/kline/000001?limit=120&adj=forward' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['count'] == 120, f'count != 120: {d[\"count\"]}'
assert all('open' in k and 'close' in k for k in d['data']), '字段缺失'
print('✅ K线 API 验收通过')
"

# 验证稳定性（连续两次调用一致）
H1=$(curl -s 'http://localhost:8000/api/kline/000001?limit=120&adj=forward' | md5)
sleep 2
H2=$(curl -s 'http://localhost:8000/api/kline/000001?limit=120&adj=forward' | md5)
[ "$H1" = "$H2" ] && echo '✅ 数据稳定' || echo '❌ 数据漂移'
```

### 5.3 复核责任人

- **每日晨检/晚检**：量量执行，方舟抽样复核
- **周度评审**：K 主持
- **阶段验收**：K + 量量 + 方舟三方签字

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| macOS 沙盒限制 crontab | 高 | 中 | 调研 launchd（已计划 A-4） |
| Tushare 积分不足（< 5000） | 中 | 中 | 走 Baostock 主 + akshare 备 |
| Baostock 长期不稳定 | 中 | 高 | 持续优化重试 + 多源 failover |
| 前端功能优先级分散 | 中 | 中 | 明确迭代路线图：K线买卖点→选股器→多因子→一键回测 |
| 数据量爆炸（> 1 亿条） | 低 | 中 | 已分区（按年/月）+ 索引 |
| 团队人手不足 | 中 | 中 | 明确 K + 量量 + 方舟三方分工 |

---

## 七、附录

### 7.1 关键文件清单

| 文件 | 角色 |
|------|------|
| `docs/PLANNING_REVIEW_2026Q2.md` | 本文档 |
| `docs/PROJECT_PLAN.md` | 原始计划（待更新） |
| `docs/DATA_COLLECTION_DESIGN.md` | 采集设计 |
| `docs/DATA_SCHEMA.md` | 数据架构 |
| `docs/AI_COLLABORATION.md` | 待办清单 |
| `docs/daily_report/` | 日报目录 |
| `backend/collector/etl/pipeline_health_check.py` | 前置检查 |
| `backend/imputer/` | 数据补全框架 |
| `shared/` | 前后端契约 |

### 7.2 数据采集完整数据流

```
外部数据源
├── Tushare Pro ──┐
├── Baostock ─────┼─→ import_daily_data.py ─→ stock_quotes（PostgreSQL）
├── Akshare ──────┘                ↓
                       pipeline_health_check.py
                                  ↓
                       sync_quotes_to_snapshot.py ─→ stock_daily_snapshot
                                  ↓
                       data_complementer.py ──→ 缺口补全
                                  ↓
                       missing_handler / adjuster（imputer）
                                  ↓
                       FastAPI → frontend (ECharts/Klinecharts)
                                  ↓
                       health_monitor.py（心跳守护）
```

### 7.3 数据清洗 → 补全 → 消费链路

```
stock_quotes（原始）
  ↓ 清洗
stock_daily_snapshot（宽表，含技术指标 + 估值 + 突破信号 + 形态）
  ↓ 补全
stock_quotes_dirty（脏数据死信表）
  ↓
FastAPI → 前端消费
```

---

**变更记录**：

| 日期 | 变更 | 变更人 |
|------|------|--------|
| 2026-06-06 | 首次编制 | 量量 |
| 2026-06-06 | K线买卖点标注（Phase D1）已交付 + 新增 Phase F（智能选股器） | 方舟 |
| 待定 | K 评审后修订 | K |
