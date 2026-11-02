"""PostgreSQL 故障表；约束防止绕过输入校验写入非法数据。"""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        *(CheckConstraint(f"{field} ~ '[^[:space:]]'", name=f"ck_incidents_{field}_nonblank")
          for field in ("incident_id", "service", "error_type", "message")),
        CheckConstraint("severity IN ('P1', 'P2', 'P3')", name="ck_incidents_severity"),
        Index("ix_incidents_service_occurred_at", "service", "occurred_at"),
    )
    incident_id: Mapped[str] = mapped_column(Text, primary_key=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    service: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
