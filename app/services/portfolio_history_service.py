"""The MEXC portfolio's total balance over time, for the /portfolio balance chart.

MEXC keeps no balance history, so the server records it: record_from_mexc() saves the total (USD) every
RECORD_SECONDS from a lifespan task in frontend.py (24/7, whether or not anyone has the page open). Only a fresh,
real reading is saved: never demo data, never the last-good numbers kept on screen during a MEXC error.
series() returns the points of a range, one per bucket (the last reading in each bucket, a balance is a level, not
a sum), so even "full" stays at about MAX_POINTS points however long the history gets. Reads are cached for
CACHE_SECONDS and shared by every viewer."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.portfolio_balance import PortfolioBalance

_log = logging.getLogger(__name__)

RECORD_SECONDS = 300
CACHE_SECONDS = 60
MAX_POINTS = 1000
FRESH_SECONDS = 120  # a snapshot older than this is not recorded (MEXC was failing)
# range -> (window seconds or None for everything, bucket seconds or None to size it from the span)
RANGES = {
    "24h": (86400, 300),
    "7d": (7 * 86400, 1800),
    "1m": (30 * 86400, 3600),
    "full": (None, None),
}

_lock = threading.Lock()
_cache: dict[str, tuple[float, list[tuple[float, float]]]] = {}


def record(total_usd: float, at: datetime | None = None) -> None:
    db = SessionLocal()
    try:
        db.add(PortfolioBalance(at=at or datetime.now(timezone.utc), total_usd=float(total_usd)))
        db.commit()
    finally:
        db.close()
    with _lock:
        _cache.clear()  # the next read includes the new point


def record_from_mexc() -> bool:
    """One recording: True when a reading was saved. Never raises for MEXC trouble (it just skips)."""
    from app.services import mexc_service

    if not mexc_service.is_configured():
        return False
    snap = mexc_service.portfolio(None)
    fresh = snap.get("ok") and not snap.get("error") and time.time() - (snap.get("updated_at") or 0) <= FRESH_SECONDS
    if not fresh or snap.get("demo"):
        return False
    record(snap["total_value"])
    return True


def _bucketed(rows: list[tuple[float, float]], bucket: float) -> list[tuple[float, float]]:
    """The last reading of each bucket (rows oldest first)."""
    out: dict[int, tuple[float, float]] = {}
    for ts, value in rows:
        out[int(ts // bucket)] = (ts, value)
    return [out[k] for k in sorted(out)]


def series(range_key: str = "7d", now: float | None = None) -> list[tuple[float, float]]:
    """[(unix seconds, total USD), ...] oldest first for one of RANGES; [] for an unknown range or no data."""
    if range_key not in RANGES:
        return []
    now = now or time.time()
    with _lock:
        hit = _cache.get(range_key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    window, bucket = RANGES[range_key]
    db = SessionLocal()
    try:
        q = select(PortfolioBalance.at, PortfolioBalance.total_usd).order_by(PortfolioBalance.at)
        if window:
            q = q.where(PortfolioBalance.at >= datetime.fromtimestamp(now - window, timezone.utc))
        rows = [(at.timestamp() if at.tzinfo else at.replace(tzinfo=timezone.utc).timestamp(), v) for at, v in db.execute(q)]
    finally:
        db.close()
    if rows:
        span = max(rows[-1][0] - rows[0][0], 1.0)
        rows = _bucketed(rows, bucket or max(RECORD_SECONDS, span / MAX_POINTS))
    with _lock:
        _cache[range_key] = (now, rows)
    return rows


def first_recorded() -> float | None:
    db = SessionLocal()
    try:
        first = db.execute(select(func.min(PortfolioBalance.at))).scalar()
    finally:
        db.close()
    if first is None:
        return None
    return (first if first.tzinfo else first.replace(tzinfo=timezone.utc)).timestamp()
