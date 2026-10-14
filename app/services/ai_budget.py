"""Cost guard shared by every OpenRouter caller (coin AI summary, coin
description fallback, news article summary). All of them already run only
when a viewer opens a page (never from a scheduler or list page); this adds
two more limits, since the free tier will be replaced by a paid model:

* a global cap on OpenRouter HTTP calls per rolling hour
  (settings.openrouter_max_calls_per_hour, 0 = unlimited), counting retries
  and fallback-model attempts;
* a failure cooldown: after a generation fails for an item (e.g. every model
  overloaded), that item is not retried on every page view for
  settings.openrouter_failure_cooldown_minutes.

The hourly cap and the failure cooldown are in-process only (they reset on restart), which is enough
to stop runaway spend. The free tier's real limit is per DAY (OpenRouter: 50 "free-models-per-day"
requests per account, reset at 00:00 UTC, shared by every process and machine using the key), so
that one is kept on disk (logs/ai_budget.json), shared by the web server, the news pipeline process
and the Telegram listener on one machine:

* `openrouter_daily_limit` calls a day (0 = unlimited, for an account with credits);
* page-visit summaries (coin summary, news summary, description) own the last
  `openrouter_visit_reserve` calls of the day: background work (Telegram post classification, news
  targeting, the weekly coin category check, run inside `with background():`) stops earlier, so the
  quota is never used up before people open pages;
* the first HTTP 429 that says the daily limit is reached (`note_response`) blocks every call until the
  reset time OpenRouter names, instead of burning more requests (each failed request still counts).
"""

import contextlib
import contextvars
import fcntl
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

_lock = threading.Lock()
_calls: deque[float] = deque()
_failed_at: dict[str, float] = {}
_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "ai_budget.json"
_background: contextvars.ContextVar[bool] = contextvars.ContextVar("ai_background", default=False)


@contextlib.contextmanager
def background():
    """Calls made inside are background work (not triggered by a page visit): they may not use the visit reserve."""
    token = _background.set(True)
    try:
        yield
    finally:
        _background.reset(token)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@contextlib.contextmanager
def _state():
    """The day's counters {"day", "used", "blocked_until"} under a file lock (shared by processes); saved on exit."""
    _STATE_FILE.parent.mkdir(exist_ok=True)
    with open(_STATE_FILE.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(_STATE_FILE.read_text())
        except Exception:  # noqa: BLE001
            state = {}
        if state.get("day") != _today():
            state = {"day": _today(), "used": 0, "blocked_until": 0}
        yield state
        _STATE_FILE.write_text(json.dumps(state))


def daily_allows(used: int, background_work: bool) -> bool:
    limit = settings.openrouter_daily_limit
    if not limit:
        return True
    cap = limit - (max(0, settings.openrouter_visit_reserve) if background_work else 0)
    return used < cap


def note_response(status: int, body: str, now: float | None = None) -> bool:
    """Call after a failed OpenRouter response. True when it was the daily free-tier limit (every further
    call is then blocked until OpenRouter's reset time, or the end of the UTC day when it names none)."""
    if status != 429 or "free-models-per-day" not in (body or ""):
        return False
    now = now or time.time()
    reset = 0.0
    try:
        reset = float(((json.loads(body).get("error") or {}).get("metadata") or {}).get("headers", {}).get("X-RateLimit-Reset", 0)) / 1000
    except Exception:  # noqa: BLE001
        pass
    if reset <= now:
        reset = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)).timestamp() + 86400
    try:
        with _state() as st:
            st["blocked_until"] = max(st.get("blocked_until", 0), reset)
    except Exception:  # noqa: BLE001
        pass
    return True


def blocked() -> bool:
    """True while the daily limit is known to be reached (nothing is attempted until the reset)."""
    try:
        with _state() as st:
            return time.time() < st.get("blocked_until", 0)
    except Exception:  # noqa: BLE001
        return False


def allow_call() -> bool:
    """True (and records the call) if the hourly and daily budgets have room."""
    limit = settings.openrouter_max_calls_per_hour
    now = time.monotonic()
    with _lock:
        while _calls and now - _calls[0] > 3600:
            _calls.popleft()
        if limit and len(_calls) >= limit:
            return False
        try:
            with _state() as st:
                if time.time() < st.get("blocked_until", 0) or not daily_allows(st["used"], _background.get()):
                    return False
                st["used"] += 1
        except Exception:  # noqa: BLE001  (an unreadable state file must not take summaries down)
            pass
        _calls.append(now)
        return True


def in_cooldown(key: str) -> bool:
    with _lock:
        failed = _failed_at.get(key)
    return failed is not None and time.monotonic() - failed < settings.openrouter_failure_cooldown_minutes * 60


def mark_failed(key: str) -> None:
    if blocked():  # the daily limit, not this item, failed: retry it as soon as the limit resets
        return
    with _lock:
        _failed_at[key] = time.monotonic()
