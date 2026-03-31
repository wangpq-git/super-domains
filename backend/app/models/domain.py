from datetime import datetime
from sqlalchemy import String, Boolean, Text, Integer, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Domain(Base):
    __tablename__ = "domains"
    __table_args__ = (
        UniqueConstraint("account_id", "domain_name", name="uq_account_domain"),
        Index("idx_domain_expiry", "expiry_date"),
        Index("idx_domain_account", "account_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("platform_accounts.id", ondelete="CASCADE"), nullable=False)
    domain_name: Mapped[str] = mapped_column(String(255), nullable=True)
    tld: Mapped[str] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    registration_date: Mapped[datetime] = mapped_column(nullable=True)
    expiry_date: Mapped[datetime] = mapped_column(nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=True)
    whois_privacy: Mapped[bool] = mapped_column(Boolean, default=False)
    nameservers: Mapped[dict] = mapped_column(default=list)
    raw_data: Mapped[dict] = mapped_column(default=dict)
    external_id: Mapped[str] = mapped_column(String(100), nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    account = relationship("PlatformAccount", back_populates="domains")
    dns_records = relationship("DnsRecord", back_populates="domain", cascade="all, delete-orphan")
    transfers = relationship("DomainTransfer", back_populates="domain")
