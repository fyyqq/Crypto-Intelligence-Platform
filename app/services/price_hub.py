"""Shared real-time price list for the whole site (homepage table, watchlist,
coin page header), from free public exchange APIs: no key, no CoinMarketCap
credits.

One bulk "all tickers" call per exchange returns every USDT pair's last price
and 24h change, so the whole site costs about four HTTP calls per refresh, no
matter how many tabs are open. Refreshed on demand: the first caller after
REFRESH_SECONDS triggers a refresh, everyone else reads the cached copy, and
nothing is called while nobody is looking at the site.

Order matters (first exchange to list a symbol wins): Binance, OKX, Bybit,
Gate. Measured 2026-10-13: from the live server (Germany) these cover 94 of
the top 100 coins and 417 of the top 500 (the gaps are mostly stablecoins);
Binance and Bybit are unreachable from Malaysia, so local development gets
OKX + Gate (91 of the top 100). An exchange that fails is skipped for
BACKOFF_SECONDS so a blocked one never slows a refresh down.

Symbols are not unique across coins (several tokens share a ticker), so a
caller must sanity-check a hub price against the coin's own stored price
before using it (see `plausible`).
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

REFRESH_SECONDS = 30
BACKOFF_SECONDS = 300
_TIMEOUT = (3, 8)  # connect, read
_UA = {"User-Agent": "Mozilla/5.0"}


def _f(v) -> float | None:
    try:
        x = float(v)
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def _binance(d) -> dict:
    out = {}
    for x in d:
        s = x.get("symbol", "")
        p = _f(x.get("lastPrice"))
        if s.endswith("USDT") and p:
            out[s[:-4]] = (p, float(x.get("priceChangePercent") or 0))
    return out


def _okx(d) -> dict:
    out = {}
    for x in d.get("data", []):
        inst = x.get("instId", "")
        p, o = _f(x.get("last")), _f(x.get("open24h"))
        if inst.endswith("-USDT") and p:
            out[inst.split("-")[0]] = (p, (p - o) / o * 100 if o else 0.0)
    return out


def _bybit(d) -> dict:
    out = {}
    for x in (d.get("result") or {}).get("list", []):
        s = x.get("symbol", "")
        p = _f(x.get("lastPrice"))
        if s.endswith("USDT") and p:
            out[s[:-4]] = (p, float(x.get("price24hPcnt") or 0) * 100)
    return out


def _gate(d) -> dict:
    out = {}
    for x in d:
        s = x.get("currency_pair", "")
        p = _f(x.get("last"))
        if s.endswith("_USDT") and p:
            out[s[:-5]] = (p, float(x.get("change_percentage") or 0))
    return out


SOURCES = [
    ("Binance", "https://api.binance.com/api/v3/ticker/24hr", _binance),
    ("OKX", "https://www.okx.com/api/v5/market/tickers?instType=SPOT", _okx),
    ("Bybit", "https://api.bybit.com/v5/market/tickers?category=spot", _bybit),
    ("Gate", "https://api.gateio.ws/api/v4/spot/tickers", _gate),
]

_lock = threading.Lock()
_refreshing = threading.Lock()
_prices: dict[str, dict] = {}  # SYMBOL -> {"price", "pct_24h", "source", "at"}
_fetched_at = 0.0
_down_until: dict[str, float] = {}


def _fetch_source(name: str, url: str, parse) -> tuple[str, dict]:
    if _down_until.get(name, 0) > time.monotonic():
        return name, {}
    try:
        r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
        r.raise_for_status()
        return name, parse(r.json())
    except Exception:  # noqa: BLE001 - blocked/slow/bad payload: skip this exchange for a while
        _down_until[name] = time.monotonic() + BACKOFF_SECONDS
        return name, {}


def refresh() -> None:
    """Fetches every source in parallel and swaps in the merged list. Only
    one refresh runs at a time; a concurrent caller just keeps the old copy."""
    global _prices, _fetched_at
    if not _refreshing.acquire(blocking=False):
        return
    try:
        with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
            results = dict(pool.map(lambda s: _fetch_source(*s), SOURCES))
        now = time.time()
        merged: dict[str, dict] = {}
        for name, _, _ in reversed(SOURCES):  # earlier sources overwrite later ones
            for sym, (price, pct) in results.get(name, {}).items():
                merged[sym] = {"price": price, "pct_24h": pct, "source": name, "at": now}
        if merged:
            with _lock:
                _prices, _fetched_at = merged, now
    finally:
        _refreshing.release()


def get_prices(max_age: float = REFRESH_SECONDS) -> dict[str, dict]:
    """The current list, refreshed first if it is older than max_age. Blocking
    (call it from a thread); returns the cached copy if a refresh is already
    running elsewhere."""
    if time.time() - _fetched_at > max_age:
        refresh()
    with _lock:
        return _prices


def plausible(price: float, reference: float) -> bool:
    """A hub price is only trusted for a coin when it is within 0.5x-2x of the
    coin's own stored price (a different coin with the same ticker is almost
    always far off). No stored price: not trusted."""
    return reference > 0 and 0.5 <= price / reference <= 2.0


def status() -> dict:
    with _lock:
        return {
            "symbols": len(_prices),
            "age_seconds": round(time.time() - _fetched_at, 1) if _fetched_at else None,
            "down": sorted(n for n, t in _down_until.items() if t > time.monotonic()),
        }
