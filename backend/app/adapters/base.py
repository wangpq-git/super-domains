from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import httpx


class DomainInfo(BaseModel):
    name: str
    tld: str
    status: str = "active"
    registration_date: Optional[datetime] = None
    expiry_date: datetime
    auto_renew: bool = False
    locked: bool = True
    whois_privacy: bool = False
    nameservers: List[str] = []
    external_id: Optional[str] = None
    raw_data: Dict[str, Any] = {}


class DnsRecordInfo(BaseModel):
    external_id: Optional[str] = None
    record_type: str
    name: str
    content: str
    ttl: int = 3600
    priority: Optional[int] = None
    proxied: Optional[bool] = None
    raw_data: Dict[str, Any] = {}


class BasePlatformAdapter(ABC):
    def __init__(self, credentials: dict):
        self.credentials = credentials
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("Use async with")
        return self._client

    @abstractmethod
    async def authenticate(self) -> bool:
        pass

    @abstractmethod
    async def list_domains(self) -> List[DomainInfo]:
        pass

    @abstractmethod
    async def list_dns_records(self, domain: str) -> List[DnsRecordInfo]:
        pass

    @abstractmethod
    async def create_dns_record(self, domain: str, record: DnsRecordInfo) -> str:
        pass

    @abstractmethod
    async def update_dns_record(self, domain: str, record_id: str, record: DnsRecordInfo) -> bool:
        pass

    @abstractmethod
    async def delete_dns_record(self, domain: str, record_id: str) -> bool:
        pass
