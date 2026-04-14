from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, require_admin
from app.models.user import User
from app.schemas.change_request import ChangeRequestListResponse, ChangeRequestRejectBody, ChangeRequestResponse
from app.services import audit_log_service, change_request_service

router = APIRouter()


@router.get("", response_model=ChangeRequestListResponse)
async def list_change_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    operation_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await change_request_service.list_change_requests(
        db,
        current_user,
        page=page,
        page_size=page_size,
        status=status_filter,
        operation_type=operation_type,
        keyword=keyword,
    )


@router.get("/{request_id}", response_model=ChangeRequestResponse)
async def get_change_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    change_request = await change_request_service.get_change_request(db, request_id, current_user)
    if not change_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")
    return change_request


@router.post("/{request_id}/approve", response_model=ChangeRequestResponse)
async def approve_change_request(
    request_id: int,
    approver: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    change_request = await change_request_service.get_change_request(db, request_id, approver)
    if not change_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")
    try:
        result = await change_request_service.approve_change_request(db, change_request, approver)
        await audit_log_service.add_audit_log(
            db,
            user_id=approver.id,
            action="change_request.approve",
            target_type="change_request",
            target_id=request_id,
            detail={"request_no": result.request_no, "operation_type": result.operation_type, "domain_id": result.domain_id},
        )
        await db.commit()
        return result
    except ValueError as exc:
        if change_request_service.is_change_request_processed(change_request):
            return await change_request_service.get_change_request_by_id(db, request_id) or change_request
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{request_id}/reject", response_model=ChangeRequestResponse)
async def reject_change_request(
    request_id: int,
    body: ChangeRequestRejectBody,
    approver: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    change_request = await change_request_service.get_change_request(db, request_id, approver)
    if not change_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")
    try:
        result = await change_request_service.reject_change_request(db, change_request, approver, body.reason)
        await audit_log_service.add_audit_log(
            db,
            user_id=approver.id,
            action="change_request.reject",
            target_type="change_request",
            target_id=request_id,
            detail={"request_no": result.request_no, "operation_type": result.operation_type, "domain_id": result.domain_id, "reason": body.reason},
        )
        await db.commit()
        return result
    except ValueError as exc:
        if change_request_service.is_change_request_processed(change_request):
            return await change_request_service.get_change_request_by_id(db, request_id) or change_request
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{request_id}/cancel", response_model=ChangeRequestResponse)
async def cancel_change_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    change_request = await change_request_service.get_change_request(db, request_id, current_user)
    if not change_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")
    try:
        result = await change_request_service.cancel_change_request(db, change_request, current_user)
        await audit_log_service.add_audit_log(
            db,
            user_id=current_user.id,
            action="change_request.cancel",
            target_type="change_request",
            target_id=request_id,
            detail={"request_no": result.request_no, "operation_type": result.operation_type, "domain_id": result.domain_id},
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
