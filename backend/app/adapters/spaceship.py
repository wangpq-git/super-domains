from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from .base import BasePlatformAdapter, DomainInfo, DnsRecordInfo
from . import register_adapter
import logging
import httpx
import base64

logger = logging.getLogger(__name__)


@register_adapter('spaceship')
class SpaceshipAdapter(BasePlatformAdapter):
    BASE_URL = "https://spaceship.dev/api/v1"
    _AUTH_PROBE_LIMIT = 1

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.api_key = credentials.get("api_key", "")
        self.api_secret = credentials.get("api_secret", "")
        if not self.api_key or not self.api_secret:
            raise ValueError("Spaceship requires 'api_key' and 'api_secret'")
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._auth_mode: Optional[str] = None

    async def _get_authenticated_client(self) -> httpx.AsyncClient:
        await self._ensure_authenticated()
        client = self.client
        self._apply_auth_headers(client)
        return client

    def _clear_auth_headers(self, client: httpx.AsyncClient) -> None:
        client.headers.pop("Authorization", None)
        client.headers.pop("X-Api-Key", None)
        client.headers.pop("X-Api-Secret", None)

    def _apply_auth_headers(self, client: httpx.AsyncClient) -> None:
        self._clear_auth_headers(client)
        if self._auth_mode == "bearer" and self._access_token:
            client.headers["Authorization"] = f"Bearer {self._access_token}"
        elif self._auth_mode == "header":
            client.headers["X-Api-Key"] = self.api_key
            client.headers["X-Api-Secret"] = self.api_secret
        elif self._auth_mode == "basic":
            credentials = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()
            client.headers["Authorization"] = f"Basic {credentials}"

    async def _ensure_authenticated(self) -> None:
        if self._auth_mode == "bearer" and self._access_token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at:
                return
            logger.info("Spaceship token expired, refreshing")

        if self._auth_mode in {"header", "basic"}:
            return

        authenticated = await self.authenticate()
        if not authenticated:
            raise RuntimeError("Spaceship authentication failed")

    async def _request(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None, data: dict | None = None, headers: dict | None = None, skip_auth: bool = False) -> Any:
        client = self.client
        if not skip_auth:
            await self._ensure_authenticated()
            self._apply_auth_headers(client)

        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)

        response = await client.request(
            method,
            f"{self.BASE_URL}{path}",
            params=params,
            json=json,
            data=data,
            headers=request_headers,
        )

        if response.status_code >= 400:
            raise RuntimeError(self._extract_error(response))

        if not response.content:
            return {}

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Spaceship API returned invalid JSON for {path}") from exc

    def _extract_error(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            body = response.text[:300].strip()
            return f"Spaceship API error ({response.status_code}): {body or 'empty response'}"

        message = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message") or error.get("description")
            elif isinstance(error, str):
                message = error
            if not message:
                message = payload.get("message") or payload.get("detail") or payload.get("description")

        if not message:
            message = str(payload)[:300]
        return f"Spaceship API error ({response.status_code}): {message}"

    async def _probe_auth_mode(self, mode: str) -> bool:
        self._auth_mode = mode
        self._apply_auth_headers(self.client)
        response = await self.client.get(
            f"{self.BASE_URL}/domains",
            params={"take": self._AUTH_PROBE_LIMIT, "skip": 0},
            headers={"Accept": "application/json"},
        )
        if response.status_code < 400:
            return True
        if response.status_code in {401, 403, 404}:
            return False
        raise RuntimeError(self._extract_error(response))

    async def authenticate(self) -> bool:
        self._clear_auth_headers(self.client)
        self._access_token = None
        self._token_expires_at = None
        self._auth_mode = None

        try:
            token_data = await self._request(
                "POST",
                "/auth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.api_key,
                    "client_secret": self.api_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                skip_auth=True,
            )
            token = token_data.get("access_token", token_data.get("token")) if isinstance(token_data, dict) else None
            if token:
                expires_in = token_data.get("expires_in", 3600) if isinstance(token_data, dict) else 3600
                self._access_token = str(token)
                self._token_expires_at = datetime.utcnow().replace(microsecond=0) + timedelta(seconds=int(expires_in))
                self._auth_mode = "bearer"
                logger.info("Spaceship authentication successful via bearer token")
                return True
        except RuntimeError as exc:
            if "(404)" not in str(exc):
                logger.info("Spaceship bearer auth probe failed: %s", exc)

        for mode in ("header", "basic"):
            try:
                if await self._probe_auth_mode(mode):
                    self._auth_mode = mode
                    logger.info("Spaceship authentication successful via %s auth", mode)
                    return True
            except Exception as exc:
                logger.info("Spaceship %s auth probe failed: %s", mode, exc)

        self._auth_mode = None
        self._clear_auth_headers(self.client)
        return False

    async def list_domains(self, page: int = 1, limit: int = 100) -> List[DomainInfo]:
        all_domains = []
        current_page = max(page, 1)

        while True:
            skip = (current_page - 1) * limit
            data = await self._request(
                "GET",
                "/domains",
                params={"take": limit, "skip": skip},
            )
            domains = self._parse_domain_list(data)
            all_domains.extend(domains)

            total = self._extract_total(data)
            if total is not None and len(all_domains) >= total:
                break
            if len(domains) < limit:
                break
            current_page += 1

        return all_domains

    def _extract_total(self, data: Any) -> Optional[int]:
        if not isinstance(data, dict):
            return None
        for container in (data, data.get("pagination", {}), data.get("meta", {})):
            if isinstance(container, dict):
                value = container.get("total")
                if isinstance(value, int):
                    return value
                if isinstance(value, str) and value.isdigit():
                    return int(value)
        return None

    def _parse_domain_list(self, data: Any) -> List[DomainInfo]:
        domains = []
        if not isinstance(data, dict):
            return domains

        domain_data = data.get("data", data.get("domains", data.get("results", data.get("items", []))))
        if isinstance(domain_data, dict):
            if isinstance(domain_data.get("items"), list):
                domain_data = domain_data["items"]
            elif isinstance(domain_data.get("results"), list):
                domain_data = domain_data["results"]
            else:
                domain_data = [domain_data]
        if not isinstance(domain_data, list):
            return domains

        for item in domain_data:
            if not isinstance(item, dict):
                continue
            try:
                name = self._extract_domain_name(item)
                if not name:
                    continue
                expiry_date = self._extract_required_expiry(item)
                if not expiry_date:
                    logger.warning("Skipping Spaceship domain without expiry date: %s", item)
                    continue
                reg_date = self._parse_date(
                    item.get("registration_date")
                    or item.get("registrationDate")
                    or item.get("created_at")
                    or item.get("created")
                )
                status_raw = str(item.get("status") or item.get("lifecycleStatus") or "active").lower()
                suspensions = item.get("suspensions") if isinstance(item.get("suspensions"), list) else []
                epp_statuses = [
                    str(value).strip().lower()
                    for value in (item.get("eppStatuses") or [])
                    if str(value).strip()
                ]
                auto_renew = item.get("auto_renew", item.get("autoRenew", item.get("autorenew", False)))
                locked = item.get("locked", item.get("is_locked", bool(item.get("eppStatuses"))))
                privacy = item.get(
                    "whois_privacy",
                    item.get("privacy", item.get("privacyProtection", item.get("contactForm", False)))
                )

                normalized_status = {
                    "active": "active",
                    "registered": "active",
                    "ok": "active",
                    "inactive": "inactive",
                    "expired": "expired",
                    "pending": "pending",
                    "pendingdelete": "expired",
                    "renewalfailed": "pending",
                    "locked": "locked",
                    "redemption": "redemption",
                    "transferring": "transferring",
                }.get(status_raw.replace("-", "").replace("_", ""), status_raw or "active")
                if suspensions or any(status.endswith("hold") for status in epp_statuses):
                    normalized_status = "suspended"

                domains.append(DomainInfo(
                    name=name,
                    tld=name.rsplit(".", 1)[-1] if "." in name else "",
                    status=normalized_status,
                    registration_date=reg_date,
                    expiry_date=expiry_date,
                    auto_renew=self._to_bool(auto_renew),
                    locked=self._to_bool(locked),
                    whois_privacy=self._to_bool(privacy),
                    nameservers=self._normalize_nameservers(
                        item.get("nameservers")
                        or item.get("name_servers")
                        or item.get("nameserver")
                    ),
                    external_id=self._stringify(item.get("id") or item.get("domain_id") or item.get("uuid")),
                    raw_data=item,
                ))
            except Exception as e:
                logger.warning(f"Failed to parse Spaceship domain item: {item}, error: {e}")
        return domains

    def _extract_domain_name(self, item: dict[str, Any]) -> str:
        domain_value = item.get("domain")
        if isinstance(domain_value, dict):
            name = domain_value.get("name", "")
            extension = domain_value.get("extension", "")
            if name and extension:
                return f"{name}.{extension}".lower()
            return str(name).strip().lower()
        return str(
            item.get("domain")
            or item.get("name")
            or item.get("unicodeName")
            or item.get("asciiName")
            or ""
        ).strip().lower()

    def _extract_required_expiry(self, item: dict[str, Any]) -> Optional[datetime]:
        return self._parse_date(
            item.get("expiry_date")
            or item.get("expires_at")
            or item.get("expiry")
            or item.get("expiration_date")
            or item.get("expirationDate")
        )

    def _normalize_nameservers(self, value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, dict):
            value = (
                value.get("hosts")
                or value.get("nameservers")
                or value.get("items")
                or value.get("values")
                or value.get("nameServers")
                or value.get("records")
            )
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        normalized = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("name") or item.get("hostname") or item.get("host")
            if not item:
                continue
            normalized.append(str(item).strip().lower().rstrip("."))
        return normalized

    def _to_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "1", "on", "enabled"}
        return bool(value)

    def _stringify(self, value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        return str(value)

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string defensively"""
        if not date_str:
            return None
        normalized = date_str.strip()
        try:
            iso_value = normalized.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(iso_value)
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            pass

        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(normalized, fmt)
                return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
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
                    external_id=self._stringify(item.get("id", item.get("record_id", item.get("uuid")))),
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
