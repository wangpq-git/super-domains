import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import data_cache_service
from app.services import system_setting_service

_SERVICE_REGION = "ap-beijing"
_ACCESS_DENIED_FLAGS = ["AccessDenied", "Access Denied"]
_DOMAIN_NOT_FOUND_FLAGS = ["DomainConfigNotFoundError", "Bucket domain config not found"]
_MAX_BUCKET_WORKERS = 8


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


def _is_access_denied(message: str) -> bool:
    return any(flag in message for flag in _ACCESS_DENIED_FLAGS)


def _is_domain_not_found(message: str) -> bool:
    return any(flag in message for flag in _DOMAIN_NOT_FOUND_FLAGS)


def _empty_domain_item(bucket_name: str) -> dict[str, str]:
    return {
        "bucket_name": bucket_name,
        "custom_domain": "",
        "origin_type": "",
        "cname": "",
    }


def _collect_bucket_domains(
    *,
    secret_id: str,
    secret_key: str,
    timeout_seconds: int,
    bucket_name: str,
    region: str,
) -> tuple[list[dict[str, str]], int]:
    from qcloud_cos import CosConfig, CosS3Client

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
        if _is_access_denied(message):
            return [], 1
        if _is_domain_not_found(message):
            return [_empty_domain_item(bucket_name)], 0
        raise RuntimeError(f"读取存储桶 {bucket_name} 的自定义域名失败: {exc}") from exc

    items: list[dict[str, str]] = []
    matched_rule = False
    for rule in _ensure_list((domain_response or {}).get("DomainRule")):
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
        items.append(_empty_domain_item(bucket_name))

    return items, 0


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

    bucket_jobs: list[tuple[str, str]] = []
    for bucket in _ensure_list(((service_response or {}).get("Buckets") or {}).get("Bucket")):
        if not isinstance(bucket, dict):
            continue
        bucket_name = str(bucket.get("Name") or "").strip()
        region = str(bucket.get("Location") or "").strip()
        if not bucket_name or not region:
            continue
        bucket_jobs.append((bucket_name, region))

    items: list[dict[str, str]] = []
    skipped_bucket_count = 0
    max_workers = min(_MAX_BUCKET_WORKERS, len(bucket_jobs)) or 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _collect_bucket_domains,
                secret_id=secret_id,
                secret_key=secret_key,
                timeout_seconds=timeout_seconds,
                bucket_name=bucket_name,
                region=region,
            )
            for bucket_name, region in bucket_jobs
        ]
        for future in as_completed(futures):
            bucket_items, skipped_count = future.result()
            items.extend(bucket_items)
            skipped_bucket_count += skipped_count

    items.sort(key=lambda item: (item["bucket_name"], item["custom_domain"]))
    return {"items": items, "skipped_bucket_count": skipped_bucket_count}


async def get_cos_discovery_config(db: AsyncSession) -> dict[str, bool]:
    ttl_seconds = await system_setting_service.get_int(db, "DATA_CACHE_TTL_SECONDS")
    cache_key = data_cache_service.build_cache_key("cos_discovery_config")

    async def _load() -> dict[str, bool]:
        secret_id = await system_setting_service.get_string(db, "TENCENT_COS_SECRET_ID")
        secret_key = await system_setting_service.get_string(db, "TENCENT_COS_SECRET_KEY")
        return {"configured": bool(secret_id.strip() and secret_key.strip())}

    return await data_cache_service.get_or_set(cache_key, _load, ttl_seconds=ttl_seconds)


async def list_cos_domains(db: AsyncSession) -> dict[str, Any]:
    secret_id = await system_setting_service.get_string(db, "TENCENT_COS_SECRET_ID")
    secret_key = await system_setting_service.get_string(db, "TENCENT_COS_SECRET_KEY")
    if not secret_id.strip() or not secret_key.strip():
        raise ValueError("请先在配置中心填写腾讯云 SecretId 和 SecretKey")

    timeout_seconds = await system_setting_service.get_int(db, "TENCENT_COS_REQUEST_TIMEOUT_SECONDS")
    cache_ttl_seconds = await system_setting_service.get_int(db, "DATA_CACHE_TTL_SECONDS")
    cache_key = data_cache_service.build_cache_key(
        "cos_domains",
        secret_id=secret_id,
        timeout_seconds=timeout_seconds,
    )

    async def _load() -> dict[str, Any]:
        return await asyncio.to_thread(_list_cos_domains_sync, secret_id, secret_key, timeout_seconds)

    return await data_cache_service.get_or_set(cache_key, _load, ttl_seconds=cache_ttl_seconds)
