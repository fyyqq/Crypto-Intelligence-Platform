from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.sync_log import SyncStatus, SyncType
from app.services.market_data_service import MarketDataService
from app.services.reflex_cache_service import sync_reflex_cache

scheduler = BackgroundScheduler(timezone="UTC")


def run_market_data_sync() -> None:
    """Runs strictly once every SYNC_INTERVAL_HOURS (default 24h) — see Rule 4:
    API Optimization & Cost Control. Each call re-checks is_sync_due() so an
    overlapping trigger (or an app restart within the window) never burns
    extra free-tier credits. Categories sync first so listings can map each
    coin's tags to a Category by slug in the same run.

    When listings actually sync (fresh percent_change_7d et al.), the Reflex
    dashboard's SQLite cache is mirrored right after — this is what keeps its
    7d Trend line (green/red/gold) in step with each 24h sync automatically,
    instead of someone having to re-run scripts/port_to_reflex_sqlite.py by hand.
    """
    db = SessionLocal()
    try:
        service = MarketDataService(db)
        if service.is_sync_due(SyncType.CATEGORIES):
            service.sync_categories()

        listings_synced = False
        if service.is_sync_due(SyncType.LISTINGS):
            listings_log = service.sync_listings()
            listings_synced = listings_log.status == SyncStatus.SUCCESS
    finally:
        db.close()

    if listings_synced:
        sync_reflex_cache()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        run_market_data_sync,
        trigger="interval",
        hours=settings.sync_interval_hours,
        id="market_data_sync",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
