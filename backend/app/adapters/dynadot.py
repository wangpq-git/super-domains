from typing import List, Optional, Dict, Any
from datetime import datetime
from .base import BasePlatformAdapter, DomainInfo, DnsRecordInfo
from . import register_adapter
import logging

logger = logging.getLogger(__name__)


@register_adapter('dynadot')
class DynadotAdapter(BasePlatformAdapter):
    BASE_URL = "https://api.dynadot.com/api3.json"

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.api_key = credentials.get("api_key", "")

    async def authenticate(self) -> bool:
        """Authenticate by attempting to list domains with limit=1"""
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/list_domain",
                params={"key": self.api_key, "limit": 1}
            )
            response.raise_for_status()
            data = response.json()
            # Dynadot returns various response codes; check for success
            if isinstance(data, dict):
                return data.get("status_code", 0) == 200 or "domain" in data.get("data", {})
            return True  # If we get any valid response, assume auth worked
        except Exception as e:
            logger.error(f"Dynadot authentication failed: {e}")
            return False

    async def list_domains(self) -> List[DomainInfo]:
        """List all domains"""
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/list_domain",
                params={"key": self.api_key}
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_domain_list(data)
        except Exception as e:
            logger.error(f"Failed to list Dynadot domains: {e}")
            return []

    def _parse_domain_list(self, data: Any) -> List[DomainInfo]:
        """Parse Dynadot domain list response defensively"""
        domains = []
        if not isinstance(data, dict):
            return domains

        # Dynadot may return data under different keys
        domain_data = data.get("data", {}).get("domain", [])
        if not domain_data:
            # Try alternative structure
            domain_data = data.get("domain", [])

        if not isinstance(domain_data, list):
            domain_data = [domain_data] if domain_data else []

        for item in domain_data:
            if not isinstance(item, dict):
                continue
            try:
                name = item.get("domain_name", item.get("name", ""))
                if not name:
                    continue
                tld = name.split(".")[-1] if "." in name else ""

                expiry_str = item.get("expiry_date", item.get("expiry", ""))
                expiry_date = self._parse_date(expiry_str) if expiry_str else datetime.now()

                reg_str = item.get("registration_date", item.get("created", ""))
                reg_date = self._parse_date(reg_str) if reg_str else None

                status_map = {
                    "active": "active",
                    "expired": "expired",
                    "pending": "pending",
                    "locked": "locked"
                }
                status = status_map.get(item.get("status", "active").lower(), "active")

                domains.append(DomainInfo(
                    name=name,
                    tld=tld,
                    status=status,
                    registration_date=reg_date,
                    expiry_date=expiry_date,
                    auto_renew=item.get("auto_renew", False),
                    locked=item.get("locked", False),
                    whois_privacy=item.get("whois_privacy", False),
                    nameservers=item.get("nameservers", []),
                    external_id=item.get("id", str(item.get("domain_id", ""))),
                    raw_data=item
                ))
            except Exception as e:
                logger.warning(f"Failed to parse Dynadot domain item: {item}, error: {e}")
                continue
        return domains

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string defensively"""
        if not date_str:
            return None
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%m/%d/%Y",
            "%d/%m/%Y"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        logger.warning(f"Could not parse date: {date_str}")
        return None

    async def list_dns_records(self, domain: str) -> List[DnsRecordInfo]:
        """List DNS records for a domain"""
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/get_dns",
                params={"key": self.api_key, "domain": domain}
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_dns_records(data, domain)
        except Exception as e:
            logger.error(f"Failed to list DNS records for {domain}: {e}")
            return []

    def _parse_dns_records(self, data: Any, domain: str) -> List[DnsRecordInfo]:
        """Parse DNS records response defensively"""
        records = []
        if not isinstance(data, dict):
            return records

        dns_data = data.get("data", {}).get("dns", [])
        if not dns_data:
            dns_data = data.get("dns", [])
        if not dns_data:
            # Some responses have records directly under data
            dns_data = data.get("data", [])

        if not isinstance(dns_data, list):
            dns_data = [dns_data] if dns_data else []

        for item in dns_data:
            if not isinstance(item, dict):
                continue
            try:
                record_type = item.get("type", item.get("record_type", ""))
                name = item.get("name", item.get("host", ""))
                content = item.get("value", item.get("content", item.get("data", "")))
                ttl = int(item.get("ttl", 3600))
                priority = item.get("priority")

                if not record_type or not name:
                    continue

                records.append(DnsRecordInfo(
                    external_id=item.get("id", item.get("record_id")),
                    record_type=record_type.upper(),
                    name=name,
                    content=str(content) if content else "",
                    ttl=ttl,
                    priority=priority,
                    raw_data=item
                ))
            except Exception as e:
                logger.warning(f"Failed to parse DNS record item: {item}, error: {e}")
                continue
        return records

    async def create_dns_record(self, domain: str, record: DnsRecordInfo) -> str:
        """Create a DNS record using set_dns2"""
        return await self._set_dns(domain, record, "add")

    async def update_dns_record(self, domain: str, record_id: str, record: DnsRecordInfo) -> bool:
        """Update a DNS record using set_dns2"""
        return await self._set_dns(domain, record, "edit", record_id)

    async def delete_dns_record(self, domain: str, record_id: str) -> bool:
        """Delete a DNS record using set_dns2 with empty values"""
        # Dynadot delete: set record with empty content or use delete action
        empty_record = DnsRecordInfo(
            external_id=record_id,
            record_type="",
            name="",
            content=""
        )
        return await self._set_dns(domain, empty_record, "delete", record_id)

    async def _set_dns(self, domain: str, record: DnsRecordInfo, action: str = "add", record_id: Optional[str] = None) -> str:
        """Common method for DNS operations via set_dns2"""
        try:
            payload = {
                "key": self.api_key,
                "domain": domain,
                "action": action,
                "dns": []
            }

            dns_entry = {
                "type": record.record_type,
                "name": record.name,
                "value": record.content,
                "ttl": record.ttl
            }
            if record_id:
                dns_entry["id"] = record_id
            if record.priority is not None:
                dns_entry["priority"] = record.priority

            payload["dns"].append(dns_entry)

            response = await self.client.post(
                f"{self.BASE_URL}/set_dns2",
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict):
                status_code = data.get("status_code", 0)
                if status_code == 200:
                    return record_id or record.name
                error = data.get("error", data.get("error_message", ""))
                if error:
                    logger.error(f"Dynadot set_dns2 error: {error}")
                    raise ValueError(error)

            return record_id or record.name
        except Exception as e:
            logger.error(f"Failed to {action} DNS record: {e}")
            raise
