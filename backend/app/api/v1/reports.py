from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.services import report_service

router = APIRouter()


@router.get("/overview")
async def get_overview(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await report_service.get_overview(db)


@router.get("/expiry")
async def get_expiry_report(
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await report_service.get_expiry_report(db, days)


@router.get("/platforms")
async def get_platform_report(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await report_service.get_platform_report(db)
