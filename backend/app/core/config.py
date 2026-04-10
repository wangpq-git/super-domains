"""
应用配置管理
使用 Pydantic Settings 管理环境变量
"""
import secrets
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

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

    # LDAP 配置
    LDAP_ENABLED: bool = True
    LDAP_HOST: str = "ldap.adsconflux.xyz"
    LDAP_PORT: int = 389
    LDAP_USE_SSL: bool = False
    LDAP_BASE_DN: str = "ou=users,dc=adsconflux,dc=xyz"
    LDAP_BIND_DN: str = "cn=read,dc=adsconflux,dc=xyz"
    LDAP_BIND_PASSWORD: str = ""
    LDAP_USER_FILTER: str = "(uid={username})"

    # 可选的环境配置
    ENV: str = "development"
    DEBUG: bool = True
    AUTO_CREATE_TABLES: bool = False

    # Feishu card template config
    FEISHU_CARD_TEMPLATE_ID: str = "AAq4KO0lxv06f"
    FEISHU_CARD_TEMPLATE_VERSION: str = "1.0.2"
    FEISHU_CARD_TABLE_VARIABLE: str = "table_raw_array_2"
    FEISHU_APPROVAL_WEBHOOK_URL: str = ""
    FEISHU_BOT_APP_ID: str = ""
    FEISHU_BOT_APP_SECRET: str = ""
    FEISHU_APPROVAL_CHAT_ID: str = ""
    FEISHU_APPROVAL_BASE_URL: str = ""
    FEISHU_APPROVAL_CALLBACK_TOKEN: str = ""
    FEISHU_APPROVAL_ENCRYPT_KEY: str = ""
    FEISHU_APPROVAL_SIGNATURE_TOLERANCE_SECONDS: int = 300
    FEISHU_APPROVAL_ADMIN_MAP: str = "{}"

# 全局配置实例
settings = Settings()
