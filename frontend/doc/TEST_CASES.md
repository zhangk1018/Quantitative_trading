# 量化选股系统测试用例

## 测试用例清单

---

## 一、健康检查测试

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| HC-001 | 前端服务可用性 | `curl http://localhost/` | 返回 HTML 页面，包含 `<title>量化选股系统</title>` | | | |
| HC-002 | 后端直连健康检查 | `curl http://localhost:8000/health` | 返回 `{"status":"healthy",...}` | | | |
| HC-003 | Nginx 反代健康检查 | `curl http://localhost/health` | 返回 `{"status":"healthy",...}` | | | |
| HC-004 | 容器状态检查 | `docker compose ps` | backend 状态为 healthy | | | |
| HC-005 | 前端容器状态 | `docker compose -f docker-compose.frontend.yml ps` | frontend 状态为 healthy | | | |

---

## 二、API 接口测试

### 2.1 元数据接口

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| API-001 | GET /api/meta/ | `curl http://localhost/api/meta/` | 返回 code=200，包含 trade_date、total、groups | | | |
| API-002 | 股票数量验证 | 解析 API-001 返回的 total | total > 0（约 5500+） | | | |
| API-003 | 字段分组完整性 | 检查 groups 字段 | 包含 price、volume、technical、fundamental 等分组 | | | |

### 2.2 股票筛选接口

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| API-004 | GET /api/stocks/ 默认参数 | `curl http://localhost/api/stocks/` | 返回股票列表，默认返回 50 条 | | | |
| API-005 | 分页参数测试 | `curl "http://localhost/api/stocks/?page=1&page_size=10"` | 返回 10 条数据 | | | |
| API-006 | 排序参数测试 | `curl "http://localhost/api/stocks/?sort_by=change_pct&sort_order=desc"` | 按涨跌幅降序排列 | | | |
| API-007 | 筛选参数测试 | `curl "http://localhost/api/stocks/?market=SH"` | 返回上海市场股票 | | | |

### 2.3 K线数据接口

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| API-008 | GET /api/kline/{code} | `curl http://localhost/api/kline/000001` | 返回 K线数据数组 | | | |
| API-009 | 周期参数测试 | `curl "http://localhost/api/kline/000001?period=daily"` | 返回日线数据 | | | |
| API-010 | 周线数据测试 | `curl "http://localhost/api/kline/000001?period=weekly"` | 返回周线数据 | | | |

### 2.4 信号接口

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| API-011 | GET /api/signals/ | `curl http://localhost/api/signals/` | 返回信号列表 | | | |
| API-012 | 信号类型筛选 | `curl "http://localhost/api/signals/?type=macd_cross"` | 返回 MACD 交叉信号 | | | |

### 2.5 自选股接口

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| API-013 | GET /api/watchlist/ | `curl http://localhost/api/watchlist/` | 返回用户自选股列表 | | | |
| API-014 | POST /api/watchlist/ | `curl -X POST -H "Content-Type: application/json" -d '{"code":"000001","group_name":"默认分组"}' http://localhost/api/watchlist/` | 返回成功信息 | | | |
| API-015 | DELETE /api/watchlist/{code} | `curl -X DELETE http://localhost/api/watchlist/000001` | 返回成功信息 | | | |

---

## 三、前端功能测试

### 3.1 页面加载

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| UI-001 | 首页加载 | 浏览器访问 http://localhost/ | 页面正常渲染，显示选股系统界面 | | | |
| UI-002 | 导航菜单 | 查看顶部导航栏 | 包含「选股视图」「自选股」「回测视图」等按钮 | | | |
| UI-003 | 市场选择 | 查看市场选择区域 | 包含沪深、港股、美股选项 | | | |

### 3.2 选股功能

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| UI-004 | 筛选条件设置 | 点击「+ 范围」添加筛选条件 | 弹出条件选择框 | | | |
| UI-005 | 条件配置 | 选择字段、操作符、值 | 条件正确添加到面板 | | | |
| UI-006 | 开始选股 | 点击「开始选股」按钮 | 显示选股结果列表 | | | |
| UI-007 | 排序功能 | 选择排序字段和方向 | 结果按指定方式排序 | | | |
| UI-008 | 分页浏览 | 点击分页按钮 | 切换到对应页码 | | | |

### 3.3 自选股管理

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| UI-009 | 自选股页面 | 点击「自选股」导航 | 显示自选股列表 | | | |
| UI-010 | 添加自选 | 在选股结果中点击「添加自选」 | 股票添加到自选列表 | | | |
| UI-011 | 删除自选 | 在自选列表中点击删除 | 股票从列表移除 | | | |
| UI-012 | 分组管理 | 创建/修改分组 | 分组功能正常 | | | |

### 3.4 股票详情

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| UI-013 | 查看详情 | 点击股票名称 | 打开股票详情页面 | | | |
| UI-014 | K线图表 | 查看详情页的K线图 | 显示K线图表及指标 | | | |
| UI-015 | 指标切换 | 切换 MA/RSI/MACD 等指标 | 图表正确切换显示 | | | |

### 3.5 策略管理

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| UI-016 | 保存策略 | 配置筛选条件后点击「保存策略」 | 策略保存成功 | | | |
| UI-017 | 加载策略 | 点击「我的策略」选择策略 | 策略配置加载到界面 | | | |
| UI-018 | 删除策略 | 在策略列表中删除 | 策略被删除 | | | |

---

## 四、数据验证测试

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| DV-001 | 股票数量完整性 | 对比 /api/meta 和 /api/stocks 的 total | 数量一致 | | | |
| DV-002 | 字段非空检查 | 检查关键字段（close, open, high, low） | 无空值或空值率 < 5% | | | |
| DV-003 | 技术指标计算 | 检查 MA5、RSI、MACD 字段 | 计算值合理 | | | |
| DV-004 | 数据日期一致性 | 检查 trade_date 字段 | 所有股票日期一致 | | | |
| DV-005 | 股票代码格式 | 检查 code 字段格式 | 纯数字格式（6位） | | | |

---

## 五、性能测试

| 编号 | 测试目标 | 测试步骤 | 预期结果 | 实际结果 | 状态 | 备注 |
|:-----|:---------|:---------|:---------|:---------|:-----|:-----|
| PERF-001 | API 响应时间 | `curl -w "%{time_total}\n" -o /dev/null http://localhost/api/meta/` | < 500ms | | | |
| PERF-002 | 股票列表响应 | `curl -w "%{time_total}\n" -o /dev/null http://localhost/api/stocks/` | < 1000ms | | | |
| PERF-003 | 页面加载时间 | 浏览器开发者工具查看 | 首屏加载 < 3s | | | |
| PERF-004 | 并发请求测试 | `ab -n 10 -c 5 http://localhost/api/meta/` | 平均响应 < 1s | | | |

---

## 六、测试执行记录

### 6.1 测试环境信息
```
测试日期: 
测试环境: 本地 Docker
前端版本: quant-frontend:1.0.0
后端版本: quant-backend:1.0.0
数据库版本: PostgreSQL 16-alpine
```

### 6.2 问题记录模板
```
问题编号: P0-001
问题描述: 
严重程度: P0/P1/P2/P3
复现步骤: 
预期结果: 
实际结果: 
修复状态: 待修复/修复中/已修复
修复方案: 
```

---

## 七、测试总结

| 测试模块 | 测试用例数 | 通过 | 失败 | 通过率 |
|:---------|:-----------|:-----|:-----|:-------|
| 健康检查 | 5 | | | |
| API 接口 | 15 | | | |
| 前端功能 | 18 | | | |
| 数据验证 | 5 | | | |
| 性能测试 | 4 | | | |
| **合计** | **47** | | | |

---

## 附录：测试命令汇总

```bash
# 健康检查
curl http://localhost/health
curl http://localhost:8000/health

# API 测试
curl http://localhost/api/meta/
curl http://localhost/api/stocks/
curl http://localhost/api/kline/000001
curl http://localhost/api/signals/
curl http://localhost/api/watchlist/

# 容器状态
docker compose ps
docker compose -f docker-compose.frontend.yml ps

# 日志查看
docker compose logs backend
docker compose -f docker-compose.frontend.yml logs
```