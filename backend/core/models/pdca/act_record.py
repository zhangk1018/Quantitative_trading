"""
ActRecord ORM 模型 — 迭代处理记录表
"""
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import ARRAY
from . import Base


class ActRecord(Base):
    """PDCA 迭代处理记录（问题清单+改进措施）"""
    __tablename__ = 'pdca_act_record'
    __table_args__ = {'schema': 'pdca'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer)
    pdca_cycle_id = Column(Integer, ForeignKey('pdca.pdca_cycle.id'), nullable=False, index=True)
    problem_list = Column(ARRAY(Text))
    rectify_plan = Column(Text, nullable=False)
    bind_next_cycle_goal = Column(Text)
    is_freeze_experience = Column(Boolean, default=False)
    new_config_version = Column(String(16))
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))
    updated_at = Column(DateTime(timezone=True), server_default=text('NOW()'))