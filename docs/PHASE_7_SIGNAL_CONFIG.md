# Phase 7：技术指标与信号参数化

## 7.0 需求背景

### 现状问题
1. **信号阈值硬编码**：买卖信号的触发阈值（如 RSI 超买 > 70，超卖 < 30）写死在 `signal_precompute.py` 中
2. **指标参数不可调**：MA/MACD/KDJ/BOLL 等指标的周期参数固定，不支持用户自定义
3. **缺乏策略模板**：无法快速切换不同的参数组合进行回测

### 用户价值
- 支持用户自定义技术指标参数（MA 周期、MACD 参数等）
- 支持自定义信号触发阈值（RSI 超买超卖区间）
- 支持策略模板保存和切换
- 为后续量化回测平台打下基础

---

## 7.1 架构设计

### 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    配置管理层（Config Layer）                │
├─────────────────────────────────────────────────────────────┤
│  signal_config.yaml    │  indicator_config.yaml            │
│  ─────────────────────  │  ─────────────────────────────   │
│  RSI 超买阈值: 70       │  MA 周期: [5,10,20,30,60]        │
│  RSI 超卖阈值: 30       │  MACD: [12,26,9]                 │
│  KDJ 超买阈值: 80       │  RSI: [6,12,24]                  │
│  KDJ 超卖阈值: 20       │  BOLL: [20,2]                    │
│  MACD 交叉灵敏度        │  KDJ: [9,3,3]                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    业务逻辑层（Business Layer）              │
├─────────────────────────────────────────────────────────────┤
│  TechnicalIndicator           SignalPrecompute              │
│  ───────────────────           ───────────────────          │
│  - 读取 indicator_config     - 读取 signal_config          │
│  - 使用配置参数计算          - 使用配置阈值检测              │
│  - 支持动态重载             - 支持动态重载                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    数据层（Data Layer）                       │
├─────────────────────────────────────────────────────────────┤
│  stock_indicators（指标快照）   trade_signals（买卖信号）   │
│  ──────────────────────        ──────────────────────       │
│  按最新配置重新计算            按最新阈值重新检测             │
└─────────────────────────────────────────────────────────────┘
```

### 配置层次设计

| 层次 | 配置内容 | 生效方式 | 适用场景 |
|:-----|:--------|:--------|:---------|
| **全局默认** | `config/default.yaml` | 程序启动加载 | 所有股票的默认参数 |
| **策略模板** | `config/templates/*.yaml` | 用户选择切换 | 不同交易策略 |
| **用户自定义** | 数据库 `user_indicator_config` 表 | 实时生效 | 个人偏好参数 |

---

## 7.2 配置文件设计

### 7.2.1 技术指标配置 `indicator_config.yaml`

```yaml
# 技术指标参数配置
# 所有参数均可自定义，支持小数

indicator:
  # 移动平均线 MA
  ma:
    periods: [5, 10, 20, 30, 60]  # 周期列表
    type: "SMA"                    # SMA(简单)/EMA(指数)/WMA(加权)

  # MACD 指标
  macd:
    fast_period: 12    # 快线周期
    slow_period: 26    # 慢线周期
    signal_period: 9   # 信号线周期

  # RSI 指标
  rsi:
    periods: [6, 12, 24]   # 周期列表
    # 注意：RSI 阈值在 signal_config.yaml 中配置

  # BOLL 布林带指标
  bollinger:
    period: 20       # 周期
    std_dev: 2       # 标准差倍数

  # KDJ 随机指标
  kdj:
    k_period: 9      # K 周期
    d_period: 3      # D 周期
    j_period: 3       # J 周期

  # CCI 顺势指标
  cci:
    period: 14       # 周期

  # WR 威廉指标
  williams:
    periods: [14, 28]  # 周期列表

# 缓存配置
cache:
  enabled: true
  ttl_seconds: 3600  # 配置缓存时间
```

### 7.2.2 信号阈值配置 `signal_config.yaml`

```yaml
# 买卖信号阈值配置
# 修改后需重新运行信号计算脚本

signal:
  # RSI 超买超卖信号
  rsi:
    enabled: true
    overbought_threshold: 70    # 超买阈值（>70 触发卖出信号）
    oversold_threshold: 30     # 超卖阈值（<30 触发买入信号）
    period: 6                 # 使用的 RSI 周期

  # MACD 金叉死叉信号
  macd:
    enabled: true
    sensitivity: 0.0           # 灵敏度（0=严格交叉，>0=提前触发）
    min_strength: 0.1          # 最小强度要求

  # KDJ 超买超卖信号
  kdj:
    enabled: true
    overbought_threshold: 80  # 超买阈值
    oversold_threshold: 20    # 超卖阈值
    golden_cross_enabled: true   # 金叉信号
    death_cross_enabled: true    # 死叉信号

  # BOLL 突破信号
  bollinger:
    enabled: true
    breakout_mode: "strict"     # strict(严格)/loose(宽松)
    position_filter: 0.8        # 突破幅度要求（0.8=突破 80%）

  # MA 交叉信号
  ma_cross:
    enabled: false
    fast_ma: 5      # 快线周期
    slow_ma: 20     # 慢线周期

  # 成交量异常信号
  volume:
    enabled: false
    threshold: 2.0  # 量比阈值（>2倍均量触发）

# 信号强度计算
strength:
  rsi_oversold: "inverse"     # inverse=(threshold-value)/threshold
  rsi_overbought: "inverse"   # inverse=(value-threshold)/threshold
  macd_cross: "abs_diff"     # abs_diff=abs(dif-dea)*100
  kdj_overbought: "inverse"   # inverse=(value-threshold)/(100-threshold)

# 过滤规则
filter:
  min_volume: 1000000         # 最小成交量（过滤僵尸股）
  exclude_st: true             # 排除 ST 股票
  exclude_suspended: true      # 排除停牌股票
```

---

## 7.3 数据库设计

### 7.3.1 用户指标配置表 `user_indicator_config`

```sql
CREATE TABLE IF NOT EXISTS user_indicator_config (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL DEFAULT 'default',
    config_type VARCHAR(32) NOT NULL,  -- 'indicator' / 'signal'
    config_name VARCHAR(64) NOT NULL,   -- 'ma_periods' / 'rsi_threshold' 等
    config_value JSONB NOT NULL,        -- 参数值（JSON 格式）
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, config_type, config_name)
);

-- 索引
CREATE INDEX idx_user_config_lookup ON user_indicator_config(user_id, config_type, is_active);
```

### 7.3.2 策略模板表 `strategy_template`

```sql
CREATE TABLE IF NOT EXISTS strategy_template (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    description TEXT,
    indicator_config JSONB NOT NULL,   -- 技术指标参数
    signal_config JSONB NOT NULL,      -- 信号阈值参数
    is_default BOOLEAN DEFAULT FALSE,
    created_by VARCHAR(64) DEFAULT 'system',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7.4 API 设计

### 7.4.1 配置管理 API

| 方法 | 路径 | 描述 |
|:-----|:-----|:-----|
| GET | `/api/config/indicator` | 获取技术指标当前配置 |
| PUT | `/api/config/indicator` | 更新技术指标配置 |
| GET | `/api/config/signal` | 获取信号阈值当前配置 |
| PUT | `/api/config/signal` | 更新信号阈值配置 |
| GET | `/api/config/templates` | 获取策略模板列表 |
| POST | `/api/config/templates` | 创建策略模板 |
| POST | `/api/config/templates/{name}/apply` | 应用策略模板 |

### 7.4.2 API 响应示例

```json
// GET /api/config/indicator
{
  "code": 200,
  "data": {
    "ma": {
      "periods": [5, 10, 20, 30, 60],
      "type": "SMA"
    },
    "macd": {
      "fast_period": 12,
      "slow_period": 26,
      "signal_period": 9
    },
    "rsi": {
      "periods": [6, 12, 24]
    }
  },
  "source": "file"  // "file" / "database"
}

// PUT /api/config/indicator
// Request
{
  "ma": {
    "periods": [5, 10, 20, 60]  // 移除 30，添加 60
  }
}
// Response
{
  "code": 200,
  "message": "配置已更新，需要重新计算指标",
  "requires_recompute": true
}
```

---

## 7.5 实施计划

### Phase 7.1：后端配置管理（方舟）
**预计工作量：0.5 天**

1. 创建配置文件 `backend/config/indicator_config.yaml`
2. 创建配置文件 `backend/config/signal_config.yaml`
3. 创建配置加载器 `backend/utils/config_loader.py`
4. 修改 `technical_indicator.py` 读取配置
5. 修改 `signal_precompute.py` 读取配置
6. 创建配置管理 API

### Phase 7.2：数据库持久化（方舟）
**预计工作量：0.5 天**

1. 创建数据库表 `user_indicator_config`
2. 创建数据库表 `strategy_template`
3. 修改配置加载器支持数据库覆盖文件配置
4. 实现策略模板 CRUD API

### Phase 7.3：前端配置页面（方舟）
**预计工作量：1 天**

1. 在「参数配置」页面添加指标参数配置
2. 添加信号阈值配置区域
3. 实现策略模板保存/加载
4. 添加「重新计算」按钮

### Phase 7.4：测试验证（方舟 + 量量）
**预计工作量：0.5 天**

1. 后端单元测试
2. API 接口测试
3. E2E 功能测试
4. 发布到测试环境
5. 验证数据正确性

---

## 7.6 涉及的代码修改

### 后端修改文件清单

| 文件 | 修改内容 | 负责人 |
|:-----|:--------|:-------|
| `backend/config/indicator_config.yaml` | 新建，指标参数默认配置 | 方舟 |
| `backend/config/signal_config.yaml` | 新建，信号阈值默认配置 | 方舟 |
| `backend/utils/config_loader.py` | 新建，配置加载器 | 方舟 |
| `backend/clean/processor/technical_indicator.py` | 读取配置文件参数 | 方舟 |
| `backend/clean/etl/signal_precompute.py` | 读取配置文件阈值 | 方舟 |
| `backend/clean/etl/compute_indicators_daily.py` | 支持自定义参数 | 方舟 |
| `backend/core/api/router/config.py` | 新建，配置管理 API | 方舟 |
| `backend/core/api/main.py` | 注册配置路由 | 方舟 |
| `backend/collector/db/models.py` | 添加配置表模型 | 量量 |

### 前端修改文件清单

| 文件 | 修改内容 | 负责人 |
|:-----|:--------|:-------|
| `frontend/src/components/ParamConfigView.tsx` | 新建，参数配置页面 | 方舟 |
| `frontend/src/api/config.ts` | 新建，配置 API 调用 | 方舟 |
| `frontend/src/types.ts` | 添加配置类型定义 | 方舟 |

---

## 7.7 配置优先级

当存在多层配置时，按以下优先级生效（高优先级覆盖低优先级）：

```
1. 用户数据库配置（user_indicator_config 表）
   ↓ 覆盖
2. 策略模板配置（strategy_template 表）
   ↓ 覆盖
3. 环境变量（.env 中的配置）
   ↓ 覆盖
4. 配置文件（config/*.yaml）
   ↓ 覆盖
5. 代码默认值（硬编码）
```

---

## 7.8 注意事项

### 1. 重新计算触发条件
修改以下配置需要重新计算历史数据：
- MA 周期变更
- MACD 参数变更
- RSI 周期变更
- KDJ 参数变更

修改以下配置只需重新检测信号：
- RSI 超买超卖阈值
- KDJ 超买超卖阈值
- 信号开关（enabled/disabled）

### 2. 性能考虑
- 配置读取使用单例模式，避免重复加载
- 大规模重算使用后台任务，不阻塞 API
- 添加进度反馈

### 3. 数据一致性
- 修改配置时记录版本号
- 重算前备份原数据
- 支持回滚

---

## 7.9 附录：参数范围参考

### 技术指标参数范围

| 指标 | 参数 | 建议范围 | 极端范围 |
|:-----|:-----|:---------|:---------|
| MA | 周期 | 5-250 | 1-500 |
| MACD | 快/慢/信号 | 12/26/9 | 5-50 |
| RSI | 周期 | 6-24 | 2-50 |
| BOLL | 周期/倍数 | 20/2 | 10-50 |
| KDJ | K/D/J 周期 | 9/3/3 | 3-30 |

### 信号阈值参考范围

| 信号类型 | 默认值 | 可调范围 |
|:---------|:-------|:---------|
| RSI 超买 | 70 | 60-90 |
| RSI 超卖 | 30 | 10-40 |
| KDJ 超买 | 80 | 70-95 |
| KDJ 超卖 | 20 | 5-30 |
| MACD 灵敏度 | 0 | 0-1 |
