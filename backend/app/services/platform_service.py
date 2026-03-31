from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_account import PlatformAccount
from app.models.domain import Domain
from app.schemas.platform_account import PlatformAccountCreate, PlatformAccountUpdate
from app.core.encryption import encrypt_credentials


async def list_accounts(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(
            PlatformAccount.id,
            PlatformAccount.platform,
            PlatformAccount.account_name,
            PlatformAccount.is_active,
            PlatformAccount.last_sync_at,
            PlatformAccount.sync_status,
            PlatformAccount.sync_error,
            PlatformAccount.created_at,
            func.count(Domain.id).label("domain_count"),
        )
        .outerjoin(Domain, Domain.account_id == PlatformAccount.id)
        .group_by(PlatformAccount.id)
        .order_by(PlatformAccount.created_at.desc())
    )
    return [row._asdict() for row in result.all()]


async def create_account(db: AsyncSession, data: PlatformAccountCreate, user_id: int) -> PlatformAccount:
    encrypted_creds = encrypt_credentials(data.credentials)
    account = PlatformAccount(
        platform=data.platform,
        account_name=data.account_name,
        credentials=encrypted_creds,
        config=data.config,
        created_by=user_id,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def get_account(db: AsyncSession, account_id: int) -> PlatformAccount | None:
    result = await db.execute(select(PlatformAccount).where(PlatformAccount.id == account_id))
    return result.scalar_one_or_none()


async def update_account(db: AsyncSession, account_id: int, data: PlatformAccountUpdate) -> PlatformAccount | None:
    account = await get_account(db, account_id)
    if not account:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "credentials" in update_data:
        update_data["credentials"] = encrypt_credentials(update_data["credentials"])

    for key, value in update_data.items():
        setattr(account, key, value)

    await db.commit()
    await db.refresh(account)
    return account


async def delete_account(db: AsyncSession, account_id: int) -> bool:
    account = await get_account(db, account_id)
    if not account:
        return False
    await db.delete(account)
    await db.commit()
    return True
