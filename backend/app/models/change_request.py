from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(16), default="api", nullable=False)
    requester_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    requester_name: Mapped[str] = mapped_column(String(100), nullable=True)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=True)
    domain_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    before_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    after_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default="high", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending_approval", nullable=False, index=True)
    approval_channel: Mapped[str] = mapped_column(String(16), default="feishu", nullable=False)
    approver_user_id: Mapped[int] = mapped_column(Integer, nullable=True)
    approver_name: Mapped[str] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    execution_result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    events = relationship(
        "ChangeRequestEvent",
        back_populates="change_request",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
