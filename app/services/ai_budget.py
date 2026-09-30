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

In-process only (resets on restart), which is enough to stop runaway spend.
"""

import threading
import time
from collections import deque

from app.core.config import settings

_lock = threading.Lock()
_calls: deque[float] = deque()
_failed_at: dict[str, float] = {}


def allow_call() -> bool:
    """True (and records the call) if the hourly budget has room."""
    limit = settings.openrouter_max_calls_per_hour
    now = time.monotonic()
    with _lock:
        while _calls and now - _calls[0] > 3600:
            _calls.popleft()
        if limit and len(_calls) >= limit:
            return False
        _calls.append(now)
        return True


def in_cooldown(key: str) -> bool:
    with _lock:
        failed = _failed_at.get(key)
    return failed is not None and time.monotonic() - failed < settings.openrouter_failure_cooldown_minutes * 60


def mark_failed(key: str) -> None:
    with _lock:
        _failed_at[key] = time.monotonic()
