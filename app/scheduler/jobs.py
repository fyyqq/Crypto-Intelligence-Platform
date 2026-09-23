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
    Contracts (per-coin chain list) sync on the same 24h cadence, gated by
    their own SyncType so a listings-only run never skips them and a
    contracts-only rerun never re-burns listings credits.
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

        contracts_synced = False
        if service.is_sync_due(SyncType.CONTRACTS):
            contracts_log = service.sync_contracts()
            contracts_synced = contracts_log.status == SyncStatus.SUCCESS
    finally:
        db.close()

    if listings_synced or contracts_synced:
        sync_reflex_cache()


def run_hot_listings_sync() -> None:
    """Runs every HOT_SYNC_INTERVAL_HOURS (default 1h): a single cheap
    listings/latest call for just the top HOT_SYNC_TOP_N coins, so their
    price/market cap/volume/1h/24h/7d stay near-live between the slower
    full 24h sync_listings runs (which cover the entire ~8,000-coin
    universe and are what protect the free-tier credit limit per Rule 4).
    """
    db = SessionLocal()
    try:
        service = MarketDataService(db)
        hot_synced = False
        if service.is_sync_due(SyncType.LISTINGS_HOT, interval_hours=settings.hot_sync_interval_hours):
            hot_log = service.sync_hot_listings()
            hot_synced = hot_log.status == SyncStatus.SUCCESS
    finally:
        db.close()

    if hot_synced:
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
    scheduler.add_job(
        run_hot_listings_sync,
        trigger="interval",
        hours=settings.hot_sync_interval_hours,
        id="hot_listings_sync",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
