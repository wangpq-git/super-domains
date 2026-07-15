from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.service_discovery import (
    ServiceDiscoveryConfigResponse,
    ServiceDiscoveryIngressListResponse,
)
from app.services import service_discovery_service

router = APIRouter()


@router.get("/config", response_model=ServiceDiscoveryConfigResponse)
async def get_service_discovery_config(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service_discovery_service.get_service_discovery_config(db)


@router.get("/ingresses", response_model=ServiceDiscoveryIngressListResponse)
async def get_namespace_ingresses(
    namespace: str | None = Query(default=None),
    refresh: bool = Query(False, description="是否强制刷新远端 Ingress 数据"),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service_discovery_service.list_ingresses(db, namespace=namespace, force_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
