"""Keeps /news current after the app (or the machine) was offline.

Nothing else ingests news unless a separate process is running: the RSS /
Google News job lives in the FastAPI scheduler and the Telegram listener is
started by hand. So after being offline, a reload showed stale news. The
first /news or homepage load in a server process now calls ensure_running(),
which starts (once per process) a daemon thread that:

  * immediately, then every few minutes, runs the RSS / Google News pipeline
    (app.scheduler.jobs.run_news_pipeline_sync, gated by its own interval so
    it never re-pulls needlessly), and
  * makes sure exactly one app.services.telegram_listener process is alive.
    On start it catches up every missed post since each group's last stored
    one, so the offline gap (up to the 30-day window) is filled.

  * (own thread) re-checks coin business-model categories with OpenRouter,
    one batch per settings.coin_category_interval_minutes
    (app/services/coin_category_service.py).

  * (own thread, kicked on every page load) picks a target coin for every
    untargeted recent Cryptocurrency article — AI in batches, plus a rule
    fallback when the AI is unavailable (app/services/news_targeting_service.py).

  * (own thread) runs the existing hourly hot listings sync
    (app.scheduler.jobs.run_hot_listings_sync: top 500 coins, one CMC call,
    gated by its own SyncLog interval) and the daily full listings sync
    (run_listings_sync: every coin, 24h gate). Both record the price
    snapshots behind /gainers-losers and the coin page's 24h market cap /
    volume change. The FastAPI scheduler that normally
    runs it is not running, so without this the snapshots would never grow.

  * (own thread) runs Telegram media maintenance
    (app.services.telegram_media_cleanup.run_media_maintenance): converts
    any stray non-webp image to .webp, strips any stray playable video file
    down to its poster, and deletes image/poster files for posts older
    than MEDIA_RETENTION_DAYS (30), clearing image_url/media so the app's
    own existing fallback takes over. Article text is never touched.

NewsState.watch_new_articles then shows the new rows without a reload.
"""

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger("news_catchup")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CHECK_INTERVAL_SECONDS = 5 * 60

_lock = threading.Lock()
_started = False


def _listener_running() -> bool:
    # Case-insensitive on purpose: macOS shows the interpreter as "Python".
    result = subprocess.run(
        ["pgrep", "-fi", "app.services.telegram_listener"], capture_output=True, text=True
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _ensure_listener() -> None:
    if _listener_running():
        return
    if not (_REPO_ROOT / "telegram_session.session").exists():
        return  # not logged in yet (scripts/telegram_login.py)
    log = open(_REPO_ROOT / "telegram_listener.log", "ab")
    subprocess.Popen(
        [sys.executable, "-m", "app.services.telegram_listener"],
        cwd=_REPO_ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # survives a Reflex restart; next check sees it running
    )
    logger.info("Started telegram_listener")


def _loop() -> None:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    while True:
        try:
            _ensure_listener()
        except Exception:  # noqa: BLE001 — never let the loop die
            logger.exception("telegram listener check failed")
        try:
            from app.scheduler.jobs import run_news_pipeline_sync

            run_news_pipeline_sync()
        except Exception:  # noqa: BLE001
            logger.exception("news pipeline catch-up failed")
        time.sleep(_CHECK_INTERVAL_SECONDS)


_target_wake = threading.Event()
_last_kick = 0.0


def _targeting_loop() -> None:
    """Coin targeting for the Narrative Radar, on its own thread so it never
    waits behind the slow RSS / Google News pull: runs at start-up, every 2
    minutes, and whenever a page load kicks it; each run drains the whole
    untargeted backlog (AI in batches of 10, rules if the AI is unavailable)."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    while True:
        try:
            from app.services.news_category import categorize_pending
            from app.services.news_targeting_service import drain

            drain()
            # Accurate label + shared use-case group for what was just targeted.
            categorize_pending()
        except Exception:  # noqa: BLE001
            logger.exception("news targeting failed")
        _target_wake.wait(timeout=120)
        _target_wake.clear()


def _category_loop() -> None:
    """Weekly coin-category re-check: one OpenRouter batch per interval."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from app.core.config import settings

    time.sleep(60)  # let start-up traffic (summaries, targeting) go first
    while True:
        try:
            from app.services.coin_category_service import refresh_batch

            refresh_batch()
        except Exception:  # noqa: BLE001
            logger.exception("coin category refresh failed")
        time.sleep(max(settings.coin_category_interval_minutes, 5) * 60)


_SNAPSHOT_CHECK_SECONDS = 10 * 60


def _hot_sync_loop() -> None:
    """Hourly top-500 and daily all-coin price refresh + price snapshots.
    Checks every 10 minutes; each job only calls CMC once its own interval
    (1h / 24h) is due."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    while True:
        try:
            from app.scheduler.jobs import run_hot_listings_sync

            run_hot_listings_sync()
        except Exception:  # noqa: BLE001
            logger.exception("hot listings sync failed")
        try:
            from app.scheduler.jobs import run_listings_sync

            run_listings_sync()  # every coin, once a day (24h gate)
        except Exception:  # noqa: BLE001
            logger.exception("daily listings sync failed")
        time.sleep(_SNAPSHOT_CHECK_SECONDS)


_MEDIA_MAINTENANCE_INTERVAL_SECONDS = 12 * 3600


def _media_maintenance_loop() -> None:
    """Keeps frontend/assets/telegram_media/ bounded — see
    app.services.telegram_media_cleanup for what each pass does. Runs at
    startup, then every 12 hours; each step is cheap/idempotent once its
    one-time backfill is done, so a 12h cadence is plenty for a 30-day
    retention window."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    while True:
        try:
            from app.services.telegram_media_cleanup import run_media_maintenance

            run_media_maintenance()
        except Exception:  # noqa: BLE001
            logger.exception("telegram media maintenance failed")
        time.sleep(_MEDIA_MAINTENANCE_INTERVAL_SECONDS)


def ensure_running() -> None:
    """Called on every /news and homepage load: starts the workers once per
    process, and on later calls re-triggers a targeting run (at most every 20s)
    so a refresh picks up articles that arrived while nobody was looking."""
    global _started, _last_kick
    with _lock:
        if _started:
            if time.monotonic() - _last_kick > 20:
                _last_kick = time.monotonic()
                _target_wake.set()
            return
        _started = True
        _last_kick = time.monotonic()
    threading.Thread(target=_loop, name="news-catchup", daemon=True).start()
    threading.Thread(target=_targeting_loop, name="news-targeting", daemon=True).start()
    threading.Thread(target=_category_loop, name="coin-categories", daemon=True).start()
    threading.Thread(target=_hot_sync_loop, name="hot-sync-snapshots", daemon=True).start()
    threading.Thread(target=_media_maintenance_loop, name="telegram-media-maintenance", daemon=True).start()
