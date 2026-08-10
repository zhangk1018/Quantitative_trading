"""
BehaviorLog ORM Model
"""
from sqlalchemy import Column, Integer, String, DateTime, text
from . import Base


class BehaviorLog(Base):
    """行为 & 违规日志表"""
    __tablename__ = 'behavior_log'
    __table_args__ = {'schema': 'pdca'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, default=1)
    pdca_cycle_id = Column(Integer, nullable=False)
    trading_record_id = Column(Integer)
    log_type = Column(String(16), nullable=False)
    violation_type = Column(String(32))
    severity = Column(String(16), default='medium')
    log_content = Column(String, nullable=False)
    happened_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))