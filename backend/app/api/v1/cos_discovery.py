from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.cos_discovery import CosDiscoveryConfigResponse, CosDiscoveryDomainListResponse
from app.services import cos_discovery_service

router = APIRouter()


@router.get("/config", response_model=CosDiscoveryConfigResponse)
async def get_cos_config(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await cos_discovery_service.get_cos_discovery_config(db)


@router.get("/domains", response_model=CosDiscoveryDomainListResponse)
async def get_cos_domains(
    _current_user: User = Depends(get_current_user),
    refresh: bool = Query(False, description="是否强制刷新远端 COS 数据"),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await cos_discovery_service.list_cos_domains(db, force_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
