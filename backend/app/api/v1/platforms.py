from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

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
    db: AsyncSession = Depends(get_db),
):
    rows = await platform_service.list_accounts(
        db,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return rows


@router.post("", response_model=PlatformAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_platform(
    data: PlatformAccountCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    account = await platform_service.create_account(db, data, admin.id)
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
    account = await platform_service.update_account(db, account_id, data)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return await _build_platform_response(db, account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_platform(account_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    deleted = await platform_service.delete_account(db, account_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")


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
        if result:
            return {"message": "连接测试成功", "status": "success"}
        else:
            return {"message": "认证失败，请检查凭证", "status": "failed"}
    except Exception as e:
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
        return {"synced": result.get("upserted", 0), "status": "success"}
    except Exception as e:
        await db.refresh(account)
        return {"synced": 0, "status": "failed", "error": str(e)}


@router.post("/sync-all")
async def sync_all_accounts(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.sync_service import sync_all_accounts as do_sync_all

    results = await do_sync_all(db)
    success_count = sum(1 for r in results if r.get("status") == "success")
    failed_count = len(results) - success_count
    return {
        "total": len(results),
        "success": success_count,
        "failed": failed_count,
        "results": results,
    }
