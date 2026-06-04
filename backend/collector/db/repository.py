"""
repository.py - 基于宽表的高性能数据访问层

利用 stock_daily_snapshot 宽表实现极简、高效的股票数据查询。
告别多表 JOIN，享受宽表带来的性能红利。
"""

from typing import Tuple, List, Optional
from sqlalchemy import select, func, desc, asc, text
from sqlalchemy.orm import Session
from models import StockDailySnapshot


class StockRepository:
    """
    股票数据仓储类
    
    基于 SQLAlchemy 实现，直接查询宽表 stock_daily_snapshot，
    支持动态过滤、排序和分页。
    """
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_stock_list(
        self,
        as_of_date: str,
        listed_board: Optional[str] = None,
        industry: Optional[str] = None,
        area: Optional[str] = None,
        sort_by: str = 'change_pct',
        sort_asc: bool = False,
        offset: int = 0,
        limit: int = 100
    ) -> Tuple[List[StockDailySnapshot], int]:
        """
        查询股票列表，直接利用宽表的高性能
        
        Args:
            as_of_date: 查询日期（格式：YYYY-MM-DD）
            listed_board: 上市板块过滤（如：主板、创业板、科创板）
            industry: 行业过滤（逗号分隔，如：银行,证券）
            area: 地域过滤（逗号分隔）
            sort_by: 排序字段（白名单校验已在上层完成）
            sort_asc: 是否升序排列
            offset: 分页偏移量
            limit: 每页数量
            
        Returns:
            (股票列表, 总记录数)
        """
        
        # 1. 基础查询 - 直接查询宽表
        query = select(StockDailySnapshot).where(
            StockDailySnapshot.trade_date == as_of_date
        )
        
        # 2. 计数查询
        count_query = select(func.count()).select_from(StockDailySnapshot).where(
            StockDailySnapshot.trade_date == as_of_date
        )
        
        # 3. 动态拼接 WHERE 条件
        if listed_board:
            query = query.where(StockDailySnapshot.listed_board == listed_board)
            count_query = count_query.where(StockDailySnapshot.listed_board == listed_board)
        
        if industry:
            industries = [i.strip() for i in industry.split(',') if i.strip()]
            if industries:
                query = query.where(StockDailySnapshot.industry.in_(industries))
                count_query = count_query.where(StockDailySnapshot.industry.in_(industries))
        
        if area:
            areas = [a.strip() for a in area.split(',') if a.strip()]
            if areas:
                query = query.where(StockDailySnapshot.area.in_(areas))
                count_query = count_query.where(StockDailySnapshot.area.in_(areas))
        
        # 4. 动态排序（直接映射字符串到 ORM 字段）
        # 安全：上层 schemas.py 已做白名单校验
        sort_column = getattr(StockDailySnapshot, sort_by)
        order_func = asc if sort_asc else desc
        query = query.order_by(order_func(sort_column))
        
        # 5. 分页
        total = self.session.execute(count_query).scalar_one()
        query = query.offset(offset).limit(limit)
        
        # 6. 执行查询
        result = self.session.execute(query)
        return result.scalars().all(), total
    
    def get_stock_by_code(
        self,
        code: str,
        as_of_date: Optional[str] = None
    ) -> Optional[StockDailySnapshot]:
        """
        查询单只股票的数据
        
        Args:
            code: 股票代码
            as_of_date: 查询日期，None 则返回最新数据
            
        Returns:
            股票快照记录
        """
        query = select(StockDailySnapshot).where(StockDailySnapshot.code == code)
        
        if as_of_date:
            query = query.where(StockDailySnapshot.trade_date == as_of_date)
        else:
            query = query.order_by(desc(StockDailySnapshot.trade_date)).limit(1)
        
        result = self.session.execute(query)
        return result.scalar_one_or_none()
    
    def get_stock_history(
        self,
        code: str,
        start_date: str,
        end_date: str,
        limit: int = 100
    ) -> List[StockDailySnapshot]:
        """
        查询股票历史数据
        
        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            limit: 返回数量限制
            
        Returns:
            股票历史快照列表
        """
        query = select(StockDailySnapshot).where(
            StockDailySnapshot.code == code,
            StockDailySnapshot.trade_date >= start_date,
            StockDailySnapshot.trade_date <= end_date
        ).order_by(desc(StockDailySnapshot.trade_date)).limit(limit)
        
        result = self.session.execute(query)
        return result.scalars().all()
    
    def get_market_summary(self, as_of_date: str) -> dict:
        """
        获取市场概况统计
        
        Args:
            as_of_date: 查询日期
            
        Returns:
            统计字典
        """
        query = text("""
            SELECT 
                COUNT(*) as total_count,
                SUM(CASE WHEN change_pct > 0 THEN 1 ELSE 0 END) as up_count,
                SUM(CASE WHEN change_pct < 0 THEN 1 ELSE 0 END) as down_count,
                SUM(CASE WHEN change_pct = 0 THEN 1 ELSE 0 END) as flat_count,
                AVG(change_pct) as avg_change_pct,
                MAX(change_pct) as max_change_pct,
                MIN(change_pct) as min_change_pct,
                SUM(volume) as total_volume,
                SUM(amount) as total_amount
            FROM stock_daily_snapshot
            WHERE trade_date = :date
        """)
        
        result = self.session.execute(query, {'date': as_of_date})
        row = result.mappings().first()
        
        return {
            'total_count': row['total_count'] if row else 0,
            'up_count': row['up_count'] if row else 0,
            'down_count': row['down_count'] if row else 0,
            'flat_count': row['flat_count'] if row else 0,
            'avg_change_pct': float(row['avg_change_pct']) if row and row['avg_change_pct'] else None,
            'max_change_pct': float(row['max_change_pct']) if row and row['max_change_pct'] else None,
            'min_change_pct': float(row['min_change_pct']) if row and row['min_change_pct'] else None,
            'total_volume': int(row['total_volume']) if row and row['total_volume'] else 0,
            'total_amount': float(row['total_amount']) if row and row['total_amount'] else None,
        }
