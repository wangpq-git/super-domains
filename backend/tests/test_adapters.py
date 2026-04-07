import pytest

from app.adapters import ADAPTER_REGISTRY, get_adapter
from app.adapters.cloudflare import CloudflareAdapter
from app.adapters.dynadot import DynadotAdapter, DEFAULT_DYNADOT_NAMESERVERS
from app.adapters.namecom import NameComAdapter


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
