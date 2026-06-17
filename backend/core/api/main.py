"""
main.py - FastAPI 应用入口

量化交易系统后端API服务入口点，集成所有路由和中间件。
"""

import os
import sys

# 修正 Python 路径：使 shared/ 和 backend/ 均可导入
# 获取项目根目录：Quantitative_trading
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
_backend_dir = os.path.join(_project_root, "backend")

for p in [_project_root, _backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from .config import settings
from .dependencies import init_pg_pool, close_pg_pool, get_loader, get_screener_service
from .router import meta, stocks, kline, signals, monitor, watchlist

# 应用生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时加载数据，关闭时清理资源"""
    print("🚀 启动量化交易系统后端API服务...")
    
    # 初始化 PostgreSQL 连接池
    init_pg_pool()
    
    # 启动时预加载数据
    loader = get_loader()
    print(f"📊 数据加载完成：{loader.trade_date}，共{len(loader.df)}只股票")
    
    # 预初始化服务
    get_screener_service()
    
    yield
    
    # 关闭时清理资源
    print("🛑 关闭量化交易系统后端API服务...")
    close_pg_pool()

# 创建FastAPI应用
app = FastAPI(
    title="量化交易系统API",
    description="基于FastAPI的量化交易系统后端服务，提供股票筛选、K线数据、买卖信号等功能",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 配置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(meta.router, prefix="/api/meta", tags=["元数据"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["股票筛选"])
app.include_router(kline.router, prefix="/api/kline", tags=["K线数据"])
app.include_router(signals.router, prefix="/api/signals", tags=["买卖信号"])
app.include_router(monitor.router, prefix="/api", tags=["数据监控"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["自选股管理"])

# 挂载静态文件服务（监控看板）
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")

# 管理员监控看板入口
@app.get("/admin", response_class=HTMLResponse)
async def get_admin_dashboard():
    """返回管理员数据监控看板页面"""
    html_path = os.path.join(static_dir, "monitor.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理器"""
    return JSONResponse(
        status_code=500,
        content={
            "error": "服务器内部错误",
            "detail": str(exc) if settings.debug else "请稍后重试",
            "path": request.url.path,
        }
    )

# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "quantitative-trading-api",
        "version": "1.0.0",
        "timestamp": os.getenv("TRADE_DATE", "unknown"),
    }

# 根路径重定向到文档
@app.get("/")
async def root():
    """根路径重定向到API文档"""
    return {"message": "欢迎使用量化交易系统API", "docs_url": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "core.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" if settings.debug else "warning",
    )