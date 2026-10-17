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
import re
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.movers_daily import MoversDaily
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

# Rank bands by current cmc_rank, not cumulative: 200 = ranks 101-200, so a
# coin shows up in exactly one band.
BUCKETS: tuple[int, ...] = (100, 200, 300, 400, 500)


def bucket_floor(bucket: int) -> int:
    """Last rank of the band below: 0 for 100, 100 for 200, ..."""
    i = BUCKETS.index(bucket)
    return BUCKETS[i - 1] if i else 0


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
def _fit(value, limit: float):
    """The value, or None when it can't fit its Numeric column."""
    if value is None:
        return None
    try:
        return value if abs(float(value)) < limit else None
    except (TypeError, ValueError):
        return None


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
        if price is None or price <= 0 or price >= 1e20:  # Numeric(38, 18)
            continue
        rows.append(
            PriceSnapshot(
                coin_id=payload["id"],
                symbol=payload.get("symbol") or "",
                price_usd=price,
                cmc_rank=payload.get("cmc_rank"),
                # Absurd CMC values that can't fit the column are dropped
                # (None) rather than failing the whole batch.
                volume_24h=_fit(quote.get("volume_24h"), 1e22),  # Numeric(24, 2)
                market_cap=_fit(quote.get("market_cap"), 1e34),  # Numeric(36, 2)
                synced_at=synced_at,
            )
        )
    db.add_all(rows)
    db.commit()
    return len(rows)


# Hourly snapshots normally come from the CMC top-500 sync. When that can't
# run (credits used up, CMC down), record_hub_snapshots fills the gap from the
# free exchange price list so the boards keep moving.
HUB_SNAPSHOT_GAP = timedelta(minutes=55)
HUB_SNAPSHOT_TOP_N = 500


def record_hub_snapshots(db: Session, now: datetime | None = None) -> int:
    """Records one snapshot of the top HUB_SNAPSHOT_TOP_N coins from the shared
    exchange price list (app/services/price_hub.py) when no snapshot of any
    source landed in the last HUB_SNAPSHOT_GAP, and commits. Only coins whose
    exchange price is plausible against their stored price are written (a
    coin no exchange lists is left out of that hour rather than given a
    stale price, which would fake a 0% change). Rank and 24h volume are the
    coin's stored values; market cap is scaled by the price move. Returns
    the rows written (0 if a recent snapshot exists or nothing was priced)."""
    from app.services import price_hub

    now = now or datetime.utcnow()
    latest = _latest_sync_time(db)
    if latest is not None and now - latest < HUB_SNAPSHOT_GAP:
        return 0
    prices = price_hub.get_prices()
    coins = db.scalars(
        select(Coin).where(Coin.cmc_rank.is_not(None), Coin.cmc_rank <= HUB_SNAPSHOT_TOP_N)
    ).all()
    rows = []
    for c in coins:
        ref = float(c.price_usd or 0)
        quote = prices.get((c.symbol or "").upper())
        if not quote or not price_hub.plausible(quote["price"], ref):
            continue
        price = quote["price"]
        cap = float(c.market_cap_usd) * price / ref if c.market_cap_usd else None
        rows.append(
            PriceSnapshot(
                coin_id=c.cmc_id,
                symbol=c.symbol or "",
                price_usd=price,
                cmc_rank=c.cmc_rank,
                volume_24h=_fit(c.volume_24h_usd, 1e22),
                market_cap=_fit(cap, 1e34),
                synced_at=now,
            )
        )
    if not rows:
        return 0
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


def pct_change(value_now, value_then) -> float | None:
    """The one formula: (now - then) / then * 100. None when either side is
    missing or the old value is zero/negative (never divides by it)."""
    if value_now is None or value_then is None:
        return None
    now, then = float(value_now), float(value_then)
    if then <= 0:
        return None
    return (now - then) / then * 100


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
    ready once a snapshot exists that is min_age..max_age older than the
    latest sync (the baseline compute_changes compares against). Otherwise it
    is "collecting" and says how long until it can start. That also covers a
    gap in the recording (e.g. CMC credits ran out and nothing was stored for
    a day): old history alone does not make a window ready, and the clock
    restarts from the first snapshot after the gap."""
    window = get_window(window_name)
    latest = _latest_sync_time(db)
    oldest = db.scalar(select(func.min(PriceSnapshot.synced_at)))
    if latest is None or oldest is None:
        remaining = window.min_age
        return {
            "status": "collecting",
            "days_remaining": math.ceil(remaining.total_seconds() / 86400),
            "hours_remaining": math.ceil(remaining.total_seconds() / 3600),
            "history_since": oldest,
        }
    lo, hi = latest - window.max_age, latest - window.min_age
    baseline = db.scalar(select(func.min(PriceSnapshot.synced_at)).where(PriceSnapshot.synced_at >= lo))
    if baseline is not None and baseline <= hi:
        return {"status": "ready", "days_remaining": 0, "hours_remaining": 0, "history_since": oldest}
    # Usable history starts at `baseline` (the first snapshot inside the
    # tolerance range); it becomes old enough min_age after it was taken.
    start = baseline if baseline is not None else latest
    remaining = max(start + window.min_age - latest, timedelta(0))
    return {
        "status": "collecting",
        "days_remaining": math.ceil(remaining.total_seconds() / 86400),
        "hours_remaining": math.ceil(remaining.total_seconds() / 3600),
        "history_since": start,
    }


# ---- Stablecoins are left out of the Gainers & Losers boards ----------------------------------------
# A stablecoin is not a mover: its few-hundredths-of-a-percent wobbles around $1 would otherwise fill the Losers
# board on a quiet day. A coin counts as one when
#  1. CoinMarketCap tags it a stablecoin (any category with "stablecoin" in its name) AND it trades near a peg
#     (0.85-1.35 USD: the dollar, euro stablecoins at ~1.12, yield-bearing ones drifting above 1). The price check
#     matters: the "Stablecoin" tags also sit on protocol and chain tokens (XPL, STABLE, FF, TEL) that really move;
#  2. or it is not tagged, looks like a dollar token by name/ticker (usd, dollar, stable, euro, US...), sits within
#     0.97-1.03 USD and moved no more than 2% in the window (a depegged, untagged coin is a real mover).
STABLE_PEG_RANGE = (0.85, 1.35)
STABLE_HINT_PRICE_RANGE = (0.97, 1.03)
STABLE_MAX_MOVE_PCT = 2.0
_STABLE_NAME_HINT = re.compile(r"usd|dollar|stable|euro|\beur", re.I)
_STABLE_SYMBOL_HINT = re.compile(r"us[a-z]{0,3}|eur[a-z]{0,3}", re.I)
_stable_cache: dict = {"at": 0.0, "ids": frozenset()}
STABLE_IDS_TTL = 600


def stablecoin_ids(db: Session) -> frozenset[int]:
    """cmc ids of the coins CoinMarketCap tags as a stablecoin (cached 10 minutes; a failed read keeps the last copy)."""
    import time

    if time.time() - _stable_cache["at"] < STABLE_IDS_TTL:
        return _stable_cache["ids"]
    from app.models.category import Category, coin_category

    try:
        ids = frozenset(
            db.scalars(
                select(Coin.cmc_id)
                .join(coin_category, coin_category.c.coin_id == Coin.id)
                .join(Category, Category.id == coin_category.c.category_id)
                .where(Category.name.ilike("%stablecoin%"))
                .distinct()
            ).all()
        )
    except Exception:  # noqa: BLE001 - keep the last known set; the price heuristic still applies
        return _stable_cache["ids"]
    _stable_cache.update(at=time.time(), ids=ids)
    return ids


def is_stablecoin(c: dict, tagged: frozenset[int] | set[int] | None = None) -> bool:
    """True for a stablecoin (see the rules above) given one change row."""
    price = float(c.get("price_now") or 0)
    if tagged and c["coin_id"] in tagged and STABLE_PEG_RANGE[0] <= price <= STABLE_PEG_RANGE[1]:
        return True
    if STABLE_HINT_PRICE_RANGE[0] <= price <= STABLE_HINT_PRICE_RANGE[1] and abs(c.get("pct_change") or 0) <= STABLE_MAX_MOVE_PCT:
        name, symbol = c.get("name") or "", c.get("symbol") or ""
        return bool(_STABLE_NAME_HINT.search(name) or _STABLE_SYMBOL_HINT.fullmatch(symbol))
    return False


def _stable(c: dict) -> bool:
    """The row's own flag (set by compute_changes / load_daily_movers from the database tags) or, for a row without
    one, the price rules alone."""
    return c["stable"] if "stable" in c else is_stablecoin(c)


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
    tagged = stablecoin_ids(db)

    changes = []
    for snap in current:
        then = then_by_coin.get(snap.coin_id)
        if then is None:
            continue  # no usable history for this window yet
        price_then, then_at = then
        price_now = float(snap.price_usd)
        change = pct_change(price_now, price_then)
        if change is None:
            continue
        changes.append(
            {
                "coin_id": snap.coin_id,
                "rank": snap.cmc_rank,
                "name": names.get(snap.coin_id) or snap.symbol,
                "symbol": snap.symbol,
                "price_now": price_now,
                "price_then": price_then,
                "pct_change": change,
                "volume_24h": float(snap.volume_24h),
                "then_at": then_at,
                "now_at": latest,
            }
        )
        changes[-1]["stable"] = is_stablecoin(changes[-1], tagged)  # kept in the list (sector scores use it), left off the boards
    return changes


# ---- Coin page: market cap / volume vs ~24h ago -----------------------------
def get_reference_values(db: Session, coin_id: int, window_name: str = "24h", now: datetime | None = None) -> dict:
    """A coin's market cap and 24h volume from about one window ago (default
    24h), for the coin page's change badges. Same lookback rule as the
    boards: the snapshot closest to (now - lookback) inside the window's
    tolerance, chosen separately per field (a snapshot may lack market cap).
    Returns {"market_cap", "market_cap_at", "volume_24h", "volume_24h_at"};
    a value is None when no usable snapshot exists."""
    window = get_window(window_name)
    now = now or datetime.utcnow()
    target = now - window.lookback
    rows = db.execute(
        select(PriceSnapshot.market_cap, PriceSnapshot.volume_24h, PriceSnapshot.synced_at).where(
            PriceSnapshot.coin_id == coin_id,
            PriceSnapshot.synced_at >= now - window.max_age,
            PriceSnapshot.synced_at <= now - window.min_age,
        )
    ).all()
    out = {"market_cap": None, "market_cap_at": None, "volume_24h": None, "volume_24h_at": None}
    for field, index in (("market_cap", 0), ("volume_24h", 1)):
        usable = [(r[index], r[2]) for r in rows if r[index] is not None and float(r[index]) > 0]
        if usable:
            value, at = min(usable, key=lambda v: abs(v[1] - target))
            out[field], out[f"{field}_at"] = float(value), at
    return out


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
    floor = bucket_floor(bucket)
    picked = [c for c in changes if floor < c["rank"] <= bucket and c["pct_change"] * sign > 0 and not _stable(c)]
    picked.sort(key=lambda c: c["pct_change"] * sign, reverse=True)
    return picked[: max(0, limit)]


# ---- Live prices on top of the hourly snapshots -----------------------------------------------------
# The boards compare a coin's price NOW with its price ~24h / 7d / 30d ago (the hourly snapshots). The snapshots only
# change once an hour, so "now" is re-priced from live sources every LIVE_TTL seconds and the % change and the
# ordering follow it. Sources, best first, per coin: the shared exchange price list (price_hub: Binance / OKX / Bybit /
# Gate, four bulk calls per refresh however many people watch, ~30 s fresh), then the stored price (refreshed every ~5
# minutes from the exchange list and DexScreener by free_price_sync), then the snapshot's own price. The result is shared
# by every viewer, and a forced refresh (the page's refresh icon) is rate limited to one per FORCE_MIN_GAP seconds.
LIVE_TTL = 30
FORCE_MIN_GAP = 10
LIVE_MAX_SNAPSHOT_AGE = timedelta(hours=3)  # a staler "latest snapshot" is not mixed with a live price (the baselines are measured from it)


def _utcnow() -> datetime:
    return datetime.utcnow()  # snapshot times are naive UTC
_live_cache: dict = {"at": 0.0, "forced_at": 0.0, "prices": {}}
_live_lock = threading.Lock()


def live_prices(db: Session, force: bool = False) -> tuple[dict[int, float], float]:
    """({coin_id: current USD price}, when it was read as a unix time) for every coin of the latest snapshot up to rank
    max(BUCKETS). Shared and cached LIVE_TTL seconds; `force` re-reads the exchanges now (at most once per
    FORCE_MIN_GAP seconds). Never raises: a failing source just leaves the snapshot's own price."""
    import time

    now = time.time()
    with _live_lock:
        age = now - _live_cache["at"]
        if age < LIVE_TTL and not (force and now - _live_cache["forced_at"] >= FORCE_MIN_GAP):
            return _live_cache["prices"], _live_cache["at"]
        if force:
            _live_cache["forced_at"] = now
        latest = _latest_sync_time(db)
        if latest is None or _utcnow() - latest > LIVE_MAX_SNAPSHOT_AGE:
            return {}, now  # no recent history: the boards show the snapshot data alone, as before
        snaps = db.execute(
            select(PriceSnapshot.coin_id, PriceSnapshot.symbol, PriceSnapshot.price_usd).where(
                PriceSnapshot.synced_at == latest, PriceSnapshot.cmc_rank.is_not(None), PriceSnapshot.cmc_rank <= BUCKETS[-1]
            )
        ).all()
        stored = dict(db.execute(select(Coin.cmc_id, Coin.price_usd).where(Coin.cmc_id.in_([s[0] for s in snaps]))).all())
        hub: dict = {}
        try:
            from app.services import price_hub

            if force:
                price_hub.refresh()
            hub = price_hub.get_prices(max_age=LIVE_TTL)
        except Exception:  # noqa: BLE001 - exchanges unreachable: fall back to the stored prices
            hub = {}
        prices: dict[int, float] = {}
        for coin_id, symbol, snap_price in snaps:
            base = float(snap_price or 0)
            if base <= 0:
                continue
            quote = hub.get((symbol or "").upper())
            if quote and 0.5 <= quote["price"] / base <= 2.0:
                prices[coin_id] = float(quote["price"])
                continue
            kept = float(stored.get(coin_id) or 0)
            prices[coin_id] = kept if kept > 0 and 0.2 <= kept / base <= 5.0 else base
        _live_cache.update(at=now, prices=prices)
        return prices, now


def apply_live(changes: list[dict], live: dict[int, float] | None) -> list[dict]:
    """The same rows with price_now replaced by the live price and pct_change recomputed from it (price_then and
    everything else unchanged). Rows without a live price are returned as they are."""
    if not live:
        return changes
    out = []
    for c in changes:
        price = live.get(c["coin_id"])
        if price and price > 0 and price != c["price_now"]:
            pct = pct_change(price, c["price_then"])
            if pct is not None:
                c = {**c, "price_now": price, "pct_change": pct}
        out.append(c)
    return out


def held_coin_ids(changes: list[dict], held: dict[str, float] | None) -> set[int]:
    """Which coins of `changes` are the ones you hold. `held` is {ticker: USD price} (the exchange account). A
    ticker is shared by several coins, so the match is the best-ranked coin with that ticker whose price is within
    0.5x-2x of the account's price (the same guard price_hub.plausible uses); no match = not shown."""
    ids: set[int] = set()
    for asset, price in (held or {}).items():
        best = None
        for c in changes:
            if (c["symbol"] or "").upper() != asset.upper():
                continue
            if price > 0 and c["price_now"] > 0 and not 0.5 <= c["price_now"] / price <= 2.0:
                continue
            if best is None or c["rank"] < best["rank"]:
                best = c
        if best is not None:
            ids.add(best["coin_id"])
    return ids


def board_rows(changes: list[dict], bucket: int, direction: str, limit: int = DEFAULT_LIMIT, held_ids: set[int] | None = None) -> list[dict]:
    """A gainers/losers board with the coins you hold marked: [{"coin", "position", "held", "extra"}].

    The first rows are rank_movers' top `limit` (position 1..N). A held coin of this rank band that is not among
    them is added at the END with its real position among that board's coins, however large that number is. A held
    coin only ever appears on the board of its own direction: up on the 24h = Gainers only, down = Losers only
    (exactly 0% goes with the gainers). A held coin outside the band (or with no change on record) is not shown."""
    sign = 1 if direction == "gainers" else -1
    floor = bucket_floor(bucket)
    band = sorted(
        (c for c in changes if floor < c["rank"] <= bucket and not _stable(c)), key=lambda c: c["pct_change"] * sign, reverse=True
    )
    held_ids = held_ids or set()
    top = rank_movers(changes, bucket, direction, limit)
    top_ids = {c["coin_id"] for c in top}
    position = {c["coin_id"]: i for i, c in enumerate(band, start=1)}
    rows = [{"coin": c, "position": position[c["coin_id"]], "held": c["coin_id"] in held_ids, "extra": False} for c in top]
    def own_side(c: dict) -> bool:
        return c["pct_change"] * sign > 0 or (sign == 1 and c["pct_change"] == 0)

    rows += [
        {"coin": c, "position": position[c["coin_id"]], "held": True, "extra": True}
        for c in band
        if c["coin_id"] in held_ids and c["coin_id"] not in top_ids and own_side(c)
    ]
    return rows


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


def top_movers(db: Session, window: str = "24h", bucket: int = 100, limit: int = 5) -> dict:
    """The few biggest gainers and losers of one window and rank band, from a
    single compute_changes pass (the homepage card). {"status", "hours_remaining",
    "gainers", "losers"}; the lists are empty until the window is ready."""
    status = window_status(db, window)
    if status["status"] != "ready":
        return {"status": status["status"], "hours_remaining": status["hours_remaining"], "gainers": [], "losers": []}
    changes = compute_changes(db, window)
    return {
        "status": "ready",
        "hours_remaining": 0,
        "gainers": rank_movers(changes, bucket, "gainers", limit),
        "losers": rank_movers(changes, bucket, "losers", limit),
    }


# ---- Daily history (the page's calendar) -----------------------------------
def record_daily_movers(db: Session) -> int:
    """Saves the current board of every ready window under the UTC day of
    the latest sync, replacing that day's earlier rows, and commits. Run
    after each scheduled sync: the last save of a day is that day's closing
    board. Skipped (returns 0) when the latest sync is already saved, so
    calling it more often than syncs happen costs one query. Stores every
    qualifying coin up to rank max(BUCKETS); returns the rows written."""
    latest = _latest_sync_time(db)
    if latest is None:
        return 0
    day = latest.date()
    saved_at = db.scalar(select(func.max(MoversDaily.now_at)).where(MoversDaily.day == day))
    if saved_at is not None and saved_at >= latest:
        return 0
    written = 0
    for name in WINDOWS:
        if window_status(db, name)["status"] != "ready":
            continue
        changes = [c for c in compute_changes(db, name) if c["rank"] <= BUCKETS[-1]]
        db.execute(delete(MoversDaily).where(MoversDaily.day == day, MoversDaily.window == name))
        db.add_all(
            MoversDaily(
                day=day,
                window=name,
                coin_id=c["coin_id"],
                symbol=c["symbol"],
                name=(c["name"] or c["symbol"])[:255],
                cmc_rank=c["rank"],
                price_now=c["price_now"],
                price_then=c["price_then"],
                pct_change=c["pct_change"],
                volume_24h=c["volume_24h"],
                then_at=c["then_at"],
                now_at=c["now_at"],
            )
            for c in changes
        )
        written += len(changes)
    db.commit()
    return written


def saved_days(db: Session) -> tuple[date | None, date | None]:
    """First and last UTC day with a saved board, or (None, None)."""
    return tuple(db.execute(select(func.min(MoversDaily.day), func.max(MoversDaily.day))).one())


def load_daily_movers(db: Session, day: date) -> dict[str, list[dict]]:
    """A saved day's boards: {window: changes}, in compute_changes' shape so
    rank_movers cuts them the same way as the live board. A window with
    nothing saved that day is absent."""
    rows = db.scalars(select(MoversDaily).where(MoversDaily.day == day, MoversDaily.window.in_(list(WINDOWS)))).all()
    tagged = stablecoin_ids(db)
    out: dict[str, list[dict]] = {}
    for r in rows:
        row = {
            "coin_id": r.coin_id,
            "rank": r.cmc_rank,
            "name": r.name,
            "symbol": r.symbol,
            "price_now": float(r.price_now),
            "price_then": float(r.price_then),
            "pct_change": r.pct_change,
            "volume_24h": float(r.volume_24h),
            "then_at": r.then_at,
            "now_at": r.now_at,
        }
        row["stable"] = is_stablecoin(row, tagged)  # saved boards from before the filter hold stablecoins too
        out.setdefault(r.window, []).append(row)
    return out
