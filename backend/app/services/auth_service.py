from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate
from app.core.security import hash_password, verify_password
from app.services import ldap_service, system_setting_service


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    ldap_enabled = await system_setting_service.get_bool(db, "LDAP_ENABLED")
    if ldap_enabled:
        ldap_info = await ldap_service.authenticate(db, username, password)
        if not ldap_info:
            return None
        # 查找本地用户
        result = await db.execute(select(User).where(User.username == ldap_info["uid"]))
        user = result.scalar_one_or_none()
        if not user:
            # 自动创建本地用户
            first = await is_first_user(db)
            user = User(
                username=ldap_info["uid"],
                email=ldap_info["mail"] if ldap_info["mail"] else None,
                display_name=ldap_info["cn"] if ldap_info["cn"] else None,
                role="admin" if first else "viewer",
                auth_source="ldap",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user
    else:
        # 本地认证回退
        result = await db.execute(select(User).where(User.username == username, User.is_active.is_(True)))
        user = result.scalar_one_or_none()
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user


async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
    user = User(
        username=user_data.username,
        password_hash=hash_password(user_data.password) if user_data.password else None,
        email=user_data.email,
        role=user_data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def is_first_user(db: AsyncSession) -> bool:
    result = await db.execute(select(func.count(User.id)))
    count = result.scalar()
    return count == 0
