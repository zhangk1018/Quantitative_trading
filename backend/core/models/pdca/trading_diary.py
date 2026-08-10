"""
TradingDiary ORM Model
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, text
from sqlalchemy.dialects.postgresql import ARRAY
from . import Base


class TradingDiary(Base):
    """交易日记表"""
    __tablename__ = 'trading_diary'
    __table_args__ = {'schema': 'pdca'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, default=1)
    trading_record_id = Column(Integer)
    pdca_cycle_id = Column(Integer, nullable=False)
    emotion_note = Column(String)
    review_text = Column(String, nullable=False)
    attach_file_paths = Column(ARRAY(String))
    three_month_review_done = Column(Boolean, default=False)
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))
    updated_at = Column(DateTime(timezone=True), server_default=text('NOW()'))