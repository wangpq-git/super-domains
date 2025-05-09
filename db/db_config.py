from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

DATABASE_URL = 'mysql+pymysql://domains_rw:%EyXkyI5fb53M0#psc@10.153.20.157:3306/domains?charset=utf8mb4'

# 初始化数据库
Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # 自动检测失效连接
    pool_recycle=3600,  # 1小时回收连接
    isolation_level="READ COMMITTED"  # 明确隔离级别
)
Session = scoped_session(
    sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False  # 避免意外过期
    )
)
session = Session()

def get_session():
    """获取全新会话（每个请求独立）"""
    return Session()

def shutdown_session(exception=None):
    """请求结束时自动清理会话"""
    if Session.registry.has():
        Session.remove()
