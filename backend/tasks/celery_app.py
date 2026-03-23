"""
PraxiAlpha — Celery Application Configuration

Sets up Celery with Redis as broker and result backend.
Configures Celery Beat schedule for daily data updates.
"""

from celery import Celery
from celery.schedules import crontab

from backend.config import get_settings

settings = get_settings()

# ---- Celery App ----
celery_app = Celery(
    "praxialpha",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
    include=[
        "backend.tasks.data_tasks",
        "backend.tasks.trade_snapshot_task",
    ],
)

# ---- Celery Configuration ----
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="US/Eastern",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Retry settings
    task_default_retry_delay=60,
    task_max_retries=3,
)

# ---- Celery Beat Schedule (Daily Updates) ----
celery_app.conf.beat_schedule = {
    # Daily OHLCV update — runs at 6 PM ET (after market close + settlement)
    "daily-ohlcv-update": {
        "task": "backend.tasks.data_tasks.daily_ohlcv_update",
        "schedule": crontab(hour=18, minute=0),  # 6:00 PM ET
        "options": {"queue": "data_pipeline"},
    },
    # Daily macro data update — runs at 6:30 PM ET
    "daily-macro-update": {
        "task": "backend.tasks.data_tasks.daily_macro_update",
        "schedule": crontab(hour=18, minute=30),  # 6:30 PM ET
        "options": {"queue": "data_pipeline"},
    },
    # Daily economic calendar sync — runs at 7 AM ET (before market open)
    "daily-economic-calendar-sync": {
        "task": "backend.tasks.data_tasks.daily_economic_calendar_sync",
        "schedule": crontab(hour=7, minute=0),  # 7:00 AM ET
        "options": {"queue": "data_pipeline"},
    },
    # Daily trade snapshot generation — runs at 7 PM ET (after OHLCV update)
    "daily-trade-snapshots": {
        "task": "backend.tasks.trade_snapshot_task.generate_snapshots",
        "schedule": crontab(hour=19, minute=0),  # 7:00 PM ET
        "options": {"queue": "data_pipeline"},
    },
}
