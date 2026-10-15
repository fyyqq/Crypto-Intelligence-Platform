"""Keeps every coin's STORED price fresh every few minutes from free sources.

The stored price (coins.price_usd, mirrored into frontend/reflex.db) normally comes from the hourly
CoinMarketCap sync. When CMC credits run out (2026-10-12 .. 1 Nov 2026) that price just stops (ETC showed $8.37
while the market was $8.05) and every list view, the first paint of a coin page, the alert reference price and
the Gainers & Losers base all go stale. This job refreshes the stored price (and its 24h change and market cap,
scaled by the price move) from:

1. the shared exchange ticker list (app/services/price_hub.py: Binance/OKX/Bybit/Gate), trusted only when it is
   within 0.5x-2x of the coin's own stored price (other tokens share tickers), and
2. DexScreener by contract address for the coins no exchange list covers (30 addresses per request; the deepest
   pool of the token wins), best-ranked coins first, MAX_DEX_COINS per run.

Runs every INTERVAL_SECONDS from the Reflex process (frontend/news_catchup.py). It writes Postgres and the Reflex
SQLite mirror; the in-memory coin universe rebuilds from the mirror when a visitor loads a page (<= 5 min old).
The live views on top (homepage/watchlist every 30 s, coin page header every second) are unchanged.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

from app.core.database import SessionLocal
from app.services import price_hub

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 300
DEX_TOP_COINS = 600  # the best-ranked uncovered coins are refreshed on every run ...
DEX_ROTATING_COINS = 900  # ... plus this many of the rest, a different slice each run (DexScreener rate limits)
DEX_BATCH = 30
DEX_PAUSE_SECONDS = 0.5
DEX_MAX_FAILURES = 3  # failed batches (in a row, per worker) before a run stops asking DexScreener
DEX_WORKERS = 4  # requests in flight at once (DexScreener allows 300/min)
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}|[1-9A-HJ-NP-Za-km-z]{32,44}")  # EVM or Solana; anything else makes a batch 404
MIN_LIQUIDITY_USD = 1000.0
_MIRROR = Path(__file__).resolve().parent.parent.parent / "frontend" / "reflex.db"


def _is_real_contract(address: str | None) -> bool:
    a = (address or "").strip()
    # 0xeeee... = the chain's native coin placeholder
    return bool(_ADDRESS.fullmatch(a)) and not a.lower().startswith("0xeeeeeeee")


def fetch_dex_prices(addresses: list[str], client: httpx.Client | None = None) -> dict[str, tuple[float, float | None]]:
    """{lower-case address: (USD price, 24h change %)} from DexScreener for up to DEX_BATCH addresses: the pool with
    the most liquidity whose BASE token is that address (and at least MIN_LIQUIDITY_USD deep)."""
    if not addresses:
        return {}
    own = client or httpx.Client(timeout=12, headers={"User-Agent": "Mozilla/5.0"})
    try:
        r = own.get("https://api.dexscreener.com/latest/dex/tokens/" + ",".join(addresses))
        r.raise_for_status()
        pairs = r.json().get("pairs") or []
    finally:
        if client is None:
            own.close()
    best: dict[str, tuple[float, float, float | None]] = {}
    for p in pairs:
        addr = str((p.get("baseToken") or {}).get("address") or "").lower()
        try:
            price = float(p.get("priceUsd") or 0)
            liq = float((p.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            continue
        if not addr or price <= 0 or liq < MIN_LIQUIDITY_USD:
            continue
        if addr not in best or liq > best[addr][1]:
            h24 = (p.get("priceChange") or {}).get("h24")
            best[addr] = (price, liq, float(h24) if h24 is not None else None)
    return {a: (v[0], v[2]) for a, v in best.items()}


_rotation = 0  # where this run's rotating DexScreener slice starts


def _dex_selection(uncovered: list[dict], top: int, rotating: int) -> list[dict]:
    """The best-ranked `top` coins always, then `rotating` more from the rest, advancing every run."""
    global _rotation
    head, rest = uncovered[:top], uncovered[top:]
    if not rest or rotating <= 0:
        return head
    start = _rotation % len(rest)
    pick = (rest + rest)[start : start + min(rotating, len(rest))]
    _rotation = start + rotating
    return head + pick


def compute_updates(
    coins: list[dict], hub: dict[str, dict], dex_fetch=fetch_dex_prices, top: int = DEX_TOP_COINS, rotating: int = DEX_ROTATING_COINS
) -> dict[int, dict]:
    """coins: [{cmc_id, symbol, price, market_cap, contract}] best-ranked first -> {cmc_id: {price, pct_24h, market_cap}}
    for the coins whose price moved. Pure apart from `dex_fetch` (injectable for tests)."""
    updates: dict[int, dict] = {}

    def add(c: dict, price: float, pct: float | None) -> None:
        old = float(c["price"] or 0)
        if price <= 0 or price == old:
            return
        cap = float(c["market_cap"] or 0)
        updates[c["cmc_id"]] = {
            "price": price,
            "pct_24h": pct,
            "market_cap": cap * price / old if old > 0 and cap > 0 else cap,
        }

    uncovered: list[dict] = []
    for c in coins:
        quote = hub.get((c["symbol"] or "").upper())
        if quote and price_hub.plausible(quote["price"], float(c["price"] or 0)):
            add(c, quote["price"], quote["pct_24h"])
        elif _is_real_contract(c.get("contract")):
            uncovered.append(c)
    uncovered = _dex_selection(uncovered, top, rotating)
    batches = [uncovered[i : i + DEX_BATCH] for i in range(0, len(uncovered), DEX_BATCH)]
    lock = threading.Lock()
    failed = [0]

    def work(batch: list[dict]) -> dict:
        with lock:
            if failed[0] >= DEX_MAX_FAILURES:
                return {}  # DexScreener keeps failing: skip the rest of this run
        try:
            found = dex_fetch([c["contract"] for c in batch])
        except Exception as exc:  # noqa: BLE001 - a rate limit / network blip: skip this batch, keep the rest
            with lock:
                failed[0] += 1
            log.warning("free price sync: DexScreener batch failed (%s)", exc)
            return {}
        time.sleep(DEX_PAUSE_SECONDS)
        return found

    with ThreadPoolExecutor(max_workers=DEX_WORKERS) as pool:
        results = list(pool.map(work, batches))
    for batch, found in zip(batches, results):
        for c in batch:
            hit = found.get(c["contract"].strip().lower())
            if hit:
                add(c, hit[0], hit[1])
    return updates


_UPDATE_SQL = text(
    "UPDATE coins SET price_usd = :price, market_cap_usd = :market_cap, "
    "percent_change_24h = COALESCE(:pct_24h, percent_change_24h) WHERE cmc_id = :cmc_id"
)
_MIRROR_SQL = text(
    "UPDATE coin SET price_usd = :price, market_cap_usd = :market_cap, "
    "percent_change_24h = COALESCE(:pct_24h, percent_change_24h) WHERE cmc_id = :cmc_id"
)


def _rows(updates: dict[int, dict]) -> list[dict]:
    return [{"cmc_id": k, **v} for k, v in updates.items()]


def load_coins(db) -> list[dict]:
    """Every coin with a stored price, best-ranked first, with its main contract."""
    contracts: dict[int, str] = {}
    for cmc_id, address in db.execute(text(
        "SELECT c.cmc_id, cc.contract_address FROM coins c JOIN coin_contracts cc ON cc.coin_id = c.id "
        "WHERE cc.contract_address IS NOT NULL ORDER BY cc.is_primary DESC, cc.sort_order"
    )):
        if _is_real_contract(address):
            contracts.setdefault(cmc_id, address.strip())
    rows = db.execute(text(
        "SELECT cmc_id, symbol, price_usd, market_cap_usd FROM coins WHERE price_usd IS NOT NULL "
        "ORDER BY cmc_rank ASC NULLS LAST, market_cap_usd DESC NULLS LAST"
    ))
    return [
        {"cmc_id": r[0], "symbol": r[1], "price": float(r[2] or 0), "market_cap": float(r[3] or 0), "contract": contracts.get(r[0], "")}
        for r in rows
    ]


def run() -> int:
    """One refresh. Returns how many coins got a new price."""
    hub = price_hub.get_prices(max_age=0)
    db = SessionLocal()
    try:
        coins = load_coins(db)
        updates = compute_updates(coins, hub)
        if updates:
            db.execute(_UPDATE_SQL, _rows(updates))
            db.commit()
    finally:
        db.close()
    if updates and _MIRROR.exists():
        engine = create_engine(f"sqlite:///{_MIRROR}", connect_args={"timeout": 15})
        try:
            with engine.begin() as conn:
                conn.execute(_MIRROR_SQL, _rows(updates))
        finally:
            engine.dispose()
    try:
        from app.services import heartbeat

        heartbeat.beat("free_price_sync")
    except Exception:  # noqa: BLE001
        pass
    log.info("free price sync: %d coin prices refreshed", len(updates))
    return len(updates)
