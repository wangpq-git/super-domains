import pytest

from app.services import cos_discovery_service


@pytest.mark.asyncio
async def test_cos_discovery_config_reads_database_settings(client, auth_headers):
    save_resp = await client.put(
        "/api/v1/system-settings",
        headers=auth_headers,
        json={
            "items": [
                {"key": "TENCENT_COS_SECRET_ID", "value": "secret-id"},
                {"key": "TENCENT_COS_SECRET_KEY", "value": "secret-key"},
            ]
        },
    )

    assert save_resp.status_code == 200

    resp = await client.get("/api/v1/cos-discovery/config", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"configured": True}


@pytest.mark.asyncio
async def test_cos_discovery_domains_returns_cos_data(client, auth_headers, monkeypatch):
    await client.put(
        "/api/v1/system-settings",
        headers=auth_headers,
        json={
            "items": [
                {"key": "TENCENT_COS_SECRET_ID", "value": "secret-id"},
                {"key": "TENCENT_COS_SECRET_KEY", "value": "secret-key"},
                {"key": "TENCENT_COS_REQUEST_TIMEOUT_SECONDS", "value": 12},
            ]
        },
    )

    captured: dict[str, object] = {}

    def fake_list_cos_domains_sync(secret_id: str, secret_key: str, timeout_seconds: int):
        captured["secret_id"] = secret_id
        captured["secret_key"] = secret_key
        captured["timeout_seconds"] = timeout_seconds
        return [
            {
                "bucket_name": "site-1250000000",
                "custom_domain": "s3.example.com",
                "origin_type": "静态网站源站",
                "cname": "site-1250000000.cos-website.ap-singapore.myqcloud.com",
            }
        ]

    monkeypatch.setattr(cos_discovery_service, "_list_cos_domains_sync", fake_list_cos_domains_sync)

    resp = await client.get("/api/v1/cos-discovery/domains", headers=auth_headers)

    assert resp.status_code == 200
    assert captured == {
        "secret_id": "secret-id",
        "secret_key": "secret-key",
        "timeout_seconds": 12,
    }
    assert resp.json() == {
        "items": [
            {
                "bucket_name": "site-1250000000",
                "custom_domain": "s3.example.com",
                "origin_type": "静态网站源站",
                "cname": "site-1250000000.cos-website.ap-singapore.myqcloud.com",
            }
        ]
    }


@pytest.mark.asyncio
async def test_cos_discovery_domains_requires_credentials(client, auth_headers):
    resp = await client.get("/api/v1/cos-discovery/domains", headers=auth_headers)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "请先在配置中心填写腾讯云 SecretId 和 SecretKey"


def test_list_cos_domains_sync_skips_access_denied_bucket(monkeypatch):
    class FakeClient:
        def __init__(self, config):
            self.region = getattr(config, "_region", None)

        def list_buckets(self):
            return {
                "Buckets": {
                    "Bucket": [
                        {"Name": "denied-bucket", "Location": "ap-singapore"},
                        {"Name": "allowed-bucket", "Location": "ap-singapore"},
                    ]
                }
            }

        def get_bucket_domain(self, Bucket):
            if Bucket == "denied-bucket":
                raise Exception("{'code': 'AccessDenied', 'message': 'Access Denied.'}")
            return {
                "DomainRule": [
                    {"Name": "s3.example.com", "Type": "WEBSITE"}
                ]
            }

    class FakeConfig:
        def __init__(self, **kwargs):
            self._region = kwargs.get("Region")

    import sys
    import types

    monkeypatch.setitem(
        sys.modules,
        "qcloud_cos",
        types.SimpleNamespace(CosConfig=FakeConfig, CosS3Client=FakeClient),
    )

    items = cos_discovery_service._list_cos_domains_sync("sid", "skey", 10)

    assert items == [
        {
            "bucket_name": "allowed-bucket",
            "custom_domain": "s3.example.com",
            "origin_type": "静态网站源站",
            "cname": "allowed-bucket.cos-website.ap-singapore.myqcloud.com",
        }
    ]
