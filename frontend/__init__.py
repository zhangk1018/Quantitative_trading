"""
frontend - 量化策略研发与展示平台

【设计目标】
1. 物理上独立于 backend/，通过 HTTP API 通信
2. 关注"脑力活"：策略逻辑、回测分析、可视化
3. 不直接访问数据库 → 所有数据通过 backend FastAPI 获取

【目录结构】
    frontend/
    ├── backtester/         # 回测引擎
    │   ├── engine.py       # 核心引擎（事件驱动 + 向量化）
    │   └── broker.py       # 模拟撮合器（手续费、滑点）
    ├── strategies/         # 策略模块
    │   ├── base_strategy.py
    │   └── my_strategies.py
    ├── analyzer/           # 绩效分析
    │   └── metrics.py      # 夏普/最大回撤/胜率等
    ├── dashboard/          # 可视化看板
    │   └── app.py          # Streamlit 入口
    └── utils/              # 前台工具
        └── api_client.py   # 后台 API 客户端
"""
