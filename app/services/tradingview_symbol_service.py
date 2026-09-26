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


def _pick_best_match(
    symbols: list[dict], ticker: str, coin_name: str, chain_hints: set[str]
) -> str | None:
    """Real spot listings only (TradingView's search also returns
    "fundamental" on-chain-metric rows and synthetic/index rows that have no
    real chart) whose de-tagged symbol starts with this coin's own ticker —
    "starts with", not "equals", since a DEX pool's symbol is
    "{TICKER}{QUOTE}_{hash}" (e.g. "ZCATWETH_95E308"), not a plain
    "{TICKER}{QUOTE}".

    Ranks candidates by three independent signals rather than just taking
    TradingView's own first result:
    - **chain match**: does the listing's own exchange/description mention
      this coin's actual known platform (CoinContract.platform_name, e.g.
      "Ethereum", "Solana", "Robinhood Chain")? TradingView's own DEX
      exchange labels consistently spell out the chain ("Uniswap v2
      Ethereum", "Raydium Solana", "Uniswap v4 Base"), so this is a
      reliable check when a chain hint exists at all. **The critical guard
      this adds**: confirmed live that the exact ticker+similar-name
      "MUMU"/"Mumu the Bull" is used by at least *three* completely
      unrelated real coins across three different chains (Robinhood Chain,
      Solana, Ethereum) — without this check, a real, well-matched listing
      for a *different* project's identical-looking name/ticker would have
      been charted as if it were this coin (worse than showing nothing).
      When a chain hint exists, a candidate that doesn't match it is
      dropped entirely rather than ranked low — see below.
    - **name match**: does the listing's own description actually mention
      this coin's real name? Guards against a short ticker coincidentally
      prefix-matching a completely unrelated listing — same spirit as
      market_pairs_service's own base/quote validation (confirmed live
      necessary: the Shiba Inu "SHIBA INU" base-field mismatch from the
      previous session's fix).
    - **USD-quoted**: a DEX pool is usually listed twice — once quoted in
      its actual pair currency (e.g. "ZKMLWETH_315ED6", priced in WETH) and
      once as a TradingView-computed ".USD" variant (e.g.
      "ZKMLWETH_315ED6.USD", currency_code "USD") — same underlying pool,
      same chart shape, just a different price axis. Confirmed live this
      was a real bug: picking the plain WETH-quoted variant made the
      chart's current price look completely wrong next to this page's own
      USD-denominated price header, even though the *chart itself* wasn't
      wrong — it was just denominated in a different currency. Preferring
      the ".USD" variant (when one exists) keeps the chart's price axis
      consistent with the rest of the page.

    Excludes "synthetic"/"index"/"discontinued" typespecs (TradingView's own
    aggregated cross-exchange index symbols, e.g. "CRYPTO:MUMUTHUSD") even
    though they're technically type "spot" — confirmed live this was a real
    bug for Mumu The Bull: TradingView's search surfaced that synthetic
    symbol ahead of two genuinely real, per-venue listings, and it was
    **also flagged "discontinued"** by TradingView itself — a dead index,
    not a live chart. A synthetic/aggregated symbol doesn't correspond to
    any single real, tradable venue the way this whole module's "find the
    coin's actual platform" approach requires, so it's excluded outright
    rather than ranked low.

    When chain_hints is non-empty and NO real candidate matches any of
    them, returns None rather than guessing between same-named-but-
    unrelated coins on other chains — "don't guess" beats "chart the wrong
    coin". When chain_hints is empty (native assets with no CoinContract
    row, e.g. BTC/ETH/SOL themselves — though those almost always resolve
    through the CEX path and never reach this function at all) or at least
    one candidate does match, falls through to the name/USD tiers as
    before: name-match + USD-quoted first, then name-match alone, then
    USD-quoted alone, then TradingView's own top relevance result — never
    returns nothing once at least one (chain-confirmed, when applicable)
    real spot match exists.
    """
    ticker_upper = ticker.upper()
    # Strips a trailing " (alias)" parenthetical some CMC coin names carry
    # (e.g. "Mumu The Bull (mumuthatbull)") before the description
    # substring check below — that alias suffix is never part of how any
    # exchange actually describes its own listing, so leaving it in would
    # make an otherwise-good name match fail on a technicality.
    name_lower = re.sub(r"\s*\([^)]*\)\s*$", "", coin_name).strip().lower() if coin_name else ""
    candidates = []
    for s in symbols:
        if s.get("type") != "spot":
            continue
        typespecs = set(s.get("typespecs") or [])
        if typespecs & {"synthetic", "index"} or "discontinued" in typespecs:
            continue
        symbol = _EM_TAG_RE.sub("", s.get("symbol", "")).upper()
        if not symbol.startswith(ticker_upper):
            continue
        prefix = s.get("prefix") or s.get("exchange", "")
        if not prefix:
            continue
        description = _EM_TAG_RE.sub("", s.get("description", "")).lower()
        haystack = f"{description} {s.get('exchange', '').lower()}"
        chain_matches = any(hint in haystack for hint in chain_hints)
        name_matches = bool(name_lower) and name_lower in description
        is_usd = (s.get("currency_code") or "").upper() == "USD"
        candidates.append((chain_matches, name_matches, is_usd, f"{prefix.upper()}:{symbol}"))

    if not candidates:
        return None

    if chain_hints:
        chain_confirmed = [c for c in candidates if c[0]]
        if not chain_confirmed:
            return None
        candidates = chain_confirmed

    for want_name, want_usd in ((True, True), (True, False), (False, True), (False, False)):
        for _, name_matches, is_usd, resolved in candidates:
            if name_matches == want_name and is_usd == want_usd:
                return resolved
    return candidates[0][3]


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
    hints = _chain_hints([c.platform_name for c in coin.contracts])
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
