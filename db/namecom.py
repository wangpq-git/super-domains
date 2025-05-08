from sqlalchemy import Column, Integer, String, DateTime, Boolean
from .db_config import Base,engine,session


class Domain(Base):
    __tablename__ = 'namecom'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    is_locked = Column(Boolean)
    auto_renew = Column(Boolean)
    created = Column(DateTime)
    expires = Column(DateTime)


# 仅开发或首次使用时启用
Base.metadata.create_all(engine)
