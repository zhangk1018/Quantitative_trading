"""
Account ORM Model
"""
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, text
from . import Base


class Account(Base):
    """账户主表"""
    __tablename__ = 'account'
    __table_args__ = {'schema': 'pdca'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String(64), nullable=False)
    account_type = Column(String(32), default='stock')
    currency = Column(String(8), default='CNY')
    initial_capital = Column(Numeric(16, 2), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))
    updated_at = Column(DateTime(timezone=True), server_default=text('NOW()'))