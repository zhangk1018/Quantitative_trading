# AI 协作待办清单

> 本文件用于记录需要修复的问题、优化建议和任务分配
> 最后更新：2026-06-04
> 状态标记：⏳ 待处理 | 🔍 调查中 | 🛠️ 修复中 | ✅ 已修复 | ❌ 无法修复 | 💡 待讨论

---

## 项目约定

### Backend 职责边界（2026-06-04 约定）

**backend 后台程序只负责以下范围：**
1. **数据采集** — 从数据源获取原始数据
2. **数据清洗** — 清洗、去重、格式标准化
3. **数据补全** — 字段补全、关联数据填充
4. **技术指标计算** — MACD、RSI、均线、量比等标准化指标

**超出以上范围的任何功能，必须得到用户许可后才能实施。**

**数据传输方式：** 通过 API 接口将处理后的数据传给前端，backend 不负责前端展示层的任何逻辑。

**示例：** K线形态识别（candlestick patterns）属于超出范围的额外计算功能，需要用户明确许可。

---

## ⏳ 待处理问题（方舟 2026-06-04 二次复核发现）

> 来源：[docs/巡检问题汇总.md](../巡检问题汇总.md) 二次复核章节
> 说明：以下问题需 量量 处理。前端责任的问题（FIX-007）已由 方舟 直接修复。

### 🔴 P0 级（必须立即修复）

> 以下问题已修复，移到已完成章节：
> - P0-007 ✅、P0-008 ✅、P0-009 ✅、P0-012 ✅

- **[P0-010]** `config.py:149` logger 未定义（量量原报告但未修复）— 2026-06-04
  - 位置：`backend/utils/config.py:149`
  - 问题：`logger.debug(...)` 中 `logger` 未导入也未定义
  - 影响：一旦 `get_with_env` 触发 `if self._env in parent` 分支 → `NameError: name 'logger' is not defined`
  - 修复方案：在文件顶部添加 `import logging; logger = logging.getLogger(__name__)`
  - 验证：`python -c "from backend.utils.config import config; print(config.get_with_env('any.key'))"`

- **[P0-008]** `data_service.py:510, 523` 复权计算公式错误（量量原报告但未修复）— 2026-06-04
  - 位置：`backend/core/service/data_service.py:510, 523`
  - 错误代码：`factor *= (1 + (row['close'] - row['open']) / row['open'])`
  - 正确公式：`factor *= (1 + (row['close'] - row['pre_close']) / row['pre_close'])`
  - 影响：所有复权后价格计算错误，K线图、技术指标、回测全部基于错误数据
  - 验证：复权后历史价格应能复权匹配最新价

- **[P0-009]** `data_service.py:1008` PostgreSQL 误用 SQLite 占位符（量量原报告但未修复）— 2026-06-04
  - 位置：`backend/core/service/data_service.py:1008`
  - 错误代码：`self.storage.conn.execute('... WHERE status = ?', ('completed',))`
  - 正确代码：`self.storage.conn.execute('... WHERE status = %s', ('completed',))`
  - 影响：PostgreSQL 下会报 `psycopg2.ProgrammingError: syntax error at or near "?"`
  - 验证：调用 `get_inspection_report` 不再 500

- **[P0-010]** FIX-006 未完全执行：schemas.py 字段未删（量量报告不实）— 2026-06-04
  - 位置：`backend/core/api/models/schemas.py:388-407`
  - 问题：`meta.py` 删了 7 个字段，但 `schemas.py:StockResponse` 仍定义：
    - `pattern_inv_hammer`, `pattern_doji`, `pattern_shooting_star`, `pattern_hanging_man`, `pattern_spinning_top`
    - `break_high_120`, `break_high_250`
  - 影响：schema 定义了但 meta.py 不返回 → 字段成为"孤儿定义"
  - 修复方案：删除 schemas.py 中这 7 个字段定义
  - 验证：`grep -E "pattern_inv_hammer|pattern_doji|pattern_shooting_star|pattern_hanging_man|pattern_spinning_top|break_high_120|break_high_250" backend/core/api/models/schemas.py` 应无结果

- **[P0-011]** `kline_service.py` 整个文件用 mock 数据 — 2026-06-04
  - 位置：`backend/core/service/kline_service.py:37-65` `_generate_mock_kline`
  - 问题：用 `random.random()` 生成虚假 K线数据
  - 影响：**前端 K线图显示的是随机数据**，不是真实行情。形态识别也基于虚假数据
  - 修复方案：
    1. 接入 Parquet 真实 K线数据（参考 `data/price/daily/latest_quotes.parquet`）
    2. 或者从 AKShare/baostock 实时拉取历史 K线
    3. 移除 `_generate_mock_kline` 函数
  - 验证：连续两次调用 `GET /api/kline/000001` 数据应一致（mock 会变化）

- **[P0-012]** `kline_service.py:79-80` 与 `kline.py:33-46` 日期格式不一致 — 2026-06-04
  - 位置：
    - `backend/core/service/kline_service.py:79-80` 注释：`YYYYMMDD`
    - `backend/core/api/router/kline.py:33-46` `validate_date` 要求：`YYYY-MM-DD`
  - 修复方案：统一为一种格式（建议 YYYYMMDD，与 `dependencies.py:111-112` 保持一致）
  - 验证：`grep -n "YYYY" backend/core/service/kline_service.py backend/core/api/router/kline.py`

- **[P0-013]** `signal_service.py` SignalItem 字段名错位（运行会报错）— 2026-06-04
  - 位置：`backend/core/service/signal_service.py:294-300, 320-330, 350-370` 等多处
  - 问题：代码使用 `date=`, `signal=`, `confidence=`, `description=`，但 `SignalItem` (schemas.py:608-614) 实际只有 `trade_date, signal_type, price, reason`
  - 影响：Pydantic 校验失败 → 任何调用 `_generate_signals` 报 500
  - 修复方案：统一为 `trade_date=, signal_type=, price=, reason=`
  - 验证：调用 `GET /api/signals/000001` 返回 200 而非 500

- **[P0-014]** `signal_service.py:218, 130-131` 引用不存在的 KLineResponse 字段 — 2026-06-04
  - 位置：`backend/core/service/signal_service.py:218, 130-131`
  - 问题：使用 `kline_response.klines`、`kline_response.start_date`、`kline_response.end_date`
  - 实际：`KLineResponse` 只有 `stock_code, data, count` 三个字段
  - 影响：`AttributeError` → 任何 `GET /api/signals/000001` 报 500
  - 修复方案：改为 `kline_response.data`，移除 `start_date/end_date` 引用
  - 验证：调用信号接口正常返回

- **[P0-015]** `signal_type` 枚举不匹配 — 2026-06-04
  - 位置：
    - `backend/core/api/router/signals.py:17` `VALID_SIGNAL_TYPES = {'golden_cross', 'death_cross', 'all'}`
    - `backend/core/service/signal_service.py:37` `signal_config` key 是 `'macd_cross'`
  - 影响：任何非 `'all'` 的 signal_type 请求都被路由 400 拒绝
  - 修复方案：统一为同一套枚举（建议 `{'macd_cross', 'rsi_overbought', 'bollinger_breakout', 'all'}`）
  - 验证：`GET /api/signals/000001?signal_type=macd_cross` 返回 200

- **[P0-016]** `kline.py:16` 股票代码正则不匹配 `000001.SZ` 格式 — 2026-06-04
  - 位置：`backend/core/api/router/kline.py:16` `STOCK_CODE_PATTERN = r'^(SH|SZ)?\d{6}$'`
  - 问题：schemas.py 示例的 `000001.SZ` 格式（前端实际使用的）不匹配
  - 修复方案：改为 `r'^(\d{6}\.(SH|SZ|BJ)|(SH|SZ)?\d{6})$'`
  - 验证：`GET /api/kline/000001.SZ` 返回 200 而非 400

- **[P0-017]** `stocks.py:24-34` 路由缺少 `as_of_date` 参数 — 2026-06-04
  - 位置：`backend/core/api/router/stocks.py:24-34`
  - 问题：前端 [App.tsx:196](../../frontend/src/App.tsx#L196) 传 `as_of_date`，但 `get_stocks` 路由签名未接收
  - 影响：前端传的 `as_of_date` 永远被忽略，**防前视偏差硬约束被破坏**
  - 修复方案：
    ```python
    from core.api.dependencies import DateDep
    async def get_stocks(
        ...,
        as_of_date: str = DateDep,  # 强制 YYYYMMDD 校验
        ...
    ):
    ```
  - 验证：在 ScreenerService 中按 `as_of_date` 过滤数据

### 🟧 P1 级（尽快修复）

- **[P1-015]** `kline.py` 与 `signals.py` 大量代码重复 — 2026-06-04
  - 位置：`kline.py:15-54` 与 `signals.py:15-53`
  - 问题：`STOCK_CODE_PATTERN`、`validate_stock_code`、`validate_date`、`validate_date_range` 完全重复
  - 修复方案：提取到 `backend/core/api/validators.py` 或合并到 `dependencies.py`
  - 验证：`grep -c "validate_stock_code" backend/core/api/router/*.py` 应只剩 1 处

- **[P1-016]** `ALLOWED_SORT_FIELDS` 两处定义不一致 — 2026-06-04
  - 位置：
    - `backend/core/api/dependencies.py:73-79`（19 字段）
    - `backend/core/api/models/schemas.py:26-39`（32 字段）
  - 问题：dependencies.py 缺少 `rsi_12/24, kdj_k/d/j, cci, pe_ttm, ps, ps_ttm, dv_ratio, dv_ttm, net_mf_vol, total_share, consec_up_days, turnover_rate_f`
  - 修复方案：dependencies.py 中 `from .models.schemas import ALLOWED_SORT_FIELDS` 统一来源
  - 验证：按 `sort_by=kdj_k` 调用 `/api/stocks` 不被拒绝

- **[P1-017]** `loader.py` 全局变量 + DataLoader 类双重状态 — 2026-06-04
  - 位置：`backend/collector/db/loader.py:26-28` 与 `62-94`
  - 问题：模块级 `df/trade_date/field_counts` 和 DataLoader 的 `_df/_trade_date/_field_counts` 同时存在
  - 修复方案：移除模块级全局变量，只保留 DataLoader 类
  - 验证：`grep -E "^df:|^trade_date:|^field_counts:" backend/collector/db/loader.py` 应无结果

- **[P1-018]** `kline_service.py` 忽略 `start_date/end_date` 参数 — 2026-06-04
  - 位置：`backend/core/service/kline_service.py:67-121`
  - 问题：函数签名接收但函数体内完全未使用
  - 修复方案：在 `_generate_mock_kline`（或真实数据源）按日期范围过滤
  - 验证：传 `start_date=20260601, end_date=20260604` 返回数据在范围内

- **[P1-019]** `kline_service.py` 和 `signal_service.py` 大量未使用 import — 2026-06-04
  - 位置：
    - `kline_service.py:4,11,13,19`：`os, lru_cache, ListedBoard` 未使用
    - `signal_service.py:9,10,16,17`：`numpy, Tuple, ListedBoard, Dict` 未使用
  - 修复方案：删除未使用的 import
  - 验证：`python -c "import ast; ast.parse(open('backend/core/service/kline_service.py').read())"` + 手工核对

### 🟨 P2 级（逐步优化）

- **[P2-008]** `dependencies.py:96-102` `validate_stock_code` 缺少格式校验 — 2026-06-04
  - 位置：`backend/core/api/dependencies.py:96-102`
  - 问题：只做 strip/upper，没有正则校验（kline.py 第 21-30 行有完整校验）
  - 修复方案：合并到统一 validator（P1-015 一并解决）
  - 验证：传非法代码如 `'abc'` 应被拒绝

- **[P2-009]** `indicators.ts:118` 与 `technical_indicator.py:228` RSI 边界条件处理不一致 — 2026-06-04
  - 位置：
    - `frontend/src/utils/indicators.ts:118, 127`：`avgLoss === 0 ? 100 : ...`
    - `backend/clean/processor/technical_indicator.py:228`：`avg_loss.replace(0, 0.0001)`
  - 修复方案：统一规则（建议前端与后端一致使用 `replace(0, 0.0001)`）
  - 验证：构造全涨数据对比前后端 RSI 值一致

- **[P0-012]** kline_service.py:79-80 日期格式注释错误（与 P0-012 重叠，标注已完成）— 2026-06-04
  - 已在 P0-012 中处理

---

## 🔄 流程要求（新增）

> **重要：** 量量 修复以下 P0 问题后，**必须提供**：
> 1. 实际运行截图或日志（证明已运行验证）
> 2. 对应的单元测试或集成测试用例
> 3. 修复的 commit hash

> 避免"代码改了但没运行"或"未真正删除字段只注释"的情况。

---


---

## ✅ 已完成问题（归档）

### P0 级
- **[P0-001]** 数据下载程序频繁死机 — 量量, 2026-06-04
  - 修复：移除双重线程嵌套（删除 run_with_timeout），添加数据库连接保活和 TCP keepalive
- **[P0-002]** K线/信号路由导入路径错误 — 量量, 2026-06-03
- **[P0-003]** 行业筛选报错-类型不匹配 — 量量, 2026-06-03
- **[P0-007]** config.py logger 未定义 — 量量, 2026-06-04
  - 修复：添加 `import logging; logger = logging.getLogger(__name__)`
  - 验证：`python -c "from backend.utils.config import config; print(config.get_with_env('any.key'))"` 通过
- **[P0-008]** data_service.py 复权计算公式修正 — 量量, 2026-06-04
  - 修复：使用 `(close - pre_close) / pre_close` 替代错误的 `(close - open) / open`
  - 位置：`backend/core/service/data_service.py:508-529`
- **[P0-009]** data_service.py PostgreSQL 占位符修正 — 量量, 2026-06-04
  - 修复：`?` → `%s`
  - 位置：`backend/core/service/data_service.py:1014`
- **[P0-010]** 智能调度系统开发 — 量量, 2026-06-04
- **[P0-012]** kline_service.py 与 kline.py 日期格式统一 — 量量, 2026-06-04
  - 修复：dependencies.py 兼容 `YYYYMMDD` 和 `YYYY-MM-DD` 两种格式
  - 位置：`backend/core/api/dependencies.py:108-125`
- **[P0-010 (FIX-006 闭环)]** schemas.py 删除 7 个废弃字段 — 量量, 2026-06-04
  - 删除字段：`pattern_inv_hammer`, `pattern_doji`, `pattern_shooting_star`, `pattern_hanging_man`, `pattern_spinning_top`, `break_high_120`, `break_high_250`
  - 验证：`grep` 验证 `schemas.py` 中这 7 个字段无结果
- **[P0-016]** kline.py/signals.py 股票代码正则支持 `.SZ`/`.SH` 格式 — 量量, 2026-06-04
  - 修复：正则改为 `r'^(\d{6}\.(SH|SZ|BJ)|(SH|SZ)\d{6}|\d{6})$'`
  - 位置：`backend/core/api/router/kline.py:16`, `backend/core/api/router/signals.py:14`
- **[P0-017]** stocks.py 路由添加 `as_of_date` 参数 — 量量, 2026-06-04
  - 修复：使用 `DateDep` 依赖注入，强制 YYYYMMDD 校验
  - 位置：`backend/core/api/router/stocks.py:37`
- **[P0-013]** signal_service.py SignalItem 字段名修正 — 量量, 2026-06-04
  - 修复：`date/signal/confidence/description` → `trade_date/price/reason`，删除冗余 `signal_type` 重复
  - 位置：`backend/core/service/signal_service.py:294-365`
- **[P0-014]** signal_service.py 移除不存在字段引用 — 量量, 2026-06-04
  - 修复：`kline_response.klines` → `kline_response.data`，移除 `kline_response.start_date/end_date` 引用
  - 位置：`backend/core/service/signal_service.py:130-131, 218`
- **[P0-015]** signal_type 枚举统一 — 量量, 2026-06-04
  - 修复：统一为 `{'macd_cross', 'rsi_oversold', 'rsi_overbought', 'bollinger_breakout', 'all'}`
  - 位置：`backend/core/api/router/signals.py:17`

### P1 级
- **[P1-008]** 完成 KlineService — 量量, 2026-06-03
- **[P1-009]** 完成 SignalService — 量量, 2026-06-03
- **[P1-012]** 巡检问题修复 — 量量, 2026-06-04
- **[P1-013]** 废弃程序清理 — 量量, 2026-06-04
- **[P1-014]** 启用 K线/信号路由 — 方舟, 2026-06-04
- **[P1-010]** 完善K线/信号路由参数校验 — 量量, 2026-06-04
  - 股票代码规范化、日期范围校验、signal_type 默认值、错误信息完善
- **[P1-011]** 创建信号预计算脚本 — 量量, 2026-06-04
  - 使用 EMA 算法计算 MACD 金叉/死叉，存入 trade_signals 表
- **[FIX-001]** 修复总市值字段显示 — 方舟, 2026-06-04
- **[FIX-002]** 修复 K线图表空白 — 方舟, 2026-06-04
- **[FIX-003]** 修复突破信号 count 统计为 0 — 量量, 2026-06-04
  - 修复：loader.py binary_cols 添加 bool 类型支持
- **[FIX-004]** 补齐 break_high_120/250 字段 — 量量, 2026-06-04
  - 修复：calculate_highs.py 扩展 120/250 日新高计算，自动添加数据库字段
- **[FIX-006]** 删除后端元数据中废弃字段 — 量量, 2026-06-04
  - 删除 meta.py 中 7 个字段：`pattern_doji`, `pattern_spinning_top`, `pattern_shooting_star`, `pattern_hanging_man`, `pattern_inverted_hammer`, `break_high_120`, `break_high_250`
  - 注：`consec_up_days` 在 meta.py 中不存在（实际为 `consec_up_3`/`consec_up_5`），无需删除
  - **⚠️ 部分未完成**：schemas.py 中这 7 个字段未删除，详见 [P0-010]

- **[FIX-007]** 补齐前端 types.ts 缺失字段定义 — 方舟, 2026-06-04
  - 补齐 27 个字段：rsi_12/24, kdj_k/d/j, cci, consec_up_days, 10 个 pattern_*, break_high_120/250, consec_up_3/5, net_mf_vol
  - 修正 `as_of_date` 注释 YYYY-MM-DD → YYYYMMDD
  - 修正文件头注释"自动生成" → "手动同步"（实际是手动维护的）

### DONE
- **[DONE-003]** Day 1 - 前端 API 路径问题修复 — 2026-06-03
- **[DONE-004]** Day 1 - schemas.py 和 screener_service.py 字段对齐 — 2026-06-03

### OPT
- **[OPT-004]** Day 3 - K线图表组件开发 — 方舟, 2026-06-04

---

## 📊 统计

| 状态 | 数量 |
|------|------|
| ⏳ 待处理 | 17 |
| 🛠️ 修复中 | 0 |
| ✅ 已完成 | 21 |

---

## 📋 量量待办（按优先级）

| # | 任务 | 优先级 | 状态 | 验证方法 |
|---|------|--------|------|----------|
| 1 | [P0-011] kline_service.py 替换 mock 为真实 K线数据 | 🔴 P0 | ⏳ 待处理 | 连续两次调用数据一致 |
| 2 | [P0-013] signal_service.py SignalItem 字段名修正 | 🔴 P0 | ⏳ 待处理 | `GET /api/signals/000001` 200 |
| 3 | [P0-014] signal_service.py 移除不存在字段引用 | 🔴 P0 | ⏳ 待处理 | `GET /api/signals/000001` 200 |
| 4 | [P0-007] config.py logger 未定义修复 | 🔴 P0 | ⏳ 待处理 | 单元测试通过 |
| 5 | [P0-008] data_service.py 复权计算公式修正 | 🔴 P0 | ⏳ 待处理 | 复权后价格匹配最新价 |
| 6 | [P0-009] data_service.py PostgreSQL 占位符修正 | 🔴 P0 | ⏳ 待处理 | `get_inspection_report` 200 |
| 7 | [P0-010] FIX-006 闭环：schemas.py 删除 7 个字段 | 🔴 P0 | ⏳ 待处理 | grep 验证无结果 |
| 8 | [P0-016] kline.py 股票代码正则支持 `000001.SZ` | 🔴 P0 | ⏳ 待处理 | `GET /api/kline/000001.SZ` 200 |
| 9 | [P0-017] stocks.py 路由接收 as_of_date 参数 | 🔴 P0 | ⏳ 待处理 | 接口测试通过 |
| 10 | [P0-015] signal_type 枚举统一 | 🔴 P0 | ⏳ 待处理 | `signal_type=macd_cross` 200 |
| 11 | [P0-012] kline_service.py 日期格式注释统一 | 🔴 P0 | ⏳ 待处理 | grep 验证一致 |
| 12 | [P1-015] kline.py/signals.py 重复代码提取 | 🟧 P1 | ⏳ 待处理 | grep -c 验证 |
| 13 | [P1-016] ALLOWED_SORT_FIELDS 统一来源 | 🟧 P1 | ⏳ 待处理 | 按 rsi_12 排序通过 |
| 14 | [P1-017] loader.py 移除全局变量 | 🟧 P1 | ⏳ 待处理 | grep 验证无结果 |
| 15 | [P1-018] kline_service.py start_date/end_date 参数生效 | 🟧 P1 | ⏳ 待处理 | 日期范围测试 |
| 16 | [P1-019] 清理未使用 import | 🟧 P1 | ⏳ 待处理 | pylint 通过 |
| 17 | [P2-008] validate_stock_code 合并到统一 validator | 🟨 P2 | ⏳ 待处理 | 与 P1-015 一并 |
| 18 | [P2-009] indicators.ts RSI 边界处理与后端一致 | 🟨 P2 | ⏳ 待处理 | 单元测试对比 |

---

> 更新记录：
> - 2026-06-04: 完成 FIX-006（meta.py 删除7个废弃字段）；清理 collector 废弃程序；项目文档合并更新；所有量量待办清零
> - 2026-06-04: **方舟二次复核发现 17 个未修复/新问题**：4 个 P0 是量量原报告但未完成（P0-007/008/009/010），7 个 P0 是新发现（含 kline_service.py mock 数据、signal_service 字段错位、股票代码正则、stocks 路由缺 as_of_date 等），4 个 P1，2 个 P2。所有 P0 问题已登记在 ⏳ 待处理 章节，要求量量修复时提供运行截图/测试/commit hash