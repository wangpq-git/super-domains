from pydantic import BaseModel


class CosDiscoveryConfigResponse(BaseModel):
    configured: bool


class CosDiscoveryDomainItem(BaseModel):
    bucket_name: str
    custom_domain: str
    origin_type: str
    cname: str


class CosDiscoveryDomainListResponse(BaseModel):
    items: list[CosDiscoveryDomainItem]
    skipped_bucket_count: int = 0
