"""CoinMarketCap monthly credit guard.

The plan (15,000 credits/month, shared by local dev and the live server
while they use the same key) must always cover the essential syncs: the
hourly top-500 sync (~3 credits) and the daily all-coins sync (~41).
Optional calls (the view sync for coins no exchange lists, the Gainers &
Losers refresh button) only run while the remaining credits exceed a
reserve for those essentials until the month resets.

Credits are read from CMC's /v1/key/info, which costs no credits, at most
every CHECK_SECONDS. If it can't be read, optional calls are allowed (the
other guards still apply: 10-min view throttle, failure backoff).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import requests

from app.core.config import settings

CHECK_SECONDS = 1800
# Essential use per day for one environment: 24 hourly syncs x ~3 credits +
# 1 daily sync x ~41, rounded up; doubled while local and live share a key.
ESSENTIAL_PER_DAY = 250

_lock = threading.Lock()
_cached: tuple[float, dict | None] = (0.0, None)
logger = logging.getLogger(__name__)


def usage(force: bool = False) -> dict | None:
    """{"limit", "used", "left", "reset_at"} for this month, or None if CMC
    can't be asked. Cached CHECK_SECONDS."""
    global _cached
    with _lock:
        at, value = _cached
        if not force and time.time() - at < CHECK_SECONDS:
            return value
    value = None
    if settings.coinmarketcap_api_key:
        try:
            r = requests.get(
                f"{settings.coinmarketcap_base_url}/v1/key/info",
                headers={"X-CMC_PRO_API_KEY": settings.coinmarketcap_api_key, "Accept": "application/json"},
                timeout=10,
            )
            data = r.json().get("data") or {}
            plan, month = data.get("plan") or {}, (data.get("usage") or {}).get("current_month") or {}
            value = {
                "limit": int(plan.get("credit_limit_monthly") or 0),
                "used": int(month.get("credits_used") or 0),
                "left": int(month.get("credits_left") or 0),
                "reset_at": plan.get("credit_limit_monthly_reset_timestamp") or "",
            }
        except Exception:  # noqa: BLE001
            logger.warning("CMC credit check failed", exc_info=True)
    with _lock:
        _cached = (time.time(), value)
    return value


def _days_until_reset(reset_at: str) -> float:
    try:
        reset = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
        return max(0.0, (reset - datetime.now(timezone.utc)).total_seconds() / 86400)
    except (TypeError, ValueError):
        return 31.0


def optional_calls_allowed() -> bool:
    """False when the remaining credits are needed for the essential syncs
    until the monthly reset (or are already used up)."""
    u = usage()
    if u is None:
        return True
    reserve = _days_until_reset(u["reset_at"]) * ESSENTIAL_PER_DAY
    return u["left"] > reserve
