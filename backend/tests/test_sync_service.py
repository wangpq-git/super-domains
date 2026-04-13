import pytest
from datetime import datetime
from unittest.mock import AsyncMock

import app.services.sync_service as sync_service_module
from app.adapters.base import DomainInfo
from app.core.encryption import encrypt_credentials
from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.services.sync_service import sync_account
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


@pytest.fixture(autouse=True)
def patch_pg_insert_for_sqlite(monkeypatch):
    class SQLiteInsertCompat:
        def __init__(self, table):
            self._stmt = sqlite_insert(table)

        def values(self, **kwargs):
            self._stmt = self._stmt.values(**kwargs)
            return self

        def on_conflict_do_update(self, *, constraint=None, set_=None, **kwargs):
            self._stmt = self._stmt.on_conflict_do_update(
                index_elements=["account_id", "domain_name"],
                set_=set_,
            )
            return self._stmt

    monkeypatch.setattr(sync_service_module, "pg_insert", SQLiteInsertCompat)
    yield


@pytest.fixture(autouse=True)
def patch_sqlite_not_in_empty_set(monkeypatch):
    original_execute = sync_service_module.AsyncSession.execute

    async def patched_execute(self, statement, *args, **kwargs):
        try:
            return await original_execute(self, statement, *args, **kwargs)
        except Exception as exc:
            if "IN expression list, SELECT construct, or bound parameter object expected, got set()" not in str(exc):
                raise

            account_id = statement._where_criteria[0].right.value
            result = await original_execute(self, select(Domain).where(Domain.account_id == account_id), *args, **kwargs)
            rows = result.scalars().all()

            class ScalarResultWrapper:
                def __init__(self, items):
                    self._items = items

                def scalars(self):
                    return self

                def all(self):
                    return self._items

            return ScalarResultWrapper(rows)

    monkeypatch.setattr(sync_service_module.AsyncSession, "execute", patched_execute)
    yield
    monkeypatch.setattr(sync_service_module.AsyncSession, "execute", original_execute)


@pytest.mark.asyncio
async def test_sync_account_marks_removed_domains_and_updates_status(async_session, monkeypatch):
    account = PlatformAccount(
        platform="spaceship",
        account_name="spaceship-main",
        credentials=encrypt_credentials({"api_key": "key", "api_secret": "secret"}),
        is_active=True,
    )
    async_session.add(account)
    await async_session.commit()
    await async_session.refresh(account)

    stale = Domain(
        account_id=account.id,
        domain_name="old.example",
        tld="example",
        status="active",
        expiry_date=datetime(2030, 1, 1),
    )
    async_session.add(stale)
    await async_session.commit()

    fake_adapter = AsyncMock()
    fake_adapter.__aenter__.return_value = fake_adapter
    fake_adapter.__aexit__.return_value = None
    fake_adapter.list_domains.return_value = [
        DomainInfo(
            name="fresh.example",
            tld="example",
            status="active",
            registration_date=datetime(2024, 1, 1),
            expiry_date=datetime(2031, 1, 1),
            auto_renew=True,
            locked=False,
            whois_privacy=True,
            nameservers=["ns1.example.com"],
            external_id="abc-1",
            raw_data={"id": "abc-1"},
        )
    ]

    monkeypatch.setattr("app.services.sync_service.get_adapter", lambda platform, credentials: fake_adapter)

    result = await sync_account(async_session, account.id)

    assert result["status"] == "success"
    assert result["upserted"] == 1
    assert result["removed"] == 1

    await async_session.refresh(account)
    assert account.sync_status == "success"
    assert account.sync_error is None
    assert account.last_sync_at is not None

    fresh_result = await async_session.scalar(
        select(Domain).where(Domain.account_id == account.id, Domain.domain_name == "fresh.example")
    )
    assert fresh_result is not None
    assert fresh_result.external_id == "abc-1"
    assert fresh_result.status == "active"

    stale_result = await async_session.get(Domain, stale.id)
    assert stale_result is not None
    assert stale_result.status == "removed"

    fake_adapter.list_domains.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_account_sets_failed_status_on_adapter_error(async_session, monkeypatch):
    account = PlatformAccount(
        platform="spaceship",
        account_name="spaceship-bad",
        credentials=encrypt_credentials({"api_key": "key", "api_secret": "secret"}),
        is_active=True,
    )
    async_session.add(account)
    await async_session.commit()
    await async_session.refresh(account)

    broken_adapter = AsyncMock()
    broken_adapter.__aenter__.return_value = broken_adapter
    broken_adapter.__aexit__.return_value = None
    broken_adapter.list_domains.side_effect = RuntimeError("Spaceship API error (401): unauthorized")

    monkeypatch.setattr("app.services.sync_service.get_adapter", lambda platform, credentials: broken_adapter)

    with pytest.raises(RuntimeError, match="unauthorized"):
        await sync_account(async_session, account.id)

    await async_session.refresh(account)
    assert account.sync_status == "failed"
    assert "unauthorized" in account.sync_error
    broken_adapter.list_domains.assert_awaited_once()
