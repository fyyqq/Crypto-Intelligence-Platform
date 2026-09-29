from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.sync_log import SyncLog, SyncStatus, SyncType
from app.services.market_data_service import MarketDataService
from app.services.reflex_cache_service import sync_reflex_cache

scheduler = BackgroundScheduler(timezone="UTC")


def _news_sync_due(db) -> bool:
    """Same once-per-interval gate as MarketDataService.is_sync_due, kept
    standalone here rather than on that class since the news pipeline is
    deliberately not a MarketDataService concern (see
    app/services/news_pipeline.py's own "genuinely standalone" docstring)
    — this only needs the shared SyncLog table's gating convention, not
    anything else that class owns. (Telegram ingestion isn't scheduled
    here — it runs in its own always-on process, telegram_listener.py.)
    """
    stmt = (
        select(SyncLog)
        .where(SyncLog.sync_type == SyncType.NEWS_PIPELINE, SyncLog.status == SyncStatus.SUCCESS)
        .order_by(SyncLog.started_at.desc())
        .limit(1)
    )
    last_success = db.scalars(stmt).first()
    if last_success is None:
        return True
    cutoff = datetime.utcnow() - timedelta(hours=settings.news_pipeline_sync_interval_hours)
    return last_success.started_at < cutoff


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


def run_news_pipeline_sync() -> None:
    """Runs the standalone news pipeline (app/services/news_pipeline.py)
    once every NEWS_PIPELINE_SYNC_INTERVAL_HOURS (default 24h). Gated by
    _news_sync_due the same way every other job in this module gates
    itself, so an app restart within the interval never re-triggers a real
    ~75-request Google News historical pull for no reason.

    Unlike this module's other jobs, the pipeline manages its own raw
    psycopg2 connection rather than taking this app's SQLAlchemy Session
    (a deliberate design choice — see that module's own docstring for why
    it's genuinely standalone) — this just calls its two ingest functions
    directly against a NewsDB(), then records the run in the same SyncLog
    table this app's other scheduled jobs already use, purely so
    _news_sync_due has something to gate on next time.

    Real-time RSS feeds (TechCrunch/Cointelegraph/WIRED) only ever expose a
    site's current "latest N" items, not a real archive — running this
    daily is what lets genuine 90-day-deep coverage for those three sources
    accumulate over time, since each day's run picks up whatever's newly
    published since the last one (already-seen URLs are skipped, per the
    pipeline's own idempotency guarantee).
    """
    db = SessionLocal()
    try:
        if not _news_sync_due(db):
            return
        log = SyncLog(sync_type=SyncType.NEWS_PIPELINE, status=SyncStatus.RUNNING)
        db.add(log)
        db.commit()
        try:
            from app.services.news_pipeline import NewsDB, ingest_historical_google_news, ingest_rss_feeds

            news_db = NewsDB()
            try:
                rss_stats = ingest_rss_feeds(news_db)
                google_stats = ingest_historical_google_news(news_db)
            finally:
                news_db.close()
            log.status = SyncStatus.SUCCESS
            log.records_synced = rss_stats.inserted + google_stats.inserted
        except Exception as exc:  # noqa: BLE001 — recorded on the log, not raised
            log.status = SyncStatus.FAILED
            log.error_message = str(exc)[:2048]
        finally:
            log.finished_at = datetime.utcnow()
            db.add(log)
            db.commit()
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
    scheduler.add_job(
        run_news_pipeline_sync,
        trigger="interval",
        hours=settings.news_pipeline_sync_interval_hours,
        id="news_pipeline_sync",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
