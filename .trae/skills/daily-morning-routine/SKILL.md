---
name: "daily-morning-routine"
description: "每日数据管道晨检：运行自动化晨检脚本 + 检查协作单待办。每天第一件事调用。"
---

# 每日数据管道晨检

在开始当天任务前执行此晨检流程。目标是通过自动化脚本快速确认数据管道健康状况，并检查协作单待办。

## 检查流程

### 阶段 1: 运行自动化晨检脚本

先执行自动化脚本，快速完成 9 项标准化检查：

```bash
cd /Users/zhangk/workspace/Quantitative_trading
venv/bin/python backend/scripts/daily_check.py --no-color
```

该脚本会自动执行以下检查并输出结果：

| 分类 | 检查项 | 说明 |
|------|--------|------|
| 基础设施 | PostgreSQL 服务状态 | pg_isready 检查进程 |
| 基础设施 | 数据库连接 | 数据库连接测试 |
| 数据下载 | 行情数据新鲜度 | 最新交易日距今是否超过阈值 |
| 数据下载 | 行情数据量 | 每日数据量是否 ≥4500 条 |
| 数据下载 | 缺失股票数 | 最新交易日缺失股票数 |
| 宽表同步 | 宽表同步状态 | stock_daily_snapshot 同步 |
| 数据补全 | 字段完整性 | 关键字段填充率 |
| 任务日志 | 任务执行日志 | 最近是否有失败任务 |
| 日志文件 | 日志文件错误 | 日志错误计数 |

**退出码含义**：
- `0` — 全部通过 ✅
- `1` — 存在警告项 ⚠️（需关注，但不阻塞）
- `2` — 存在失败项 🚨（需人工介入）

**告警触发条件**：
- 退出码 `2`：立即通知 K，标记为异常
- 数据库连接失败：检查 PostgreSQL 服务状态，尝试重启
- 数据新鲜度异常：检查最新交易日，若为工作日且数据缺失，尝试手动触发增量导入

#### 保存报告到文件（可选）

```bash
venv/bin/python backend/scripts/daily_check.py --output /tmp/daily_check_report.json
```

查看 JSON 报告可直接读取 `/tmp/daily_check_report.json`，包含每个检查项的详细结果和汇总信息。

#### 跳过特定检查项

```bash
venv/bin/python backend/scripts/daily_check.py --skip log_file_errors
```

### 阶段 2: 检查协作单待办

查看以下两个文件的待办任务：

1. **[docs/协作单.md](file:///Users/zhangk/workspace/Quantitative_trading/docs/协作单.md)** — 活动工单区：
   - 查找状态为 `NEW`（待认领）或 `REOPENED`（需重新处理）的工单
   - 优先认领属于量量职责范围（backend）的 `NEW` 工单
   - 优先跟进自己上次处理的 `REOPENED` 工单
   - 关注 P0（紧急）任务

2. **[.trae/topics.md](file:///Users/zhangk/workspace/Quantitative_trading/.trae/topics.md)** — 跨会话通知：
   - 读取最新通知，确认是否有新的状态变更需要响应
   - 特别关注 `→量量` 标记的通知（明确由量量接单）

## 报告格式

向用户输出以下格式的晨检报告：

```markdown
## 每日数据管道晨检报告 (YYYY-MM-DD)

### 自动化晨检结果
- 基础设施: ✅/⚠️/🚨 PostgreSQL / 数据库连接
- 数据下载: ✅/⚠️/🚨 最新交易日 XXXX-XX-XX, 共 XXXX 条
- 缺失股票数: XX 只
- 宽表同步: ✅/⚠️/🚨 最新: XXXX-XX-XX
- 数据补全: ✅/⚠️ 字段完整率
- 任务日志: ✅/⚠️/🚨 最近失败任务: X
- 退出码: 0 / 1 / 2

### 待办任务
- 协作单活动工单: X 个（NEW: X, REOPENED: X, VERIFY: X）
- P0 任务: X 个 | P1 任务: X 个
- topics.md 新通知: X 条需响应
- 新/变化的重要事项: ...
```

## 异常处理

当自动化脚本退出码为 `2` 时：
1. 读取脚本输出的 JSON 报告，定位具体的失败项
2. 根据失败项类型执行对应操作：
   - **数据库连接失败**：检查 PostgreSQL 服务状态，尝试 `pg_ctl -D /usr/local/var/postgresql@18 start`
   - **数据下载异常**：尝试手动触发增量导入：
     ```bash
     cd /Users/zhangk/workspace/Quantitative_trading && \
     PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/collector/etl/import_daily_data.py --incremental
     ```
   - **宽表同步异常**：尝试手动触发宽表同步：
     ```bash
     cd /Users/zhangk/workspace/Quantitative_trading && \
     PG_PASSWORD=$PG_PASSWORD venv/bin/python backend/collector/etl/daily_snapshot_sync.py --latest
     ```
   - **任务执行失败**：查看 `task_run_log` 表的具体失败任务和错误信息
3. **待办任务阻塞**：协作单中有 P0 未处理时，优先处理或提醒用户

## 注意

- 自动化脚本已覆盖所有数据管道检查项，无需再手动编写 SQL 查询
- 脚本依赖 `psycopg2` 和项目 `.env` 文件中的数据库配置
- 脚本退出码是判断晨检结果的主要依据，需在报告中明确标注
- 测试报告：`docs/daily_check_test_report.json`（17/17 通过）