from sqlalchemy import Column, Integer, String, DateTime, Boolean
from .db_config import Base,engine,session

class Domain(Base):
    __tablename__ = 'dynadot'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    created = Column(DateTime)
    expires = Column(DateTime)
    is_locked = Column(Boolean)
    privacy = Column(String(255))
    is_for_sale = Column(String(255))
    renew_option = Column(String(255), nullable=False)

# 仅开发或首次使用时启用
Base.metadata.create_all(engine)
