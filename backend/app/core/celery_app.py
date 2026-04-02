from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "domain_manage",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    beat_schedule={
        "sync-all-accounts-every-6h": {
            "task": "app.tasks.sync_tasks.sync_all_accounts",
            "schedule": 6 * 3600,
        },
        "check-expiring-domains-hourly": {
            "task": "app.tasks.sync_tasks.check_expiring_domains",
            "schedule": crontab(minute=0),
        },
    },
)
