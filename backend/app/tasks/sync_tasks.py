import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.platform_account import PlatformAccount
from app.services import sync_job_service

logger = logging.getLogger(__name__)
SYNC_ALL_CONCURRENCY = 5


def create_session_factory():
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def _run_sync_account(account_id: int) -> dict:
    from app.services.sync_service import sync_account

    engine, session_factory = create_session_factory()
    try:
        async with session_factory() as db:
            try:
                result = await sync_account(db, account_id)
                return result
            except Exception:
                await db.rollback()
                raise
    finally:
        await engine.dispose()


async def _run_sync_account_with_factory(
    session_factory: async_sessionmaker[AsyncSession],
    account_snapshot: dict[str, Any],
) -> dict[str, Any]:
    from app.services.sync_service import sync_account

    async with session_factory() as db:
        try:
            return await sync_account(db, account_snapshot["id"])
        except Exception as exc:
            await db.rollback()
            logger.error("Failed to sync account %s: %s", account_snapshot["id"], exc)
            return {
                "account_id": account_snapshot["id"],
                "platform": account_snapshot["platform"],
                "account_name": account_snapshot["account_name"],
                "status": "failed",
                "error": str(exc),
            }


async def _run_sync_all(task_id: str, triggered_by: int | None = None, source: str = "system") -> dict:
    engine, session_factory = create_session_factory()
    try:
        async with session_factory() as db:
            started_at = sync_job_service.now_iso()
            result = await db.execute(
                select(PlatformAccount.id, PlatformAccount.platform, PlatformAccount.account_name)
                .where(PlatformAccount.is_active == True)
                .order_by(PlatformAccount.id.asc())
            )
            accounts = [
                {
                    "id": row.id,
                    "platform": row.platform,
                    "account_name": row.account_name,
                }
                for row in result.all()
            ]
            account_order = {account["id"]: index for index, account in enumerate(accounts)}
            total = len(accounts)
            progress_lock = asyncio.Lock()
            semaphore = asyncio.Semaphore(SYNC_ALL_CONCURRENCY)
            completed = 0
            success_count = 0
            failed_count = 0
            results: list[dict[str, Any]] = []
            running_accounts: set[str] = set()

            async def report_progress(update: dict[str, Any]) -> None:
                current = await sync_job_service.get_sync_all_status() or {}
                payload = {
                    **current,
                    **update,
                    "task_id": task_id,
                    "state": "running",
                    "source": source,
                    "triggered_by": triggered_by,
                    "started_at": current.get("started_at") or started_at,
                    "updated_at": sync_job_service.now_iso(),
                }
                await sync_job_service.set_sync_all_status(payload)
                await sync_job_service.refresh_sync_all_lock(task_id)

            async def sync_one(account_snapshot: dict[str, Any]) -> dict[str, Any]:
                nonlocal completed, success_count, failed_count
                async with semaphore:
                    async with progress_lock:
                        running_accounts.add(account_snapshot["account_name"])
                        await report_progress({
                            "total": total,
                            "completed": completed,
                            "success": success_count,
                            "failed": failed_count,
                            "current_account": "、".join(
                                account["account_name"]
                                for account in accounts
                                if account["account_name"] in running_accounts
                            ) or None,
                            "message": f"正在同步 {account_snapshot['account_name']}",
                        })

                    sync_result = await _run_sync_account_with_factory(session_factory, account_snapshot)

                    async with progress_lock:
                        running_accounts.discard(account_snapshot["account_name"])
                        results.append(sync_result)
                        completed += 1
                        if sync_result.get("status") == "success":
                            success_count += 1
                        else:
                            failed_count += 1
                        await report_progress({
                            "total": total,
                            "completed": completed,
                            "success": success_count,
                            "failed": failed_count,
                            "current_account": "、".join(
                                account["account_name"]
                                for account in accounts
                                if account["account_name"] in running_accounts
                            ) or None,
                            "last_result": sync_result,
                            "message": "账户同步进行中（并发执行）" if completed < total else "账户同步即将完成",
                        })
                    return sync_result

            try:
                await report_progress({
                    "message": f"开始同步全部账户（并发 {SYNC_ALL_CONCURRENCY}）",
                    "total": total,
                    "completed": 0,
                    "success": 0,
                    "failed": 0,
                    "current_account": None,
                })
                if total:
                    await asyncio.gather(*(sync_one(account_snapshot) for account_snapshot in accounts))
                results.sort(key=lambda item: account_order.get(item.get("account_id", -1), total))
                final_status = {
                    "task_id": task_id,
                    "state": "succeeded",
                    "source": source,
                    "triggered_by": triggered_by,
                    "started_at": started_at,
                    "finished_at": sync_job_service.now_iso(),
                    "updated_at": sync_job_service.now_iso(),
                    "total": total,
                    "completed": completed,
                    "success": success_count,
                    "failed": failed_count,
                    "current_account": None,
                    "results": results,
                    "message": "账户同步完成",
                }
                await sync_job_service.set_sync_all_status(final_status)
                return final_status
            except Exception as exc:
                failure_status = {
                    "task_id": task_id,
                    "state": "failed",
                    "source": source,
                    "triggered_by": triggered_by,
                    "started_at": started_at,
                    "finished_at": sync_job_service.now_iso(),
                    "updated_at": sync_job_service.now_iso(),
                    "message": str(exc),
                }
                await sync_job_service.set_sync_all_status(failure_status)
                raise
    finally:
        await sync_job_service.release_sync_all_lock(task_id)
        await engine.dispose()


@celery_app.task
def sync_account_task(account_id: int) -> dict:
    return asyncio.run(_run_sync_account(account_id))


@celery_app.task
def sync_all_accounts() -> dict:
    task_id = sync_all_accounts.request.id
    accepted = asyncio.run(sync_job_service.acquire_sync_all_lock(task_id))
    if not accepted:
        logger.info("Skip scheduled sync_all task %s because another sync is running", task_id)
        return {
            "task_id": task_id,
            "state": "skipped",
            "message": "another sync task is already running",
            "synced_at": datetime.utcnow().isoformat(),
        }
    result = asyncio.run(_run_sync_all(task_id=task_id, source="schedule"))
    result["synced_at"] = datetime.utcnow().isoformat()
    return result


@celery_app.task(bind=True, name="app.tasks.sync_tasks.sync_all_accounts_manual")
def sync_all_accounts_manual(self, triggered_by: int | None = None) -> dict:
    result = asyncio.run(_run_sync_all(task_id=self.request.id, triggered_by=triggered_by, source="manual"))
    result["synced_at"] = datetime.utcnow().isoformat()
    return result


@celery_app.task
def check_expiring_domains() -> dict:
    from app.services.alert_service import run_scheduled_alerts

    async def _run():
        engine, session_factory = create_session_factory()
        try:
            async with session_factory() as db:
                result = await run_scheduled_alerts(db)
                logger.info("Scheduled alert check: %s", result)
                return result
        finally:
            await engine.dispose()

    return asyncio.run(_run())
