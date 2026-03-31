from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
import base64

from .base import BasePlatformAdapter, DomainInfo, DnsRecordInfo
from . import register_adapter
from .rate_limiter import AsyncRateLimiter


@register_adapter('namecom')
class NameComAdapter(BasePlatformAdapter):
    BASE_URL = "https://api.name.com/v4"

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self._rate_limiter = AsyncRateLimiter(calls_per_minute=120)

        if "username" not in self.credentials or "api_token" not in self.credentials:
            raise ValueError("Name.com requires 'username' and 'api_token'")

        auth_string = f"{self.credentials['username']}:{self.credentials['api_token']}"
        self._auth_header = base64.b64encode(auth_string.encode()).decode()

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Basic {self._auth_header}",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with self._rate_limiter:
            url = f"{self.BASE_URL}{path}"
            headers = self._get_headers()
            response = await self.client.request(method, url, headers=headers, **kwargs)

            if response.status_code == 401:
                raise RuntimeError("Name.com authentication failed")

            try:
                data = response.json()
            except Exception:
                data = {}

            if response.status_code >= 400:
                error_msg = data.get("message", f"HTTP {response.status_code}")
                raise RuntimeError(f"Name.com API error: {error_msg}")

            return data

    async def authenticate(self) -> bool:
        await self._request("GET", "/hello")
        return True

    async def list_domains(self) -> List[DomainInfo]:
        domains = []
        page = 1
        per_page = 1000

        while True:
            response = await self._request(
                "GET",
                "/domains",
                params={"page": page, "perPage": per_page}
            )

            domain_list = response.get("domains", [])
            for domain_data in domain_list:
                domain_name = domain_data.get("domainName", "")
                expiry_date = None
                registration_date = None

                if domain_data.get("expireDate"):
                    try:
                        expiry_date = datetime.strptime(
                            domain_data["expireDate"], "%Y-%m-%dT%H:%M:%SZ"
                        )
                    except Exception:
                        pass

                if domain_data.get("createDate"):
                    try:
                        registration_date = datetime.strptime(
                            domain_data["createDate"], "%Y-%m-%dT%H:%M:%SZ"
                        )
                    except Exception:
                        pass

                if not expiry_date:
                    expiry_date = datetime.max.replace(tzinfo=None)

                nameservers = domain_data.get("nameservers", [])

                status = "active"
                if domain_data.get("locked"):
                    status = "locked"
                elif domain_data.get("autorenewEnabled"):
                    status = "auto_renew"

                domains.append(DomainInfo(
                    name=domain_name,
                    tld=domain_name.split(".")[-1] if "." in domain_name else "",
                    status=status,
                    registration_date=registration_date,
                    expiry_date=expiry_date,
                    auto_renew=domain_data.get("autorenewEnabled", False),
                    locked=domain_data.get("locked", True),
                    whois_privacy=domain_data.get("whoisPrivacy", False),
                    nameservers=nameservers,
                    external_id=str(domain_data.get("id", "")),
                    raw_data=domain_data
                ))

            last_page = response.get("lastPage", 1)
            if page >= last_page:
                break
            page += 1

        return domains

    async def list_dns_records(self, domain: str) -> List[DnsRecordInfo]:
        response = await self._request(
            "GET",
            f"/domains/{domain}/records"
        )

        records = []
        for record_data in response.get("records", []):
            record_type = record_data.get("type", "")
            name = record_data.get("host", "")
            if name == "@":
                name = domain
            elif name and not name.endswith(f".{domain}"):
                name = f"{name}.{domain}"

            ttl = record_data.get("ttl", 3600)
            if ttl == 0:
                ttl = 3600

            priority = record_data.get("priority")
            if record_type in ("MX", "SRV") and priority is None:
                priority = 0

            records.append(DnsRecordInfo(
                external_id=str(record_data.get("id", "")),
                record_type=record_type,
                name=name,
                content=record_data.get("answer", ""),
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
            "host": name,
            "answer": record.content,
            "ttl": record.ttl
        }

        if record.priority is not None and record.record_type in ("MX", "SRV"):
            payload["priority"] = record.priority

        response = await self._request(
            "POST",
            f"/domains/{domain}/records",
            json=payload
        )

        return str(response.get("id", ""))

    async def update_dns_record(self, domain: str, record_id: str, record: DnsRecordInfo) -> bool:
        name = record.name
        if name.endswith(f".{domain}"):
            name = name[:-(len(domain) + 1)]
        elif name == domain:
            name = "@"

        payload: Dict[str, Any] = {
            "type": record.record_type,
            "host": name,
            "answer": record.content,
            "ttl": record.ttl
        }

        if record.priority is not None and record.record_type in ("MX", "SRV"):
            payload["priority"] = record.priority

        await self._request(
            "PUT",
            f"/domains/{domain}/records/{record_id}",
            json=payload
        )

        return True

    async def delete_dns_record(self, domain: str, record_id: str) -> bool:
        await self._request(
            "DELETE",
            f"/domains/{domain}/records/{record_id}"
        )

        return True
