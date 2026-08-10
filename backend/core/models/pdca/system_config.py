"""
SystemConfig ORM Model
"""
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, text
from . import Base


class SystemConfig(Base):
    """系统配置 & 规则版本表"""
    __tablename__ = 'system_config'
    __table_args__ = {'schema': 'pdca'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(64), nullable=False)
    config_value = Column(String, nullable=False)
    numeric_value = Column(Numeric)
    bool_value = Column(Boolean)
    description = Column(String)
    version = Column(String(16), nullable=False)
    modified_at = Column(DateTime(timezone=True), server_default=text('NOW()'))
    modified_by = Column(String(64))
    modify_reason = Column(String, nullable=False)