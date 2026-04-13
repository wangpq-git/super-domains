import pytest
import httpx

from app.adapters import ADAPTER_REGISTRY, get_adapter
from app.adapters.cloudflare import CloudflareAdapter
from app.adapters.dynadot import DynadotAdapter, DEFAULT_DYNADOT_NAMESERVERS
from app.adapters.namecom import NameComAdapter
from app.adapters.porkbun import PorkbunAdapter
from app.adapters.spaceship import SpaceshipAdapter


def test_adapter_registry():
    assert len(ADAPTER_REGISTRY) == 9
    expected_platforms = {
        "cloudflare", "namecom", "godaddy", "namecheap",
        "porkbun", "namesilo", "dynadot", "openprovider", "spaceship",
    }
    assert set(ADAPTER_REGISTRY.keys()) == expected_platforms


def test_get_adapter():
    cf = get_adapter("cloudflare", {"api_token": "test"})
    assert isinstance(cf, CloudflareAdapter)

    nc = get_adapter("namecom", {"username": "user", "api_token": "token"})
    assert isinstance(nc, NameComAdapter)


def test_unknown_adapter():
    with pytest.raises(ValueError, match="Unsupported platform"):
        get_adapter("nonexistent_platform", {"key": "value"})


def test_spaceship_init_requires_credentials():
    with pytest.raises(ValueError, match="requires 'api_key' and 'api_secret'"):
        SpaceshipAdapter({"api_key": "only-key"})


def test_cloudflare_init():
    adapter = CloudflareAdapter({"api_token": "cf_test_token"})
    assert adapter.credentials["api_token"] == "cf_test_token"
    assert adapter._zone_cache == {}

    adapter_with_key = CloudflareAdapter({"api_key": "key123", "email": "user@example.com"})
    assert adapter_with_key.credentials["api_key"] == "key123"
    assert adapter_with_key.credentials["email"] == "user@example.com"


def test_namecom_init():
    adapter = NameComAdapter({"username": "testuser", "api_token": "test_token"})
    assert adapter.credentials["username"] == "testuser"
    assert adapter.credentials["api_token"] == "test_token"
    assert adapter._auth_header is not None


def test_namecom_init_missing_credentials():
    with pytest.raises(ValueError, match="requires 'username' and 'api_token'"):
        NameComAdapter({"username": "onlyuser"})


def test_dynadot_parse_domain_nameservers():
    adapter = DynadotAdapter({"api_key": "test"})
    domains = adapter._parse_domain_list({
        "data": {
            "domain": [
                {
                    "Name": "managed.example",
                    "Expiration": "2030-01-01",
                    "Status": "active",
                    "NameServerSettings": {
                        "Type": "Name Servers",
                        "NameServers": [
                            {"ServerName": "ns1.dynadot.com"},
                            {"ServerName": "ns2.dynadot.com"},
                        ],
                    },
                },
                {
                    "Name": "parking.example",
                    "Expiration": "2030-01-01",
                    "Status": "active",
                    "NameServerSettings": {"Type": "Dynadot Parking"},
                },
            ]
        }
    })

    assert domains[0].nameservers == ["ns1.dynadot.com", "ns2.dynadot.com"]
    assert domains[1].nameservers == DEFAULT_DYNADOT_NAMESERVERS


def test_dynadot_parse_domain_list_with_nested_main_domains_object():
    adapter = DynadotAdapter({"api_key": "test"})
    domains = adapter._parse_domain_list({
        "ListDomainInfoResponse": {
            "ResponseCode": 0,
            "Status": "success",
            "MainDomains": {
                "DomainInfo": [
                    {
                        "Name": "nested.example",
                        "Expiration": "2030-01-01",
                        "Registration": "2025-01-01",
                        "Status": "active",
                    }
                ]
            },
        }
    })

    assert len(domains) == 1
    assert domains[0].name == "nested.example"


def test_dynadot_extracts_response_error():
    adapter = DynadotAdapter({"api_key": "bad-key"})

    error = adapter._extract_api_error({
        "Response": {"ResponseCode": "-1", "Error": "invalid key"}
    })

    assert error == "invalid key (code: -1)"


@pytest.mark.asyncio
async def test_dynadot_update_nameservers_uses_set_ns(monkeypatch):
    adapter = DynadotAdapter({"api_key": "test-key"})

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status_code": 200}

    captured = {}

    class FakeClient:
        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    adapter._client = FakeClient()

    ok = await adapter.update_nameservers(
        "example.com",
        ["NS1.CLOUDFLARE.COM", "  ns2.cloudflare.com "],
    )

    assert ok is True
    assert captured["url"] == adapter.BASE_URL
    assert captured["json"] == {
        "key": "test-key",
        "command": "set_ns",
        "domain": "example.com",
        "name_server": ["ns1.cloudflare.com", "ns2.cloudflare.com"],
    }


@pytest.mark.asyncio
async def test_porkbun_get_domain_nameservers_falls_back_to_public_dns(monkeypatch):
    adapter = PorkbunAdapter({"api_key": "test", "secret_key": "secret"})

    async def fake_request(method, path, **kwargs):
        raise RuntimeError("Porkbun API error: Domain is not opted in to API access.")

    async def fake_public_lookup(domain_name):
        assert domain_name == "fallback.example"
        return ["ns1.porkbun.com", "ns2.porkbun.com"]

    monkeypatch.setattr(adapter, "_request", fake_request)
    monkeypatch.setattr(adapter, "_resolve_public_nameservers", fake_public_lookup)

    nameservers = await adapter._get_domain_nameservers("fallback.example")

    assert nameservers == ["ns1.porkbun.com", "ns2.porkbun.com"]


@pytest.mark.asyncio
async def test_porkbun_get_domain_nameservers_uses_api_response_when_available(monkeypatch):
    adapter = PorkbunAdapter({"api_key": "test", "secret_key": "secret"})

    async def fake_request(method, path, **kwargs):
        assert path == "/domain/getNs/api.example"
        return {"ns": ["NS1.PORKBUN.COM", " ns2.porkbun.com "]}

    async def fail_public_lookup(domain_name):
        raise AssertionError("public DNS lookup should not run when API returns nameservers")

    monkeypatch.setattr(adapter, "_request", fake_request)
    monkeypatch.setattr(adapter, "_resolve_public_nameservers", fail_public_lookup)

    nameservers = await adapter._get_domain_nameservers("api.example")

    assert nameservers == ["ns1.porkbun.com", "ns2.porkbun.com"]


@pytest.mark.asyncio
async def test_spaceship_authenticate_falls_back_to_header_auth(monkeypatch):
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    async with adapter:
        async def fake_request(method, path, **kwargs):
            if method == "POST" and path == "/auth/token":
                raise RuntimeError("Spaceship API error (404): missing")
            raise AssertionError("unexpected _request call")

        async def fake_probe(mode):
            return mode == "header"

        monkeypatch.setattr(adapter, "_request", fake_request)
        monkeypatch.setattr(adapter, "_probe_auth_mode", fake_probe)

        assert await adapter.authenticate() is True
        assert adapter._auth_mode == "header"


@pytest.mark.asyncio
async def test_spaceship_parse_domain_list_normalizes_payload():
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    domains = adapter._parse_domain_list({
        "data": {
            "items": [
                {
                    "domain": {"name": "Example", "extension": "COM"},
                    "status": "ACTIVE",
                    "registration_date": "2024-01-02T03:04:05Z",
                    "expiry_date": "2030-01-02T03:04:05Z",
                    "auto_renew": "yes",
                    "locked": "1",
                    "privacy": True,
                    "nameservers": ["NS1.EXAMPLE.COM", {"host": "ns2.example.com."}],
                    "id": 123,
                }
            ]
        }
    })

    assert len(domains) == 1
    domain = domains[0]
    assert domain.name == "example.com"
    assert domain.tld == "com"
    assert domain.status == "active"
    assert domain.auto_renew is True
    assert domain.locked is True
    assert domain.whois_privacy is True
    assert domain.nameservers == ["ns1.example.com", "ns2.example.com"]
    assert domain.external_id == "123"
    assert domain.registration_date == __import__("datetime").datetime(2024, 1, 2, 3, 4, 5)
    assert domain.expiry_date == __import__("datetime").datetime(2030, 1, 2, 3, 4, 5)


def test_spaceship_parse_domain_list_skips_missing_expiry():
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    domains = adapter._parse_domain_list({
        "data": [
            {"domain": "missing-expiry.com", "status": "active"}
        ]
    })

    assert domains == []


@pytest.mark.asyncio
async def test_spaceship_list_domains_uses_page_pagination(monkeypatch):
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    async with adapter:
        adapter._auth_mode = "header"
        seen_pages = []

        async def fake_request(method, path, **kwargs):
            seen_pages.append(kwargs["params"]["page"])
            page = kwargs["params"]["page"]
            if page == 1:
                return {
                    "data": [
                        {"domain": "one.com", "expiry_date": "2030-01-01T00:00:00Z"},
                        {"domain": "two.com", "expiry_date": "2030-01-01T00:00:00Z"},
                    ],
                    "pagination": {"total": 3},
                }
            return {
                "data": [
                    {"domain": "three.com", "expiry_date": "2030-01-01T00:00:00Z"},
                ],
                "pagination": {"total": 3},
            }

        monkeypatch.setattr(adapter, "_request", fake_request)

        domains = await adapter.list_domains(limit=2)

    assert seen_pages == [1, 2]
    assert [domain.name for domain in domains] == ["one.com", "two.com", "three.com"]


@pytest.mark.asyncio
async def test_spaceship_list_domains_raises_when_auth_fails(monkeypatch):
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    async with adapter:
        async def fake_authenticate():
            return False

        monkeypatch.setattr(adapter, "authenticate", fake_authenticate)

        with pytest.raises(RuntimeError, match="authentication failed"):
            await adapter.list_domains()


@pytest.mark.asyncio
async def test_spaceship_request_raises_provider_error():
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    async with adapter:
        adapter._auth_mode = "header"
        response = httpx.Response(422, json={"message": "invalid request"}, request=httpx.Request("GET", "https://spaceship.dev/api/v1/domains"))

        async def fake_client_request(*args, **kwargs):
            return response

        adapter.client.request = fake_client_request

        with pytest.raises(RuntimeError, match="invalid request"):
            await adapter._request("GET", "/domains")


@pytest.mark.asyncio
async def test_spaceship_probe_auth_mode_sets_expected_headers():
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    async with adapter:
        response = httpx.Response(200, json={"data": []}, request=httpx.Request("GET", "https://spaceship.dev/api/v1/domains"))

        async def fake_get(url, **kwargs):
            assert kwargs["params"] == {"page": 1, "per_page": 1}
            assert adapter.client.headers["X-Api-Key"] == "key"
            assert adapter.client.headers["X-Api-Secret"] == "secret"
            return response

        adapter.client.get = fake_get
        assert await adapter._probe_auth_mode("header") is True
        assert adapter._auth_mode == "header"


@pytest.mark.asyncio
async def test_spaceship_probe_auth_mode_uses_basic_header():
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    async with adapter:
        response = httpx.Response(200, json={"data": []}, request=httpx.Request("GET", "https://spaceship.dev/api/v1/domains"))

        async def fake_get(url, **kwargs):
            assert adapter.client.headers["Authorization"].startswith("Basic ")
            return response

        adapter.client.get = fake_get
        assert await adapter._probe_auth_mode("basic") is True
        assert adapter._auth_mode == "basic"


@pytest.mark.asyncio
async def test_spaceship_authenticate_uses_token_response(monkeypatch):
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    async with adapter:
        async def fake_request(method, path, **kwargs):
            assert method == "POST"
            assert path == "/auth/token"
            return {"access_token": "token-123", "expires_in": 120}

        monkeypatch.setattr(adapter, "_request", fake_request)

        assert await adapter.authenticate() is True
        assert adapter._auth_mode == "bearer"
        assert adapter._access_token == "token-123"
        assert adapter._token_expires_at is not None


@pytest.mark.asyncio
async def test_spaceship_extract_total_supports_string_value():
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    assert adapter._extract_total({"pagination": {"total": "5"}}) == 5
    assert adapter._extract_total({"meta": {"total": 7}}) == 7
    assert adapter._extract_total({}) is None


@pytest.mark.asyncio
async def test_spaceship_parse_dns_records_normalizes_values():
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    records = adapter._parse_dns_records({
        "data": [
            {"id": 1, "type": "a", "host": "www.", "data": "1.1.1.1", "ttl": "600"}
        ]
    }, "example.com")

    assert len(records) == 1
    assert records[0].external_id == "1"
    assert records[0].record_type == "A"
    assert records[0].name == "www"
    assert records[0].content == "1.1.1.1"
    assert records[0].ttl == 600


@pytest.mark.asyncio
async def test_spaceship_get_authenticated_client_applies_bearer_header(monkeypatch):
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    async with adapter:
        adapter._auth_mode = "bearer"
        adapter._access_token = "token-xyz"
        adapter._token_expires_at = __import__("datetime").datetime.utcnow().replace(microsecond=0) + __import__("datetime").timedelta(seconds=60)

        client = await adapter._get_authenticated_client()

    assert client.headers["Authorization"] == "Bearer token-xyz"


@pytest.mark.asyncio
async def test_spaceship_ensure_authenticated_raises_on_failure(monkeypatch):
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    async with adapter:
        async def fake_authenticate():
            return False

        monkeypatch.setattr(adapter, "authenticate", fake_authenticate)

        with pytest.raises(RuntimeError, match="authentication failed"):
            await adapter._ensure_authenticated()


@pytest.mark.asyncio
async def test_spaceship_parse_date_strips_timezone():
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    parsed = adapter._parse_date("2030-01-01T00:00:00+00:00")

    assert parsed == __import__("datetime").datetime(2030, 1, 1, 0, 0)


@pytest.mark.asyncio
async def test_spaceship_extract_domain_name_from_flat_payload():
    adapter = SpaceshipAdapter({"api_key": "key", "api_secret": "secret"})

    assert adapter._extract_domain_name({"domain": "Flat.COM"}) == "flat.com"
    assert adapter._extract_domain_name({"name": "Another.NET"}) == "another.net"
