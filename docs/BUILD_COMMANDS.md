# 镜像构建命令

## 架构说明

前后端分离部署（两台独立容器）：

| 容器 | 镜像 | 端口 | 说明 |
|:-----|:-----|:----:|:-----|
| 后端服务器 | quant-backend:1.0.0 | 8000 | postgres + FastAPI |
| 前端服务器 | quant-frontend:1.0.0 | 80 | Nginx 反代（→ localhost:8000）|

## 前置条件

```bash
# 1. 从模板创建生产环境变量文件
cp .env.production.example .env.production

# 2. 修改密码（必改项）
# PG_PASSWORD=   # PostgreSQL 数据库密码
```

## 构建镜像

```bash
# 后端镜像（~790MB，首次构建约 10 分钟）
docker build -t quant-backend:1.0.0 -f Dockerfile.backend .

# 前端镜像（~50MB，首次构建约 2 分钟）
# 构建时注入后端地址 host.docker.internal:8000（Docker Desktop macOS）
docker build -t quant-frontend:1.0.0 -f Dockerfile.frontend .
```

## 启动服务

```bash
# 步骤1：启动后端（postgres + backend，端口 8000）
docker compose --env-file .env.production up -d

# 步骤2：启动前端（nginx，端口 80）
docker compose -f docker-compose.frontend.yml --env-file .env.production up -d
```

## 验证

```bash
# 后端健康检查
curl http://localhost:8000/health

# 前端健康检查
curl http://localhost/

# 查看容器状态
docker compose ps
docker compose -f docker-compose.frontend.yml ps
```

## 停止与清理

```bash
# 停止前端
docker compose -f docker-compose.frontend.yml down

# 停止后端
docker compose down

# 清理构建缓存
docker builder prune -a -f

# 删除 dangling 镜像
docker image prune -f
```

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `container quant-backend is unhealthy` | 应用启动失败 | `docker logs quant-backend` 查看错误 |
| `"user" directive is not allowed here` | nginx 镜像不允许 user 指令 | 已从 nginx.conf 删除 `user nginx;` |
| 前端 502 | 后端未启动或端口不对 | 确认 backend 在 localhost:8000 运行中 |
| Linux 下前端 502 | host.docker.internal 不生效 | 在 docker-compose.frontend.yml 中取消 `extra_hosts` 注释，改用宿主机 IP |
| TA-Lib `make install` 报错 | gcc-14 并行编译竞争 | 已去掉 `make -j$(nproc)` 中的 `-j` 参数 |