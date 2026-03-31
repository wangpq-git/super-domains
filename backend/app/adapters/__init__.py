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


# Auto-import all adapters to trigger @register_adapter decorators
from . import cloudflare  # noqa: F401,E402
from . import namecom  # noqa: F401,E402
from . import godaddy  # noqa: F401,E402
from . import namecheap  # noqa: F401,E402
from . import porkbun  # noqa: F401,E402
from . import namesilo  # noqa: F401,E402
from . import dynadot  # noqa: F401,E402
from . import openprovider  # noqa: F401,E402
from . import spaceship  # noqa: F401,E402
