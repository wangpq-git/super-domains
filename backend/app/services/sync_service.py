import logging
from datetime import datetime
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.platform_account import PlatformAccount
from app.models.domain import Domain
from app.adapters import get_adapter
from app.core.encryption import decrypt_credentials

logger = logging.getLogger(__name__)


async def sync_account(db: AsyncSession, account_id: int) -> dict:
    result = await db.execute(
        select(PlatformAccount).where(PlatformAccount.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise ValueError(f"Account {account_id} not found")

    account.sync_status = "syncing"
    account.sync_error = None
    await db.commit()

    credentials = decrypt_credentials(account.credentials)
    adapter_cls = get_adapter(account.platform, credentials)

    try:
        async with adapter_cls:
            domains_info = await adapter_cls.list_domains()
    except Exception as e:
        account.sync_status = "failed"
        account.sync_error = str(e)
        await db.commit()
        raise

    now = datetime.utcnow()
    seen_names = set()
    upserted = 0

    for d in domains_info:
        seen_names.add(d.name)

        tld = d.tld or d.name.rsplit(".", 1)[-1] if "." in d.name else ""

        stmt = pg_insert(Domain).values(
            account_id=account.id,
            domain_name=d.name,
            tld=tld,
            status=d.status,
            registration_date=d.registration_date,
            expiry_date=d.expiry_date,
            auto_renew=d.auto_renew,
            locked=d.locked,
            whois_privacy=d.whois_privacy,
            nameservers=d.nameservers,
            external_id=d.external_id,
            raw_data=d.raw_data,
            last_synced_at=now,
        ).on_conflict_do_update(
            constraint="uq_account_domain",
            set_={
                "tld": tld,
                "status": d.status,
                "registration_date": d.registration_date,
                "expiry_date": d.expiry_date,
                "auto_renew": d.auto_renew,
                "locked": d.locked,
                "whois_privacy": d.whois_privacy,
                "nameservers": d.nameservers,
                "external_id": d.external_id,
                "raw_data": d.raw_data,
                "last_synced_at": now,
            },
        )
        await db.execute(stmt)
        upserted += 1

    removed_result = await db.execute(
        select(Domain).where(
            Domain.account_id == account.id,
            Domain.domain_name.notin_(seen_names),
        )
    )
    removed_count = 0
    for dom in removed_result.scalars().all():
        dom.status = "removed"
        removed_count += 1

    account.last_sync_at = now
    account.sync_status = "success"
    account.sync_error = None
    await db.commit()

    logger.info(
        "Synced account %d (%s): %d upserted, %d removed",
        account.id,
        account.platform,
        upserted,
        removed_count,
    )

    return {
        "account_id": account.id,
        "platform": account.platform,
        "account_name": account.account_name,
        "status": "success",
        "upserted": upserted,
        "removed": removed_count,
    }


ProgressReporter = Callable[[dict], Awaitable[None]]


async def sync_all_accounts(db: AsyncSession, progress_reporter: ProgressReporter | None = None) -> list[dict]:
    result = await db.execute(
        select(PlatformAccount).where(PlatformAccount.is_active == True)
    )
    accounts = result.scalars().all()

    results = []
    total = len(accounts)
    completed = 0

    if progress_reporter:
        await progress_reporter({
            "total": total,
            "completed": completed,
            "success": 0,
            "failed": 0,
            "current_account": accounts[0].account_name if accounts else None,
        })

    for account in accounts:
        try:
            sync_result = await sync_account(db, account.id)
            results.append(sync_result)
        except Exception as e:
            logger.error("Failed to sync account %d: %s", account.id, e)
            results.append({
                "account_id": account.id,
                "platform": account.platform,
                "account_name": account.account_name,
                "status": "failed",
                "error": str(e),
            })
        completed += 1
        if progress_reporter:
            success_count = sum(1 for item in results if item.get("status") == "success")
            failed_count = len(results) - success_count
            next_account = accounts[completed].account_name if completed < total else None
            await progress_reporter({
                "total": total,
                "completed": completed,
                "success": success_count,
                "failed": failed_count,
                "current_account": next_account,
                "last_result": results[-1],
            })

    return results
