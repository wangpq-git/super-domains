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
        if "api_key" in self.credentials and "email" in self.credentials:
            return {
                "X-Auth-Key": self.credentials["api_key"],
                "X-Auth-Email": self.credentials["email"],
                "Content-Type": "application/json"
            }
        elif "api_token" in self.credentials:
            return {
                "Authorization": f"Bearer {self.credentials['api_token']}",
                "Content-Type": "application/json"
            }
        else:
            raise ValueError("Cloudflare requires 'api_key' + 'email' or 'api_token'")

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with self._rate_limiter:
            url = f"{self.BASE_URL}{path}"
            headers = self._get_headers()
            response = await self.client.request(method, url, headers=headers, **kwargs)

            if response.status_code >= 400:
                try:
                    err_data = response.json()
                    errors = err_data.get("errors", [])
                    if errors:
                        error_msg = "; ".join([e.get("message", str(e)) for e in errors])
                        raise RuntimeError(f"Cloudflare API error ({response.status_code}): {error_msg}")
                except (ValueError, KeyError):
                    pass
                response.raise_for_status()

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
        import asyncio
        domains = []
        page = 1
        zones_data = []

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
                zones_data.append(zone)

            result_info = response.get("result_info", {})
            if page >= result_info.get("total_pages", 1):
                break
            page += 1

        semaphore = asyncio.Semaphore(10)

        async def fetch_registrar(zone):
            zone_id = zone["id"]
            domain_name = zone["name"]
            nameservers = zone.get("name_servers") or []
            expiry_date = None
            registration_date = None
            auto_renew = False

            async with semaphore:
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
                                ).replace(tzinfo=None)
                            except Exception:
                                pass
                        if registrar_data.get("registered_at"):
                            try:
                                registration_date = datetime.fromisoformat(
                                    registrar_data["registered_at"].replace("Z", "+00:00")
                                ).replace(tzinfo=None)
                            except Exception:
                                pass
                except Exception:
                    pass

            if not expiry_date:
                expiry_date = datetime.max.replace(tzinfo=None)

            return DomainInfo(
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
            )

        results = await asyncio.gather(*[fetch_registrar(z) for z in zones_data], return_exceptions=True)
        for r in results:
            if isinstance(r, DomainInfo):
                domains.append(r)

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

    async def create_zone(self, domain: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/zones",
            json={
                "name": domain,
                "type": "full",
                "jump_start": False,
            },
        )
        zone = response.get("result", {})
        zone_id = zone.get("id")
        if not zone_id:
            raise RuntimeError("Cloudflare zone creation returned no zone id")
        self._zone_cache[domain] = zone_id
        return {
            "zone_id": zone_id,
            "status": zone.get("status"),
            "nameservers": zone.get("name_servers") or [],
            "zone": zone,
        }

    async def ensure_cache_rule(
        self,
        domain: str,
        *,
        expression: str,
        description: str,
    ) -> dict[str, Any]:
        zone_id = await self._get_zone_id(domain)
        if not zone_id:
            raise ValueError(f"Zone not found for domain: {domain}")

        new_rule = {
            "expression": expression,
            "description": description,
            "action": "set_cache_settings",
            "action_parameters": {
                "cache": True,
            },
            "enabled": True,
        }

        response = await self._request("GET", f"/zones/{zone_id}/rulesets")
        rulesets = response.get("result", [])
        ruleset = next(
            (
                item
                for item in rulesets
                if item.get("kind") == "zone" and item.get("phase") == "http_request_cache_settings"
            ),
            None,
        )

        if ruleset:
            for rule in ruleset.get("rules", []):
                if (
                    rule.get("action") == "set_cache_settings"
                    and rule.get("expression") == expression
                    and rule.get("description") == description
                ):
                    return {
                        "zone_id": zone_id,
                        "ruleset_id": ruleset.get("id"),
                        "rule_id": rule.get("id"),
                        "created": False,
                    }

            updated = await self._request(
                "PUT",
                f"/zones/{zone_id}/rulesets/{ruleset['id']}",
                json={"rules": [*ruleset.get("rules", []), new_rule]},
            )
            updated_ruleset = updated.get("result", {})
            created_rule = next(
                (
                    rule
                    for rule in updated_ruleset.get("rules", [])
                    if rule.get("expression") == expression and rule.get("description") == description
                ),
                None,
            )
            return {
                "zone_id": zone_id,
                "ruleset_id": updated_ruleset.get("id"),
                "rule_id": created_rule.get("id") if created_rule else None,
                "created": True,
            }

        created = await self._request(
            "POST",
            f"/zones/{zone_id}/rulesets",
            json={
                "name": "Default cache rules",
                "kind": "zone",
                "phase": "http_request_cache_settings",
                "rules": [new_rule],
            },
        )
        created_ruleset = created.get("result", {})
        created_rule = (created_ruleset.get("rules") or [{}])[0]
        return {
            "zone_id": zone_id,
            "ruleset_id": created_ruleset.get("id"),
            "rule_id": created_rule.get("id"),
            "created": True,
        }
