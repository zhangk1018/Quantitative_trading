# Phase 5.3 上线验收清单

**版本**: v1.0
**日期**: 2026-06-17
**执行人**: 方舟（Fangzhou）
**前置条件**: `docker compose --env-file .env.production up -d` 已执行，服务运行中

---

## 一、验收方式

### 方式 A（全自动，推荐）
```bash
chmod +x verify_prod.sh
./verify_prod.sh
```
脚本会自动完成所有检查项并输出 PASS/FAIL/WARN，5 分钟内完成。

### 方式 B（手动逐项验证）
按以下清单逐项验证，适合首次部署时熟悉流程。

---

## 二、检查项清单

### 2.1 容器健康（手动）
```bash
docker compose -f docker-compose.yml ps
```
**预期**：
- `postgres` 状态 `healthy`
- `backend` 状态 `healthy`（启动后约 60s 变为 healthy）

---

### 2.2 API 端点（手动 curl）
在浏览器或终端执行：

| # | 检查命令 | 预期响应 |
|---|----------|----------|
| 1 | `curl -s http://localhost:8000/health` | `{"status":"ok"}` |
| 2 | `curl -s http://localhost:8000/api/meta/` | JSON 含 `stock_count` 字段 |
| 3 | `curl -s http://localhost:8000/api/stocks/` | JSON 含 `items` 数组 |
| 4 | `curl -s http://localhost:8000/api/kline/000001.SZ?period=daily` | JSON 含 `macd/diff/dea/rsi_12/rsi_24` 字段 |

**特别关注**：K 线 API 第 4 项返回的 `diff`、`dea`、`rsi_12`、`rsi_24` 字段是否**有值不为 NULL**（协作单 [6.8] 修复验证）。

---

### 2.3 数据库（手动）
```bash
docker compose exec postgres psql -U quant_user -d quant_trading -c \
  "SELECT COUNT(*) FROM stock_indicators;"
```
**预期**：`count > 0`（指标数据已入库）

---

### 2.4 资源配额（自动验证脚本已覆盖）
- PostgreSQL 内存限制 2G
- Backend CPU 配额 0.5~2核，内存 1G
- 可用 `docker stats` 查看实际使用

---

### 2.5 日志错误扫描（自动验证脚本已覆盖）
```bash
docker compose logs --tail=100 backend
```
**预期**：无 ERROR 级别日志

---

## 三、Phase 5.2 性能优化验收

| 优化项 | 验证方式 | 预期 |
|--------|----------|------|
| Worker 自动调优 | `docker exec quant-backend ps aux \| grep uvicorn \| wc -l` | workers 数量 ≈ CPU核×2+1 |
| 连接池初始化 | `docker logs quant-backend \| grep "db_pool"` | 启动日志含 `[db_pool] 连接池已初始化` |
| PG 参数生效 | `docker compose exec postgres psql -U quant_user -c "SHOW shared_buffers;"` | `512MB` |

---

## 四、验收结论

**PASS 条件**：
- 2.2 中全部 4 个 API 返回 HTTP 200 且数据有效
- 2.3 中 stock_indicators 有数据
- 2.5 日志无 ERROR

请在下方记录验收结果并签字：

- [ ] **验收通过** — 签名：______  日期：______
- [ ] **有异议** — 问题描述：____________________
