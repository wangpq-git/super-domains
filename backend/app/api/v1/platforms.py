from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from uuid import uuid4

from app.api.deps import get_db, get_current_user, require_admin
from app.models.user import User
from app.core.config import settings
from app.schemas.platform_account import (
    PlatformAccountCreate,
    PlatformAccountUpdate,
    PlatformAccountResponse,
    PlatformAccountListResponse,
)
from app.services import platform_service
from app.services import audit_log_service
from app.services import sync_job_service
from app.tasks.sync_tasks import sync_all_accounts_manual

router = APIRouter()


async def _build_platform_response(db: AsyncSession, account) -> dict:
    domain_count = await platform_service.get_account_domain_count(db, account.id)
    return {
        "id": account.id,
        "platform": account.platform,
        "account_name": account.account_name,
        "is_active": account.is_active,
        "last_sync_at": account.last_sync_at,
        "sync_status": account.sync_status,
        "sync_error": account.sync_error,
        "domain_count": domain_count,
        "created_at": account.created_at,
    }


@router.get("", response_model=PlatformAccountListResponse)
async def list_platforms(
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向 asc/desc"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    platform: str = Query("", description="平台筛选"),
    sync_status: str = Query("", description="同步状态筛选"),
    keyword: str = Query("", description="账户关键词搜索"),
    db: AsyncSession = Depends(get_db),
):
    rows = await platform_service.list_accounts(
        db,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
        platform=platform or None,
        sync_status=sync_status or None,
        keyword=keyword or None,
    )
    return rows


@router.post("", response_model=PlatformAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_platform(
    data: PlatformAccountCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    account = await platform_service.create_account(db, data, admin.id)
    await audit_log_service.add_audit_log(
        db,
        user_id=admin.id,
        action="platform.create",
        target_type="platform_account",
        target_id=account.id,
        detail={"platform": account.platform, "account_name": account.account_name},
    )
    await db.commit()
    result = await platform_service.get_account(db, account.id)
    return await _build_platform_response(db, result)


@router.get("/{account_id}", response_model=PlatformAccountResponse)
async def get_platform(account_id: int, db: AsyncSession = Depends(get_db)):
    account = await platform_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return await _build_platform_response(db, account)


@router.put("/{account_id}", response_model=PlatformAccountResponse)
async def update_platform(
    account_id: int,
    data: PlatformAccountUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    before = await platform_service.get_account(db, account_id)
    before_snapshot = {
        "account_name": before.account_name if before else None,
        "is_active": before.is_active if before else None,
    }
    account = await platform_service.update_account(db, account_id, data)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    await audit_log_service.add_audit_log(
        db,
        user_id=admin.id,
        action="platform.update",
        target_type="platform_account",
        target_id=account.id,
        detail={
            "platform": account.platform,
            "account_name": account.account_name,
            "before": before_snapshot,
            "after": {
                "account_name": account.account_name,
                "is_active": account.is_active,
            },
        },
    )
    await db.commit()
    return await _build_platform_response(db, account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_platform(account_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    account = await platform_service.get_account(db, account_id)
    deleted = await platform_service.delete_account(db, account_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    await audit_log_service.add_audit_log(
        db,
        user_id=admin.id,
        action="platform.delete",
        target_type="platform_account",
        target_id=account_id,
        detail={
            "platform": account.platform if account else None,
            "account_name": account.account_name if account else None,
        },
    )
    await db.commit()


@router.post("/{account_id}/test")
async def test_connection(account_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    account = await platform_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    from app.core.encryption import decrypt_credentials
    from app.adapters import get_adapter

    credentials = decrypt_credentials(account.credentials)
    adapter = get_adapter(account.platform, credentials)
    try:
        async with adapter:
            result = await adapter.authenticate()
        await audit_log_service.add_audit_log(
            db,
            user_id=admin.id,
            action="platform.test_connection",
            target_type="platform_account",
            target_id=account.id,
            detail={"platform": account.platform, "account_name": account.account_name, "status": "success" if result else "failed"},
        )
        await db.commit()
        if result:
            return {"message": "连接测试成功", "status": "success"}
        else:
            return {"message": "认证失败，请检查凭证", "status": "failed"}
    except Exception as e:
        await audit_log_service.add_audit_log(
            db,
            user_id=admin.id,
            action="platform.test_connection",
            target_type="platform_account",
            target_id=account.id,
            detail={"platform": account.platform, "account_name": account.account_name, "status": "failed", "error": str(e)},
        )
        await db.commit()
        return {"message": f"连接测试失败: {str(e)}", "status": "failed"}


@router.post("/{account_id}/sync")
async def sync_account(account_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = aioredis.from_url(settings.REDIS_URL)
    key = f"sync_rate:{current_user.id}"
    count = await r.get(key)
    if count and int(count) >= 3:
        await r.aclose()
        raise HTTPException(status_code=429, detail="同步频率过高，每5分钟最多3次")
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, 300)
    await pipe.execute()
    await r.aclose()

    account = await platform_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    from app.services.sync_service import sync_account as do_sync

    try:
        result = await do_sync(db, account_id)
        await audit_log_service.add_audit_log(
            db,
            user_id=current_user.id,
            action="platform.sync",
            target_type="platform_account",
            target_id=account.id,
            detail={"platform": account.platform, "account_name": account.account_name, "status": "success", "synced": result.get("upserted", 0)},
        )
        await db.commit()
        return {"synced": result.get("upserted", 0), "status": "success"}
    except Exception as e:
        await db.refresh(account)
        await audit_log_service.add_audit_log(
            db,
            user_id=current_user.id,
            action="platform.sync",
            target_type="platform_account",
            target_id=account.id,
            detail={"platform": account.platform, "account_name": account.account_name, "status": "failed", "error": str(e)},
        )
        await db.commit()
        return {"synced": 0, "status": "failed", "error": str(e)}


@router.post("/sync-all")
async def sync_all_accounts(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    current_status = await sync_job_service.get_sync_all_status()
    current_lock_owner = await sync_job_service.get_sync_all_lock_owner()
    if current_status and current_status.get("state") in {"queued", "running"} and current_lock_owner:
        return {
            "accepted": False,
            "detail": "已有同步任务执行中，请稍后查看进度",
            "task": current_status,
        }

    task_id = str(uuid4())
    locked = await sync_job_service.acquire_sync_all_lock(task_id)
    if not locked:
        current_status = await sync_job_service.get_sync_all_status()
        return {
            "accepted": False,
            "detail": "已有同步任务执行中，请稍后查看进度",
            "task": current_status,
        }
    sync_all_accounts_manual.apply_async(args=[current_user.id], task_id=task_id)

    status_payload = {
        "task_id": task_id,
        "state": "queued",
        "source": "manual",
        "triggered_by": current_user.id,
        "queued_at": sync_job_service.now_iso(),
        "updated_at": sync_job_service.now_iso(),
        "total": 0,
        "completed": 0,
        "success": 0,
        "failed": 0,
        "message": "同步任务已提交，正在排队执行",
    }
    await sync_job_service.set_sync_all_status(status_payload)

    await audit_log_service.add_audit_log(
        db,
        user_id=current_user.id,
        action="platform.sync_all",
        target_type="platform_account",
        target_id=None,
        detail={"task_id": task_id, "status": "queued"},
    )
    await db.commit()
    return {
        "accepted": True,
        "detail": "同步任务已提交",
        "task": status_payload,
    }


@router.get("/sync-all/status")
async def get_sync_all_accounts_status(current_user: User = Depends(get_current_user)):
    status_payload = await sync_job_service.get_sync_all_status()
    if not status_payload:
        return {
            "state": "idle",
            "message": "当前没有同步任务",
        }
    if status_payload.get("state") in {"queued", "running"}:
        current_lock_owner = await sync_job_service.get_sync_all_lock_owner()
        if not current_lock_owner:
            return {
                **status_payload,
                "state": "failed",
                "message": "同步任务已中断，可重新发起",
            }
    return status_payload
