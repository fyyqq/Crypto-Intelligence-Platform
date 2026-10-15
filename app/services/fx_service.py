"""Live USD -> local currency rate for display (the MYR button on the /portfolio hero card).

Free forex feeds differ a lot in freshness, so three are combined and the freshest agreeing quote wins:
- Yahoo Finance chart quote (USD<code>=X): intraday, polled every YAHOO_TTL seconds. Its MYR quote is only 2
  decimals and can sit still for a while when the market is quiet.
- open.er-api.com (exchangerate-api open data): one update a day, more precise; polled hourly.
- Frankfurter (European Central Bank reference): one update each working day; polled hourly.
A quote is kept when it is within AGREE_PCT of the median of all fresh quotes (a garbage reading is dropped);
among those the one with the newest timestamp is used, and the page shows which one it was and how old it is.
A source that fails is skipped for DOWN_SECONDS; if every source fails the last rate is kept for up to
MAX_AGE_SECONDS (then there is no rate and the page stays in USD). No key, no cost, no credentials; every call
is a plain HTTPS GET shared by every viewer, so the number of open tabs never changes the number of calls."""

from __future__ import annotations

import logging
import re
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

_log = logging.getLogger(__name__)
_UA = {"User-Agent": "Mozilla/5.0"}
_TIMEOUT = (3, 6)  # connect, read

YAHOO_TTL = 60
DAILY_TTL = 3600
DOWN_SECONDS = 300
MAX_AGE_SECONDS = 72 * 3600  # a weekend + a day: older than this is not shown
LIVE_SECONDS = 15 * 60  # a quote younger than this is called "live"
AGREE_PCT = 2.0
SYMBOLS = {"USD": "$", "MYR": "RM"}
_TZ = ZoneInfo("Asia/Kuala_Lumpur")


# ---------------------------------------------------------------------------------------------- sources


def _yahoo(quote: str) -> tuple[float, float]:
    r = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/USD{quote}=X",
        params={"interval": "1m", "range": "1d"},
        headers=_UA,
        timeout=_TIMEOUT,
        allow_redirects=False,
    )
    meta = r.json()["chart"]["result"][0]["meta"]
    return float(meta["regularMarketPrice"]), float(meta["regularMarketTime"])


def _er_api(quote: str) -> tuple[float, float]:
    r = requests.get("https://open.er-api.com/v6/latest/USD", headers=_UA, timeout=_TIMEOUT, allow_redirects=False)
    j = r.json()
    if j.get("result") != "success":
        raise ValueError("er-api: not a success reply")
    return float(j["rates"][quote]), float(j["time_last_update_unix"])


def _frankfurter(quote: str) -> tuple[float, float]:
    r = requests.get(
        "https://api.frankfurter.dev/v1/latest",
        params={"base": "USD", "symbols": quote},
        headers=_UA,
        timeout=_TIMEOUT,
        allow_redirects=False,
    )
    j = r.json()
    day = datetime.strptime(j["date"], "%Y-%m-%d").replace(hour=15, tzinfo=timezone.utc)  # ECB publishes ~16:00 CET
    return float(j["rates"][quote]), day.timestamp()


# (name, label, ttl seconds, fetch)
SOURCES = [
    ("yahoo", "Yahoo Finance", YAHOO_TTL, _yahoo),
    ("er-api", "ExchangeRate-API (daily)", DAILY_TTL, _er_api),
    ("ecb", "European Central Bank (daily)", DAILY_TTL, _frankfurter),
]

_lock = threading.Lock()
_refreshing = threading.Lock()
_quotes: dict[tuple[str, str], dict] = {}  # (source, quote currency) -> {"rate", "as_of", "fetched_at"}
_down_until: dict[str, float] = {}


# ---------------------------------------------------------------------------------------------- choosing


def _valid(rate: float) -> bool:
    return 0 < rate < 1e7


def cached(quote: str) -> dict | None:
    """The best rate known right now, from what was already fetched (no network). None = no usable rate."""
    now = time.time()
    with _lock:
        fresh = [
            (name, label, q)
            for name, label, _, _ in SOURCES
            if (q := _quotes.get((name, quote))) and _valid(q["rate"]) and now - q["as_of"] <= MAX_AGE_SECONDS
        ]
    if not fresh:
        return None
    middle = statistics.median(q["rate"] for _, _, q in fresh)
    agreeing = [t for t in fresh if abs(t[2]["rate"] / middle - 1) * 100 <= AGREE_PCT] or fresh
    name, label, q = max(agreeing, key=lambda t: t[2]["as_of"])
    age = max(now - q["as_of"], 0.0)
    live = age <= LIVE_SECONDS
    when = datetime.fromtimestamp(q["as_of"], _TZ).strftime("%d %b %H:%M")
    return {
        "rate": q["rate"],
        "source": label,
        "as_of": q["as_of"],
        "age": age,
        "live": live,
        "note": f"{label} · live" if live else f"{label} · quote of {when} (KL)",
    }


def get_rate(quote: str = "MYR") -> dict | None:
    """The best rate, refreshing any source whose cache is older than its TTL first. Blocking (call from a
    thread); never raises. While another caller is refreshing, the cached rate is returned straight away."""
    quote = (quote or "").upper()
    if not re.fullmatch(r"[A-Z]{3}", quote):
        return None
    if quote == "USD":
        return {"rate": 1.0, "source": "USD", "as_of": time.time(), "age": 0.0, "live": True, "note": ""}
    if _refreshing.acquire(blocking=False):
        try:
            _refresh(quote)
        finally:
            _refreshing.release()
    return cached(quote)


def _refresh(quote: str) -> None:
    now = time.time()
    due = [
        (name, ttl, fetch)
        for name, _, ttl, fetch in SOURCES
        if _down_until.get(name, 0) <= now and now - _quotes.get((name, quote), {}).get("fetched_at", 0) >= ttl
    ]
    if not due:
        return

    def run(item):
        name, _, fetch = item
        try:
            rate, as_of = fetch(quote)
            if not _valid(rate):
                raise ValueError("implausible rate")
            now = time.time()
            return name, {"rate": rate, "as_of": min(as_of, now), "fetched_at": now}  # a future stamp never wins
        except Exception as exc:  # noqa: BLE001 - blocked/slow/bad payload: skip this source for a while
            _log.warning("FX source %s failed (%s); skipping it for %ds", name, type(exc).__name__, DOWN_SECONDS)
            return name, None

    with ThreadPoolExecutor(max_workers=len(due)) as pool:
        results = list(pool.map(run, due))
    with _lock:
        for name, q in results:
            if q is None:
                _down_until[name] = time.time() + DOWN_SECONDS
            else:
                _quotes[(name, quote)] = q


# ---------------------------------------------------------------------------------------------- display


def format_amount(value: float, currency: str = "USD", signed: bool = False) -> str:
    """"$1,234.56" / "RM1,234.56" (with a leading + or - when signed; negatives always get the -)."""
    symbol = SYMBOLS.get(currency, currency + " ")
    sign = "-" if value < 0 else ("+" if signed and value > 0 else "")
    return f"{sign}{symbol}{abs(value):,.2f}"
