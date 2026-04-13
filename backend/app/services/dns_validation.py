import ipaddress
import re
from typing import Any


_HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
_NAME_LABEL_RE = re.compile(r"^[A-Za-z0-9_*-]{1,63}$")
_SUPPORTED_PROXIED_TYPES = {"A", "AAAA", "CNAME"}


def _normalize_record_type(record_type: str) -> str:
    normalized = (record_type or "").strip().upper()
    if not normalized:
        raise ValueError("记录类型不能为空")
    return normalized


def _validate_dns_name(value: str, *, field_label: str, allow_root: bool, allow_wildcard: bool) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_label}不能为空")
    if allow_root and normalized == "@":
        return normalized

    candidate = normalized[:-1] if normalized.endswith(".") else normalized
    if not candidate:
        raise ValueError(f"{field_label}格式不正确")

    for label in candidate.split("."):
        if not label:
            raise ValueError(f"{field_label}格式不正确")
        if allow_wildcard and label == "*":
            continue
        pattern = _NAME_LABEL_RE if allow_wildcard else _HOST_LABEL_RE
        if not pattern.fullmatch(label):
            raise ValueError(f"{field_label}格式不正确")
        if label.startswith("-") or label.endswith("-"):
            raise ValueError(f"{field_label}格式不正确")

    return normalized


def validate_dns_record_fields(
    *,
    record_type: str,
    name: str,
    content: str,
    ttl: int | None,
    priority: int | None,
    proxied: bool | None,
) -> dict[str, Any]:
    normalized_type = _normalize_record_type(record_type)
    normalized_name = _validate_dns_name(name, field_label="记录名称", allow_root=True, allow_wildcard=True)
    normalized_content = (content or "").strip()
    if not normalized_content:
        raise ValueError("记录值不能为空")

    if ttl is not None and ttl < 1:
        raise ValueError("TTL 必须大于 0")
    if priority is not None and priority < 0:
        raise ValueError("优先级不能小于 0")
    if proxied and normalized_type not in _SUPPORTED_PROXIED_TYPES:
        raise ValueError("仅 A、AAAA、CNAME 记录支持开启代理")

    if normalized_type == "A":
        try:
            ipaddress.IPv4Address(normalized_content)
        except ipaddress.AddressValueError as exc:
            raise ValueError("A 记录值必须是合法的 IPv4 地址") from exc
    elif normalized_type == "AAAA":
        try:
            ipaddress.IPv6Address(normalized_content)
        except ipaddress.AddressValueError as exc:
            raise ValueError("AAAA 记录值必须是合法的 IPv6 地址") from exc
    elif normalized_type in {"CNAME", "MX", "NS", "PTR"}:
        _validate_dns_name(normalized_content, field_label=f"{normalized_type} 记录值", allow_root=False, allow_wildcard=False)
    elif normalized_type == "SRV":
        parts = normalized_content.split()
        if len(parts) != 3:
            raise ValueError("SRV 记录值格式应为: weight port target")
        weight, port, target = parts
        if not weight.isdigit() or not port.isdigit():
            raise ValueError("SRV 记录值中的 weight 和 port 必须是数字")
        if not 0 <= int(weight) <= 65535 or not 1 <= int(port) <= 65535:
            raise ValueError("SRV 记录值中的 weight 或 port 超出范围")
        _validate_dns_name(target, field_label="SRV 目标", allow_root=False, allow_wildcard=False)

    return {
        "record_type": normalized_type,
        "name": normalized_name,
        "content": normalized_content,
        "ttl": ttl,
        "priority": priority,
        "proxied": proxied,
    }


def validate_nameserver_list(nameservers: list[str]) -> list[str]:
    normalized = []
    for nameserver in nameservers:
        cleaned = _validate_dns_name(
            nameserver,
            field_label="Nameserver",
            allow_root=False,
            allow_wildcard=False,
        ).rstrip(".")
        normalized.append(cleaned)

    if len(normalized) < 2:
        raise ValueError("请至少提供 2 个 Nameserver")
    return normalized
