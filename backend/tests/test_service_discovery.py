import pytest

from app.services import service_discovery_service


@pytest.mark.asyncio
async def test_service_discovery_config_reads_database_settings(client, auth_headers):
    save_resp = await client.put(
        "/api/v1/system-settings",
        headers=auth_headers,
        json={
            "items": [
                {
                    "key": "K8S_INGRESS_KUBECONFIG",
                    "value": "apiVersion: v1\nclusters: []\ncontexts: []\nusers: []\ncurrent-context: ''",
                },
                {
                    "key": "K8S_INGRESS_NAMESPACE_OPTIONS",
                    "value": [
                        {"label": "生产", "namespace": "prod"},
                        {"label": "测试", "namespace": "staging"},
                    ],
                },
            ]
        },
    )

    assert save_resp.status_code == 200

    resp = await client.get("/api/v1/service-discovery/config", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "configured": True,
        "namespace_options": [
            {"label": "生产", "namespace": "prod"},
            {"label": "测试", "namespace": "staging"},
        ],
    }


@pytest.mark.asyncio
async def test_service_discovery_ingresses_returns_cluster_data(client, auth_headers, monkeypatch):
    await client.put(
        "/api/v1/system-settings",
        headers=auth_headers,
        json={
            "items": [
                {"key": "K8S_INGRESS_KUBECONFIG", "value": "apiVersion: v1\nclusters: []"},
                {
                    "key": "K8S_INGRESS_NAMESPACE_OPTIONS",
                    "value": [{"label": "生产", "namespace": "prod"}],
                },
                {"key": "K8S_INGRESS_REQUEST_TIMEOUT_SECONDS", "value": 9},
            ]
        },
    )

    captured: dict[str, object] = {}

    def fake_list_ingresses_sync(kubeconfig: str, namespace: str, timeout_seconds: int):
        captured["kubeconfig"] = kubeconfig
        captured["namespace"] = namespace
        captured["timeout_seconds"] = timeout_seconds
        return [
            {
                "name": "gateway",
                "namespace": namespace,
                "hosts": ["api.example.com", "www.example.com"],
                "ingress_class_name": "nginx",
                "load_balancers": ["lb.example.com"],
                "tls_hosts": ["api.example.com"],
            }
        ]

    monkeypatch.setattr(service_discovery_service, "_list_ingresses_sync", fake_list_ingresses_sync)

    resp = await client.get(
        "/api/v1/service-discovery/ingresses",
        headers=auth_headers,
        params={"namespace": "prod"},
    )

    assert resp.status_code == 200
    assert captured == {
        "kubeconfig": "apiVersion: v1\nclusters: []",
        "namespace": "prod",
        "timeout_seconds": 9,
    }
    assert resp.json() == {
        "namespace": "prod",
        "items": [
            {
                "name": "gateway",
                "namespace": "prod",
                "hosts": ["api.example.com", "www.example.com"],
                "ingress_class_name": "nginx",
                "load_balancers": ["lb.example.com"],
                "tls_hosts": ["api.example.com"],
            }
        ],
    }


@pytest.mark.asyncio
async def test_service_discovery_ingresses_rejects_unconfigured_namespace(client, auth_headers):
    await client.put(
        "/api/v1/system-settings",
        headers=auth_headers,
        json={
            "items": [
                {"key": "K8S_INGRESS_KUBECONFIG", "value": "apiVersion: v1\nclusters: []"},
                {
                    "key": "K8S_INGRESS_NAMESPACE_OPTIONS",
                    "value": [{"label": "生产", "namespace": "prod"}],
                },
            ]
        },
    )

    resp = await client.get(
        "/api/v1/service-discovery/ingresses",
        headers=auth_headers,
        params={"namespace": "staging"},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "当前命名空间未在配置中心开放"
