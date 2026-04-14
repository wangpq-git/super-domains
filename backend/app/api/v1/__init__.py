"""API v1 router"""
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.audit_logs import router as audit_logs_router
from app.api.v1.platforms import router as platforms_router
from app.api.v1.domains import router as domains_router
from app.api.v1.dns import router as dns_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.batch import router as batch_router
from app.api.v1.change_requests import router as change_requests_router
from app.api.v1.export import router as export_router
from app.api.v1.reports import router as reports_router
from app.api.v1.users import router as users_router
from app.api.v1.system_settings import router as system_settings_router
from app.api.v1.service_discovery import router as service_discovery_router
from app.api.v1.cos_discovery import router as cos_discovery_router
from app.api.v1.webhooks import router as webhooks_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(audit_logs_router, prefix="/audit-logs", tags=["audit-logs"])
api_router.include_router(platforms_router, prefix="/platforms", tags=["platforms"])
api_router.include_router(domains_router, prefix="/domains", tags=["domains"])
api_router.include_router(dns_router, prefix="/dns", tags=["dns"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["alerts"])
api_router.include_router(batch_router, prefix="/batch", tags=["batch"])
api_router.include_router(change_requests_router, prefix="/change-requests", tags=["change-requests"])
api_router.include_router(export_router, prefix="/export", tags=["export"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(system_settings_router, prefix="/system-settings", tags=["system-settings"])
api_router.include_router(service_discovery_router, prefix="/service-discovery", tags=["service-discovery"])
api_router.include_router(cos_discovery_router, prefix="/cos-discovery", tags=["cos-discovery"])
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])


@api_router.get("/ping")
async def ping() -> dict:
    """Health check endpoint"""
    return {"message": "pong"}
