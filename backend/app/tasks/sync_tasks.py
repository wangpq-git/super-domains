import asyncio
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)

async_engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionFactory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _run_sync_account(account_id: int) -> dict:
    from app.services.sync_service import sync_account

    async with AsyncSessionFactory() as db:
        try:
            result = await sync_account(db, account_id)
            return result
        except Exception:
            await db.rollback()
            raise


async def _run_sync_all() -> dict:
    from app.services.sync_service import sync_all_accounts as _sync_all

    async with AsyncSessionFactory() as db:
        return await _sync_all(db)


@celery_app.task
def sync_account_task(account_id: int) -> dict:
    return asyncio.run(_run_sync_account(account_id))


@celery_app.task
def sync_all_accounts() -> dict:
    results = asyncio.run(_run_sync_all())
    return {
        "synced_at": datetime.utcnow().isoformat(),
        "results": results,
    }


@celery_app.task
def check_expiring_domains() -> dict:
    from app.services.alert_service import run_scheduled_alerts

    async def _run():
        async with AsyncSessionFactory() as db:
            result = await run_scheduled_alerts(db)
            logger.info("Scheduled alert check: %s", result)
            return result

    return asyncio.run(_run())
