# 部署文档（Phase 5.1.a）

> 量化交易系统生产环境部署指南
>
> 创建日期：2026-06-10
>
> 适用范围：Docker + Docker Compose 部署（Linux/macOS/Windows WSL2）

## 📋 目录

- [架构概览](#架构概览)
- [前置要求](#前置要求)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [日常运维](#日常运维)
- [性能调优](#性能调优)
- [故障排查](#故障排查)
- [升级与回滚](#升级与回滚)
- [生产化清单](#生产化清单)

---

## 🏗️ 架构概览

```
┌──────────────────────────────────────────────────────────────┐
│                    用户浏览器 (HTTPS)                         │
└────────────────────────┬─────────────────────────────────────┘
                         │
                  ┌──────▼───────┐
                  │   Nginx 80   │ (Docker: frontend 容器)
                  │  - 静态前端  │
                  │  - /api 反代 │
                  │  - /admin    │
                  └──────┬───────┘
                         │
                ┌────────┴────────┐
                │                 │
        ┌───────▼──────┐  ┌──────▼──────┐
        │ FastAPI 8000 │  │ PostgreSQL  │
        │ (4 workers)  │  │   16-alpine │
        │  (backend)   │◄─┤  (postgres) │
        └───────┬──────┘  └─────────────┘
                │
        ┌───────▼──────┐
        │ Redis 7      │ (缓存/任务队列)
        │   (redis)    │
        └──────────────┘
```

**关键设计**：
- 单机部署（4 服务 + 1 网络 + 3 持久化卷）
- 资源限制：后端 2CPU/4GB，PostgreSQL 1CPU/2GB，Redis 0.5CPU/320MB，Nginx 0.5CPU/256MB
- 数据持久化：3 个 named volumes（postgres_data / redis_data / backend_data）

---

## ✅ 前置要求

| 组件 | 版本 | 用途 |
|------|------|------|
| Docker | ≥ 24.0 | 容器运行时 |
| Docker Compose | ≥ 2.20 | 容器编排（Docker Desktop 自带） |
| 操作系统 | Linux / macOS 12+ / WSL2 | 推荐 Ubuntu 22.04 LTS |
| 磁盘 | ≥ 50GB 可用 | 数据库 + 镜像 + 日志 |
| 内存 | ≥ 8GB | 推荐 16GB（多 worker 并发） |
| CPU | ≥ 4 核 | 推荐 8 核 |

**健康检查**：
```bash
docker --version        # Docker version 24.0.0+
docker compose version  # Docker Compose version v2.20.0+
docker info             # Server Version / Storage Driver / ...
```

---

## 🚀 快速开始

### 1. 克隆代码（生产环境首次部署）

```bash
git clone <repo-url> quant-trading
cd quant-trading
```

### 2. 配置环境变量

```bash
# 复制模板
cp .env.production.example .env.production

# 生成强密码
echo "PG_PASSWORD=$(openssl rand -base64 32)" >> .env.production.new
echo "PGADMIN_PASSWORD=$(openssl rand -base64 24)" >> .env.production.new

# 编辑配置
vim .env.production
```

**必填项**：
- `PG_PASSWORD`：PostgreSQL 主密码
- `PGADMIN_PASSWORD`：pgAdmin 密码（可选）
- `TUSHARE_TOKEN`：Tushare 数据源 token（如使用）

### 3. 启动

```bash
# 构建镜像（首次需要 5-10 分钟）
./start_prod.sh build

# 启动所有服务
./start_prod.sh start

# 查看状态
./start_prod.sh status

# 详细健康检查
./start_prod.sh health
```

### 4. 验证

```bash
# Nginx 健康
curl http://localhost/nginx-health
# → ok

# 后端健康
curl http://localhost/health
# → {"status":"ok","version":"1.0.0",...}

# 前端首页
curl -I http://localhost/
# → 200 OK, content-type: text/html

# API 测试
curl http://localhost/api/meta/
# → {"code":200,"data":{"trade_date":"20260608","total":5515}}
```

### 5. 访问

| 地址 | 说明 |
|------|------|
| `http://localhost/` | 前端首页（选股视图） |
| `http://localhost/admin` | 管理后台（监控看板） |
| `http://localhost/api/...` | API 端点 |
| `http://localhost:5050` | pgAdmin（debug profile 启动） |

---

## ⚙️ 配置说明

### `.env.production`

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PG_HOST` | postgres | 容器内数据库地址（生产环境不要改成 localhost） |
| `PG_PORT` | 5432 | 数据库端口 |
| `PG_DATABASE` | quant_trading | 数据库名 |
| `PG_USER` | quant_user | 数据库用户 |
| `PG_PASSWORD` | （必填） | 数据库密码 |
| `TUSHARE_TOKEN` | 空 | Tushare 数据源 token |
| `HTTP_PORT` | 80 | Nginx 对外端口（生产建议改 443） |
| `LOG_LEVEL` | info | 日志级别（debug/info/warning/error） |
| `CORS_ORIGINS` | http://localhost | 允许的跨域来源（逗号分隔） |

### docker-compose.yml 服务

| 服务 | 端口 | 资源限制 | 健康检查 |
|------|------|----------|----------|
| postgres | 5432（仅内部） | 2GB / 1.0 CPU | pg_isready |
| backend | 8000（仅内部） | 4GB / 2.0 CPU | /health |
| redis | 6379（仅内部） | 320MB / 0.5 CPU | PING |
| frontend | 80 → 宿主 | 256MB / 0.5 CPU | / |
| pgadmin | 5050 → 宿主（debug） | - | - |

### Nginx 反代

`/api/`、`/static/`、`/admin` 三个前缀都反代到 `backend:8000`。

**为什么用单一 Nginx 而不是每个服务独立端口？**
- 统一对外端口（80/443）→ 简化防火墙规则
- 统一 TLS/SSL 证书管理
- 集中处理 gzip / cache / 安全头
- 静态资源由 Nginx 直接服务（不打到后端）

---

## 🛠️ 日常运维

### 查看状态

```bash
./start_prod.sh status
```

输出示例：
```
SERVICE          STATE    PORTS
quant-postgres   running  5432/tcp
quant-backend    running  8000/tcp
quant-redis      running  6379/tcp
quant-frontend   running  0.0.0.0:80->80/tcp
```

### 查看日志

```bash
# 全部服务（最近 100 行 + 实时）
./start_prod.sh logs

# 指定服务
./start_prod.sh logs backend
./start_prod.sh logs frontend
./start_prod.sh logs postgres
```

### 进入数据库

```bash
./start_prod.sh psql
# 相当于：docker compose exec postgres psql -U quant_user -d quant_trading
```

常用 SQL：
```sql
-- 查看最新数据
SELECT trade_date, COUNT(*) FROM stock_quotes WHERE cycle='1d' GROUP BY trade_date ORDER BY trade_date DESC LIMIT 5;

-- 查看表大小
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;

-- 查看活动连接
SELECT count(*) FROM pg_stat_activity;
```

### 进入容器 Shell

```bash
# 后端容器
./start_prod.sh shell backend
# 容器内
which python && python --version
ls /app/backend/
cat /app/logs/*.log 2>/dev/null | tail -20
exit

# 数据库容器
./start_prod.sh shell postgres
```

### 详细健康检查

```bash
./start_prod.sh health
```

输出包含：
1. 容器状态（4 个服务）
2. API 健康（4 个端点：nginx-health / health / api/meta/ / api/stocks/）
3. 数据库连接
4. 资源使用（CPU/内存/网络）

---

## 🔧 性能调优

### 后端 Worker 数量

`Dockerfile.backend` 默认 4 worker，可按 CPU 核数调整：

```bash
# 启动时覆盖（修改 Dockerfile CMD 或 docker-compose.yml）
CMD ["uvicorn", "...", "--workers", "8"]
```

**经验公式**：`workers = 2 * CPU_cores + 1`

### PostgreSQL 配置

默认参数适合 2-8GB 数据。生产大数据量（> 100GB）需调整：

```bash
# docker/postgres/init/01-tuning.sql
ALTER SYSTEM SET shared_buffers = '2GB';
ALTER SYSTEM SET effective_cache_size = '6GB';
ALTER SYSTEM SET work_mem = '64MB';
ALTER SYSTEM SET maintenance_work_mem = '512MB';
ALTER SYSTEM SET max_connections = 200;
```

### Redis 内存

默认 256MB，maxmemory-policy: allkeys-lru。监控：

```bash
docker compose exec redis redis-cli INFO memory
```

### Nginx 缓存

`nginx.conf` 已配置：
- 静态资源（JS/CSS/图片）：1 年（immutable）
- 后端静态（/static）：30 天
- 文档（PDF/CSV）：7 天
- HTML：no-cache

---

## 🔍 故障排查

### 常见问题

#### Q1: `start_prod.sh start` 报 "port 80 already in use"

```bash
# 查找占用 80 端口的进程
lsof -i :80
# 或
sudo lsof -i :80

# 停止占用进程
sudo kill -9 <PID>
# 或改 .env.production: HTTP_PORT=8080
```

#### Q2: 后端启动后 502 Bad Gateway

```bash
# 1. 检查后端是否健康
./start_prod.sh health

# 2. 查看后端日志
./start_prod.sh logs backend | tail -50

# 3. 常见原因：数据库连接失败 → 检查 PG 密码
docker compose exec backend env | grep PG_

# 4. 进入后端容器手动启动调试
./start_prod.sh shell backend
uvicorn backend.core.api.main:app --host 0.0.0.0 --port 8000
```

#### Q3: 前端页面打开是空白

```bash
# 1. 浏览器 DevTools → Network → 查看是否 404 资源
# 2. 检查 Nginx 是否有权限
docker compose exec frontend ls -la /usr/share/nginx/html/
# 3. 重新构建
./start_prod.sh clean
./start_prod.sh build
./start_prod.sh start
```

#### Q4: 数据库数据丢失

**立即停止所有写入！**

```bash
# 1. 检查数据卷是否还存在
docker volume ls | grep quant
# 2. 如果是误删，参考 nuke 操作的回收站（一般 24h 内可恢复）
# 3. 从备份恢复（见下方"备份与恢复"）
```

### 备份与恢复

```bash
# 备份数据库
docker compose exec postgres pg_dump -U quant_user -d quant_trading \
    | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# 恢复数据库
gunzip -c backup_20260610_120000.sql.gz \
    | docker compose exec -T postgres psql -U quant_user -d quant_trading
```

建议加到 cron：
```bash
# 每天凌晨 3 点备份
0 3 * * * cd /path/to/quant-trading && \
    ./start_prod.sh exec postgres pg_dump -U quant_user -d quant_trading | \
    gzip > /backup/quant_$(date +\%Y\%m\%d).sql.gz
```

---

## ⬆️ 升级与回滚

### 升级流程

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 重新构建
./start_prod.sh build

# 3. 重启（注意：先 down 再 up 才能用新镜像）
docker compose --env-file .env.production -p quant-trading down
docker compose --env-file .env.production -p quant-trading up -d

# 4. 验证
./start_prod.sh health
```

### 回滚流程

```bash
# 1. 查看历史镜像
docker images | grep quant-backend

# 2. 修改 docker-compose.yml 的 image tag
# image: quant-backend:0.9.0  # 从 1.0.0 回滚

# 3. 重启
docker compose --env-file .env.production -p quant-trading up -d
```

---

## 🏁 生产化清单

上线前必检：

### 安全
- [ ] 修改所有默认密码（PG_PASSWORD / PGADMIN_PASSWORD）
- [ ] 启用 HTTPS（Let's Encrypt + certbot）
- [ ] 配置防火墙（只开放 80/443）
- [ ] 关闭 pgAdmin（或限制内网访问）
- [ ] 配置 CORS_ORIGINS（不要用 `*`）
- [ ] 关闭后端 8000 端口对外暴露（保持内网）
- [ ] 启用 fail2ban（防 SSH 爆破）

### 监控
- [ ] 配置日志收集（ELK / Loki）
- [ ] 配置指标监控（Prometheus + Grafana）
- [ ] 配置告警（CPU > 80%, 内存 > 85%, 磁盘 > 90%）
- [ ] 配置健康检查端点监控（Uptime Kuma / Pingdom）

### 备份
- [ ] 数据库每日全量备份（crontab）
- [ ] 备份文件异地存储（S3 / OSS）
- [ ] 定期恢复演练（每月一次）

### 性能
- [ ] 压测基线（wrk / k6）
- [ ] 数据库 EXPLAIN ANALYZE 慢查询
- [ ] 启用 Nginx access log 统计

### 文档
- [ ] 更新运维手册
- [ ] 故障应急联系人
- [ ] 变更日志

---

## 📞 联系方式

- **项目负责人**: K
- **后端**: 量量
- **前端**: 方舟

问题反馈：通过项目协作单 `docs/协作单.md` 提交

---

**最后更新**: 2026-06-10（方舟，Phase 5.1.a）
