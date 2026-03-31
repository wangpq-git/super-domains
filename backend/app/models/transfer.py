from datetime import datetime
from sqlalchemy import String, Text, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DomainTransfer(Base):
    __tablename__ = "domain_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"), nullable=False)
    from_account_id: Mapped[int] = mapped_column(Integer, nullable=True)
    to_platform: Mapped[str] = mapped_column(String(32), nullable=False)
    to_account: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    auth_code: Mapped[str] = mapped_column(String(255), nullable=True)
    initiated_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime] = mapped_column(nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    domain = relationship("Domain", back_populates="transfers")
    creator = relationship("User", backref="domain_transfers")
