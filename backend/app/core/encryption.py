"""
凭证加密模块
使用 Fernet (AES-256-GCM) 加密敏感凭证
"""
import json
import base64
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings


def _get_fernet() -> Fernet:
    """
    获取 Fernet 实例
    使用 PBKDF2 从配置密钥派生加密密钥
    """
    # 使用固定 salt（生产环境应使用更安全的密钥管理方式）
    salt = b"domain_manage_salt"

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )

    # 从配置密钥派生 32 字节密钥
    key = base64.urlsafe_b64encode(
        kdf.derive(settings.ENCRYPTION_KEY.encode())
    )

    return Fernet(key)


def encrypt_credentials(data: dict) -> str:
    """
    加密凭证数据

    Args:
        data: 要加密的凭证字典

    Returns:
        加密后的 Base64 字符串
    """
    fernet = _get_fernet()

    # 将字典转换为 JSON 字符串
    json_data = json.dumps(data, ensure_ascii=False)
    data_bytes = json_data.encode("utf-8")

    # 加密
    encrypted_bytes = fernet.encrypt(data_bytes)

    # 返回 Base64 编码的字符串
    return encrypted_bytes.decode("utf-8")


def decrypt_credentials(encrypted: str) -> dict:
    """
    解密凭证数据

    Args:
        encrypted: 加密的 Base64 字符串

    Returns:
        解密后的凭证字典
    """
    fernet = _get_fernet()

    # 解码 Base64
    encrypted_bytes = encrypted.encode("utf-8")

    # 解密
    decrypted_bytes = fernet.decrypt(encrypted_bytes)

    # 解析 JSON
    json_data = decrypted_bytes.decode("utf-8")
    return json.loads(json_data)
