import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.platform_account import PlatformAccount
from app.tasks import sync_tasks


@pytest.mark.asyncio
async def test_run_sync_all_returns_results_in_account_order(async_session, monkeypatch):
    accounts = [
        PlatformAccount(platform="cloudflare", account_name="acct-1", credentials={}, is_active=True),
        PlatformAccount(platform="dynadot", account_name="acct-2", credentials={}, is_active=True),
        PlatformAccount(platform="spaceship", account_name="acct-3", credentials={}, is_active=True),
    ]
    async_session.add_all(accounts)
    await async_session.commit()
    for account in accounts:
        await async_session.refresh(account)

    session_factory = async_sessionmaker(async_session.bind, expire_on_commit=False)
    monkeypatch.setattr(sync_tasks, "create_session_factory", lambda: (async_session.bind, session_factory))

    status_updates = []

    async def fake_get_status():
        return status_updates[-1] if status_updates else {}

    async def fake_set_status(payload):
        status_updates.append(payload)

    async def fake_noop(*args, **kwargs):
        return True

    monkeypatch.setattr(sync_tasks.sync_job_service, "get_sync_all_status", fake_get_status)
    monkeypatch.setattr(sync_tasks.sync_job_service, "set_sync_all_status", fake_set_status)
    monkeypatch.setattr(sync_tasks.sync_job_service, "refresh_sync_all_lock", fake_noop)
    monkeypatch.setattr(sync_tasks.sync_job_service, "release_sync_all_lock", fake_noop)

    async def fake_run_sync_account_with_factory(_session_factory, account_snapshot):
        delays = {
            "acct-1": 0.03,
            "acct-2": 0.01,
            "acct-3": 0.02,
        }
        await asyncio.sleep(delays[account_snapshot["account_name"]])
        return {
            "account_id": account_snapshot["id"],
            "platform": account_snapshot["platform"],
            "account_name": account_snapshot["account_name"],
            "status": "success",
        }

    monkeypatch.setattr(sync_tasks, "_run_sync_account_with_factory", fake_run_sync_account_with_factory)

    result = await sync_tasks._run_sync_all(task_id="task-1", triggered_by=1, source="manual")

    assert [item["account_name"] for item in result["results"]] == ["acct-1", "acct-2", "acct-3"]
    assert result["current_account"] is None
    assert result["completed"] == 3
    assert result["success"] == 3
