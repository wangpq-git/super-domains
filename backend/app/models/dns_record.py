from datetime import datetime
from sqlalchemy import String, Boolean, Text, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DnsRecord(Base):
    __tablename__ = "dns_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    record_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    ttl: Mapped[int] = mapped_column(Integer, default=3600)
    priority: Mapped[int] = mapped_column(Integer, nullable=True)
    proxied: Mapped[bool] = mapped_column(Boolean, nullable=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="synced")
    raw_data: Mapped[dict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    domain = relationship("Domain", back_populates="dns_records")
