from typing import Dict
from .base import BasePlatformAdapter

ADAPTER_REGISTRY: Dict[str, type] = {}


def register_adapter(platform: str):
    def decorator(cls):
        ADAPTER_REGISTRY[platform] = cls
        return cls
    return decorator


def get_adapter(platform: str, credentials: dict) -> BasePlatformAdapter:
    cls = ADAPTER_REGISTRY.get(platform)
    if not cls:
        raise ValueError(f"Unsupported platform: {platform}")
    return cls(credentials)
