from sqlalchemy import Column, Integer, String
from .db_config import Base,engine,session



class Domain(Base):
    __tablename__ = 'cloudflare'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False, unique=True)
    status = Column(String(255))
    email = Column(String(255))
    ns = Column(String(255))
    origin_ns = Column(String(255))

# 仅开发或首次使用时启用
Base.metadata.create_all(engine)
