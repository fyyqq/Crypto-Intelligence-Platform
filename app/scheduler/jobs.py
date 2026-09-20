from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.sync_log import SyncType
from app.services.market_data_service import MarketDataService

scheduler = BackgroundScheduler(timezone="UTC")


def run_market_data_sync() -> None:
    """Runs strictly once every SYNC_INTERVAL_HOURS (default 24h) — see Rule 4:
    API Optimization & Cost Control. Each call re-checks is_sync_due() so an
    overlapping trigger never burns extra free-tier credits.
    """
    db = SessionLocal()
    try:
        service = MarketDataService(db)
        if service.is_sync_due(SyncType.LISTINGS):
            service.sync_listings()
        if service.is_sync_due(SyncType.CATEGORIES):
            service.sync_categories()
    finally:
        db.close()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        run_market_data_sync,
        trigger="interval",
        hours=settings.sync_interval_hours,
        id="market_data_sync",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
