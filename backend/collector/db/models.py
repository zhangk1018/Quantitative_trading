"""
models.py - SQLAlchemy ORM 模型定义
基于 PostgreSQL 宽表 stock_daily_snapshot 创建
"""

from sqlalchemy import (
    Column, Integer, BigInteger, String, Date, DateTime, 
    Numeric, Boolean, text, Index
)
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class StockDailySnapshot(Base):
    """
    股票每日快照宽表模型
    
    用于存储盘后 ETL 物理化合并的高频查询字段，
    支持高性能的股票列表查询、排序和筛选。
    """
    
    __tablename__ = 'stock_daily_snapshot'
    
    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 基础标识字段
    code = Column(String(10), nullable=False, comment='股票代码')
    stock_name = Column(String(50), comment='股票名称')
    listed_board = Column(String(20), comment='上市板块')
    industry = Column(String(50), comment='行业')
    sub_industry = Column(String(50), comment='细分行业')
    area = Column(String(50), comment='地区')
    
    # 日期字段
    trade_date = Column(Date, nullable=False, comment='交易日期')
    created_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'), comment='创建时间')
    updated_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'), comment='更新时间')
    
    # 行情基础字段
    open = Column(Numeric(10, 2), comment='开盘价')
    high = Column(Numeric(10, 2), comment='最高价')
    low = Column(Numeric(10, 2), comment='最低价')
    close = Column(Numeric(10, 2), comment='收盘价')
    pre_close = Column(Numeric(10, 2), comment='前收盘价')
    volume = Column(BigInteger, comment='成交量')
    amount = Column(Numeric(18, 2), comment='成交额')
    adjust_type = Column(String(10), server_default='qfq', comment='复权类型')
    
    # 高频查询字段（ETL 计算）
    change = Column(Numeric(10, 2), comment='涨跌额')
    change_pct = Column(Numeric(8, 2), comment='涨跌幅（%）')
    turnover_rate = Column(Numeric(8, 2), comment='换手率（%）')
    
    # 估值指标
    pe = Column(Numeric(10, 2), comment='市盈率')
    pb = Column(Numeric(10, 2), comment='市净率')
    market_cap = Column(Numeric(18, 2), comment='总市值（万元）')
    circ_mv = Column(Numeric(18, 2), comment='流通市值（万元）')
    
    # 扩展估值指标
    pe_ttm = Column(Numeric(10, 2), comment='市盈率TTM')
    ps = Column(Numeric(10, 2), comment='市销率')
    ps_ttm = Column(Numeric(10, 2), comment='市销率TTM')
    dv_ratio = Column(Numeric(8, 4), comment='股息率')
    dv_ttm = Column(Numeric(8, 4), comment='股息率TTM')
    float_share = Column(Numeric(18, 2), comment='流通股（万股）')
    
    # 技术指标
    ma5 = Column(Numeric(10, 2), comment='5日均线')
    ma10 = Column(Numeric(10, 2), comment='10日均线')
    ma20 = Column(Numeric(10, 2), comment='20日均线')
    v_ma5 = Column(BigInteger, comment='5日均量')
    rsi_6 = Column(Numeric(6, 2), comment='RSI6')
    macd = Column(Numeric(10, 4), comment='MACD值')
    boll_upper = Column(Numeric(10, 2), comment='布林带上轨')
    boll_mid = Column(Numeric(10, 2), comment='布林带中轨')
    boll_lower = Column(Numeric(10, 2), comment='布林带下轨')
    volume_ratio = Column(Numeric(8, 2), comment='量比')
    vol_ratio_5 = Column(Numeric(8, 2), comment='5日量比')
    
    # 资金流向
    net_mf_amount = Column(Numeric(18, 2), comment='净流入（万元）')
    buy_sm_amount = Column(Numeric(18, 2), comment='小单买入（万元）')
    sell_sm_amount = Column(Numeric(18, 2), comment='小单卖出（万元）')
    buy_md_amount = Column(Numeric(18, 2), comment='中单买入（万元）')
    sell_md_amount = Column(Numeric(18, 2), comment='中单卖出（万元）')
    buy_lg_amount = Column(Numeric(18, 2), comment='大单买入（万元）')
    sell_lg_amount = Column(Numeric(18, 2), comment='大单卖出（万元）')
    buy_elg_amount = Column(Numeric(18, 2), comment='特大单买入（万元）')
    sell_elg_amount = Column(Numeric(18, 2), comment='特大单卖出（万元）')
    
    # 新高/连涨标记
    break_high_20 = Column(Boolean, server_default='false', comment='20日新高')
    break_high_60 = Column(Boolean, server_default='false', comment='60日新高')
    consec_up_days = Column(Integer, comment='连涨天数')
    
    # 状态标记字段（保留但不在前端展示）
    is_st = Column(Boolean, server_default='false', comment='是否ST股票')
    is_new = Column(Boolean, server_default='false', comment='是否新股')
    limit_up = Column(Boolean, server_default='false', comment='是否涨停')
    limit_down = Column(Boolean, server_default='false', comment='是否跌停')
    
    # 索引定义
    __table_args__ = (
        Index('idx_snapshot_date_change', 'trade_date', 'change_pct', postgresql_using='btree'),
        Index('idx_snapshot_date_pe', 'trade_date', 'pe', postgresql_using='btree'),
        Index('idx_snapshot_date_market_cap', 'trade_date', 'market_cap', postgresql_using='btree'),
        Index('idx_snapshot_code_date', 'code', 'trade_date', postgresql_using='btree'),
        Index('idx_snapshot_industry', 'industry', postgresql_using='btree'),
    )
    
    def to_dict(self):
        """将模型转换为字典"""
        return {
            'id': self.id,
            'stock_code': self.code,
            'stock_name': self.stock_name,
            'listed_board': self.listed_board,
            'industry': self.industry,
            'sub_industry': self.sub_industry,
            'trade_date': self.trade_date.isoformat() if self.trade_date else None,
            
            # 行情基础字段
            'open': float(self.open) if self.open is not None else None,
            'high': float(self.high) if self.high is not None else None,
            'low': float(self.low) if self.low is not None else None,
            'close': float(self.close) if self.close is not None else None,
            'pre_close': float(self.pre_close) if self.pre_close is not None else None,
            'volume': int(self.volume) if self.volume is not None else None,
            'amount': float(self.amount) if self.amount is not None else None,
            
            # 涨跌字段
            'change': float(self.change) if self.change is not None else None,
            'change_pct': float(self.change_pct) if self.change_pct is not None else None,
            'turnover_rate': float(self.turnover_rate) if self.turnover_rate is not None else None,
            
            # 估值指标
            'pe': float(self.pe) if self.pe is not None else None,
            'pb': float(self.pb) if self.pb is not None else None,
            'market_cap': float(self.market_cap) if self.market_cap is not None else None,
            'circ_mv': float(self.circ_mv) if self.circ_mv is not None else None,
            'pe_ttm': float(self.pe_ttm) if self.pe_ttm is not None else None,
            'ps': float(self.ps) if self.ps is not None else None,
            'ps_ttm': float(self.ps_ttm) if self.ps_ttm is not None else None,
            'dv_ratio': float(self.dv_ratio) if self.dv_ratio is not None else None,
            'dv_ttm': float(self.dv_ttm) if self.dv_ttm is not None else None,
            'float_share': float(self.float_share) if self.float_share is not None else None,
            
            # 技术指标
            'ma5': float(self.ma5) if self.ma5 is not None else None,
            'ma10': float(self.ma10) if self.ma10 is not None else None,
            'ma20': float(self.ma20) if self.ma20 is not None else None,
            'v_ma5': int(self.v_ma5) if self.v_ma5 is not None else None,
            'rsi_6': float(self.rsi_6) if self.rsi_6 is not None else None,
            'macd': float(self.macd) if self.macd is not None else None,
            'boll_upper': float(self.boll_upper) if self.boll_upper is not None else None,
            'boll_mid': float(self.boll_mid) if self.boll_mid is not None else None,
            'boll_lower': float(self.boll_lower) if self.boll_lower is not None else None,
            'volume_ratio': float(self.volume_ratio) if self.volume_ratio is not None else None,
            'vol_ratio_5': float(self.vol_ratio_5) if self.vol_ratio_5 is not None else None,
            
            # 资金流向
            'net_mf_amount': float(self.net_mf_amount) if self.net_mf_amount is not None else None,
            'buy_sm_amount': float(self.buy_sm_amount) if self.buy_sm_amount is not None else None,
            'sell_sm_amount': float(self.sell_sm_amount) if self.sell_sm_amount is not None else None,
            'buy_md_amount': float(self.buy_md_amount) if self.buy_md_amount is not None else None,
            'sell_md_amount': float(self.sell_md_amount) if self.sell_md_amount is not None else None,
            'buy_lg_amount': float(self.buy_lg_amount) if self.buy_lg_amount is not None else None,
            'sell_lg_amount': float(self.sell_lg_amount) if self.sell_lg_amount is not None else None,
            'buy_elg_amount': float(self.buy_elg_amount) if self.buy_elg_amount is not None else None,
            'sell_elg_amount': float(self.sell_elg_amount) if self.sell_elg_amount is not None else None,
            
            # 新高/连涨标记
            'break_high_20': bool(self.break_high_20) if self.break_high_20 is not None else False,
            'break_high_60': bool(self.break_high_60) if self.break_high_60 is not None else False,
            'consec_up_days': int(self.consec_up_days) if self.consec_up_days is not None else None,
        }
