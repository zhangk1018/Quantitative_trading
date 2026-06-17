# Phase 5.3 上线验收清单

**版本**: v1.1（2026-06-17 强化：新增 Docker daemon 前置检查 + sleep 15 复检步骤）
**日期**: 2026-06-17
**执行人**: 方舟（Fangzhou）
**前置条件**: `docker compose --env-file .env.production up -d` 已执行，服务运行中

> **v1.1 变更说明**（防止协作单 [6.11] 复现）：Phase 5 部署 commit `5f6ab5e` 时未启动 Docker Desktop，导致 `./start_prod.sh` 静默失败。v1.1 新增 0. Docker daemon 前置检查、2.1 sleep 15 复检、2.6 .env.production 占位符扫描三道防线。

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

### 0. Docker daemon 前置检查（**v1.1 新增**）
```bash
docker info >/dev/null 2>&1 && echo "✅ Docker daemon running" || echo "❌ Docker daemon NOT running"
```
**预期**：✅ Docker daemon running
**异常处理**：若 daemon 未运行 → `open -a Docker` 启动 Docker Desktop → 轮询 `docker info` 至就绪（通常 30-60s）→ 重新执行 start_prod.sh

### 0.1 .env.production 占位符扫描（**v1.1 新增**）
```bash
grep -E "^\s*[A-Z_]+=.*CHANGE_ME" .env.production && echo "❌ 仍有 CHANGE_ME 占位符" || echo "✅ 无占位符"
```
**预期**：✅ 无占位符
**异常处理**：若存在 → 替换为 `openssl rand -base64 32` 强密码

---

### 2.1 容器健康（手动）— **v1.1 强化：增加 sleep 15 复检**
```bash
# 第 1 轮（启动后立即）
docker compose -f docker-compose.yml ps

# ⚠️ v1.1 关键：Uvicorn workers 启动需要时间，首次 health: starting 属正常
sleep 15

# 第 2 轮（sleep 15 后复检）
docker compose -f docker-compose.yml ps
```
**预期**：
- `postgres` 状态 `healthy`
- `backend` 状态 `healthy`（**v1.1 关键**：启动后约 60s 变为 healthy；首次 health: starting 属正常，需 sleep 15 复检）

---

### 2.2 API 端点（手动 curl）— **v1.1 强化：Nginx 502 时绕过直连验证**
在浏览器或终端执行：

| # | 检查命令 | 预期响应 |
|---|----------|----------|
| 1 | `curl -s http://localhost:8000/health` | `{"status":"ok"}` |
| 2 | `curl -s http://localhost:8000/api/meta/` | JSON 含 `stock_count` 字段 |
| 3 | `curl -s http://localhost:8000/api/stocks/` | JSON 含 `items` 数组 |
| 4 | `curl -s http://localhost:8000/api/kline/000001.SZ?period=daily` | JSON 含 `macd/diff/dea/rsi_12/rsi_24` 字段 |
| 5 | `curl -s http://localhost/nginx-health` | Nginx 200 |
| 6 | `curl -s http://localhost/api/stocks/?limit=2` | Nginx → backend 200 |

**特别关注**：K 线 API 第 4 项返回的 `diff`、`dea`、`rsi_12`、`rsi_24` 字段是否**有值不为 NULL**（协作单 [6.8] 修复验证）。

**v1.1 关键经验**（防止协作单 [6.11] 误判）：Nginx 报 502 时，绕过 Nginx 直接 curl `:8000` 是真实后端状态指标——Nginx upstream 在 workers 启动期间会持续 502，但后端 /health 200 才是真实的"后端就绪"信号。

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

**PASS 条件**（**v1.1 强化**）：
- 0. Docker daemon running ✅
- 0.1 .env.production 无 CHANGE_ME 占位符 ✅
- 2.1 容器 healthy（**含 sleep 15 复检**）
- 2.2 中全部 6 个 API 返回 HTTP 200 且数据有效（**含绕过 Nginx 直连验证**）
- 2.3 中 stock_indicators 有数据
- 2.5 日志无 ERROR

请在下方记录验收结果并签字：

- [ ] **验收通过** — 签名：______  日期：______
- [ ] **有异议** — 问题描述：____________________

---

## 五、变更记录

| 版本 | 日期 | 变更内容 | 触发原因 |
|------|------|----------|----------|
| v1.0 | 2026-06-10 | 初版（量量） | Phase 5 上线 |
| v1.1 | 2026-06-17 | + 0. Docker daemon 前置检查 + 0.1 占位符扫描 + 2.1 sleep 15 复检 + 2.2 直连绕过 + PASS 条件扩展 | 协作单 [6.11] Phase 5 部署时未启动 Docker Desktop 导致 500 错误 |
