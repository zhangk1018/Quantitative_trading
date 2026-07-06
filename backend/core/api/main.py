"""
main.py - FastAPI 应用入口
"""
import os
import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
_backend_dir = os.path.join(_project_root, "backend")
for p in [_project_root, _backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

from core.api.config import settings
from core.api.dependencies import init_pg_pool, close_pg_pool, get_loader, get_screener_service, get_snapshot_service
from core.api.router import meta, stocks, kline, signals, monitor, watchlist, snapshot

logger = logging.getLogger(__name__)

# 静态文件目录全局常量
_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
_admin_html_content = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _admin_html_content
    logger.info("🚀 启动量化交易系统后端API服务...")

    # 1. 初始化数据库连接池
    init_pg_pool()

    # 2. 预加载基础行情数据
    loader = get_loader()
    logger.info("📊 数据加载完成：%s，共%d只股票", loader.trade_date, len(loader.df))

    # 3. 初始化筛选服务
    get_screener_service()

    # 4. 初始化快照服务（内部后台线程加载数据，不阻塞启动）
    snapshot_svc = get_snapshot_service()
    logger.info("📦 快照服务初始化完成，数据后台加载中...")

    # 5. 加载管理后台页面
    html_path = os.path.join(_STATIC_DIR, "monitor.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            _admin_html_content = f.read()
    else:
        _admin_html_content = "<h1>Admin page not found</h1>"

    yield

    logger.info("🛑 关闭量化交易系统后端API服务...")
    close_pg_pool()


app = FastAPI(
    title="量化交易系统API",
    description="基于FastAPI的量化交易系统后端服务",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(meta.router, prefix="/api/meta", tags=["元数据"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["股票筛选"])
app.include_router(kline.router, prefix="/api/kline", tags=["K线数据"])
app.include_router(signals.router, prefix="/api/signals", tags=["买卖信号"])
app.include_router(monitor.router, prefix="/api", tags=["数据监控"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["自选股管理"])
app.include_router(snapshot.router, prefix="/api/snapshot", tags=["全量快照"])

# 挂载静态资源
app.mount("/static", StaticFiles(directory=_STATIC_DIR, html=True), name="static")


@app.get("/admin", response_class=HTMLResponse)
async def get_admin_dashboard():
    return HTMLResponse(content=_admin_html_content)


# 全局异常处理器
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(RuntimeError)
async def runtime_exception_handler(request: Request, exc: RuntimeError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "服务器内部错误",
            "detail": str(exc) if settings.debug else "请稍后重试",
            "path": request.url.path,
        }
    )


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "quantitative-trading-api",
        "version": "1.0.0",
        "timestamp": os.getenv("TRADE_DATE", "unknown"),
    }


@app.get("/")
async def root():
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