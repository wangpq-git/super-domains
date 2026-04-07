from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
import httpx

from .base import BasePlatformAdapter, DomainInfo, DnsRecordInfo
from . import register_adapter
from .rate_limiter import AsyncRateLimiter


@register_adapter('porkbun')
class PorkbunAdapter(BasePlatformAdapter):
    BASE_URL = "https://api.porkbun.com/api/json/v3"

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self._rate_limiter = AsyncRateLimiter(calls_per_minute=60)

        if "api_key" not in self.credentials or "secret_key" not in self.credentials:
            raise ValueError("Porkbun requires 'api_key' and 'secret_key'")

    def _get_base_payload(self) -> dict:
        return {
            "apikey": self.credentials["api_key"],
            "secretapikey": self.credentials["secret_key"]
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with self._rate_limiter:
            url = f"{self.BASE_URL}{path}"

            if method == "POST":
                payload = kwargs.pop("json", {})
                kwargs["json"] = {**self._get_base_payload(), **payload}
            elif method == "GET":
                params = kwargs.pop("params", {})
                kwargs["params"] = {**self._get_base_payload(), **params}

            response = await self.client.request(method, url, **kwargs)

            if response.status_code != 200:
                try:
                    err_data = response.json()
                    err_msg = err_data.get("message", f"HTTP {response.status_code}")
                except Exception:
                    err_msg = f"HTTP {response.status_code}"
                raise RuntimeError(f"Porkbun API error: {err_msg}")

            try:
                data = response.json()
            except Exception:
                data = {}

            if data.get("status") == "ERROR":
                error_msg = data.get("message", "Unknown error")
                raise RuntimeError(f"Porkbun API error: {error_msg}")

            return data

    async def authenticate(self) -> bool:
        payload = self._get_base_payload()
        await self._request("POST", "/ping", json=payload)
        return True

    async def _get_domain_nameservers(self, domain_name: str) -> List[str]:
        try:
            response = await self._request("POST", f"/domain/getNs/{domain_name}", json={})
        except Exception:
            return []

        nameservers = response.get("ns", [])
        if not isinstance(nameservers, list):
            return []
        return [str(ns).strip().lower() for ns in nameservers if str(ns).strip()]

    async def list_domains(self) -> List[DomainInfo]:
        payload = self._get_base_payload()
        response = await self._request("POST", "/domain/listAll", json=payload)

        domains = []
        domain_list = response.get("domains", [])
        metadata_by_domain: dict[str, dict[str, Any]] = {}

        for domain_data in domain_list:
            domain_name = domain_data.get("domain", "")
            expiry_date = None
            registration_date = None

            if domain_data.get("expirydate"):
                try:
                    expiry_date = datetime.strptime(domain_data["expirydate"], "%Y-%m-%d")
                except Exception:
                    pass

            if domain_data.get("createdate"):
                try:
                    registration_date = datetime.strptime(domain_data["createdate"], "%Y-%m-%d")
                except Exception:
                    pass

            if not expiry_date:
                expiry_date = datetime.max.replace(tzinfo=None)

            auto_renew = domain_data.get("autoRenew", False)
            if isinstance(auto_renew, str):
                auto_renew = auto_renew.lower() == "true"

            locked = domain_data.get("locked", False)
            if isinstance(locked, str):
                locked = locked.lower() == "true"

            status = "active"
            if domain_data.get("status"):
                status = domain_data.get("status", "active").lower()

            metadata_by_domain[domain_name] = {
                "tld": domain_name.split(".")[-1] if "." in domain_name else "",
                "status": status,
                "registration_date": registration_date,
                "expiry_date": expiry_date,
                "auto_renew": auto_renew,
                "locked": locked,
                "raw_data": domain_data,
            }

        semaphore = asyncio.Semaphore(5)

        async def build_domain(domain_name: str) -> DomainInfo:
            async with semaphore:
                nameservers = await self._get_domain_nameservers(domain_name)
            meta = metadata_by_domain[domain_name]
            raw_data = dict(meta["raw_data"])
            raw_data["nameservers"] = nameservers
            return DomainInfo(
                name=domain_name,
                tld=meta["tld"],
                status=meta["status"],
                registration_date=meta["registration_date"],
                expiry_date=meta["expiry_date"],
                auto_renew=meta["auto_renew"],
                locked=meta["locked"],
                whois_privacy=False,
                nameservers=nameservers,
                external_id=domain_name,
                raw_data=raw_data,
            )

        if metadata_by_domain:
            domains = await asyncio.gather(*(build_domain(name) for name in metadata_by_domain))

        return domains

    async def list_dns_records(self, domain: str) -> List[DnsRecordInfo]:
        payload = self._get_base_payload()
        response = await self._request("POST", f"/dns/retrieve/{domain}", json=payload)

        records = []
        record_list = response.get("records", [])

        for record_data in record_list:
            record_type = record_data.get("type", "")

            if record_type in ("NS", "SOA"):
                continue

            name = record_data.get("host", "")
            if name == "@":
                name = domain
            elif name and not name.endswith(f".{domain}"):
                name = f"{name}.{domain}"

            content = record_data.get("content", "")
            ttl = record_data.get("ttl", 3600)
            priority = record_data.get("prio")

            try:
                ttl = int(ttl)
            except Exception:
                ttl = 3600

            try:
                priority = int(priority) if priority else None
            except Exception:
                priority = None

            records.append(DnsRecordInfo(
                external_id=record_data.get("id", f"{record_type}_{name}_{content}"),
                record_type=record_type,
                name=name,
                content=content,
                ttl=ttl,
                priority=priority,
                raw_data=record_data
            ))

        return records

    async def create_dns_record(self, domain: str, record: DnsRecordInfo) -> str:
        name = record.name
        if name.endswith(f".{domain}"):
            name = name[:-(len(domain) + 1)]
        elif name == domain:
            name = "@"

        payload: Dict[str, Any] = {
            **self._get_base_payload(),
            "type": record.record_type,
            "host": name,
            "content": record.content,
            "ttl": str(record.ttl)
        }

        if record.priority is not None:
            payload["prio"] = str(record.priority)

        response = await self._request("POST", f"/dns/create/{domain}", json=payload)

        record_id = response.get("id", f"{record.record_type}_{name}_{record.content}")
        return str(record_id)

    async def update_dns_record(self, domain: str, record_id: str, record: DnsRecordInfo) -> bool:
        name = record.name
        if name.endswith(f".{domain}"):
            name = name[:-(len(domain) + 1)]
        elif name == domain:
            name = "@"

        payload: Dict[str, Any] = {
            **self._get_base_payload(),
            "type": record.record_type,
            "host": name,
            "content": record.content,
            "ttl": str(record.ttl)
        }

        if record.priority is not None:
            payload["prio"] = str(record.priority)

        await self._request("POST", f"/dns/edit/{domain}/{record_id}", json=payload)

        return True

    async def delete_dns_record(self, domain: str, record_id: str) -> bool:
        payload = self._get_base_payload()
        await self._request("POST", f"/dns/delete/{domain}/{record_id}", json=payload)

        return True
