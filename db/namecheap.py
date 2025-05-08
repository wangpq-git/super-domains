from sqlalchemy import Column, Integer, String, DateTime, Boolean
from .db_config import Base,engine,session

class Domain(Base):
    __tablename__ = 'namecheap'

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_id = Column(Integer, unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    created = Column(DateTime)
    expires = Column(DateTime)
    is_expired = Column(Boolean)
    is_locked = Column(Boolean)
    auto_renew = Column(Boolean)
    whois_guard = Column(String(50))
    is_our_dns = Column(Boolean)


# 仅开发或首次使用时启用
Base.metadata.create_all(engine)
