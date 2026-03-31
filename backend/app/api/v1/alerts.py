from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.alert_rule import (
    AlertRuleCreate,
    AlertRuleUpdate,
    AlertRuleResponse,
)
from app.services import alert_service

router = APIRouter()


@router.get("/rules", response_model=list[AlertRuleResponse])
async def get_alert_rules(db: AsyncSession = Depends(get_db)):
    rules = await alert_service.get_alert_rules(db)
    return rules


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    data: AlertRuleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rule = await alert_service.create_alert_rule(db, data, current_user.id)
    return rule


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: int,
    data: AlertRuleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rule = await alert_service.update_alert_rule(db, rule_id, data)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await alert_service.delete_alert_rule(db, rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")


@router.post("/check")
async def check_alerts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await alert_service.check_expiring_domains(db)
    return result


@router.get("/expiring")
async def get_expiring_domains(
    days: int = Query(default=30, ge=1, le=365, description="Days threshold"),
    db: AsyncSession = Depends(get_db),
):
    domains = await alert_service.get_expiring_domains(db, days=days)
    return {"items": domains, "total": len(domains)}
