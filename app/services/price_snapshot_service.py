"""Price history and the Top Gainers / Top Losers boards (/gainers-losers).

% change is computed from the app's own price_snapshot rows, never from
CMC's percent_change_* fields:

    pct_change = (price_now - price_then) / price_then * 100

price_now  = the coin's row in the most recent sync.
price_then = the coin's snapshot closest to (now - lookback), but only if it
             falls inside that window's tolerance range; otherwise the coin
             is skipped for that window (new coin or missing history).

Every window lives in WINDOWS; adding a window means adding one entry there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.price_snapshot import PriceSnapshot


@dataclass(frozen=True)
class Window:
    label: str  # shown in the UI
    lookback: timedelta  # target age of the "then" snapshot
    min_age: timedelta  # accepted range for the "then" snapshot: min_age..max_age old
    max_age: timedelta


# One entry per window. A fixed 30 days, not a calendar month.
WINDOWS: dict[str, Window] = {
    "24h": Window("24h", timedelta(hours=24), timedelta(hours=20), timedelta(hours=28)),
    "7d": Window("7d", timedelta(days=7), timedelta(days=6), timedelta(days=8)),
    "30d": Window("1 Month", timedelta(days=30), timedelta(days=28), timedelta(days=32)),
}

BUCKETS: tuple[int, ...] = (100, 200, 300, 400, 500)  # Top N by cmc_rank, cumulative
DIRECTIONS: tuple[str, ...] = ("gainers", "losers")
DEFAULT_LIMIT = 30

# Dust floor: coins whose CURRENT 24h volume is below this are left out of
# every board (gainers and losers, every window).
MIN_VOLUME_USD = 50_000

# Snapshots older than this are deleted. Must stay longer than the longest
# window's lookback plus its tolerance (validate_retention).
RETENTION_DAYS = 45


class SnapshotConfigError(ValueError):
    pass


# ---- Step 1: recording -----------------------------------------------------
def record_snapshots(db: Session, payloads: list[dict], synced_at: datetime | None = None) -> int:
    """Adds one PriceSnapshot per coin in a CMC listings/quotes payload and
    commits. Insert-only: never updates or deletes an existing row. A coin
    with no usable price (missing, zero or negative) is skipped, since it
    could never be used to compute a % change. Returns the rows added.

    `synced_at` is UTC (naive, like the rest of the app); one sync shares one
    timestamp so all its rows line up."""
    synced_at = synced_at or datetime.utcnow()
    rows = []
    for payload in payloads:
        quote = (payload.get("quote") or {}).get("USD") or {}
        price = quote.get("price")
        if price is None or price <= 0:
            continue
        rows.append(
            PriceSnapshot(
                coin_id=payload["id"],
                symbol=payload.get("symbol") or "",
                price_usd=price,
                cmc_rank=payload.get("cmc_rank"),
                volume_24h=quote.get("volume_24h"),
                synced_at=synced_at,
            )
        )
    db.add_all(rows)
    db.commit()
    return len(rows)


# ---- Step 3 (storage): retention -------------------------------------------
def longest_window_reach(windows: dict[str, Window] = WINDOWS) -> timedelta:
    """The oldest snapshot any window can ever need (lookback + tolerance)."""
    return max(w.max_age for w in windows.values())


def validate_retention(retention_days: float = RETENTION_DAYS, windows: dict[str, Window] = WINDOWS) -> None:
    """Raises if retention would delete snapshots a window still needs."""
    reach = longest_window_reach(windows)
    if timedelta(days=retention_days) <= reach:
        raise SnapshotConfigError(
            f"RETENTION_DAYS={retention_days} is too short: it must be longer than the longest "
            f"window's lookback plus tolerance ({reach.days} days), or cleanup would delete "
            "snapshots that window still needs."
        )


# Checked when this module is imported, i.e. at app start-up.
validate_retention()


def cleanup_snapshots(db: Session, now: datetime | None = None, retention_days: float = RETENTION_DAYS) -> int:
    """Deletes snapshots older than the retention period and commits.
    Returns the rows deleted. Refuses to run with an unsafe retention."""
    validate_retention(retention_days)
    cutoff = (now or datetime.utcnow()) - timedelta(days=retention_days)
    result = db.execute(delete(PriceSnapshot).where(PriceSnapshot.synced_at < cutoff))
    db.commit()
    return result.rowcount or 0


# ---- Steps 2-4: lookback + cold start --------------------------------------
def get_window(name: str) -> Window:
    window = WINDOWS.get(name)
    if window is None:
        raise SnapshotConfigError(f"Unknown window '{name}'. Valid windows: {', '.join(WINDOWS)}.")
    return window


def _latest_sync_time(db: Session) -> datetime | None:
    return db.scalar(select(func.max(PriceSnapshot.synced_at)))


def window_status(db: Session, window_name: str) -> dict:
    """Cold start, per window and independent of the others: a window is
    ready once the oldest stored snapshot is at least its min_age old
    (relative to the latest sync). Otherwise it is "collecting" and says how
    long until it can start."""
    window = get_window(window_name)
    latest = _latest_sync_time(db)
    oldest = db.scalar(select(func.min(PriceSnapshot.synced_at)))
    history = (latest - oldest) if latest and oldest else timedelta(0)
    if latest is not None and history >= window.min_age:
        return {"status": "ready", "days_remaining": 0, "hours_remaining": 0, "history_since": oldest}
    remaining = window.min_age - history
    hours = math.ceil(remaining.total_seconds() / 3600)
    return {
        "status": "collecting",
        "days_remaining": math.ceil(remaining.total_seconds() / 86400),
        "hours_remaining": hours,
        "history_since": oldest,
    }


def compute_changes(db: Session, window_name: str) -> list[dict]:
    """THE one % change calculation, shared by gainers and losers.

    For every coin in the latest sync: finds its snapshot closest to
    (now - lookback) inside the window's tolerance and computes the change.
    Skipped: coins with no snapshot in tolerance (new coins / missed syncs
    with nothing usable), a zero or missing price, and dust coins (current
    volume_24h below MIN_VOLUME_USD). Coins are returned unsorted, with their
    current rank, so any bucket/direction can be cut from one result."""
    window = get_window(window_name)
    latest = _latest_sync_time(db)
    if latest is None:
        return []

    current = db.scalars(select(PriceSnapshot).where(PriceSnapshot.synced_at == latest)).all()
    current = [
        s for s in current
        if s.price_usd and float(s.price_usd) > 0
        and s.volume_24h is not None and float(s.volume_24h) >= MIN_VOLUME_USD
        and s.cmc_rank is not None
    ]
    if not current:
        return []
    ids = [s.coin_id for s in current]

    target = latest - window.lookback
    lo, hi = latest - window.max_age, latest - window.min_age
    candidates = db.execute(
        select(PriceSnapshot.coin_id, PriceSnapshot.price_usd, PriceSnapshot.synced_at).where(
            PriceSnapshot.coin_id.in_(ids),
            PriceSnapshot.synced_at >= lo,
            PriceSnapshot.synced_at <= hi,
        )
    ).all()
    # Closest to the target time wins (a missed sync falls back to the next
    # closest snapshot that is still inside the tolerance).
    then_by_coin: dict[int, tuple[float, datetime]] = {}
    for coin_id, price, synced_at in candidates:
        if price is None or float(price) <= 0:
            continue
        best = then_by_coin.get(coin_id)
        if best is None or abs(synced_at - target) < abs(best[1] - target):
            then_by_coin[coin_id] = (float(price), synced_at)

    names = dict(db.execute(select(Coin.cmc_id, Coin.name).where(Coin.cmc_id.in_(ids))).all())

    changes = []
    for snap in current:
        then = then_by_coin.get(snap.coin_id)
        if then is None:
            continue  # no usable history for this window yet
        price_then, then_at = then
        price_now = float(snap.price_usd)
        changes.append(
            {
                "coin_id": snap.coin_id,
                "rank": snap.cmc_rank,
                "name": names.get(snap.coin_id) or snap.symbol,
                "symbol": snap.symbol,
                "price_now": price_now,
                "price_then": price_then,
                "pct_change": (price_now - price_then) / price_then * 100,
                "volume_24h": float(snap.volume_24h),
                "then_at": then_at,
                "now_at": latest,
            }
        )
    return changes


# ---- Step 5: one ranking for both directions -------------------------------
def rank_movers(changes: list[dict], bucket: int, direction: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Cuts gainers or losers out of compute_changes' result. Gainers: change
    > 0, biggest first. Losers: change < 0, most negative first. Exactly 0%
    is in neither. Never padded: fewer qualifying coins = a shorter list."""
    if bucket not in BUCKETS:
        raise SnapshotConfigError(f"Unknown bucket {bucket}. Valid buckets: {', '.join(map(str, BUCKETS))}.")
    if direction not in DIRECTIONS:
        raise SnapshotConfigError(f"Unknown direction '{direction}'. Use 'gainers' or 'losers'.")
    sign = 1 if direction == "gainers" else -1
    picked = [c for c in changes if c["rank"] <= bucket and c["pct_change"] * sign > 0]
    picked.sort(key=lambda c: c["pct_change"] * sign, reverse=True)
    return picked[: max(0, limit)]


# ---- Step 6: output ----------------------------------------------------------
def get_movers(
    db: Session, bucket: int, window: str, direction: str, limit: int = DEFAULT_LIMIT
) -> dict:
    """Top gainers or losers for one bucket and window. Returns
    {"window", "label", "status", "days_remaining", "hours_remaining", "coins"}:
    status "collecting" (with time remaining and no coins) until the window
    has enough history, then "ready" with up to `limit` coins, each with
    rank, name, symbol, price_now, price_then, pct_change, volume_24h and
    then_at (the snapshot time used for price_then)."""
    w = get_window(window)  # rejects unknown windows first
    status = window_status(db, window)
    coins = rank_movers(compute_changes(db, window), bucket, direction, limit) if status["status"] == "ready" else []
    return {
        "window": window,
        "label": w.label,
        "status": status["status"],
        "days_remaining": status["days_remaining"],
        "hours_remaining": status["hours_remaining"],
        "coins": coins,
    }
