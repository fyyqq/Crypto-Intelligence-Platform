"""Fetches 7-day price sparklines from CoinGecko's free public API and
attaches them to matching coins in the Reflex SQLite cache (frontend/reflex.db).

CoinMarketCap's Basic (free) tier has no historical-price endpoint, so this
uses a separate free source for the sparkline series only. Matching is
two-tier: prefer (symbol, name) exact match; if that misses (CMC and
CoinGecko sometimes spell the same coin's name slightly differently, e.g.
"Tether USDt" vs "Tether"), fall back to symbol alone only when that symbol
is unique across the fetched CoinGecko set — safe for well-known top coins,
where ticker collisions among market-cap leaders are rare. Coins with no
confident match simply get no sparkline (not a wrong one).

Safe to re-run: it always overwrites with the latest fetch. Not part of the
main 24h CMC sync — run manually or on its own schedule.
"""

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "frontend"))

from sqlmodel import Session, create_engine, select  # noqa: E402

from frontend.models.coin import Coin  # noqa: E402

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
PAGES = 12  # 12 * 250 = up to top 3,000 coins by market cap on CoinGecko
PER_PAGE = 250
REQUEST_DELAY_SECONDS = 3
MAX_RETRIES = 5


def _get_with_retry(page: int) -> list[dict]:
    delay = 15
    for attempt in range(MAX_RETRIES):
        response = requests.get(
            COINGECKO_URL,
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": PER_PAGE,
                "page": page,
                "sparkline": "true",
            },
            timeout=20,
        )
        if response.status_code == 429:
            print(f"  page {page}: rate-limited, waiting {delay}s (attempt {attempt + 1}/{MAX_RETRIES})...")
            time.sleep(delay)
            delay = min(delay * 2, 120)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Gave up on page {page} after {MAX_RETRIES} rate-limit retries")


def fetch_coingecko_markets() -> list[dict]:
    all_rows: list[dict] = []
    for page in range(1, PAGES + 1):
        rows = _get_with_retry(page)
        if not rows:
            break
        all_rows.extend(rows)
        print(f"  page {page}: {len(rows)} coins (total {len(all_rows)})")
        time.sleep(REQUEST_DELAY_SECONDS)
    return all_rows


def main() -> None:
    print(f"Fetching up to {PAGES * PER_PAGE} coins from CoinGecko...")
    markets = fetch_coingecko_markets()
    print(f"Fetched {len(markets)} coins from CoinGecko.")

    exact_map: dict[tuple[str, str], list[float]] = {}
    symbol_map: dict[str, list[float]] = {}
    symbol_counts: dict[str, int] = {}
    for entry in markets:
        prices = entry.get("sparkline_in_7d", {}).get("price") or []
        if not prices:
            continue
        symbol = entry["symbol"].strip().lower()
        name = entry["name"].strip().lower()
        exact_map[(symbol, name)] = prices
        symbol_map[symbol] = prices
        symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1

    engine = create_engine(f"sqlite:///{ROOT / 'frontend' / 'reflex.db'}")
    matched_exact = 0
    matched_symbol = 0
    with Session(engine) as db:
        coins = db.exec(select(Coin)).all()

        # The unique-symbol fallback is only safe if the symbol is unique on
        # BOTH sides — unique among CoinGecko's fetched set (checked above via
        # symbol_counts) AND unique among our own cached coins. Otherwise two
        # different coins we track under the same ticker (e.g. "Tether USDt"
        # and a separately-listed "Bridged USDT") would both get stamped with
        # the one CoinGecko entry's chart, which is a wrong chart for one of them.
        our_symbol_counts: dict[str, int] = {}
        for coin in coins:
            key = coin.symbol.strip().lower()
            our_symbol_counts[key] = our_symbol_counts.get(key, 0) + 1

        for coin in coins:
            symbol = coin.symbol.strip().lower()
            name = coin.name.strip().lower()
            prices = exact_map.get((symbol, name))
            if prices:
                matched_exact += 1
            elif symbol_counts.get(symbol) == 1 and our_symbol_counts.get(symbol) == 1:
                prices = symbol_map.get(symbol)
                if prices:
                    matched_symbol += 1
            coin.sparkline_7d = json.dumps(prices) if prices else None
        db.commit()

    total_matched = matched_exact + matched_symbol
    print(
        f"Matched sparklines for {total_matched} / {len(coins)} cached coins "
        f"({matched_exact} exact name+symbol, {matched_symbol} unique-symbol fallback)."
    )


if __name__ == "__main__":
    main()
