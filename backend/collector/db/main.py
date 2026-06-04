"""
main.py - 股票筛选器 API 服务

基于 FastAPI 构建，直接查询 stock_daily_snapshot 宽表，
提供高性能的股票数据查询接口。
"""

from contextlib import asynccontextmanager
from pathlib import Path
import json
from datetime import date, datetime
from decimal import Decimal
import math

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import database
from repository import StockRepository


STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"


class CustomJSONEncoder(json.JSONEncoder):
    """自定义 JSON 编码器，处理 Decimal、date、datetime 等类型"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 测试数据库连接
    print("🔍 检查数据库连接...")
    if not database.test_connection():
        print("⚠️ 警告: 无法连接到 PostgreSQL 数据库")
        print("💡 提示: 请确保 PostgreSQL 服务正在运行，并检查 .env 配置")
    else:
        print("✅ 数据库连接正常")
    yield


app = FastAPI(title="Stock Screener API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# 排序字段白名单（与宽表字段对齐）
VALID_SORT_FIELDS = {
    "change_pct", "close", "market_cap", "amount",
    "turnover_rate", "volume", "pe", "pb",
    "ma5", "ma10", "ma20", "rsi_6", "macd",
    "boll_upper", "boll_mid", "boll_lower",
    "high", "low", "change", "pe_ttm", "ps",
    "ps_ttm", "dv_ratio", "dv_ttm", "circ_mv",
    "float_share", "volume_ratio", "net_mf_amount",
    "break_high_20", "break_high_60", "consec_up_days",
    "vol_ratio_5", "v_ma5", "buy_sm_amount", "sell_sm_amount",
    "buy_md_amount", "sell_md_amount", "buy_lg_amount",
    "sell_lg_amount", "buy_elg_amount", "sell_elg_amount",
}


@app.get("/api/meta")
def get_meta():
    """获取元数据（行业/地区选项）"""
    # 获取最新交易日期
    latest_date = None
    try:
        # 先获取宽表中最新的交易日期
        with database.get_db_session() as session:
            from sqlalchemy import text
            result = session.execute(text("SELECT MAX(trade_date) FROM stock_daily_snapshot"))
            latest_date = result.scalar_one()
        
        trade_date_str = latest_date.strftime('%Y-%m-%d') if latest_date else datetime.now().strftime('%Y-%m-%d')
        
        # 使用获取到的最新日期查询市场概况
        summary = None
        if latest_date:
            with database.get_db_session() as session:
                repo = StockRepository(session)
                summary = repo.get_market_summary(trade_date_str)
        
        # 获取行业和板块选项
        industries = []
        boards = []
        with database.get_db_session() as session:
            result = session.execute(text("SELECT DISTINCT industry FROM stock_daily_snapshot WHERE industry IS NOT NULL AND industry != '' ORDER BY industry"))
            industries = [row[0] for row in result.fetchall()]
            
            result = session.execute(text("SELECT DISTINCT listed_board FROM stock_daily_snapshot WHERE listed_board IS NOT NULL ORDER BY listed_board"))
            boards = [row[0] for row in result.fetchall()]
        
        # 构建前端期望的 groups 数组格式
        # 前端期望: { id: string, label: string, fields: [{ key: string, label: string, count: number }] }
        groups = []
        
        # 上市板块分组
        board_fields = []
        for board in boards:
            # 查询每个板块的股票数量
            count = 0
            with database.get_db_session() as session:
                result = session.execute(
                    text("SELECT COUNT(*) FROM stock_daily_snapshot WHERE listed_board = :board AND trade_date = :date"),
                    {"board": board, "date": trade_date_str}
                )
                count = result.scalar_one()
            
            board_fields.append({
                "key": f"board_{board}",
                "label": board,
                "count": count
            })
        
        if board_fields:
            groups.append({
                "id": "listed_board",
                "label": "上市板块",
                "fields": board_fields
            })
        
        # 获取地区选项
        areas = []
        with database.get_db_session() as session:
            result = session.execute(text("SELECT DISTINCT area FROM stock_daily_snapshot WHERE area IS NOT NULL AND area != '' ORDER BY area"))
            areas = [row[0] for row in result.fetchall()]
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "trade_date": trade_date_str,
                "total": summary.get('total_count', 0) if summary else 0,
                "groups": groups,
                "industry_options": industries,
                "area_options": areas,
            }
        }
    except Exception as e:
        print(f"❌ 获取元数据失败: {e}")
        return {
            "code": 500,
            "message": "获取元数据失败",
            "data": None
        }


@app.get("/api/stocks")
def get_stocks(
    as_of_date: str = "",
    listed_board: str = "",
    industry: str = "",
    area: str = "",
    sort_by: str = "change_pct",
    sort_asc: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    """
    查询股票列表
    
    Args:
        as_of_date: 查询日期（格式：YYYY-MM-DD），为空则使用最新日期
        listed_board: 上市板块（主板/创业板/科创板/中小板）
        industry: 行业（逗号分隔）
        area: 地域（逗号分隔）
        sort_by: 排序字段（白名单校验）
        sort_asc: 是否升序排列
        offset: 分页偏移量
        limit: 每页数量
    """
    # 校验排序字段
    if sort_by not in VALID_SORT_FIELDS:
        raise HTTPException(400, detail=f"Invalid sort_by: '{sort_by}'. "
                                        f"Allowed: {sorted(VALID_SORT_FIELDS)}")

    try:
        with database.get_db_session() as session:
            repo = StockRepository(session)
            
            # 确定查询日期
            query_date = as_of_date if as_of_date else datetime.now().strftime('%Y-%m-%d')
            
            # 查询宽表
            stocks, total = repo.get_stock_list(
                as_of_date=query_date,
                listed_board=listed_board if listed_board else None,
                industry=industry if industry else None,
                area=area if area else None,
                sort_by=sort_by,
                sort_asc=sort_asc,
                offset=offset,
                limit=limit
            )
            
            # 转换为字典列表
            data = []
            for stock in stocks:
                record = stock.to_dict()
                # 处理 NaN 值
                for key, value in record.items():
                    if isinstance(value, float) and math.isnan(value):
                        record[key] = None
                data.append(record)
            
            return {
                "code": 200,
                "message": "success",
                "data": {
                    "items": data,
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                }
            }
    except Exception as e:
        print(f"❌ 查询股票列表失败: {e}")
        raise HTTPException(500, detail=f"查询失败: {str(e)}")


@app.get("/api/stock/{code}")
def get_stock(code: str, as_of_date: str = ""):
    """
    查询单只股票详情
    
    Args:
        code: 股票代码
        as_of_date: 查询日期，为空则返回最新数据
    """
    try:
        with database.get_db_session() as session:
            repo = StockRepository(session)
            
            stock = repo.get_stock_by_code(
                code=code,
                as_of_date=as_of_date if as_of_date else None
            )
            
            if not stock:
                raise HTTPException(404, detail=f"股票 {code} 未找到")
            
            record = stock.to_dict()
            # 处理 NaN 值
            for key, value in record.items():
                if isinstance(value, float) and math.isnan(value):
                    record[key] = None
            
            return {
                "code": 200,
                "message": "success",
                "data": record,
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 查询股票详情失败: {e}")
        raise HTTPException(500, detail=f"查询失败: {str(e)}")


@app.get("/api/market/summary")
def get_market_summary(as_of_date: str = ""):
    """
    获取市场概况统计
    
    Args:
        as_of_date: 查询日期，为空则使用最新日期
    """
    try:
        with database.get_db_session() as session:
            repo = StockRepository(session)
            
            query_date = as_of_date if as_of_date else datetime.now().strftime('%Y-%m-%d')
            summary = repo.get_market_summary(query_date)
            
            return {
                "code": 200,
                "message": "success",
                "data": summary,
            }
    except Exception as e:
        print(f"❌ 获取市场概况失败: {e}")
        raise HTTPException(500, detail=f"查询失败: {str(e)}")


# Serve frontend static files (only if dist/ exists, i.e. after npm run build)
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str = ""):  # noqa: ARG001
        return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
