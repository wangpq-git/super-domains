from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_account import PlatformAccount
from app.models.domain import Domain
from app.schemas.platform_account import PlatformAccountCreate, PlatformAccountUpdate
from app.core.encryption import encrypt_credentials
from app.services import data_cache_service, system_setting_service


async def list_accounts(
    db: AsyncSession,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    platform: str | None = None,
) -> dict:
    ttl_seconds = await system_setting_service.get_int(db, "DATA_CACHE_TTL_SECONDS")
    cache_key = data_cache_service.build_cache_key(
        "platform_accounts",
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
        platform=platform or "",
    )

    async def _load() -> dict:
        allowed_sort_fields = {"platform", "account_name", "last_sync_at", "sync_status", "created_at"}
        if sort_by in allowed_sort_fields:
            col = getattr(PlatformAccount, sort_by)
            order_col = col.desc() if sort_order == "desc" else col.asc()
        else:
            order_col = PlatformAccount.created_at.desc()

        filters = []
        if platform:
            filters.append(PlatformAccount.platform == platform)

        total_query = select(func.count()).select_from(PlatformAccount)
        if filters:
            total_query = total_query.where(*filters)
        total_result = await db.execute(total_query)
        total = total_result.scalar_one()

        query = (
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
            .order_by(order_col)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if filters:
            query = query.where(*filters)

        result = await db.execute(query)
        return {
            "items": [row._asdict() for row in result.all()],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    return await data_cache_service.get_or_set(cache_key, _load, ttl_seconds=ttl_seconds)


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


async def get_account_domain_count(db: AsyncSession, account_id: int) -> int:
    result = await db.execute(
        select(func.count(Domain.id)).where(Domain.account_id == account_id)
    )
    return result.scalar_one() or 0


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
