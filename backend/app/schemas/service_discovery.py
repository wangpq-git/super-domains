from pydantic import BaseModel


class ServiceDiscoveryNamespaceOption(BaseModel):
    label: str
    namespace: str


class ServiceDiscoveryConfigResponse(BaseModel):
    configured: bool
    namespace_options: list[ServiceDiscoveryNamespaceOption]


class ServiceDiscoveryIngressItem(BaseModel):
    name: str
    namespace: str
    hosts: list[str]
    ingress_class_name: str | None = None
    load_balancers: list[str] = []
    tls_hosts: list[str] = []


class ServiceDiscoveryIngressListResponse(BaseModel):
    namespace: str
    items: list[ServiceDiscoveryIngressItem]
