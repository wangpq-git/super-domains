import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.encryption import decrypt_credentials, encrypt_credentials
from app.models.audit_log import AuditLog
from app.models.system_setting import SystemSetting
from app.models.user import User


SETTING_DEFINITIONS = {
    "APPROVAL_ENABLED": {
        "category": "approval",
        "label": "启用审批流",
        "description": "开启后，写操作先进入审批中心，审批通过后再执行。",
        "value_type": "boolean",
        "default": True,
        "is_secret": False,
        "restart_required": False,
        "public": True,
    },
    "APPROVAL_ALLOW_ADMIN_BYPASS": {
        "category": "approval",
        "label": "管理员免审批",
        "description": "开启后，管理员发起的变更可直接执行。",
        "value_type": "boolean",
        "default": False,
        "is_secret": False,
        "restart_required": False,
        "public": True,
    },
    "LDAP_ENABLED": {
        "category": "ldap",
        "label": "启用 LDAP 登录",
        "description": "关闭后仅允许本地账号登录。",
        "value_type": "boolean",
        "default": True,
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "LDAP_HOST": {
        "category": "ldap",
        "label": "LDAP 主机",
        "description": "LDAP 服务器地址。",
        "value_type": "string",
        "default": "",
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "LDAP_PORT": {
        "category": "ldap",
        "label": "LDAP 端口",
        "description": "LDAP 服务端口。",
        "value_type": "integer",
        "default": 389,
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "LDAP_USE_SSL": {
        "category": "ldap",
        "label": "LDAP SSL",
        "description": "是否使用 LDAPS 连接。",
        "value_type": "boolean",
        "default": False,
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "LDAP_BASE_DN": {
        "category": "ldap",
        "label": "LDAP Base DN",
        "description": "用户搜索的基础 DN。",
        "value_type": "string",
        "default": "",
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "LDAP_BIND_DN": {
        "category": "ldap",
        "label": "LDAP 绑定账号 DN",
        "description": "用于搜索用户的只读账号 DN。",
        "value_type": "string",
        "default": "",
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "LDAP_BIND_PASSWORD": {
        "category": "ldap",
        "label": "LDAP 绑定账号密码",
        "description": "用于搜索用户的只读账号密码。",
        "value_type": "string",
        "default": "",
        "is_secret": True,
        "restart_required": False,
        "public": False,
    },
    "LDAP_USER_FILTER": {
        "category": "ldap",
        "label": "LDAP 用户过滤器",
        "description": "支持 {username} 占位符。",
        "value_type": "string",
        "default": "(uid={username})",
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "FEISHU_APPROVAL_WEBHOOK_URL": {
        "category": "feishu",
        "label": "飞书群机器人 Webhook",
        "description": "用于发送待审批卡片和审批结果通知。",
        "value_type": "string",
        "default": "",
        "is_secret": True,
        "restart_required": False,
        "public": False,
    },
    "FEISHU_APPROVAL_BASE_URL": {
        "category": "feishu",
        "label": "系统公网地址",
        "description": "用于生成卡片链接和回调相关元数据。",
        "value_type": "string",
        "default": "",
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "FEISHU_APPROVAL_CALLBACK_TOKEN": {
        "category": "feishu",
        "label": "飞书回调 Token",
        "description": "用于校验飞书事件订阅请求。",
        "value_type": "string",
        "default": "",
        "is_secret": True,
        "restart_required": False,
        "public": False,
    },
    "FEISHU_APPROVAL_ENCRYPT_KEY": {
        "category": "feishu",
        "label": "飞书回调 Encrypt Key",
        "description": "用于校验飞书回调签名。",
        "value_type": "string",
        "default": "",
        "is_secret": True,
        "restart_required": False,
        "public": False,
    },
    "FEISHU_APPROVAL_SIGNATURE_TOLERANCE_SECONDS": {
        "category": "feishu",
        "label": "飞书签名时间容忍秒数",
        "description": "允许的飞书回调时间偏差，默认 300 秒。",
        "value_type": "integer",
        "default": 300,
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "FEISHU_APPROVAL_ADMIN_MAP": {
        "category": "feishu",
        "label": "飞书管理员映射",
        "description": "JSON 格式，支持 open_id / user_id / email / username 到本地管理员映射。",
        "value_type": "json",
        "default": {},
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "SMTP_HOST": {
        "category": "notification",
        "label": "SMTP 主机",
        "description": "邮件服务器地址。",
        "value_type": "string",
        "default": "",
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "SMTP_PORT": {
        "category": "notification",
        "label": "SMTP 端口",
        "description": "邮件服务器端口。",
        "value_type": "integer",
        "default": 587,
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "SMTP_USER": {
        "category": "notification",
        "label": "SMTP 用户名",
        "description": "邮件发送账号。",
        "value_type": "string",
        "default": "",
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "SMTP_PASSWORD": {
        "category": "notification",
        "label": "SMTP 密码",
        "description": "邮件发送账号密码。",
        "value_type": "string",
        "default": "",
        "is_secret": True,
        "restart_required": False,
        "public": False,
    },
    "SMTP_FROM": {
        "category": "notification",
        "label": "发件人地址",
        "description": "邮件 From 字段，留空时使用 SMTP 用户名。",
        "value_type": "string",
        "default": "",
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "SMTP_USE_TLS": {
        "category": "notification",
        "label": "SMTP 使用 TLS",
        "description": "是否直接使用 TLS 连接。",
        "value_type": "boolean",
        "default": True,
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
    "SMTP_START_TLS": {
        "category": "notification",
        "label": "SMTP STARTTLS",
        "description": "是否在明文连接后升级到 TLS。",
        "value_type": "boolean",
        "default": True,
        "is_secret": False,
        "restart_required": False,
        "public": False,
    },
}

def _get_env_fallback(key: str) -> Any:
    return getattr(settings, key, None)


@dataclass
class ResolvedSetting:
    key: str
    definition: dict[str, Any]
    value: Any
    source: str
    is_configured: bool


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}***{value[-4:]}"


def _serialize_for_storage(value: Any, value_type: str, is_secret: bool) -> str | None:
    if value is None:
        return None
    if value_type == "boolean":
        raw = "true" if bool(value) else "false"
    elif value_type == "integer":
        raw = str(int(value))
    elif value_type == "json":
        raw = json.dumps(value, ensure_ascii=False)
    else:
        raw = str(value)
    if is_secret and raw:
        return encrypt_credentials({"value": raw})
    return raw


def _deserialize_from_storage(raw: str | None, value_type: str, is_secret: bool) -> Any:
    if raw in (None, ""):
        if value_type == "json":
            return {}
        return None
    if is_secret:
        raw = decrypt_credentials(raw).get("value", "")
    if value_type == "boolean":
        return str(raw).lower() in {"1", "true", "yes", "on"}
    if value_type == "integer":
        return int(raw)
    if value_type == "json":
        return json.loads(raw)
    return raw


def _deserialize_env_value(key: str, raw: Any, value_type: str) -> Any:
    if raw in (None, ""):
        if value_type == "json":
            return {}
        return None
    if value_type == "boolean":
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() in {"1", "true", "yes", "on"}
    if value_type == "integer":
        return int(raw)
    if value_type == "json":
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)
    return raw


async def _get_setting_record_map(db: AsyncSession) -> dict[str, SystemSetting]:
    result = await db.execute(select(SystemSetting))
    items = result.scalars().all()
    return {item.key: item for item in items}


async def resolve_setting(db: AsyncSession, key: str) -> ResolvedSetting:
    definition = SETTING_DEFINITIONS[key]
    record_map = await _get_setting_record_map(db)
    record = record_map.get(key)
    if record and record.value not in (None, ""):
        value = _deserialize_from_storage(record.value, definition["value_type"], definition["is_secret"])
        return ResolvedSetting(key=key, definition=definition, value=value, source="database", is_configured=True)

    env_value = _get_env_fallback(key)
    if env_value not in (None, ""):
        value = _deserialize_env_value(key, env_value, definition["value_type"])
        return ResolvedSetting(key=key, definition=definition, value=value, source="environment", is_configured=True)

    return ResolvedSetting(
        key=key,
        definition=definition,
        value=definition.get("default"),
        source="default",
        is_configured=definition.get("default") not in (None, "", {}),
    )


async def resolve_settings(db: AsyncSession, *, only_public: bool = False) -> list[ResolvedSetting]:
    record_map = await _get_setting_record_map(db)
    resolved: list[ResolvedSetting] = []
    for key, definition in SETTING_DEFINITIONS.items():
        if only_public and not definition.get("public"):
            continue
        record = record_map.get(key)
        if record and record.value not in (None, ""):
            value = _deserialize_from_storage(record.value, definition["value_type"], definition["is_secret"])
            resolved.append(ResolvedSetting(key=key, definition=definition, value=value, source="database", is_configured=True))
            continue
        env_value = _get_env_fallback(key)
        if env_value not in (None, ""):
            value = _deserialize_env_value(key, env_value, definition["value_type"])
            resolved.append(ResolvedSetting(key=key, definition=definition, value=value, source="environment", is_configured=True))
            continue
        default = definition.get("default")
        resolved.append(ResolvedSetting(key=key, definition=definition, value=default, source="default", is_configured=default not in (None, "", {})))
    return resolved


async def list_settings(db: AsyncSession) -> list[dict[str, Any]]:
    resolved = await resolve_settings(db)
    items = []
    for item in resolved:
        value = item.value
        masked_value = None
        if item.definition["is_secret"]:
            masked_value = _mask_secret(str(value) if value not in (None, "") else None)
            value = None
        items.append({
            "key": item.key,
            "category": item.definition["category"],
            "label": item.definition["label"],
            "description": item.definition.get("description"),
            "value_type": item.definition["value_type"],
            "is_secret": item.definition["is_secret"],
            "restart_required": item.definition["restart_required"],
            "value": value,
            "masked_value": masked_value,
            "is_configured": item.is_configured,
            "source": item.source,
        })
    return items


async def list_public_settings(db: AsyncSession) -> list[dict[str, Any]]:
    resolved = await resolve_settings(db, only_public=True)
    return [{"key": item.key, "value": item.value, "source": item.source} for item in resolved]


async def update_settings(db: AsyncSession, admin: User, payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    record_map = await _get_setting_record_map(db)
    changed_keys: list[str] = []
    for entry in payload:
        key = entry["key"]
        if key not in SETTING_DEFINITIONS:
            raise ValueError(f"Unsupported setting key: {key}")
        definition = SETTING_DEFINITIONS[key]
        value = entry.get("value")
        stored = _serialize_for_storage(value, definition["value_type"], definition["is_secret"])
        record = record_map.get(key)
        if not record:
            record = SystemSetting(
                key=key,
                category=definition["category"],
                value_type=definition["value_type"],
                is_secret=definition["is_secret"],
                description=definition.get("description"),
                restart_required=definition["restart_required"],
            )
            db.add(record)
            record_map[key] = record
        record.category = definition["category"]
        record.value_type = definition["value_type"]
        record.is_secret = definition["is_secret"]
        record.description = definition.get("description")
        record.restart_required = definition["restart_required"]
        record.value = stored
        record.updated_by_user_id = admin.id
        changed_keys.append(key)

    if changed_keys:
        db.add(
            AuditLog(
                user_id=admin.id,
                action="system_settings.update",
                target_type="system_setting",
                target_id=None,
                detail={"keys": changed_keys},
                ip_address=None,
            )
        )
    await db.commit()
    return await list_settings(db)


async def get_bool(db: AsyncSession, key: str) -> bool:
    resolved = await resolve_setting(db, key)
    return bool(resolved.value)


async def get_string(db: AsyncSession, key: str) -> str:
    resolved = await resolve_setting(db, key)
    return "" if resolved.value is None else str(resolved.value)


async def get_int(db: AsyncSession, key: str) -> int:
    resolved = await resolve_setting(db, key)
    return int(resolved.value or 0)


async def get_json_dict(db: AsyncSession, key: str) -> dict[str, Any]:
    resolved = await resolve_setting(db, key)
    value = resolved.value or {}
    return value if isinstance(value, dict) else {}
