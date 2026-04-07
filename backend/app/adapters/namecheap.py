from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
import httpx
from lxml import etree

from .base import BasePlatformAdapter, DomainInfo, DnsRecordInfo
from . import register_adapter
from .rate_limiter import AsyncRateLimiter


@register_adapter('namecheap')
class NamecheapAdapter(BasePlatformAdapter):
    BASE_URL = "https://api.namecheap.com/xml.response"

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self._rate_limiter = AsyncRateLimiter(calls_per_minute=60)

        required_fields = ["api_key", "username", "client_ip"]
        for field in required_fields:
            if field not in self.credentials:
                raise ValueError(f"Namecheap requires '{field}'")

    def _get_base_params(self) -> dict:
        return {
            "ApiUser": self.credentials["username"],
            "ApiKey": self.credentials["api_key"],
            "UserName": self.credentials["username"],
            "ClientIp": self.credentials["client_ip"]
        }

    async def _request(self, params: dict) -> etree._Element:
        async with self._rate_limiter:
            all_params = {**self._get_base_params(), **params}
            response = await self.client.get(self.BASE_URL, params=all_params)

            if response.status_code != 200:
                raise RuntimeError(f"Namecheap API HTTP error: {response.status_code}")

            try:
                root = etree.fromstring(response.content)
            except Exception as e:
                raise RuntimeError(f"Namecheap API XML parse error: {e}")

            for elem in root.iter():
                if elem.tag and isinstance(elem.tag, str) and '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]

            status = root.get("Status", "")
            if status == "ERROR":
                errors = root.findall(".//Errors/Error")
                if errors:
                    error_msg = "; ".join([err.text or "Unknown error" for err in errors])
                    raise RuntimeError(f"Namecheap API error: {error_msg}")
                raw_text = etree.tostring(root, encoding="unicode", pretty_print=False)[:500]
                raise RuntimeError(f"Namecheap API error (Status=ERROR). Raw: {raw_text}")

            return root

    async def authenticate(self) -> bool:
        params = {
            "Command": "namecheap.domains.getList",
            "PageSize": "1"
        }
        await self._request(params)
        return True

    def _parse_domain_name(self, domain_name: str) -> tuple:
        if "." not in domain_name:
            return domain_name, ""
        parts = domain_name.rsplit(".", 1)
        return parts[0], parts[1]

    async def _get_domain_nameservers(self, domain_name: str) -> List[str]:
        try:
            root = await self._request({
                "Command": "namecheap.domains.getInfo",
                "DomainName": domain_name,
            })
        except Exception:
            return []

        nodes = root.findall(".//DnsDetails/Nameserver")
        nameservers = []
        for node in nodes:
            value = (node.text or "").strip().lower()
            if value:
                nameservers.append(value)
        return nameservers

    async def list_domains(self) -> List[DomainInfo]:
        domains = []
        page = 1
        page_size = 100
        domain_names: list[str] = []
        metadata_by_domain: dict[str, dict[str, Any]] = {}

        while True:
            params = {
                "Command": "namecheap.domains.getList",
                "Page": str(page),
                "PageSize": str(page_size)
            }
            root = await self._request(params)

            result = root.find(".//DomainGetListResult")
            if result is None:
                break

            domain_elements = result.findall("Domain")
            for domain_elem in domain_elements:
                domain_name = domain_elem.get("Name", "")
                expires = domain_elem.get("Expires", "")
                auto_renew = domain_elem.get("AutoRenew", "false").lower() == "true"
                is_locked = domain_elem.get("IsLocked", "false").lower() == "true"
                whois_guard = domain_elem.get("WhoisGuard", "false").lower() == "true"

                expiry_date = None
                if expires:
                    try:
                        expiry_date = datetime.strptime(expires, "%m/%d/%Y")
                    except Exception:
                        try:
                            expiry_date = datetime.fromisoformat(expires)
                        except Exception:
                            pass

                if not expiry_date:
                    expiry_date = datetime.max.replace(tzinfo=None)

                status = "active"
                if is_locked:
                    status = "locked"

                domain_names.append(domain_name)
                metadata_by_domain[domain_name] = {
                    "tld": domain_name.split(".")[-1] if "." in domain_name else "",
                    "status": status,
                    "expiry_date": expiry_date,
                    "auto_renew": auto_renew,
                    "locked": is_locked,
                    "whois_privacy": whois_guard,
                    "raw_data": {
                        "Name": domain_name,
                        "Expires": expires,
                        "AutoRenew": auto_renew,
                        "IsLocked": is_locked,
                        "WhoisGuard": whois_guard,
                    },
                }

            paging = root.find(".//Paging")
            total_items = 0
            if paging is not None:
                total_elem = paging.find("TotalItems")
                if total_elem is not None and total_elem.text:
                    try:
                        total_items = int(total_elem.text)
                    except Exception:
                        pass

            if len(domain_elements) < page_size or (total_items > 0 and page * page_size >= total_items):
                break
            page += 1

        semaphore = asyncio.Semaphore(5)

        async def build_domain(domain_name: str) -> DomainInfo:
            async with semaphore:
                nameservers = await self._get_domain_nameservers(domain_name)
            meta = metadata_by_domain[domain_name]
            raw_data = dict(meta["raw_data"])
            raw_data["Nameservers"] = nameservers
            return DomainInfo(
                name=domain_name,
                tld=meta["tld"],
                status=meta["status"],
                registration_date=None,
                expiry_date=meta["expiry_date"],
                auto_renew=meta["auto_renew"],
                locked=meta["locked"],
                whois_privacy=meta["whois_privacy"],
                nameservers=nameservers,
                external_id=domain_name,
                raw_data=raw_data,
            )

        if domain_names:
            domains = await asyncio.gather(*(build_domain(name) for name in domain_names))

        return domains

    async def list_dns_records(self, domain: str) -> List[DnsRecordInfo]:
        sld, tld = self._parse_domain_name(domain)

        params = {
            "Command": "namecheap.domains.dns.getHosts",
            "SLD": sld,
            "TLD": tld
        }
        root = await self._request(params)

        records = []
        result = root.find(".//CommandResponse")
        if result is None:
            return records

        for host_record in result.iter():
            if host_record.tag.endswith("HostRecord"):
                record_type = host_record.get("Type", "")
                name = host_record.get("Name", "")
                content = host_record.get("Address", "")
                ttl = host_record.get("TTL", "3600")
                mxpref = host_record.get("MXPref")

                if name == "@":
                    name = domain
                elif name and not name.endswith(f".{domain}"):
                    name = f"{name}.{domain}"

                try:
                    ttl_int = int(ttl)
                except Exception:
                    ttl_int = 3600

                priority = None
                if mxpref:
                    try:
                        priority = int(mxpref)
                    except Exception:
                        pass

                records.append(DnsRecordInfo(
                    external_id=f"{record_type}_{name}_{content}",
                    record_type=record_type,
                    name=name,
                    content=content,
                    ttl=ttl_int,
                    priority=priority,
                    raw_data={
                        "Type": record_type,
                        "Name": name,
                        "Address": content,
                        "TTL": ttl,
                        "MXPref": mxpref
                    }
                ))

        return records

    async def create_dns_record(self, domain: str, record: DnsRecordInfo) -> str:
        sld, tld = self._parse_domain_name(domain)

        existing_records = await self.list_dns_records(domain)

        name = record.name
        if name.endswith(f".{domain}"):
            name = name[:-(len(domain) + 1)]
        elif name == domain:
            name = "@"

        new_record = {
            "Hostname": name,
            "RecordType": record.record_type,
            "Address": record.content,
            "TTL": str(record.ttl)
        }

        if record.priority is not None and record.record_type in ("MX", "SRV"):
            new_record["MXPref"] = str(record.priority)

        all_records = existing_records + [record]

        hosts_data = []
        for rec in all_records:
            rec_name = rec.name
            if rec_name.endswith(f".{domain}"):
                rec_name = rec_name[:-(len(domain) + 1)]
            elif rec_name == domain:
                rec_name = "@"

            host_entry = {
                "Hostname": rec_name,
                "RecordType": rec.record_type,
                "Address": rec.content,
                "TTL": str(rec.ttl)
            }

            if rec.priority is not None and rec.record_type in ("MX", "SRV"):
                host_entry["MXPref"] = str(rec.priority)

            hosts_data.append(host_entry)

        params = {
            "Command": "namecheap.domains.dns.setHosts",
            "SLD": sld,
            "TLD": tld
        }

        for i, host in enumerate(hosts_data):
            params[f"HostName{i+1}"] = host.get("Hostname", "")
            params[f"RecordType{i+1}"] = host.get("RecordType", "")
            params[f"Address{i+1}"] = host.get("Address", "")
            params[f"TTL{i+1}"] = host.get("TTL", "3600")
            if host.get("MXPref"):
                params[f"MXPref{i+1}"] = host.get("MXPref")
            if host.get("Protocol"):
                params[f"Protocol{i+1}"] = host.get("Protocol")
            if host.get("Port"):
                params[f"Port{i+1}"] = host.get("Port")
            if host.get("Weight"):
                params[f"Weight{i+1}"] = host.get("Weight")

        await self._request(params)

        return f"{record.record_type}_{name}_{record.content}"

    async def update_dns_record(self, domain: str, record_id: str, record: DnsRecordInfo) -> bool:
        existing_records = await self.list_dns_records(domain)

        updated_records = []
        for rec in existing_records:
            if rec.external_id == record_id:
                updated_records.append(record)
            else:
                updated_records.append(rec)

        sld, tld = self._parse_domain_name(domain)

        params = {
            "Command": "namecheap.domains.dns.setHosts",
            "SLD": sld,
            "TLD": tld
        }

        hosts_data = []
        for rec in updated_records:
            rec_name = rec.name
            if rec_name.endswith(f".{domain}"):
                rec_name = rec_name[:-(len(domain) + 1)]
            elif rec_name == domain:
                rec_name = "@"

            host_entry = {
                "Hostname": rec_name,
                "RecordType": rec.record_type,
                "Address": rec.content,
                "TTL": str(rec.ttl)
            }

            if rec.priority is not None and rec.record_type in ("MX", "SRV"):
                host_entry["MXPref"] = str(rec.priority)

            hosts_data.append(host_entry)

        for i, host in enumerate(hosts_data):
            params[f"HostName{i+1}"] = host.get("Hostname", "")
            params[f"RecordType{i+1}"] = host.get("RecordType", "")
            params[f"Address{i+1}"] = host.get("Address", "")
            params[f"TTL{i+1}"] = host.get("TTL", "3600")
            if host.get("MXPref"):
                params[f"MXPref{i+1}"] = host.get("MXPref")

        params["HostNameCount"] = str(len(hosts_data))

        await self._request(params)

        return True

    async def delete_dns_record(self, domain: str, record_id: str) -> bool:
        existing_records = await self.list_dns_records(domain)

        remaining_records = [
            rec for rec in existing_records
            if rec.external_id != record_id
        ]

        sld, tld = self._parse_domain_name(domain)

        params = {
            "Command": "namecheap.domains.dns.setHosts",
            "SLD": sld,
            "TLD": tld
        }

        hosts_data = []
        for rec in remaining_records:
            rec_name = rec.name
            if rec_name.endswith(f".{domain}"):
                rec_name = rec_name[:-(len(domain) + 1)]
            elif rec_name == domain:
                rec_name = "@"

            host_entry = {
                "Hostname": rec_name,
                "RecordType": rec.record_type,
                "Address": rec.content,
                "TTL": str(rec.ttl)
            }

            if rec.priority is not None and rec.record_type in ("MX", "SRV"):
                host_entry["MXPref"] = str(rec.priority)

            hosts_data.append(host_entry)

        for i, host in enumerate(hosts_data):
            params[f"HostName{i+1}"] = host.get("Hostname", "")
            params[f"RecordType{i+1}"] = host.get("RecordType", "")
            params[f"Address{i+1}"] = host.get("Address", "")
            params[f"TTL{i+1}"] = host.get("TTL", "3600")
            if host.get("MXPref"):
                params[f"MXPref{i+1}"] = host.get("MXPref")

        params["HostNameCount"] = str(len(hosts_data))

        await self._request(params)

        return True
