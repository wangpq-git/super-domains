import asyncio
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import system_setting_service


def _parse_namespace_options(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []

    options: list[dict[str, str]] = []
    seen_namespaces: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        namespace = str(entry.get("namespace") or "").strip()
        if not namespace or namespace in seen_namespaces:
            continue
        label = str(entry.get("label") or namespace).strip() or namespace
        options.append({"label": label, "namespace": namespace})
        seen_namespaces.add(namespace)
    return options


def _parse_kubeconfig(raw: str) -> dict[str, Any]:
    content = raw.strip()
    if not content:
        raise ValueError("请先在配置中心填写 K8s Kubeconfig")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("缺少 PyYAML 依赖，无法解析 kubeconfig") from exc
        parsed = yaml.safe_load(content)

    if not isinstance(parsed, dict):
        raise ValueError("K8s Kubeconfig 格式不正确")
    return parsed


def _list_ingresses_sync(kubeconfig: str, namespace: str, timeout_seconds: int) -> list[dict[str, Any]]:
    try:
        from kubernetes import client as k8s_client
        from kubernetes import config as k8s_config
    except ImportError as exc:
        raise RuntimeError("缺少 kubernetes 依赖，无法读取集群 Ingress") from exc

    api_client = None
    try:
        kubeconfig_dict = _parse_kubeconfig(kubeconfig)
        client_config = k8s_client.Configuration()
        client_config.client_side_validation = False
        client_config.connection_pool_maxsize = 4
        client_config.timeout = timeout_seconds
        k8s_config.load_kube_config_from_dict(
            kubeconfig_dict,
            client_configuration=client_config,
        )
        api_client = k8s_client.ApiClient(client_config)
        networking_api = k8s_client.NetworkingV1Api(api_client)
        response = networking_api.list_namespaced_ingress(namespace=namespace)

        items: list[dict[str, Any]] = []
        for ingress in response.items:
            rules = ingress.spec.rules or []
            tls_entries = ingress.spec.tls or []
            lb_entries = ingress.status.load_balancer.ingress or [] if ingress.status and ingress.status.load_balancer else []

            hosts = sorted({rule.host for rule in rules if getattr(rule, "host", None)})
            tls_hosts = sorted({host for tls in tls_entries for host in (tls.hosts or []) if host})
            load_balancers = sorted(
                {
                    entry.hostname or entry.ip
                    for entry in lb_entries
                    if getattr(entry, "hostname", None) or getattr(entry, "ip", None)
                }
            )
            items.append(
                {
                    "name": ingress.metadata.name,
                    "namespace": namespace,
                    "hosts": hosts,
                    "ingress_class_name": ingress.spec.ingress_class_name if ingress.spec else None,
                    "load_balancers": load_balancers,
                    "tls_hosts": tls_hosts,
                }
            )
        items.sort(key=lambda item: item["name"])
        return items
    finally:
        if api_client is not None:
            api_client.close()


async def get_service_discovery_config(db: AsyncSession) -> dict[str, Any]:
    namespace_raw = await system_setting_service.resolve_setting(db, "K8S_INGRESS_NAMESPACE_OPTIONS")
    kubeconfig = await system_setting_service.get_string(db, "K8S_INGRESS_KUBECONFIG")
    options = _parse_namespace_options(namespace_raw.value)
    return {
        "configured": bool(kubeconfig.strip()),
        "namespace_options": options,
    }


async def list_ingresses(db: AsyncSession, namespace: str | None = None) -> dict[str, Any]:
    config = await get_service_discovery_config(db)
    namespace_options = config["namespace_options"]
    allowed_namespaces = {item["namespace"] for item in namespace_options}

    resolved_namespace = (namespace or "").strip()
    if not resolved_namespace:
        if namespace_options:
            resolved_namespace = namespace_options[0]["namespace"]
        else:
            raise ValueError("请先在配置中心配置可用的命名空间")

    if allowed_namespaces and resolved_namespace not in allowed_namespaces:
        raise ValueError("当前命名空间未在配置中心开放")

    kubeconfig = await system_setting_service.get_string(db, "K8S_INGRESS_KUBECONFIG")
    timeout_seconds = await system_setting_service.get_int(db, "K8S_INGRESS_REQUEST_TIMEOUT_SECONDS")
    items = await asyncio.to_thread(_list_ingresses_sync, kubeconfig, resolved_namespace, max(timeout_seconds, 1))
    return {
        "namespace": resolved_namespace,
        "items": items,
    }
