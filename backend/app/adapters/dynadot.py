from typing import List, Optional, Dict, Any
from datetime import datetime
from .base import BasePlatformAdapter, DomainInfo, DnsRecordInfo
from . import register_adapter
import logging

logger = logging.getLogger(__name__)

DEFAULT_DYNADOT_NAMESERVERS = ["ns1.dynadot.com", "ns2.dynadot.com"]


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
                self.BASE_URL,
                params={"key": self.api_key, "command": "list_domain", "limit": 1}
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type and not response.text.strip().startswith(("{", "[")):
                logger.error(f"Dynadot API returned non-JSON response: {response.text[:200]}")
                return False
            try:
                data = response.json()
            except Exception as e:
                logger.error(f"Dynadot API JSON parse error: {e}, response: {response.text[:200]}")
                return False
            api_error = self._extract_api_error(data)
            if api_error:
                logger.error(f"Dynadot authentication failed: {api_error}")
                return False
            # Dynadot returns various response codes; check for success
            if isinstance(data, dict):
                return data.get("status_code", 0) == 200 or "domain" in data.get("data", {})
            return True  # If we get any valid response, assume auth worked
        except Exception as e:
            logger.error(f"Dynadot authentication failed: {e}")
            return False

    async def list_domains(self) -> List[DomainInfo]:
        """List all domains"""
        response = await self.client.get(
            self.BASE_URL,
            params={"key": self.api_key, "command": "list_domain"}
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type and not response.text.strip().startswith(("{", "[")):
            raise RuntimeError(f"Dynadot API returned non-JSON response: {response.text[:200]}")
        try:
            data = response.json()
        except Exception as e:
            raise RuntimeError(f"Dynadot API JSON parse error: {e}, response: {response.text[:200]}")
        api_error = self._extract_api_error(data)
        if api_error:
            raise RuntimeError(f"Dynadot API error: {api_error}")
        return self._parse_domain_list(data)

    def _parse_domain_list(self, data: Any) -> List[DomainInfo]:
        """Parse Dynadot domain list response defensively"""
        domains = []
        if not isinstance(data, dict):
            return domains

        response_data = data.get("ListDomainInfoResponse", data)
        if not isinstance(response_data, dict):
            return domains

        domain_data = self._extract_domain_items(response_data)
        if not domain_data:
            domain_data = self._extract_domain_items(data)
        if not domain_data:
            logger.warning(
                "Dynadot list_domain returned 0 parseable domains; response keys=%s nested keys=%s",
                list(data.keys()),
                list(response_data.keys()),
            )

        for item in domain_data:
            if not isinstance(item, dict):
                continue
            try:
                name = item.get("Name", item.get("domain_name", item.get("name", "")))
                if not name:
                    continue
                tld = name.split(".")[-1] if "." in name else ""

                expiry_str = item.get("Expiration", item.get("expiry_date", item.get("expiry", "")))
                expiry_date = self._parse_date(expiry_str) if expiry_str else datetime.now()

                reg_str = item.get("Registration", item.get("registration_date", item.get("created", "")))
                reg_date = self._parse_date(reg_str) if reg_str else None

                raw_status = item.get("Status", item.get("status", "active"))
                if isinstance(raw_status, str):
                    raw_status = raw_status.lower()
                status_map = {
                    "active": "active",
                    "expired": "expired",
                    "pending": "pending",
                    "locked": "locked"
                }
                status = status_map.get(raw_status, "active")

                locked_val = item.get("Locked", item.get("locked", False))
                locked = locked_val in (True, "yes", "Yes", "true", "1")

                renew_option = item.get("RenewOption", item.get("auto_renew", ""))
                auto_renew = renew_option in ("auto", True, "true", "yes")

                privacy_val = item.get("Privacy", item.get("whois_privacy", False))
                whois_privacy = privacy_val in (True, "on", "yes", "true", "1")

                ns_settings = item.get("NameServerSettings", {})
                nameservers = []
                if isinstance(ns_settings, dict):
                    ns_list = ns_settings.get("NameServers", ns_settings.get("Nameservers", ns_settings.get("nameservers", [])))
                    if isinstance(ns_list, list):
                        for ns in ns_list:
                            if isinstance(ns, dict):
                                ns_name = ns.get("ServerName", ns.get("ServName", ns.get("name", ns.get("value", ""))))
                                if ns_name:
                                    nameservers.append(ns_name)
                            elif isinstance(ns, str):
                                nameservers.append(ns)
                    ns_type = str(ns_settings.get("Type", "")).lower()
                    if not nameservers and ns_type.startswith("dynadot"):
                        nameservers = DEFAULT_DYNADOT_NAMESERVERS.copy()

                domains.append(DomainInfo(
                    name=name,
                    tld=tld,
                    status=status,
                    registration_date=reg_date,
                    expiry_date=expiry_date,
                    auto_renew=auto_renew,
                    locked=locked,
                    whois_privacy=whois_privacy,
                    nameservers=nameservers,
                    external_id=item.get("id", str(item.get("domain_id", name))),
                    raw_data=item
                ))
            except Exception as e:
                logger.warning(f"Failed to parse Dynadot domain item: {item}, error: {e}")
                continue
        return domains

    def _extract_domain_items(self, payload: Any) -> List[dict]:
        if not payload:
            return []

        candidate_keys = (
            "MainDomains",
            "domain",
            "domains",
            "Domain",
            "DomainInfo",
            "DomainList",
        )

        if isinstance(payload, list):
            flattened = []
            for item in payload:
                if isinstance(item, dict) and any(
                    key in item for key in ("Name", "domain_name", "name")
                ):
                    flattened.append(item)
                else:
                    flattened.extend(self._extract_domain_items(item))
            return flattened

        if not isinstance(payload, dict):
            return []

        for key in candidate_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = self._extract_domain_items(value)
                if nested:
                    return nested

        nested_data = payload.get("data")
        if isinstance(nested_data, (dict, list)):
            nested = self._extract_domain_items(nested_data)
            if nested:
                return nested

        if any(key in payload for key in ("Name", "domain_name", "name")):
            return [payload]

        flattened = []
        for value in payload.values():
            if isinstance(value, (dict, list)):
                flattened.extend(self._extract_domain_items(value))
        return flattened

    def _extract_api_error(self, data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return None

        response = data.get("Response")
        if isinstance(response, dict):
            error = response.get("Error") or response.get("error")
            code = response.get("ResponseCode") or response.get("response_code")
            if error:
                return f"{error} (code: {code})" if code is not None else str(error)

        error = data.get("error") or data.get("Error") or data.get("error_message")
        if error:
            code = data.get("status_code") or data.get("code") or data.get("ResponseCode")
            if code is not None:
                return f"{error} (code: {code})"
            return str(error)

        return None

    def _parse_date(self, date_val) -> Optional[datetime]:
        """Parse date value defensively — handles both timestamps (ms) and date strings"""
        if not date_val:
            return None
        # Handle Unix timestamp in milliseconds (Dynadot API v3 format)
        if isinstance(date_val, (int, float)):
            try:
                if date_val > 1e12:  # milliseconds
                    return datetime.fromtimestamp(date_val / 1000)
                return datetime.fromtimestamp(date_val)
            except Exception:
                pass
        # Handle string timestamps
        date_str = str(date_val)
        if date_str.isdigit():
            try:
                ts = int(date_str)
                if ts > 1e12:
                    return datetime.fromtimestamp(ts / 1000)
                return datetime.fromtimestamp(ts)
            except Exception:
                pass
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
        logger.warning(f"Could not parse date: {date_val}")
        return None

    async def list_dns_records(self, domain: str) -> List[DnsRecordInfo]:
        """List DNS records for a domain"""
        try:
            response = await self.client.get(
                self.BASE_URL,
                params={"key": self.api_key, "command": "get_dns", "domain": domain}
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
                "command": "set_dns2",
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
                self.BASE_URL,
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

    async def update_nameservers(self, domain: str, nameservers: List[str]) -> bool:
        normalized = [str(ns).strip().lower() for ns in nameservers if str(ns).strip()]
        if len(normalized) < 2:
            raise ValueError("At least 2 nameservers are required")

        response = await self.client.post(
            self.BASE_URL,
            json={
                "key": self.api_key,
                "command": "set_ns",
                "domain": domain,
                "name_server": normalized,
            },
        )
        response.raise_for_status()
        data = response.json()

        api_error = self._extract_api_error(data)
        if api_error:
            raise RuntimeError(f"Dynadot API error: {api_error}")

        if isinstance(data, dict) and data.get("status_code") not in (None, 200):
            raise RuntimeError(f"Dynadot API error: unexpected status {data.get('status_code')}")

        return True
