from datetime import datetime
from sqlalchemy import String, Boolean, Integer, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(30), nullable=False)
    days_before: Mapped[int] = mapped_column(Integer, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    channels: Mapped[dict] = mapped_column(JSON, default=list)
    recipients: Mapped[dict] = mapped_column(JSON, default=list)
    apply_to_all: Mapped[bool] = mapped_column(Boolean, default=True)
    specific_platforms: Mapped[dict] = mapped_column(JSON, nullable=True)
    specific_domains: Mapped[dict] = mapped_column(JSON, nullable=True)
    excluded_platforms: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    creator = relationship("User", backref="alert_rules")
