"""
AccountSnapshot ORM Model
"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, text
from . import Base


class AccountSnapshot(Base):
    """账户资金快照表（每日净值 + 出入金记录）"""
    __tablename__ = 'account_snapshot'
    __table_args__ = {'schema': 'pdca'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, default=1)
    snapshot_date = Column(Date, nullable=False)
    total_asset = Column(Numeric(16, 2), nullable=False)
    available_cash = Column(Numeric(16, 2), nullable=False)
    position_value = Column(Numeric(16, 2), nullable=False)
    deposit = Column(Numeric(16, 2), default=0)
    withdrawal = Column(Numeric(16, 2), default=0)
    realized_pnl = Column(Numeric(16, 2), default=0)
    adjusted_nav = Column(Numeric(16, 2))
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))