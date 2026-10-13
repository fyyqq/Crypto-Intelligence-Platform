"""Last-resort TradingView chart-symbol lookup for coins with no real CEX
pair — see frontend/frontend/state/coin_state.py's _resolve_tradingview_symbol,
which only ever calls into this module after its own fast, already-cached
CEX-pairs path (market_pairs_service.py) comes up empty.

Some real coins genuinely have no CEX listing at all, only a DEX pool (e.g.
a Uniswap pair) — confirmed live for zKML (Uniswap v2 on Ethereum) and
several others. TradingView itself tracks a real, chartable symbol for many
of these pools directly (its own symbol-search UI surfaces them when you
search the bare ticker and filter to "Crypto"), just under a pool-specific
symbol format this app has no way to construct on its own (a hash suffix
TradingView derives from the pool's contract address, e.g. "ZKMLWETH_315ED6"
— not something CoinGecko's ticker data exposes in a way we could compute
ourselves). Querying TradingView's own public symbol-search endpoint is the
only reliable way to find that symbol, so this module does exactly what a
person manually browsing tradingview.com's search box would do.

This is a real HTTP call to an undocumented, third-party endpoint (not an
official public API) — it returns 403 without a browser-like User-Agent/
Referer/Origin (confirmed live), and could change shape without notice.
Treated the same defensive way as every other external call in this
codebase: never raises, and gated behind a long Postgres-cached TTL
(settings.tradingview_symbol_ttl_hours, default 24h — far longer than
market_pairs_cache_ttl_hours, since whether a DEX pool has a chartable
TradingView symbol at all almost never changes day to day) so this endpoint
is hit at most once per coin per day, not once per page view.
"""

import logging
import re
from datetime import datetime, timedelta

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.coin import Coin

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/v3/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://www.tradingview.com/",
    "Origin": "https://www.tradingview.com",
}
_EM_TAG_RE = re.compile(r"</?em>")


def needs_refresh(coin: Coin) -> bool:
    """Mirrors market_pairs_service.needs_refresh's shape — checked_at alone
    gates re-checking, regardless of whether a symbol was actually found
    last time (a coin confirmed to have no real chart anywhere shouldn't be
    re-queried every single page view either).
    """
    if coin.tradingview_dex_symbol_checked_at is None:
        return True
    ttl = timedelta(hours=settings.tradingview_symbol_ttl_hours)
    return datetime.utcnow() - coin.tradingview_dex_symbol_checked_at > ttl


def _search_tradingview(ticker: str) -> list[dict] | None:
    try:
        resp = requests.get(
            _SEARCH_URL,
            params={
                "text": ticker,
                "hl": "1",
                "exchange": "",
                "lang": "en",
                "domain": "production",
            },
            headers=_HEADERS,
            timeout=6,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("TradingView symbol search failed for %s: %s", ticker, exc)
        return None
    return data.get("symbols", [])


# Stripped from a CoinContract.platform_name (e.g. "Robinhood Chain" ->
# "robinhood", "BNB Smart Chain (BEP20)" -> "bnb"/"bep20") before using what's
# left as a chain-identity hint — these words appear in enough unrelated
# platform names to carry no real disambiguating signal on their own.
_CHAIN_HINT_STOPWORDS = {"chain", "smart", "network", "mainnet", "the", "v2", "v3", "v4"}


def _chain_hints(platform_names: list[str]) -> set[str]:
    words: set[str] = set()
    for name in platform_names:
        for word in re.findall(r"[a-z0-9]+", name.lower()):
            if len(word) >= 3 and word not in _CHAIN_HINT_STOPWORDS:
                words.add(word)
    return words


# TradingView labels a DEX listing by venue ("Uniswap v4 Base", "Raydium",
# "PumpSwap"...) and puts the pool's contract in its description; a CEX
# listing is just "COIN / USDT". These tell the two apart.
_DEX_EXCHANGE_RE = re.compile(
    r"swap|uniswap|raydium|orca|meteora|pancake|sushi|curve|aerodrome|velodrome|pump|jupiter|\bdex\b|"
    r"camelot|trader ?joe|balancer|quickswap|thruster|ston|dedust|cetus|turbos|lifinity|fluxbeam",
    re.I,
)
_ADDRESS_IN_DESC_RE = re.compile(r"\((0x[0-9a-fA-F]{6,}|[1-9A-HJ-NP-Za-km-z]{30,})\)")
_CEX_QUOTES = ("USDT", "USDC", "USD", "FDUSD")
# Preferred real exchanges, best first; any other CEX comes after these.
_CEX_ORDER = ["BINANCE", "OKX", "BYBIT", "BITGET", "GATEIO", "KUCOIN", "MEXC", "HTX", "COINBASE", "KRAKEN"]


def _is_dex_listing(s: dict) -> bool:
    description = _EM_TAG_RE.sub("", s.get("description", ""))
    return bool(_DEX_EXCHANGE_RE.search(s.get("exchange", "")) or _ADDRESS_IN_DESC_RE.search(description) or " on " in description.lower())


def _pick_best_match(
    symbols: list[dict], ticker: str, coin_name: str, chain_hints: set[str]
) -> str | None:
    """The chart symbol for a coin with no cached CEX pair, from TradingView's
    own search results. Real spot listings only (no perpetuals, no
    synthetic/index/discontinued rows such as "CRYPTO:XUSD").

    1. **CEX first** (rule since 2026-10-13): a centralized-exchange spot
       listing "{TICKER}{USDT|USDC|USD|FDUSD}" whose description names this
       coin, preferred exchanges first (_CEX_ORDER), then any other CEX
       (e.g. KCEX for CyberLeek). A CEX listing is not chain-specific, so no
       chain check: it trades the coin itself.
    2. **DEX only on the coin's own chain**: a DEX pool (Uniswap, Raydium,
       PumpSwap...) is only taken when its venue/description matches one of
       chain_hints (the coin's contract platforms or its "X Ecosystem"
       category). Same-name tokens on other chains are common for memecoins
       (CyberLeek is Solana-only, but TradingView lists two "CyberLeek" pools
       on Base; "MUMU" exists on three chains), so with no chain hint at all a
       DEX pool is only taken when every DEX candidate is on one single
       venue/chain; otherwise nothing ("don't guess" beats charting the wrong
       coin). Among chain-confirmed pools: name match + ".USD" variant
       first (keeps the chart's axis in USD like the page), then name match,
       then USD, then the first.
    """
    ticker_upper = ticker.upper()
    name_lower = re.sub(r"\s*\([^)]*\)\s*$", "", coin_name).strip().lower() if coin_name else ""
    cex: list[tuple[int, int, str]] = []
    dex: list[tuple[bool, bool, bool, str, str]] = []
    for s in symbols:
        if s.get("type") != "spot":
            continue
        typespecs = set(s.get("typespecs") or [])
        if typespecs & {"synthetic", "index"} or "discontinued" in typespecs:
            continue
        symbol = _EM_TAG_RE.sub("", s.get("symbol", "")).upper()
        if not symbol.startswith(ticker_upper):
            continue
        prefix = (s.get("prefix") or s.get("exchange") or "").upper().replace(" ", "")
        if not prefix:
            continue
        description = _EM_TAG_RE.sub("", s.get("description", "")).lower()
        name_matches = bool(name_lower) and name_lower in description
        if not _is_dex_listing(s):
            quote = symbol[len(ticker_upper):]
            if quote in _CEX_QUOTES and (name_matches or description.startswith(ticker.lower())):
                rank = _CEX_ORDER.index(prefix) if prefix in _CEX_ORDER else len(_CEX_ORDER)
                cex.append((rank, _CEX_QUOTES.index(quote), f"{prefix}:{symbol}"))
            continue
        haystack = f"{description} {s.get('exchange', '').lower()}"
        chain_matches = any(hint in haystack for hint in chain_hints)
        is_usd = (s.get("currency_code") or "").upper() == "USD"
        dex.append((chain_matches, name_matches, is_usd, f"{prefix}:{symbol}", s.get("exchange", "")))

    if cex:
        cex.sort()
        return cex[0][2]
    if not dex:
        return None
    if chain_hints:
        dex = [d for d in dex if d[0]]
        if not dex:
            return None
    elif len({d[4] for d in dex}) > 1:
        return None  # pools on several venues/chains and no idea which chain is ours
    for want_name, want_usd in ((True, True), (True, False), (False, True), (False, False)):
        for _, name_matches, is_usd, resolved, _venue in dex:
            if name_matches == want_name and is_usd == want_usd:
                return resolved
    return dex[0][3]


def _ecosystem_hints(category_names: list[str]) -> set[str]:
    """Chain hints from "X Ecosystem" categories ("Solana Ecosystem" ->
    "solana"), used when the coin has no contract rows (the live database
    has none: its contracts sync never ran)."""
    names = [re.sub(r"\s+ecosystem$", "", n.strip(), flags=re.I) for n in category_names if re.search(r"ecosystem$", n.strip(), re.I)]
    return _chain_hints(names)


def resolve_dex_chart_symbol(db: Session, coin: Coin) -> str | None:
    """Returns this coin's cached last-resort TradingView symbol (refreshing
    from TradingView's search API first if the cache is stale — see
    needs_refresh), or None if this coin genuinely has no real chart
    anywhere TradingView tracks. Never raises.

    Skips the external call entirely (no checked_at write either, so a
    coin that later loses its only CEX pair still gets a fresh check next
    visit) whenever this coin already has at least one real CEX market
    pair cached — market_pairs_service.py's own get_market_pairs already
    ran as part of the same page's on_load, so this is just reading its
    already-cached result, never a second network call. This module exists
    specifically for the CEX-empty case (confirmed live for zKML, a
    Uniswap-only listing) — a coin with a real CEX pair already resolves
    through the fast, purely-local _resolve_tradingview_symbol path in
    coin_state.py, and never needs TradingView's own search API at all.
    """
    from app.services.market_pairs_service import get_market_pairs

    pairs = get_market_pairs(db, coin)
    if any(not p.get("is_dex") for p in pairs):
        return None

    if not needs_refresh(coin):
        return coin.tradingview_dex_symbol

    symbols = _search_tradingview(coin.symbol)
    hints = _chain_hints([c.platform_name for c in coin.contracts]) or _ecosystem_hints(
        [c.name for c in coin.categories]
    )
    resolved = (
        _pick_best_match(symbols, coin.symbol, coin.name or "", hints)
        if symbols is not None
        else coin.tradingview_dex_symbol
    )

    coin.tradingview_dex_symbol = resolved
    coin.tradingview_dex_symbol_checked_at = datetime.utcnow()
    db.add(coin)
    db.commit()
    return resolved
