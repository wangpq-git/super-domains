from datetime import datetime, timedelta

from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.services.dns_eligibility import is_dns_managed_by_account


def test_is_dns_managed_by_account_ignores_cloudflare_ns_for_namecheap():
    account = PlatformAccount(platform="namecheap", account_name="nc", credentials="{}")
    domain = Domain(
        domain_name="example.com",
        status="active",
        expiry_date=datetime.utcnow() + timedelta(days=30),
        nameservers=["graham.ns.cloudflare.com", "peaches.ns.cloudflare.com"],
    )
    domain.account = account

    assert is_dns_managed_by_account(domain) is False


def test_is_dns_managed_by_account_accepts_namesilo_dnsowl():
    account = PlatformAccount(platform="namesilo", account_name="ns", credentials="{}")
    domain = Domain(
        domain_name="example.com",
        status="active",
        expiry_date=datetime.utcnow() + timedelta(days=30),
        nameservers=["ns1.dnsowl.com", "ns2.dnsowl.com", "ns3.dnsowl.com"],
    )
    domain.account = account

    assert is_dns_managed_by_account(domain) is True


def test_is_dns_managed_by_account_accepts_porkbun_anycast_nameservers():
    account = PlatformAccount(platform="porkbun", account_name="pb", credentials="{}")
    domain = Domain(
        domain_name="example.com",
        status="active",
        expiry_date=datetime.utcnow() + timedelta(days=30),
        nameservers=[
            "curitiba.ns.porkbun.com",
            "fortaleza.ns.porkbun.com",
            "maceio.ns.porkbun.com",
            "salvador.ns.porkbun.com",
        ],
    )
    domain.account = account

    assert is_dns_managed_by_account(domain) is True
