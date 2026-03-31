from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx

from .base import BasePlatformAdapter, DomainInfo, DnsRecordInfo
from . import register_adapter
from .rate_limiter import AsyncRateLimiter


@register_adapter('godaddy')
class GoDaddyAdapter(BasePlatformAdapter):
    BASE_URL = "https://api.godaddy.com/v1"

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self._rate_limiter = AsyncRateLimiter(calls_per_minute=60)

        if "api_key" not in self.credentials or "api_secret" not in self.credentials:
            raise ValueError("GoDaddy requires 'api_key' and 'api_secret'")

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"sso-key {self.credentials['api_key']}:{self.credentials['api_secret']}",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        async with self._rate_limiter:
            url = f"{self.BASE_URL}{path}"
            headers = self._get_headers()
            response = await self.client.request(method, url, headers=headers, **kwargs)

            if response.status_code == 401:
                raise RuntimeError("GoDaddy authentication failed")

            try:
                data = response.json()
            except Exception:
                data = {}

            if response.status_code >= 400:
                if isinstance(data, list):
                    errors = "; ".join([str(e) for e in data])
                    raise RuntimeError(f"GoDaddy API error: {errors}")
                error_msg = data.get("message", f"HTTP {response.status_code}")
                raise RuntimeError(f"GoDaddy API error: {error_msg}")

            return data

    async def authenticate(self) -> bool:
        await self._request("GET", "/domains?limit=1")
        return True

    async def list_domains(self) -> List[DomainInfo]:
        domains = []
        page = 1
        limit = 100

        while True:
            response = await self._request(
                "GET",
                "/domains",
                params={"limit": limit, "offset": (page - 1) * limit}
            )

            if not isinstance(response, list):
                break

            for domain_data in response:
                domain_name = domain_data.get("domain", "")
                expiry_date = None
                registration_date = None

                if domain_data.get("expires"):
                    try:
                        expiry_date = datetime.fromisoformat(domain_data["expires"])
                    except Exception:
                        pass

                if domain_data.get("purchasePrice") and "year" in domain_data:
                    pass

                if not expiry_date:
                    expiry_date = datetime.max.replace(tzinfo=None)

                nameservers = domain_data.get("nameServers") or []

                status_map = {
                    "ACTIVE": "active",
                    "EXPIRED": "expired",
                    "GRACE": "grace",
                    "REDEMPTION": "redemption",
                    "PENDING_DELETE": "pending_delete"
                }
                status = status_map.get(domain_data.get("status"), "active")

                domains.append(DomainInfo(
                    name=domain_name,
                    tld=domain_name.split(".")[-1] if "." in domain_name else "",
                    status=status,
                    registration_date=registration_date,
                    expiry_date=expiry_date,
                    auto_renew=domain_data.get("renewAuto", False),
                    locked=domain_data.get("locked", True),
                    whois_privacy=False,
                    nameservers=nameservers,
                    external_id=domain_name,
                    raw_data=domain_data
                ))

            if len(response) < limit:
                break
            page += 1

        return domains

    async def list_dns_records(self, domain: str) -> List[DnsRecordInfo]:
        response = await self._request(
            "GET",
            f"/domains/{domain}/records"
        )

        records = []
        if not isinstance(response, list):
            return records

        for record_data in response:
            record_type = record_data.get("type", "")
            name = record_data.get("name", "")

            if name == "@" or not name:
                name = domain
            elif not name.endswith(f".{domain}"):
                name = f"{name}.{domain}"

            ttl = record_data.get("ttl", 3600)
            priority = record_data.get("priority")

            records.append(DnsRecordInfo(
                external_id=f"{record_type}_{name}_{record_data.get('data', '')}",
                record_type=record_type,
                name=name,
                content=record_data.get("data", ""),
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
            "type": record.record_type,
            "name": name,
            "data": record.content,
            "ttl": record.ttl
        }

        if record.priority is not None:
            payload["priority"] = record.priority

        await self._request(
            "PATCH",
            f"/domains/{domain}/records",
            json=[payload]
        )

        return f"{record.record_type}_{name}_{record.content}"

    async def update_dns_record(self, domain: str, record_id: str, record: DnsRecordInfo) -> bool:
        name = record.name
        if name.endswith(f".{domain}"):
            name = name[:-(len(domain) + 1)]
        elif name == domain:
            name = "@"

        payload: Dict[str, Any] = {
            "type": record.record_type,
            "name": name,
            "data": record.content,
            "ttl": record.ttl
        }

        if record.priority is not None:
            payload["priority"] = record.priority

        await self._request(
            "PUT",
            f"/domains/{domain}/records/{record.record_type}/{name}",
            json=[payload]
        )

        return True

    async def delete_dns_record(self, domain: str, record_id: str) -> bool:
        parts = record_id.split("_", 2)
        if len(parts) >= 2:
            record_type = parts[0]
            record_name = parts[1]
            if record_name.endswith(f".{domain}"):
                record_name = record_name[:-(len(domain) + 1)]
            elif record_name == domain:
                record_name = "@"

            await self._request(
                "DELETE",
                f"/domains/{domain}/records/{record_type}/{record_name}"
            )

        return True
