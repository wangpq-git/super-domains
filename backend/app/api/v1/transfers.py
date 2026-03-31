from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api.deps import get_db
from app.services import transfer_service
from app.schemas.transfer import TransferCreate, TransferUpdate, TransferResponse, TransferListResponse

router = APIRouter()


@router.post("", response_model=TransferResponse)
async def create_transfer(
    transfer_data: TransferCreate,
    db: AsyncSession = Depends(get_db),
):
    user_id = 1
    try:
        transfer = await transfer_service.initiate_transfer(
            db,
            domain_id=transfer_data.domain_id,
            to_platform=transfer_data.to_platform,
            to_account=transfer_data.to_account,
            user_id=user_id,
        )
        return transfer
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=TransferListResponse)
async def list_transfers(
    status: Optional[str] = Query(default=None),
    domain_id: Optional[int] = Query(default=None),
    from_platform: Optional[str] = Query(default=None),
    to_platform: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await transfer_service.list_transfers(
        db,
        status=status,
        domain_id=domain_id,
        from_platform=from_platform,
        to_platform=to_platform,
        page=page,
        page_size=page_size,
    )
    return result


@router.get("/{transfer_id}", response_model=TransferResponse)
async def get_transfer(transfer_id: int, db: AsyncSession = Depends(get_db)):
    transfer = await transfer_service.get_transfer(db, transfer_id)
    if not transfer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")
    return transfer


@router.put("/{transfer_id}", response_model=TransferResponse)
async def update_transfer(
    transfer_id: int,
    transfer_data: TransferUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        transfer = await transfer_service.update_transfer_status(
            db,
            transfer_id=transfer_id,
            status=transfer_data.status,
            notes=transfer_data.notes,
        )
        return transfer
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{transfer_id}", response_model=TransferResponse)
async def cancel_transfer(transfer_id: int, db: AsyncSession = Depends(get_db)):
    try:
        transfer = await transfer_service.cancel_transfer(db, transfer_id)
        return transfer
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
