from ldap3 import Server, Connection, SUBTREE
from ldap3.utils.conv import escape_filter_chars
from app.core.config import settings


async def authenticate(username: str, password: str) -> dict | None:
    """LDAP 认证，成功返回 {uid, cn, mail}"""
    server = Server(settings.LDAP_HOST, port=settings.LDAP_PORT, use_ssl=settings.LDAP_USE_SSL)
    # 1. 用只读账号连接
    conn = Connection(server, user=settings.LDAP_BIND_DN, password=settings.LDAP_BIND_PASSWORD, auto_bind=True)
    # 2. 搜索用户
    safe_username = escape_filter_chars(username)
    search_filter = settings.LDAP_USER_FILTER.replace("{username}", safe_username)
    conn.search(settings.LDAP_BASE_DN, search_filter, SUBTREE, attributes=["uid", "cn", "mail"])
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
