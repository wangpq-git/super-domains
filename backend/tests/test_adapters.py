import pytest

from app.adapters import ADAPTER_REGISTRY, get_adapter
from app.adapters.cloudflare import CloudflareAdapter
from app.adapters.dynadot import DynadotAdapter, DEFAULT_DYNADOT_NAMESERVERS
from app.adapters.namecom import NameComAdapter
from app.adapters.porkbun import PorkbunAdapter


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
