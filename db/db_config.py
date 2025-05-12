from contextlib import contextmanager
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session


if os.getenv('Env') == "test":
    DB_HOST = "test.scmp.sgt.sg2.mysql"
elif os.getenv('Env') == "prod":
    DB_HOST = "prod.scmp.sgt.sg2.mysql"
else:
    print("Env is not set")
    exit(1)
    
DB_PORT = 3306
DB_USER = "domains_rw"
DB_PASSWORD = "%EyXkyI5fb53M0#psc"
DB_NAME = "domains"
DATABASE_URL = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4'

# 初始化数据库
Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # 自动检测失效连接
    pool_recycle=3600,  # 1小时回收连接
    pool_size=5,
    max_overflow=10,
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

@contextmanager
def session_scope():
    """提供事务范围的会话管理"""
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
