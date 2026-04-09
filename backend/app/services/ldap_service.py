from ldap3 import Server, Connection, SUBTREE
from sqlalchemy.ext.asyncio import AsyncSession
from ldap3.utils.conv import escape_filter_chars

from app.core.config import settings
from app.services import system_setting_service


async def authenticate(db: AsyncSession, username: str, password: str) -> dict | None:
    """LDAP 认证，成功返回 {uid, cn, mail}"""
    ldap_host = await system_setting_service.get_string(db, "LDAP_HOST")
    ldap_port = await system_setting_service.get_int(db, "LDAP_PORT")
    ldap_use_ssl = await system_setting_service.get_bool(db, "LDAP_USE_SSL")
    ldap_base_dn = await system_setting_service.get_string(db, "LDAP_BASE_DN")
    ldap_bind_dn = await system_setting_service.get_string(db, "LDAP_BIND_DN")
    ldap_bind_password = await system_setting_service.get_string(db, "LDAP_BIND_PASSWORD")
    ldap_user_filter = await system_setting_service.get_string(db, "LDAP_USER_FILTER")

    server = Server(
        ldap_host or settings.LDAP_HOST,
        port=ldap_port or settings.LDAP_PORT,
        use_ssl=ldap_use_ssl,
    )
    # 1. 用只读账号连接
    conn = Connection(
        server,
        user=ldap_bind_dn or settings.LDAP_BIND_DN,
        password=ldap_bind_password or settings.LDAP_BIND_PASSWORD,
        auto_bind=True,
    )
    # 2. 搜索用户
    safe_username = escape_filter_chars(username)
    search_filter = (ldap_user_filter or settings.LDAP_USER_FILTER).replace("{username}", safe_username)
    conn.search(ldap_base_dn or settings.LDAP_BASE_DN, search_filter, SUBTREE, attributes=["uid", "cn", "mail"])
    if not conn.entries:
        conn.unbind()
        return None
    user_dn = conn.entries[0].entry_dn
    user_info = {"uid": str(conn.entries[0].uid), "cn": str(conn.entries[0].cn), "mail": str(conn.entries[0].mail)}
    conn.unbind()
    # 3. 用用户 DN + 密码 rebind 验证
    try:
        user_conn = Connection(server, user=user_dn, password=password, auto_bind=True)
        user_conn.unbind()
        return user_info
    except Exception:
        return None
