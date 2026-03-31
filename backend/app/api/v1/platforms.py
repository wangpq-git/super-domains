from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.platform_account import (
    PlatformAccountCreate,
    PlatformAccountUpdate,
    PlatformAccountResponse,
)
from app.services import platform_service

router = APIRouter()


@router.get("", response_model=list[PlatformAccountResponse])
async def list_platforms(db: AsyncSession = Depends(get_db)):
    rows = await platform_service.list_accounts(db)
    return rows


@router.post("", response_model=PlatformAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_platform(
    data: PlatformAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await platform_service.create_account(db, data, current_user.id)
    result = await platform_service.get_account(db, account.id)
    result_dict = {
        "id": result.id,
        "platform": result.platform,
        "account_name": result.account_name,
        "is_active": result.is_active,
        "last_sync_at": result.last_sync_at,
        "sync_status": result.sync_status,
        "sync_error": result.sync_error,
        "domain_count": 0,
        "created_at": result.created_at,
    }
    return result_dict


@router.get("/{account_id}", response_model=PlatformAccountResponse)
async def get_platform(account_id: int, db: AsyncSession = Depends(get_db)):
    account = await platform_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    result = {
        "id": account.id,
        "platform": account.platform,
        "account_name": account.account_name,
        "is_active": account.is_active,
        "last_sync_at": account.last_sync_at,
        "sync_status": account.sync_status,
        "sync_error": account.sync_error,
        "domain_count": len(account.domains),
        "created_at": account.created_at,
    }
    return result


@router.put("/{account_id}", response_model=PlatformAccountResponse)
async def update_platform(
    account_id: int,
    data: PlatformAccountUpdate,
    db: AsyncSession = Depends(get_db),
):
    account = await platform_service.update_account(db, account_id, data)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    result = {
        "id": account.id,
        "platform": account.platform,
        "account_name": account.account_name,
        "is_active": account.is_active,
        "last_sync_at": account.last_sync_at,
        "sync_status": account.sync_status,
        "sync_error": account.sync_error,
        "domain_count": len(account.domains),
        "created_at": account.created_at,
    }
    return result


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_platform(account_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await platform_service.delete_account(db, account_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")


@router.post("/{account_id}/test")
async def test_connection(account_id: int, db: AsyncSession = Depends(get_db)):
    account = await platform_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return {"message": f"Connection test for platform '{account.platform}' is not yet implemented", "status": "not_implemented"}


@router.post("/{account_id}/sync")
async def sync_account(account_id: int, db: AsyncSession = Depends(get_db)):
    account = await platform_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    account.sync_status = "syncing"
    account.sync_error = None
    await db.commit()
    return {"message": "Sync triggered", "sync_status": "syncing"}
