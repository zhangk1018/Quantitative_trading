# 测试模块文档索引

> 本目录存放所有前端测试模块的**辅助说明文档**。**测试用例代码本身**继续位于
> [`quant-trading-frontend/tests/`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests)，
> 命名规范、运行命令、覆盖率等规则不变。
>
> 本目录的 .md 文件与测试代码 1:1 对应，**文件名 = 测试模块名**（去掉 `.test` 后缀）。
>
> **目录位置**：`quant-trading-frontend/docs/tests/`（与 `src/` / `tests/` 平级，便于 IDE 中一并查看）

---

## 文档列表

| 测试模块 | 测试代码 | 文档 | 用例数 | 覆盖率 (L/B/F) |
|---------|---------|------|------:|----------------|
| 指标配置静态校验 | [indicatorConfig.test.ts](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/config/indicatorConfig.test.ts) | [indicatorConfig.md](./indicatorConfig.md) | **17** | 100% / 100% / 100% |
| 选股 Context reducer | [ScreenerContext.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/context/ScreenerContext.test.tsx) | [ScreenerContext.md](./ScreenerContext.md) | **25** | 91.36% / 88.67% / 100% |
| 行情指标筛选组件 | [IndicatorFilter.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/IndicatorFilter.test.tsx) | [IndicatorFilter.md](./IndicatorFilter.md) | **16** | 100% / 82.75% / 100% |
| 财务指标筛选组件 | [FinancialFilter.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/FinancialFilter.test.tsx) | [FinancialFilter.md](./FinancialFilter.md) | **29** | 100% / 91.17% / 100% |
| 技术指标筛选组件 + Modal | [TechnicalFilter.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/TechnicalFilter.test.tsx) | [TechnicalFilter.md](./TechnicalFilter.md) | **27** | 100% / 95% / 100% |
| 条件构建器组件 | [ConditionBuilder.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/components/ConditionBuilder.test.tsx) | [ConditionBuilder.md](./ConditionBuilder.md) | **15** | 100% / 96.29% / 100% |
| 选股视图集成测试 | [StockPickerView.test.tsx](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/views/StockPickerView.test.tsx) | [StockPickerView.md](./StockPickerView.md) | **13** | （视图层，未配置覆盖率） |
| **合计** | | | **142** | **84.27% / 88.29% / 78.42%** |

> 覆盖率数据来源：[`tests/README.md`](file:///Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/tests/README.md) §4.1（v8 provider，行/分支/函数）

---

## 文档约定

每个 `*.md` 文档包含以下章节（按需省略）：

1. **模块职责**：被测源码的职责概述
2. **测试用例清单**：按 `describe` 块组织，每个 `it` 标题 + 一句话说明
3. **关键 mock / helper**：测试中用到的 mock、spy、helper 组件
4. **维护要点**：已知坑点、脆弱点、后续 TODO
5. **变更记录**：K 审阅后补充的测试条目

---

## 与 `tests/README.md` 的关系

- `quant-trading-frontend/tests/README.md` 是**测试运行 / 框架说明**（如何跑、覆盖配置、命名规范）
- `quant-trading-frontend/docs/tests/*.md` 是**单个测试模块的详细说明**（用例清单、维护要点）

两者互补，不重复。

---

## 维护规则

- 每次新增 / 变更测试用例，**同步更新对应 `*.md` 文档**
- K 审阅后新增的边界测试，必须在文档"变更记录"小节注明背景
- 删除用例时同步删除文档条目
