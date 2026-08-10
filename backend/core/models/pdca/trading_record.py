"""
TradingRecord ORM Model
"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, text
from . import Base


class TradingRecord(Base):
    """逐笔交易电子台账"""
    __tablename__ = 'trading_record'
    __table_args__ = {'schema': 'pdca'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, default=1)
    pdca_cycle_id = Column(Integer, nullable=False)
    trading_plan_id = Column(Integer)
    code = Column(String(32), nullable=False)
    security_name = Column(String(128))
    instrument_type = Column(String(16), default='stock')
    long_short = Column(String(8), nullable=False)
    order_type = Column(String(16), default='limit')
    entry_date = Column(Date, nullable=False)
    exit_date = Column(Date)
    entry_price = Column(Numeric(12, 4), nullable=False)
    exit_price = Column(Numeric(12, 4))
    quantity = Column(Integer, nullable=False)
    commission_entry = Column(Numeric(12, 4), default=0)
    commission_exit = Column(Numeric(12, 4), default=0)
    slip_point = Column(Numeric(12, 4), default=0)
    channel_height = Column(Numeric(12, 4))
    gross_profit = Column(Numeric(12, 4))
    entry_score = Column(Numeric(5, 2))
    exit_score = Column(Numeric(5, 2))
    trade_score = Column(Numeric(5, 2))
    trade_grade = Column(String(4))
    trigger_source = Column(String(16))
    actual_stop_loss = Column(Numeric(12, 4))
    exit_reason = Column(String(16))
    settlement_currency = Column(String(8), default='CNY')
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))
    updated_at = Column(DateTime(timezone=True), server_default=text('NOW()'))