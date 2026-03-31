from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx

from .base import BasePlatformAdapter, DomainInfo, DnsRecordInfo
from . import register_adapter
from .rate_limiter import AsyncRateLimiter


@register_adapter('cloudflare')
class CloudflareAdapter(BasePlatformAdapter):
    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self._zone_cache: Dict[str, str] = {}
        self._rate_limiter = AsyncRateLimiter(calls_per_minute=120)

    def _get_headers(self) -> dict:
        if "api_token" in self.credentials:
            return {
                "Authorization": f"Bearer {self.credentials['api_token']}",
                "Content-Type": "application/json"
            }
        elif "api_key" in self.credentials and "email" in self.credentials:
            return {
                "X-Auth-Key": self.credentials["api_key"],
                "X-Auth-Email": self.credentials["email"],
                "Content-Type": "application/json"
            }
        else:
            raise ValueError("Invalid Cloudflare credentials")

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with self._rate_limiter:
            url = f"{self.BASE_URL}{path}"
            headers = self._get_headers()
            response = await self.client.request(method, url, headers=headers, **kwargs)

            try:
                data = response.json()
            except Exception:
                data = {}

            if not data.get("success", True):
                errors = data.get("errors", [])
                error_msg = "; ".join([e.get("message", str(e)) for e in errors])
                raise RuntimeError(f"Cloudflare API error: {error_msg}")

            return data

    async def authenticate(self) -> bool:
        if "api_token" in self.credentials:
            await self._request("GET", "/user/tokens/verify")
        else:
            await self._request("GET", "/user")
        return True

    async def _get_zone_id(self, domain: str) -> Optional[str]:
        if domain in self._zone_cache:
            return self._zone_cache[domain]

        page = 1
        while True:
            response = await self._request(
                "GET",
                "/zones",
                params={"page": page, "per_page": 50, "name": domain}
            )
            zones = response.get("result", [])
            for zone in zones:
                if zone.get("name") == domain:
                    self._zone_cache[domain] = zone["id"]
                    return zone["id"]

            if page >= response.get("result_info", {}).get("total_pages", 1):
                break
            page += 1

        return None

    async def list_domains(self) -> List[DomainInfo]:
        domains = []
        page = 1

        while True:
            response = await self._request(
                "GET",
                "/zones",
                params={"page": page, "per_page": 50}
            )

            zones = response.get("result", [])
            for zone in zones:
                zone_id = zone["id"]
                domain_name = zone["name"]
                self._zone_cache[domain_name] = zone_id

                expiry_date = None
                registration_date = None
                auto_renew = False
                nameservers = zone.get("name_servers") or []

                try:
                    registrar_info = await self._request(
                        "GET",
                        f"/zones/{zone_id}/registrar/domains/{domain_name}"
                    )
                    registrar_data = registrar_info.get("result", {})
                    if registrar_data:
                        auto_renew = registrar_data.get("auto_renew", False)
                        if registrar_data.get("expires_at"):
                            try:
                                expiry_date = datetime.fromisoformat(
                                    registrar_data["expires_at"].replace("Z", "+00:00")
                                )
                            except Exception:
                                pass
                        if registrar_data.get("registered_at"):
                            try:
                                registration_date = datetime.fromisoformat(
                                    registrar_data["registered_at"].replace("Z", "+00:00")
                                )
                            except Exception:
                                pass
                except Exception:
                    pass

                if not expiry_date:
                    expiry_date = datetime.max.replace(tzinfo=None)

                domains.append(DomainInfo(
                    name=domain_name,
                    tld=domain_name.split(".")[-1],
                    status="active" if zone.get("status") == "active" else "inactive",
                    registration_date=registration_date,
                    expiry_date=expiry_date,
                    auto_renew=auto_renew,
                    locked=zone.get("owner", {}).get("type") != "external",
                    whois_privacy=False,
                    nameservers=nameservers,
                    external_id=zone_id,
                    raw_data=zone
                ))

            result_info = response.get("result_info", {})
            if page >= result_info.get("total_pages", 1):
                break
            page += 1

        return domains

    async def list_dns_records(self, domain: str) -> List[DnsRecordInfo]:
        zone_id = await self._get_zone_id(domain)
        if not zone_id:
            raise ValueError(f"Zone not found for domain: {domain}")

        records = []
        page = 1

        while True:
            response = await self._request(
                "GET",
                f"/zones/{zone_id}/dns_records",
                params={"page": page, "per_page": 100}
            )

            for record in response.get("result", []):
                records.append(DnsRecordInfo(
                    external_id=record["id"],
                    record_type=record["type"],
                    name=record["name"],
                    content=record.get("content", ""),
                    ttl=record.get("ttl", 3600),
                    priority=record.get("priority"),
                    proxied=record.get("proxied"),
                    raw_data=record
                ))

            result_info = response.get("result_info", {})
            if page >= result_info.get("total_pages", 1):
                break
            page += 1

        return records

    async def create_dns_record(self, domain: str, record: DnsRecordInfo) -> str:
        zone_id = await self._get_zone_id(domain)
        if not zone_id:
            raise ValueError(f"Zone not found for domain: {domain}")

        payload: Dict[str, Any] = {
            "type": record.record_type,
            "name": record.name,
            "content": record.content,
            "ttl": record.ttl
        }

        if record.priority is not None:
            payload["priority"] = record.priority
        if record.proxied is not None:
            payload["proxied"] = record.proxied

        response = await self._request(
            "POST",
            f"/zones/{zone_id}/dns_records",
            json=payload
        )

        result = response.get("result", {})
        return result["id"]

    async def update_dns_record(self, domain: str, record_id: str, record: DnsRecordInfo) -> bool:
        zone_id = await self._get_zone_id(domain)
        if not zone_id:
            raise ValueError(f"Zone not found for domain: {domain}")

        payload: Dict[str, Any] = {
            "type": record.record_type,
            "name": record.name,
            "content": record.content,
            "ttl": record.ttl
        }

        if record.priority is not None:
            payload["priority"] = record.priority
        if record.proxied is not None:
            payload["proxied"] = record.proxied

        await self._request(
            "PATCH",
            f"/zones/{zone_id}/dns_records/{record_id}",
            json=payload
        )

        return True

    async def delete_dns_record(self, domain: str, record_id: str) -> bool:
        zone_id = await self._get_zone_id(domain)
        if not zone_id:
            raise ValueError(f"Zone not found for domain: {domain}")

        await self._request(
            "DELETE",
            f"/zones/{zone_id}/dns_records/{record_id}"
        )

        return True
