"""
CheckReport ORM 模型 — 复盘报告表
"""
from sqlalchemy import Column, Integer, String, Numeric, Text, DateTime, ForeignKey, text
from . import Base


class CheckReport(Base):
    """PDCA 复盘报告"""
    __tablename__ = 'pdca_check_report'
    __table_args__ = {'schema': 'pdca'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer)
    pdca_cycle_id = Column(Integer, ForeignKey('pdca.pdca_cycle.id'), nullable=False, unique=True)
    report_status = Column(String(16), default='draft')
    total_trade_count = Column(Integer)
    complete_by_plan_count = Column(Integer)
    execution_rate = Column(Numeric(6, 2))
    win_rate = Column(Numeric(6, 2))
    profit_loss_ratio = Column(Numeric(8, 4))
    avg_entry_score = Column(Numeric(6, 2))
    avg_exit_score = Column(Numeric(6, 2))
    avg_trade_score = Column(Numeric(6, 2))
    max_drawdown = Column(Numeric(8, 4))
    violation_total = Column(Integer)
    report_content = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))
    updated_at = Column(DateTime(timezone=True), server_default=text('NOW()'))