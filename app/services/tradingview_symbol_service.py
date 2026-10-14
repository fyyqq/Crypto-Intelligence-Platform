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
    """TradingView's own symbol search with the "Crypto" tab selected
    (search_type=crypto): only crypto listings, in TradingView's order. Much
    faster and cleaner than an unfiltered search: "SI" alone returned silver
    futures and stocks in 6.5s, the Crypto tab returns Super Inu in 0.8s."""
    try:
        resp = requests.get(
            _SEARCH_URL,
            params={
                "text": ticker,
                "hl": "1",
                "exchange": "",
                "lang": "en",
                "search_type": "crypto",
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
# Preferred real exchanges, best first; any other CEX comes after these, in
# TradingView's own order. Same chart priority as the coin page's CEX-pairs path
# (coin_state._EXCHANGE_PRIORITY: MEXC > KuCoin > HTX > Bybit), then the big ones.
_CEX_ORDER = ["MEXC", "KUCOIN", "HTX", "BYBIT", "BINANCE", "OKX", "BITGET", "GATE", "GATEIO", "COINBASE", "KRAKEN"]


def _is_perpetual(s: dict) -> bool:
    return s.get("type") == "swap" or "perpetual" in (s.get("typespecs") or []) or _EM_TAG_RE.sub("", s.get("symbol", "")).upper().endswith(".P")


def _is_index(s: dict) -> bool:
    """TradingView's own aggregates: CRYPTO:<coin>USD price index, CRYPTOCAP market cap/dominance."""
    typespecs = set(s.get("typespecs") or [])
    return s.get("type") == "index" or bool(typespecs & {"synthetic", "cryptoasset"})


def _is_dex_listing(s: dict) -> bool:
    description = _EM_TAG_RE.sub("", s.get("description", ""))
    return bool(_DEX_EXCHANGE_RE.search(s.get("exchange", "")) or _ADDRESS_IN_DESC_RE.search(description) or " on " in description.lower())


def _pick_best_match(
    symbols: list[dict], ticker: str, coin_name: str, chain_hints: set[str]
) -> str | None:
    """The chart symbol for a coin from TradingView's Crypto-tab search results
    (rows in TradingView's own order), CEX first:

    1. **CEX spot**: "{TICKER}{USDT|USDC|USD|FDUSD}" on a centralized exchange
       whose description names this coin, _CEX_ORDER first (MEXC, KuCoin,
       HTX, Bybit, Binance...), then TradingView's order. Not chain-specific:
       it trades the coin itself.
    2. **CEX perpetual** ("{TICKER}USDT.P"), same checks and order.
    3. **DEX only on the coin's own chain** (chain_hints = its contract
       platforms or "X Ecosystem" category). Same-name tokens on other chains
       are common for memecoins (CyberLeek is Solana-only, but TradingView
       lists two "CyberLeek" pools on Base), so with no chain hint a pool is
       only taken when every DEX candidate is on one single venue. Name match
       + ".USD" variant first (keeps the axis in USD), then name match, then
       USD, then the first.
    4. **The first listing that names this coin**, whatever its kind (spot,
       perpetual, or a pool when the coin's chain is unknown), in TradingView's
       order: what a person would pick from the top of the Crypto tab. Only when
       its description contains the coin's name, so a same-ticker different coin
       ("SI" is also SpaceX Inu and Super Intelligence) is never charted, and
       never a pool on a chain the coin is known not to be on.
    5. **TradingView's CRYPTO:<coin> price index** with the coin's exact name.
    Otherwise None (the page shows "No live chart"; the report icon picks one).
    """
    ticker_upper = ticker.upper()
    name_lower = re.sub(r"\s*\([^)]*\)\s*$", "", coin_name).strip().lower() if coin_name else ""
    cex_spot: list[tuple[int, int, int, str]] = []
    cex_perp: list[tuple[int, int, str]] = []
    dex: list[tuple[bool, bool, bool, str, str]] = []
    named_any: list[str] = []
    index_rows: list[str] = []
    for pos, s in enumerate(symbols):
        typespecs = set(s.get("typespecs") or [])
        if "discontinued" in typespecs:
            continue
        symbol = _EM_TAG_RE.sub("", s.get("symbol", "")).upper()
        prefix = (s.get("prefix") or s.get("exchange") or "").upper().replace(" ", "")
        if not prefix or not symbol:
            continue
        description = _EM_TAG_RE.sub("", s.get("description", "")).lower()
        name_matches = bool(name_lower) and name_lower in description
        full = f"{prefix}:{symbol}"
        if _is_index(s):
            if s.get("type") != "index" and name_lower and description.strip() == name_lower and symbol.startswith(ticker_upper):
                index_rows.append(full)
            continue
        is_dex = _is_dex_listing(s)
        haystack = f"{description} {s.get('exchange', '').lower()}"
        chain_matches = any(hint in haystack for hint in chain_hints)
        # A pool on a chain the coin is known NOT to be on is a different token with the same
        # name (CyberLeek is Solana-only; TradingView's "CyberLeek" pools are on Base): never charted.
        if name_matches and (not is_dex or not chain_hints or chain_matches):
            named_any.append(full)
        if not symbol.startswith(ticker_upper):
            continue
        rank = _CEX_ORDER.index(prefix) if prefix in _CEX_ORDER else len(_CEX_ORDER)
        if is_dex:
            if s.get("type") != "spot":
                continue
            is_usd = (s.get("currency_code") or "").upper() == "USD"
            dex.append((chain_matches, name_matches, is_usd, full, s.get("exchange", "")))
            continue
        if not (name_matches or description.startswith(ticker.lower())):
            continue
        if _is_perpetual(s):
            quote = symbol[len(ticker_upper):].removesuffix(".P")
            if quote in _CEX_QUOTES:
                cex_perp.append((rank, pos, full))
        elif s.get("type") == "spot":
            quote = symbol[len(ticker_upper):]
            if quote in _CEX_QUOTES:
                cex_spot.append((rank, _CEX_QUOTES.index(quote), pos, full))

    if cex_spot:
        return sorted(cex_spot)[0][3]
    if cex_perp:
        return sorted(cex_perp)[0][2]
    if dex:
        candidates = [d for d in dex if d[0]] if chain_hints else (dex if len({d[4] for d in dex}) == 1 else [])
        for want_name, want_usd in ((True, True), (True, False), (False, True), (False, False)):
            for _, name_matches, is_usd, resolved, _venue in candidates:
                if name_matches == want_name and is_usd == want_usd:
                    return resolved
    if named_any:
        return named_any[0]
    return index_rows[0] if index_rows else None


def _ecosystem_hints(category_names: list[str]) -> set[str]:
    """Chain hints from "X Ecosystem" categories ("Solana Ecosystem" ->
    "solana"), used when the coin has no contract rows (the live database
    has none: its contracts sync never ran)."""
    names = [re.sub(r"\s+ecosystem$", "", n.strip(), flags=re.I) for n in category_names if re.search(r"ecosystem$", n.strip(), re.I)]
    return _chain_hints(names)


def resolve_dex_chart_symbol(db: Session, coin: Coin) -> str | None:
    """This coin's TradingView chart symbol from TradingView's own Crypto-tab
    search (see _pick_best_match), cached in Postgres for
    settings.tradingview_symbol_ttl_hours (24h). coin_state._resolve_chart_symbol
    still prefers a symbol built from the coin's own CEX market pairs and only
    falls back to this one, but this no longer waits for those pairs (it used
    to call get_market_pairs first, a CoinGecko round trip, and only then
    search), so a coin with no usable CEX pair gets its chart in about a
    second. Searches the coin's name first (much more specific than a short
    ticker: "Super Inu" vs "SI"), then its ticker. Never raises.
    """
    if not needs_refresh(coin):
        return coin.tradingview_dex_symbol

    hints = _chain_hints([c.platform_name for c in coin.contracts]) or _ecosystem_hints(
        [c.name for c in coin.categories]
    )
    name = re.sub(r"\s*\([^)]*\)\s*$", "", coin.name or "").strip()
    resolved = None
    searched = False
    for query in dict.fromkeys(q for q in (name, coin.symbol) if q):
        symbols = _search_tradingview(query)
        if symbols is None:
            continue
        searched = True
        resolved = _pick_best_match(symbols, coin.symbol, coin.name or "", hints)
        if resolved:
            break
    if not searched:  # TradingView unreachable: keep what we had, try again next view
        return coin.tradingview_dex_symbol

    coin.tradingview_dex_symbol = resolved
    coin.tradingview_dex_symbol_checked_at = datetime.utcnow()
    db.add(coin)
    db.commit()
    return resolved
