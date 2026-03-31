from typing import List, Optional, Dict, Any
from datetime import datetime
from .base import BasePlatformAdapter, DomainInfo, DnsRecordInfo
from . import register_adapter
import logging
import httpx

logger = logging.getLogger(__name__)


@register_adapter('spaceship')
class SpaceshipAdapter(BasePlatformAdapter):
    """
    Spaceship API adapter.

    TODO: API documentation is unclear on the following points:
    - Exact pagination format (offset-based vs cursor-based)
    - Whether DNS zone must be activated before managing records
    - Rate limiting headers and retry-after behavior
    - Exact error response format for 4xx/5xx
    """
    BASE_URL = "https://spaceship.dev/api/v1"

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.api_key = credentials.get("api_key", "")
        self.api_secret = credentials.get("api_secret", "")
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    async def _get_authenticated_client(self) -> httpx.AsyncClient:
        """Get client with auth headers, ensuring token is valid"""
        await self._ensure_authenticated()
        client = self.client
        if self._access_token:
            client.headers["Authorization"] = f"Bearer {self._access_token}"
        return client

    async def _ensure_authenticated(self) -> bool:
        """Check token validity and refresh if needed"""
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at:
                return True
            logger.info("Spaceship token expired, refreshing...")

        return await self.authenticate()

    async def authenticate(self) -> bool:
        """
        Authenticate using API key and secret.

        TODO: Confirm the exact authentication endpoint and token format.
        Current implementation assumes OAuth2-style token exchange.
        """
        try:
            # TODO: Verify if this is the correct auth endpoint
            response = await self.client.post(
                f"{self.BASE_URL}/auth/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.api_key,
                    "client_secret": self.api_secret
                }
            )

            if response.status_code == 404:
                # Try alternative auth method - direct header auth
                logger.info("Token endpoint not found, trying API key header auth")
                self._access_token = f"{self.api_key}:{self.api_secret}"
                self._token_expires_at = datetime.now().replace(microsecond=0) + httpx.Timeout(3600).connect_timeout
                # Set to 24 hours as fallback
                self._token_expires_at = datetime.now().replace(microsecond=0) + __import__("datetime").timedelta(hours=24)
                return True

            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict):
                token = data.get("access_token", data.get("token"))
                expires_in = data.get("expires_in", 3600)

                if token:
                    self._access_token = token
                    self._token_expires_at = datetime.now().replace(
                        microsecond=0
                    ) + __import__("datetime").timedelta(seconds=expires_in)
                    logger.info("Spaceship authentication successful")
                    return True

            logger.error("No token in Spaceship auth response")
            return False
        except Exception as e:
            logger.error(f"Spaceship authentication failed: {e}")
            return False

    async def list_domains(self, page: int = 1, limit: int = 50) -> List[DomainInfo]:
        """
        List all domains with pagination.

        TODO: Confirm pagination parameters (offset/limit vs page/limit vs cursor)
        """
        try:
            client = await self._get_authenticated_client()

            all_domains = []
            offset = (page - 1) * limit

            while True:
                # TODO: Verify pagination parameter names
                response = await client.get(
                    f"{self.BASE_URL}/domains",
                    params={
                        "offset": offset,
                        "limit": limit
                    }
                )
                response.raise_for_status()
                data = response.json()

                domains = self._parse_domain_list(data)
                all_domains.extend(domains)

                # Check if there are more results
                total = data.get("total", data.get("pagination", {}).get("total", 0))
                if len(all_domains) >= total or len(domains) < limit:
                    break

                offset += limit

            return all_domains
        except Exception as e:
            logger.error(f"Failed to list Spaceship domains: {e}")
            raise

    def _parse_domain_list(self, data: Any) -> List[DomainInfo]:
        """Parse Spaceship domain list response defensively"""
        domains = []
        if not isinstance(data, dict):
            return domains

        # Spaceship typically returns data under 'data', 'domains', or 'results'
        domain_data = data.get("data", data.get("domains", data.get("results", data.get("items", []))))
        if not isinstance(domain_data, list):
            domain_data = [domain_data] if domain_data else []

        for item in domain_data:
            if not isinstance(item, dict):
                continue
            try:
                name = item.get("domain", item.get("name", ""))
                if not name:
                    continue
                tld = name.split(".")[-1] if "." in name else ""

                # Parse expiry date
                expiry_str = item.get("expiry_date", item.get("expires_at", item.get("expiry", "")))
                expiry_date = self._parse_date(expiry_str) if expiry_str else datetime.now()

                # Parse registration date
                reg_str = item.get("registration_date", item.get("created_at", item.get("created", "")))
                reg_date = self._parse_date(reg_str) if reg_str else None

                # Map status
                status_map = {
                    "active": "active",
                    "inactive": "inactive",
                    "expired": "expired",
                    "pending": "pending",
                    "locked": "locked",
                    "redemption": "redemption",
                    "transferring": "transferring"
                }
                status = status_map.get(item.get("status", "active").lower(), "active")

                # Auto-renew
                auto_renew = item.get("auto_renew", item.get("autorenew", False))
                if isinstance(auto_renew, str):
                    auto_renew = auto_renew.lower() in ("true", "yes", "1")

                domains.append(DomainInfo(
                    name=name,
                    tld=tld,
                    status=status,
                    registration_date=reg_date,
                    expiry_date=expiry_date,
                    auto_renew=auto_renew,
                    locked=item.get("locked", False),
                    whois_privacy=item.get("whois_privacy", item.get("privacy", False)),
                    nameservers=item.get("nameservers") or [],
                    external_id=item.get("id", item.get("domain_id", item.get("uuid"))),
                    raw_data=item
                ))
            except Exception as e:
                logger.warning(f"Failed to parse Spaceship domain item: {item}, error: {e}")
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
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        logger.warning(f"Could not parse date: {date_str}")
        return None

    async def list_dns_records(self, domain: str) -> List[DnsRecordInfo]:
        """
        List DNS records for a domain.

        TODO: Confirm if domain needs to be URL-encoded for API calls
        """
        try:
            client = await self._get_authenticated_client()

            response = await client.get(
                f"{self.BASE_URL}/dns/zones/{domain}/records"
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

        # Spaceship returns records under 'data', 'records', or 'items'
        dns_data = data.get("data", data.get("records", data.get("items", [])))
        if not isinstance(dns_data, list):
            dns_data = [dns_data] if dns_data else []

        for item in dns_data:
            if not isinstance(item, dict):
                continue
            try:
                record_type = item.get("type", item.get("record_type", ""))
                name = item.get("name", item.get("hostname", item.get("host", "")))
                content = item.get("value", item.get("content", item.get("data", "")))
                ttl = int(item.get("ttl", 3600))
                priority = item.get("priority")

                if not record_type:
                    continue

                records.append(DnsRecordInfo(
                    external_id=item.get("id", item.get("record_id", item.get("uuid"))),
                    record_type=record_type.upper(),
                    name=name.rstrip(".") if name else "",
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
        """
        Create a DNS record.

        TODO: Confirm response format and how to extract created record ID
        """
        try:
            client = await self._get_authenticated_client()

            payload = {
                "type": record.record_type,
                "name": record.name,
                "value": record.content,
                "ttl": record.ttl
            }
            if record.priority is not None:
                payload["priority"] = record.priority

            response = await client.post(
                f"{self.BASE_URL}/dns/zones/{domain}/records",
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            # Extract created record ID
            if isinstance(data, dict):
                created = data.get("data", data.get("result", data.get("record", {})))
                if isinstance(created, list) and len(created) > 0:
                    return str(created[0].get("id", record.name))
                return str(created.get("id", record.name))

            return record.name
        except Exception as e:
            logger.error(f"Failed to create DNS record: {e}")
            raise

    async def update_dns_record(self, domain: str, record_id: str, record: DnsRecordInfo) -> bool:
        """
        Update a DNS record.

        TODO: Verify if PUT or PATCH is the correct method for updates
        """
        try:
            client = await self._get_authenticated_client()

            payload = {
                "type": record.record_type,
                "name": record.name,
                "value": record.content,
                "ttl": record.ttl
            }
            if record.priority is not None:
                payload["priority"] = record.priority

            response = await client.put(
                f"{self.BASE_URL}/dns/zones/{domain}/records/{record_id}",
                json=payload
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to update DNS record: {e}")
            return False

    async def delete_dns_record(self, domain: str, record_id: str) -> bool:
        """
        Delete a DNS record.
        """
        try:
            client = await self._get_authenticated_client()

            response = await client.delete(
                f"{self.BASE_URL}/dns/zones/{domain}/records/{record_id}"
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to delete DNS record: {e}")
            return False
