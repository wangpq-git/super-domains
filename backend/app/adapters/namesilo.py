from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
from lxml import etree

from .base import BasePlatformAdapter, DomainInfo, DnsRecordInfo
from . import register_adapter
from .rate_limiter import AsyncRateLimiter


@register_adapter('namesilo')
class NamesiloAdapter(BasePlatformAdapter):
    BASE_URL = "https://www.namesilo.com/api"

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self._rate_limiter = AsyncRateLimiter(calls_per_minute=60)

        if "api_key" not in self.credentials:
            raise ValueError("Namesilo requires 'api_key'")

    def _get_base_params(self) -> dict:
        return {
            "version": "1",
            "type": "xml",
            "key": self.credentials["api_key"]
        }

    async def _request(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> etree._Element:
        async with self._rate_limiter:
            all_params = {**self._get_base_params()}
            if params:
                all_params.update(params)

            url = f"{self.BASE_URL}/{endpoint}"
            response = await self.client.get(url, params=all_params)

            if response.status_code != 200:
                raise RuntimeError(f"Namesilo API HTTP error: {response.status_code}")

            try:
                root = etree.fromstring(response.content)
            except Exception as e:
                raise RuntimeError(f"Namesilo API XML parse error: {e}")

            reply = root.find("reply")
            if reply is not None:
                errors = reply.find("errors")
                if errors is not None:
                    error_items = errors.findall("error")
                    if error_items:
                        error_msg = "; ".join([err.text or "Unknown error" for err in error_items])
                        raise RuntimeError(f"Namesilo API error: {error_msg}")

            return root

    async def authenticate(self) -> bool:
        params = {"limit": "1"}
        await self._request("listDomains", params)
        return True

    async def list_domains(self) -> List[DomainInfo]:
        domains = []
        page = 1
        limit = 100

        while True:
            params = {
                "limit": str(limit),
                "page": str(page)
            }
            root = await self._request("listDomains", params)

            reply = root.find("reply")
            if reply is None:
                break

            domains_elem = reply.find("domains")
            if domains_elem is None:
                break

            domain_elements = domains_elem.findall("domain")
            if not domain_elements:
                break

            for domain_elem in domain_elements:
                domain_name = domain_elem.text
                if not domain_name:
                    continue

                expiry_date = datetime.max.replace(tzinfo=None)
                auto_renew = False
                locked = True

                try:
                    info_root = await self._request("getDomainInfo", {"domain": domain_name})
                    info_reply = info_root.find("reply")
                    if info_reply is not None:
                        expires_elem = info_reply.find("expires")
                        if expires_elem is not None and expires_elem.text:
                            try:
                                expiry_date = datetime.strptime(expires_elem.text, "%Y-%m-%d")
                            except Exception:
                                pass

                        auto_renew_elem = info_reply.find("auto_renew")
                        if auto_renew_elem is not None and auto_renew_elem.text:
                            auto_renew = auto_renew_elem.text.lower() in ("yes", "1", "true")

                        locked_elem = info_reply.find("locked")
                        if locked_elem is not None and locked_elem.text:
                            locked = locked_elem.text.lower() in ("yes", "1", "true")
                except Exception:
                    pass

                domains.append(DomainInfo(
                    name=domain_name,
                    tld=domain_name.split(".")[-1] if "." in domain_name else "",
                    status="active",
                    registration_date=None,
                    expiry_date=expiry_date,
                    auto_renew=auto_renew,
                    locked=locked,
                    whois_privacy=False,
                    nameservers=[],
                    external_id=domain_name,
                    raw_data={"domain": domain_name}
                ))

            if len(domain_elements) < limit:
                break
            page += 1

        return domains

    async def list_dns_records(self, domain: str) -> List[DnsRecordInfo]:
        params = {"domain": domain}
        root = await self._request("dnsListRecords", params)

        records = []
        reply = root.find("reply")
        if reply is None:
            return records

        for record_elem in reply.findall("resource_record"):
            record_id_elem = record_elem.find("record_id")
            record_id = record_id_elem.text if record_id_elem is not None else ""

            type_elem = record_elem.find("type")
            record_type = type_elem.text if type_elem is not None else ""

            host_elem = record_elem.find("host")
            name = host_elem.text if host_elem is not None else ""

            value_elem = record_elem.find("value")
            content = value_elem.text if value_elem is not None else ""

            ttl_elem = record_elem.find("ttl")
            ttl = 3600
            if ttl_elem is not None and ttl_elem.text:
                try:
                    ttl = int(ttl_elem.text)
                except Exception:
                    pass

            priority = None

            distance_elem = record_elem.find("distance")
            if distance_elem is not None and distance_elem.text:
                try:
                    priority = int(distance_elem.text)
                except Exception:
                    pass

            if name == "@":
                name = domain
            elif name and not name.endswith(f".{domain}"):
                name = f"{name}.{domain}"

            records.append(DnsRecordInfo(
                external_id=record_id,
                record_type=record_type,
                name=name,
                content=content,
                ttl=ttl,
                priority=priority,
                raw_data={
                    "record_id": record_id,
                    "type": record_type,
                    "host": host_elem.text if host_elem is not None else "",
                    "value": value_elem.text if value_elem is not None else "",
                    "ttl": str(ttl)
                }
            ))

        return records

    async def create_dns_record(self, domain: str, record: DnsRecordInfo) -> str:
        name = record.name
        if name.endswith(f".{domain}"):
            name = name[:-(len(domain) + 1)]
        elif name == domain:
            name = "@"

        params = {
            "domain": domain,
            "rrtype": record.record_type,
            "rrhost": name,
            "rrvalue": record.content,
            "rrttl": str(record.ttl)
        }

        if record.priority is not None:
            params["rrpriority"] = str(record.priority)

        root = await self._request("dnsAddRecord", params)

        reply = root.find("reply")
        if reply is not None:
            record_id_elem = reply.find("record_id")
            if record_id_elem is not None and record_id_elem.text:
                return record_id_elem.text

        return f"{record.record_type}_{name}_{record.content}"

    async def update_dns_record(self, domain: str, record_id: str, record: DnsRecordInfo) -> bool:
        name = record.name
        if name.endswith(f".{domain}"):
            name = name[:-(len(domain) + 1)]
        elif name == domain:
            name = "@"

        params = {
            "domain": domain,
            "rrid": record_id,
            "rrtype": record.record_type,
            "rrhost": name,
            "rrvalue": record.content,
            "rrttl": str(record.ttl)
        }

        if record.priority is not None:
            params["rrpriority"] = str(record.priority)

        await self._request("dnsUpdateRecord", params)

        return True

    async def delete_dns_record(self, domain: str, record_id: str) -> bool:
        params = {
            "domain": domain,
            "rrid": record_id
        }

        await self._request("dnsDeleteRecord", params)

        return True
