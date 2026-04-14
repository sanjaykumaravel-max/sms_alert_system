"""
Celery Configuration for SMS Alert App Background Tasks.

This module configures Celery for background job processing including:
- SMS sending tasks
- Bulk message processing
- Scheduled notifications
- Report generation
"""

import os
from celery import Celery
from celery.schedules import crontab

# Celery configuration
celery_app = Celery(
    "sms_alert",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    include=["src.tasks"]
)

# Celery settings
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Worker settings
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=False,

    # Result backend settings
    result_expires=3600,  # 1 hour
    result_cache_max=10000,

    # Routing
    task_routes={
        "src.tasks.send_sms_task": {"queue": "sms"},
        "src.tasks.send_bulk_sms_task": {"queue": "bulk_sms"},
        "src.tasks.send_scheduled_notifications": {"queue": "scheduled"},
        "src.tasks.generate_reports": {"queue": "reports"},
    },

    # Task time limits
    task_soft_time_limit=300,  # 5 minutes
    task_time_limit=600,  # 10 minutes

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Scheduled tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    "send-maintenance-reminders": {
        "task": "src.tasks.send_scheduled_notifications",
        "schedule": crontab(hour=9, minute=0),  # Daily at 9 AM
        "args": ("maintenance",),
    },
    "send-critical-alerts": {
        "task": "src.tasks.send_scheduled_notifications",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "args": ("critical",),
    },
    "generate-daily-reports": {
        "task": "src.tasks.generate_reports",
        "schedule": crontab(hour=18, minute=0),  # Daily at 6 PM
        "args": ("daily",),
    },
    "cleanup-old-data": {
        "task": "src.tasks.cleanup_old_data",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
        "args": (),
    },
}

# Error handling
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def retry_task(self):
    """Base task with automatic retry."""
    pass

if __name__ == "__main__":
    celery_app.start()