from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.models.user import User
from app.schemas.system_setting import (
    SystemSettingListResponse,
    SystemSettingPublicResponse,
    SystemSettingUpdateRequest,
)
from app.services import system_setting_service

router = APIRouter()


@router.get("", response_model=SystemSettingListResponse)
async def get_system_settings(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await system_setting_service.list_settings(db)}


@router.put("", response_model=SystemSettingListResponse)
async def save_system_settings(
    body: SystemSettingUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await system_setting_service.update_settings(
            db,
            admin,
            [{"key": item.key, "value": item.value} for item in body.items],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items}


@router.get("/public", response_model=SystemSettingPublicResponse)
async def get_public_settings(db: AsyncSession = Depends(get_db)):
    return {"items": await system_setting_service.list_public_settings(db)}
