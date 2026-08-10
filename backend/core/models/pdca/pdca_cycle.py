"""
PDCACycle ORM Model
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, text
from . import Base


class PDCACycle(Base):
    """PDCA 周期主表"""
    __tablename__ = 'pdca_cycle'
    __table_args__ = {'schema': 'pdca'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, default=1)
    prev_cycle_id = Column(Integer)
    cycle_type = Column(String(16), nullable=False)
    cycle_name = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default='PLAN')
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    goal_text = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))
    updated_at = Column(DateTime(timezone=True), server_default=text('NOW()'))