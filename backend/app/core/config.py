"""
应用配置管理
使用 Pydantic Settings 管理环境变量
"""
import secrets
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置类"""

    # 应用信息
    APP_NAME: str = "Domain Manage"

    # 数据库配置
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/domain_manage"

    # Redis 配置
    REDIS_URL: str = "redis://redis:6379/0"

    # JWT 配置
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 小时

    # 加密密钥 - 用于凭证加密
    ENCRYPTION_KEY: str = secrets.token_urlsafe(32)

    # 可选的环境配置
    ENV: str = "development"
    DEBUG: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 全局配置实例
settings = Settings()
