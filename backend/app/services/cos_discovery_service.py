import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import system_setting_service

_SERVICE_REGION = "ap-beijing"


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _origin_type_label(domain_type: str) -> str:
    normalized = (domain_type or "").strip().upper()
    if normalized == "WEBSITE":
        return "静态网站源站"
    if normalized == "REST":
        return "默认源站"
    if normalized:
        return normalized
    return "未知"


def _build_cname(bucket_name: str, region: str, domain_type: str) -> str:
    normalized = (domain_type or "").strip().upper()
    if normalized == "WEBSITE":
        return f"{bucket_name}.cos-website.{region}.myqcloud.com"
    return f"{bucket_name}.cos.{region}.myqcloud.com"


def _should_skip_bucket(message: str) -> bool:
    return any(flag in message for flag in ["AccessDenied", "Access Denied", "DomainConfigNotFoundError", "Bucket domain config not found"])


def _list_cos_domains_sync(secret_id: str, secret_key: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as exc:
        raise RuntimeError("缺少 cos-python-sdk-v5 依赖，无法读取 COS 信息") from exc

    try:
        service_client = CosS3Client(
            CosConfig(
                SecretId=secret_id,
                SecretKey=secret_key,
                Region=_SERVICE_REGION,
                Timeout=max(timeout_seconds, 1),
            )
        )
        service_response = service_client.list_buckets()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"读取 COS 存储桶失败: {exc}") from exc

    buckets = _ensure_list(((service_response or {}).get("Buckets") or {}).get("Bucket"))
    items: list[dict[str, str]] = []
    skipped_bucket_count = 0

    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        bucket_name = str(bucket.get("Name") or "").strip()
        region = str(bucket.get("Location") or "").strip()
        if not bucket_name or not region:
            continue

        try:
            bucket_client = CosS3Client(
                CosConfig(
                    SecretId=secret_id,
                    SecretKey=secret_key,
                    Region=region,
                    Timeout=max(timeout_seconds, 1),
                )
            )
            domain_response = bucket_client.get_bucket_domain(Bucket=bucket_name)
        except Exception as exc:  # pragma: no cover
            message = str(exc)
            if _should_skip_bucket(message):
                skipped_bucket_count += 1
                continue
            raise RuntimeError(f"读取存储桶 {bucket_name} 的自定义域名失败: {exc}") from exc

        rules = _ensure_list((domain_response or {}).get("DomainRule"))
        matched_rule = False
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            custom_domain = str(rule.get("Name") or "").strip()
            if not custom_domain:
                continue
            matched_rule = True
            domain_type = str(rule.get("Type") or "REST").strip().upper() or "REST"
            items.append(
                {
                    "bucket_name": bucket_name,
                    "custom_domain": custom_domain,
                    "origin_type": _origin_type_label(domain_type),
                    "cname": _build_cname(bucket_name, region, domain_type),
                }
            )

        if not matched_rule:
            skipped_bucket_count += 1

    items.sort(key=lambda item: (item["bucket_name"], item["custom_domain"]))
    return {"items": items, "skipped_bucket_count": skipped_bucket_count}


async def get_cos_discovery_config(db: AsyncSession) -> dict[str, bool]:
    secret_id = await system_setting_service.get_string(db, "TENCENT_COS_SECRET_ID")
    secret_key = await system_setting_service.get_string(db, "TENCENT_COS_SECRET_KEY")
    return {"configured": bool(secret_id.strip() and secret_key.strip())}


async def list_cos_domains(db: AsyncSession) -> dict[str, Any]:
    secret_id = await system_setting_service.get_string(db, "TENCENT_COS_SECRET_ID")
    secret_key = await system_setting_service.get_string(db, "TENCENT_COS_SECRET_KEY")
    if not secret_id.strip() or not secret_key.strip():
        raise ValueError("请先在配置中心填写腾讯云 SecretId 和 SecretKey")

    timeout_seconds = await system_setting_service.get_int(db, "TENCENT_COS_REQUEST_TIMEOUT_SECONDS")
    return await asyncio.to_thread(_list_cos_domains_sync, secret_id, secret_key, timeout_seconds)
