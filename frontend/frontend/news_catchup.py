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


def ensure_running() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="news-catchup", daemon=True).start()
