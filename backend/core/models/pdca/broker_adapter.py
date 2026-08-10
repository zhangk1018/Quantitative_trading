"""
BrokerAdapter ORM Model
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from . import Base


class BrokerAdapter(Base):
    """券商适配器配置表"""
    __tablename__ = 'broker_adapter'
    __table_args__ = {'schema': 'pdca'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    broker_name = Column(String(64), nullable=False, unique=True)
    display_name = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True)
    column_mapping = Column(JSONB, nullable=False)
    date_format = Column(String(32), default='YYYY-MM-DD')
    skip_rows = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))
    updated_at = Column(DateTime(timezone=True), server_default=text('NOW()'))