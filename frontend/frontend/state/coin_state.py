"""State for the coin list page: loads the cached CoinMarketCap data and
exposes a narrative filter, backed by the SQLModel tables in frontend/models.
"""

import asyncio
import functools
import json
import math
import time
import re
import sys
from pathlib import Path
from collections import Counter
from urllib.parse import urlencode

import reflex as rx
from sqlalchemy.orm import selectinload
from sqlmodel import select

from frontend.models.coin import Coin

# Repo root, so handlers can import the Postgres-side `app` package (Reflex only has frontend/ on sys.path).
_ROOT_FOR_APP = str(Path(__file__).resolve().parent.parent.parent.parent)

# Eye-catching, mutually distinct colors for the About/AI-summary keyword
# underline highlight — picked for contrast against both light and dark
# mode's gray-a2 card background (see coin_detail.py's _render_highlight_
# token), not tied to any single brand color the way indigo/green links
# elsewhere on this page are.
_HIGHLIGHT_COLORS = [
    "#22d3ee", "#fb923c", "#f472b6", "#a78bfa", "#a3e635", "#fbbf24", "#38bdf8", "#fb7185",
]

# Generic crypto/investor-relevant terms and value patterns worth calling
# out in free-text project descriptions/summaries — deliberately broad
# (not tied to any one coin's vocabulary, e.g. Ethereum's) since this same
# list highlights across every coin's page. Numeric patterns (dollar
# amounts, percentages, "N per second"/"N annually") catch concrete
# figures an investor would actually stop and read, alongside the named
# concepts.
_HIGHLIGHT_KEYWORDS = (
    r"layer\s*[123]\b", r"layer\s*one\b", r"layer\s*two\b", r"business model",
    r"market cap(?:italization)?", r"total supply", r"circulating supply",
    r"max(?:imum)? supply", r"staking", r"validators?", r"smart contracts?",
    r"proof of stake", r"proof of work", r"defi", r"decentrali[sz]ed",
    r"tokenomics", r"roadmap", r"institutional", r"liquidity", r"airdrops?",
    r"governance", r"gas fees?", r"transaction fees?", r"annual yields?",
    r"apy", r"tps\b", r"transactions per second", r"burn(?:ing|ed)?",
    r"deflationary", r"\betf\b", r"mining",
)
_HIGHLIGHT_PATTERN = re.compile(
    "(" + "|".join(_HIGHLIGHT_KEYWORDS) + ")"
    r"|(\$[\d,]+(?:\.\d+)?\s?(?:billion|million|trillion|B|M|T)?)"
    r"|(\d[\d,]*(?:\.\d+)?\+?\s?%)"
    r"|(\d[\d,]*(?:\.\d+)?\+?\s?(?:per second|transactions per second|annually|per year))",
    re.IGNORECASE,
)


def _highlight_color(keyword: str) -> str:
    # Deterministic (not Python's salted str hash, which changes every
    # process restart) so the same term always gets the same color within
    # a session and across reloads, rather than visibly reshuffling.
    return _HIGHLIGHT_COLORS[sum(ord(c) for c in keyword.lower()) % len(_HIGHLIGHT_COLORS)]


def _tokenize_highlights(text: str) -> list[dict]:
    """Splits free text into an ordered list of {text, highlight, color}
    runs — plain runs render as-is, highlighted runs (see _HIGHLIGHT_
    PATTERN) get a colored underline (see coin_detail.py's _render_
    highlight_token). Done here in Python rather than as a live Reflex Var
    transform since this is arbitrary string tokenization, not something
    Reflex's Var operations express — computed once per row build/refresh
    instead, same as every other derived field in _build_row.
    """
    if not text:
        return []
    tokens: list[dict] = []
    last_end = 0
    for match in _HIGHLIGHT_PATTERN.finditer(text):
        start, end = match.span()
        if start > last_end:
            tokens.append({"text": text[last_end:start], "highlight": False, "color": ""})
        matched = match.group(0)
        tokens.append({"text": matched, "highlight": True, "color": _highlight_color(matched)})
        last_end = end
    if last_end < len(text):
        tokens.append({"text": text[last_end:], "highlight": False, "color": ""})
    return tokens


def _parse_business_summary_sections(raw: str) -> list[dict]:
    """Splits the AI business summary into {title, tokens} sections when the
    model followed the "TITLE: <heading>" convention (see business_summary_
    service.py's system prompt) — falls back to one untitled section for
    older cached summaries generated before that convention existed, so an
    already-cached coin doesn't break until its next TTL-driven regeneration.
    """
    if not raw:
        return []
    parts = re.split(r"(?m)^TITLE:\s*(.+)$", raw.strip())
    if len(parts) == 1:
        return [{"title": "", "tokens": _tokenize_highlights(raw.strip())}]
    sections: list[dict] = []
    leading = parts[0].strip()
    if leading:
        sections.append({"title": "", "tokens": _tokenize_highlights(leading)})
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections.append({"title": title, "tokens": _tokenize_highlights(body)})
    return sections


# OpenRouter model slugs are "<provider>/<model-name>[:variant]" — only the
# providers actually reachable through this project's free-tier account are
# named here (see settings.openrouter_model); any other provider still gets
# a sensible title-cased fallback rather than breaking the badge.
_PROVIDER_DISPLAY_NAMES = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "meta": "Meta",
    "meta-llama": "Meta",
    "mistralai": "Mistral AI",
    "nvidia": "NVIDIA",
    "deepseek": "DeepSeek",
    "qwen": "Qwen",
    "x-ai": "xAI",
    "z-ai": "Z.ai",
    "cohere": "Cohere",
}

_MODEL_UNIT_SUFFIX = re.compile(r"^\d+(\.\d+)?[bmkt]$", re.IGNORECASE)


def _format_model_badge(raw_model: str) -> dict:
    """Turns an OpenRouter model slug (e.g. "nvidia/nemotron-3-ultra-550b-
    a55b:free") into {provider, provider_display, model_display} for
    coin_detail.py's attribution badge — provider drives which brand icon
    renders, provider_display/model_display are the shown text. Capped to
    the model name's first 3 words for a short badge (e.g. "Nemotron 3
    Ultra") rather than the full, much longer raw slug.
    """
    if not raw_model:
        return {"provider": "", "provider_display": "", "model_display": ""}
    slug = raw_model.split(":")[0]
    provider, _, model_part = slug.partition("/")
    provider_display = _PROVIDER_DISPLAY_NAMES.get(provider, provider.replace("-", " ").title())
    words = [w for w in model_part.split("-") if w][:3]
    pretty_words = [w.upper() if _MODEL_UNIT_SUFFIX.match(w) else w.capitalize() for w in words]
    return {
        "provider": provider,
        "provider_display": provider_display,
        "model_display": " ".join(pretty_words) or provider_display,
    }


# CMC's Basic tier has no historical-price endpoint, and an earlier attempt to
# source a real 7d line from CoinGecko only matched ~26% of coins (and risked
# mismatches). Rather than show a real chart for some coins and nothing for
# most, every coin gets a simple directional trend line instead (one for 24h,
# one for 7d): it only encodes the sign of the % change we already have, not
# a fabricated price path.
_TREND_UP = [{"v": 0}, {"v": 1}]
_TREND_DOWN = [{"v": 1}, {"v": 0}]


def _fmt_usd(value: float) -> str:
    """The one place a coin's USD price gets turned into a display string —
    every "price_display" field in this file (homepage table, coin detail's
    big price header, Markets section pair rows, the header search
    dropdown) is built from this function or from
    _price_display_with_fallback below it, which itself just calls this.
    That's deliberate, not incidental: PRICE-DISPLAY RULE — any new feature
    that needs to show a coin's USD price must format it through this
    function (or a helper that itself calls it), never a fresh ad hoc
    f"${value:.2f}"/similar. A fixed decimal count silently rounds a real,
    nonzero price down to "$0.00" once the coin is cheap enough (confirmed
    live for both a sub-cent coin at a fixed 2 decimals, and later an
    even-smaller coin at a fixed 8 decimals) — this function's whole job is
    guaranteeing that never happens again, so any bypass reopens the exact
    bug this was written to close.
    """
    # Always 2 decimals (e.g. $3.11) for $1+ prices — was rounding to a
    # whole dollar there ("$3"), which lost precision on both the homepage
    # table's Price column and the coin detail page's big price display
    # (both read this same price_display field).
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value == 0 or value >= 1:
        return f"{sign}${value:,.2f}"
    # Sub-$1: start at 8 decimals (enough for the vast majority of coins,
    # e.g. SHIB's real $0.000005887), but keep extending in steps of 4 for
    # anything smaller — a fixed decimal count of any size eventually rounds
    # a real, nonzero price down to all zeros once a coin is cheap enough
    # (well under a billionth of a dollar isn't rare among newly-listed
    # micro-cap tokens), which used to silently display as "$0.00" instead
    # of the coin's real price. Capped at 24 decimals — several times past
    # any real crypto price's meaningful precision — purely so a
    # pathological near-zero float can't loop forever.
    decimals = 8
    formatted = f"{value:.{decimals}f}"
    while decimals < 24 and set(formatted.split(".")[1]) == {"0"}:
        decimals += 4
        formatted = f"{value:.{decimals}f}"
    # Trailing zeros stripped (but not below 2 decimals) so e.g. $0.05
    # still shows as "$0.05", not "$0.05000000" — this is what guarantees
    # the displayed string always ends on a real, non-zero digit rather
    # than a rounding artifact.
    formatted = formatted.rstrip("0")
    if formatted.endswith("."):
        formatted += "00"
    return f"{sign}${formatted}"


def _price_display_with_fallback(price_usd: float | None, cached_market_pairs: list[dict] | None) -> str:
    """_fmt_usd(price_usd), falling back to this coin's own already-fetched
    top-volume real market pair's price when CMC's own quote is exactly
    zero (or missing) — confirmed live for several obscure/low-cap coins
    (e.g. CatCoin) where CMC's tracked price feed reports a flat $0 (likely
    an illiquid/stale market CMC itself is quoting) while a real, actively-
    traded pool exists and shows a genuine nonzero price — CoinGecko-sourced
    the same way this coin's own Markets section already does (see
    market_pairs_service.py). _fmt_usd itself already handles arbitrarily
    small nonzero prices correctly (up to 8 decimals) — this only kicks in
    when the canonical price is truly absent/zero, not merely small.

    Only ever affects the DISPLAYED string, never coin.price_usd itself —
    market cap, sorting, and every other calculation still use CMC's own
    canonical (possibly-zero) number, same "raw stays raw, formatting
    happens here" division of labor as every other _fmt_* helper.
    """
    if price_usd:
        return _fmt_usd(price_usd)
    pairs = cached_market_pairs or []
    if not pairs:
        return _fmt_usd(0.0)
    best = max(pairs, key=lambda p: p.get("volume_24h") or 0)
    fallback_price = best.get("price")
    if not fallback_price:
        return _fmt_usd(0.0)
    return _fmt_usd(fallback_price)


def _fmt_compact_usd(value: float) -> str:
    """Abbreviated $ amount for Market Cap / Volume columns, e.g. $2.43M."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= threshold:
            return f"{sign}${value / threshold:,.2f}{suffix}"
    return f"{sign}${value:,.2f}"


# Maps market_pairs_service.py's real CEX exchange_name values (see that
# module's _CEX_ALLOWED_NAMES) to the exchange prefix TradingView's own
# widgetembed actually recognizes for that venue's crypto symbols (e.g.
# "MEXC:ZKMLUSDT") — confirmed live that a bare, unprefixed "{SYMBOL}USDT"
# (TradingView resolving the venue itself) shows "This symbol doesn't
# exist" for coins whose only real USDT listing is on a smaller-but-still-
# top-15 exchange (e.g. MEXC/Gate/HTX) rather than Binance, since TradingView
# doesn't reliably fall back to another venue on its own for a low-cap
# ticker. Picking the coin's own highest-volume real CEX pair and
# exchange-prefixing it fixes that instead of guessing.
_TRADINGVIEW_EXCHANGE_PREFIXES = {
    "binance": "BINANCE",
    "binance tr": "BINANCE",
    "binance alpha": "BINANCE",
    "coinbase exchange": "COINBASE",
    "upbit": "UPBIT",
    "okx": "OKX",
    "bybit": "BYBIT",
    "bitget": "BITGET",
    "gate": "GATEIO",
    "gate.io": "GATEIO",
    "kucoin": "KUCOIN",
    "mexc": "MEXC",
    "htx": "HTX",
    "crypto.com exchange": "CRYPTOCOM",
    "bitfinex": "BITFINEX",
    "bingx": "BINGX",
    "kraken": "KRAKEN",
}

# Every real quote asset this app's own USD-denominated price header/Markets
# tables should be considered equivalent to when ranking a coin's real CEX
# pairs for a TradingView chart symbol — a pair quoted in any of these reads
# as "the same price" a viewer already sees elsewhere on the page; anything
# else (KRW, JPY, EUR, a coin's own native L1 asset, ...) doesn't, even
# though it's a perfectly real listing. See _resolve_tradingview_symbol.
_USD_EQUIVALENT_QUOTES = {
    "USD", "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDD", "FDUSD", "PYUSD", "GUSD", "USDP",
}

# Per explicit request: the TradingView chart should prefer whichever of
# these four the coin is actually listed on, in this order — MEXC, then
# KuCoin, then HTX, then Bybit — instead of ranking by volume/USD-equivalent
# quote, which otherwise picks Binance for most coins (Binance/Coinbase/any
# other real exchange only get used when a coin has NONE of these four).
# Unlike an earlier version of this rule, this doesn't require all four (or
# any specific subset) to be present at once — a coin listed on just one of
# them (e.g. only Bybit) still prefers it over a higher-volume Binance pair.
# See _resolve_tradingview_symbol.
_EXCHANGE_PRIORITY = ["MEXC", "KUCOIN", "HTX", "BYBIT"]


def _resolve_chart_symbol(symbol: str, coin: dict | None) -> str | None:
    """Shared by CoinState._resolve_tradingview_symbol (the viewed coin's chart)
    and the floating watchlist popup's live prices (one call per watched
    coin) — see that method's docstring for the full ranking rules."""
    base = re.sub(r"[^A-Z0-9]", "", (symbol or "").strip().upper())
    if not base:
        return None
    pairs = coin.get("market_pairs", []) if coin else []
    coin_price = float((coin or {}).get("price_raw") or 0)
    candidates = []
    for p in pairs:
        if p.get("is_dex"):
            continue
        prefix = _TRADINGVIEW_EXCHANGE_PREFIXES.get(p.get("exchange_name", "").strip().lower())
        if not prefix:
            continue
        pair_base, _, quote = p.get("market_pair", "").partition("/")
        quote = quote.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{2,10}", quote):
            continue
        # Price sanity: a pair whose USD price is far from this coin's own
        # price is a different asset that merely shares the ticker.
        pair_price = float(p.get("price") or 0)
        if coin_price > 0 and pair_price > 0 and not (0.5 <= pair_price / coin_price <= 2.0):
            continue
        # Use the exchange's own base when it is a plain ticker (Beam is
        # listed as BEAMX on Binance/MEXC/HTX/Gate; "BEAMUSDT" there is
        # the unrelated privacy coin). A full-name base such as
        # "SHIBA INU" is not a ticker, so those keep this coin's ticker.
        pair_base = pair_base.strip().upper()
        pbase = pair_base if re.fullmatch(r"[A-Z0-9]{2,15}", pair_base) else base
        candidates.append((prefix, quote, p.get("volume_24h", 0), pbase))
    if candidates:
        priority_rank = {p: i for i, p in enumerate(_EXCHANGE_PRIORITY)}
        priority_candidates = [c for c in candidates if c[0] in priority_rank]
        if priority_candidates:
            # Ascending sort: priority rank first (MEXC < KuCoin < HTX <
            # Bybit), then a USD-equivalent quote before a foreign-fiat
            # one, then higher volume first — same tiebreakers as the
            # else branch below, just applied within the priority tier.
            priority_candidates.sort(
                key=lambda c: (priority_rank[c[0]], c[1] not in _USD_EQUIVALENT_QUOTES, -c[2])
            )
            prefix, quote, _volume, base = priority_candidates[0]
        else:
            # None of MEXC/KuCoin/HTX/Bybit exist for this coin — rank
            # whatever's left (Binance, Coinbase, or any other real
            # exchange) by USD-equivalent quote first, then volume; a
            # USD-equivalent-quoted pair always outranks a foreign-fiat
            # one, whatever the raw volume gap — see this function's
            # own docstring.
            candidates.sort(key=lambda c: (c[1] in _USD_EQUIVALENT_QUOTES, c[2]), reverse=True)
            prefix, quote, _volume, base = candidates[0]
        return f"{prefix}:{base}{quote}"
    dex_symbol = coin.get("tradingview_dex_symbol", "") if coin else ""
    return dex_symbol or None


def _login_required(handler):
    """Guard for event handlers that need an account (price alerts): a
    logged-out caller is sent to /login and the handler never runs. Checked on
    the server for every event, so it can't be bypassed from the browser."""

    @functools.wraps(handler)
    async def wrapper(self, *args, **kwargs):
        if not (self.is_logged_in and self.user_id):
            self.alert_dialog_open = False
            return rx.call_script("window.location.assign('/login')")
        return await handler(self, *args, **kwargs)

    return wrapper


def _plain_price(value: float) -> str:
    """A price for an input field: _fmt_usd's precision without "$" and commas."""
    return _fmt_usd(value).lstrip("$").replace(",", "")


# X's cashtag search names a chain with a lowercase slug: "<slug>:native" for a
# chain's own coin, "<slug>:<contract>" for a token. Verified from X's own
# examples (bitcoin:native, ethereum:0x… for FET, robinhood:0x… for PONS); the
# rest follow the same pattern. A chain that isn't listed here falls back to a
# plain "$TICKER" search rather than guessing a slug X might not know.
_X_CHAIN_SLUGS = {
    "Ethereum": "ethereum",
    "Solana": "solana",
    "Base": "base",
    "Arbitrum": "arbitrum",
    "Polygon": "polygon",
    "Optimism": "optimism",
    "Robinhood Chain": "robinhood",
    "Avalanche C-Chain": "avalanche",
}


def _x_search_url(symbol: str, name: str, main_chain: str, contract_address: str) -> str:
    """Link for the coin page's Social Insights "See More": an X search for the
    coin's cashtag OR its on-chain identity, e.g. "$BTC OR bitcoin:native" or
    "$PONS OR robinhood:0x39db…" — the query X builds when you pick the coin
    from its search dropdown."""
    sym = re.sub(r"[^A-Za-z0-9]", "", symbol or "")
    if not sym:
        query = name or symbol or ""
    else:
        query = f"${sym.upper()}"
        if contract_address:
            slug = _X_CHAIN_SLUGS.get(main_chain)
            if slug:
                query += f" OR {slug}:{contract_address}"
        else:
            # A coin with no contract is its own chain: "<chain>:native".
            native = re.sub(r"[^a-z0-9]", "", (main_chain or name or "").lower())
            if native:
                query += f" OR {native}:native"
    return "https://x.com/search?" + urlencode({"q": query, "src": "typed_query"})


def _fmt_alert_time(moment) -> str:
    """Kuala Lumpur wall-clock time (the app's display timezone) for alert history rows."""
    import datetime as _dt
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kuala_Lumpur")
    moment = moment.astimezone(tz) if moment else _dt.datetime.now(tz)
    return moment.strftime("%d %b %Y, %H:%M")


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def _fmt_compact_number(value: float) -> str:
    """Abbreviated plain (non-$) count for supply figures, e.g. 19.87M."""
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= threshold:
            return f"{value / threshold:,.2f}{suffix}"
    return f"{value:,.2f}"


def _pct_color(value: float) -> str:
    return "red" if value < 0 else "green"


def _trend_line(percent_change: float) -> tuple[list[dict], str, str]:
    if percent_change > 100:
        return _TREND_UP, "gold", "trend-gold-shine"
    if percent_change < -50:
        return _TREND_DOWN, "red", "trend-red-shine"
    if percent_change < 0:
        return _TREND_DOWN, "red", ""
    return _TREND_UP, "green", ""


# Tags that are VC-portfolio / exchange-listing noise rather than a real
# narrative — filtered out when picking the one short label to show per coin.
_NOISE_PATTERNS = (
    "portfolio",
    "ecosystem",
    "listing",
    "estate",
    "reserve",
    "taxonomy",
    "commodities",
    "alt season",
    "capital",
    "labs",
    "launchpad",
    "ventures",
)


# CMC tags that describe where a coin is listed / who backs it, not what the
# project does ("Binance Alpha", "Coinbase Ventures Portfolio", "Solana
# Ecosystem", "Polkastarter", ...). Never shown as the category badge.
_BADGE_NOISE_RE = re.compile(
    r"binance|coinbase|robinhood|okx|bybit|kucoin|portfolio|ecosystem|listing|launchpad|alpha|"
    r"capital|ventures|labs|holdings|\bvc\b|fund|alliance|hackathon|yearbook|made in|presale|"
    r"airdrop|polkastarter|seedify|oxbull|dao maker|spartan|jump crypto|\bmvb\b|\bpow\b|\bpos\b|"
    r"mineable|sha 256|tron20|bep-?20|erc-?20|rehypothecated|cmc community",
    re.I,
)


def _category_badge(category: str | None, primary_narrative: str) -> str:
    """The badge next to the chart heading: the curated business-model
    category, else the coin's first CMC tag that says what the project does,
    else nothing (better than a listing tag like "Binance Alpha")."""
    if category:
        return category
    if primary_narrative and not _BADGE_NOISE_RE.search(primary_narrative):
        return primary_narrative
    return ""


def _pick_primary_narrative(names: list[str]) -> str:
    for name in names:
        lowered = name.lower()
        if not any(pattern in lowered for pattern in _NOISE_PATTERNS):
            return name
    return names[0] if names else ""


# Maps narrative keywords to a representative lucide icon for the badge.
# Order matters (first match wins); falls back to a generic tag icon for any
# narrative name that doesn't hit one of these — new/unseen CMC tags still
# render correctly, just with the generic icon.
_NARRATIVE_ICONS: tuple[tuple[str, str], ...] = (
    ("meme", "smile"),
    ("artificial intelligence", "cpu"),
    (" ai", "cpu"),
    ("gaming", "gamepad-2"),
    ("metaverse", "gamepad-2"),
    ("stablecoin", "dollar-sign"),
    ("nft", "image"),
    ("collectible", "image"),
    ("privacy", "eye-off"),
    ("exchange", "arrow-left-right"),
    ("storage", "database"),
    ("oracle", "radio"),
    ("payment", "credit-card"),
    ("defi", "landmark"),
    ("layer", "layers"),
)


def _narrative_icon(name: str) -> str:
    lowered = f" {name.lower()} "
    for pattern, icon in _NARRATIVE_ICONS:
        if pattern in lowered:
            return icon
    return "tag"


def _resolve_unlock_source_url(symbol: str, defillama_slug: str | None) -> str:
    """Three-tier fallback for the Locked Supply section's "View live
    unlock data" link, in order:
    1. A real per-project DeFiLlama Unlocks page, when
       defillama_unlocks_service resolved one (contract-address/gecko_id/
       cmcId matched — see that module's own docstring).
    2. Tokenomist's own per-coin unlock-events page, keyed by this coin's
       CoinGecko id — confirmed live tokenomist.ai's own slug convention
       IS the CoinGecko id (e.g. "fetch-ai", "bitcoin", "chainlink"), not
       the ticker (which 404s: "fet" does, "fetch-ai" doesn't). Reuses the
       exact same top-500 ticker->gecko_id map defillama_unlocks_service's
       own gecko_id path already depends on, so no new external call.
    3. DeFiLlama's own per-ticker Token page, for a coin outside that
       top-500 map (no gecko_id known at all) — the same real, ticker-
       based page confirmed live for any listed coin.
    Never guesses a slug from the coin's own name/ticker for tokenomist
    either — same "real match or a known-safe fallback, never a guess"
    rule this whole feature already follows.
    """
    if defillama_slug:
        return f"https://defillama.com/protocol/unlocks/{defillama_slug}"

    import sys
    from pathlib import Path

    # Reflex's own process runs with only frontend/ on sys.path — see the
    # matching comment on this same fix elsewhere in this file (e.g.
    # _fetch_business_summary) for why this is needed before any `app.*`
    # import. Confirmed live this was a real, silent bug: on a fresh
    # session whose very first page is /news (whose own on_load runs
    # CoinState.load_coins before anything else has had a chance to patch
    # sys.path), every coin lacking a real defillama_slug hit this import
    # and crashed load_coins entirely with ModuleNotFoundError.
    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.services.coingecko_service import _get_top_coin_symbol_map

    gecko_id = _get_top_coin_symbol_map().get(symbol.upper())
    if gecko_id:
        return f"https://tokenomist.ai/{gecko_id}/unlock-events"
    return f"https://defillama.com/token/{symbol.upper()}"


def _build_row(coin: Coin) -> dict:
    """Builds one table row dict from a Coin (with categories/contracts
    eager-loaded). Shared by load_coins (full load) and the view-driven
    live sync (refreshes just the coins on whichever page is on screen).
    """
    names = sorted(category.name for category in coin.categories)
    trend_24h_data, trend_24h_color, trend_24h_shine = _trend_line(coin.percent_change_24h or 0.0)
    trend_7d_data, trend_7d_color, trend_7d_shine = _trend_line(coin.percent_change_7d or 0.0)
    primary_narrative = _pick_primary_narrative(names)

    # A coin with no contract rows is single-chain — it IS its own chain.
    # Otherwise the row already flagged as primary (see
    # MarketDataService._upsert_contracts) is the main chain; everything
    # else feeds the "other chains" dropdown.
    chains = sorted(coin.contracts, key=lambda c: c.sort_order)
    primary_chain = next((c for c in chains if c.is_primary), None)
    main_chain = primary_chain.platform_name if primary_chain else coin.name
    other_chains = [c.platform_name for c in chains if c is not primary_chain]

    # Native coins (BTC, ETH, SOL...) have no contract rows at all — only
    # tokens deployed on top of another chain have a real address to show.
    contract_address = (primary_chain.contract_address if primary_chain else None) or ""
    # CMC's own /v2/info data occasionally reports a placeholder like "0"
    # for a wrapped/bridged listing that hasn't been assigned a real
    # address yet (confirmed live on TAO's Solana-Ecosystem entry) — too
    # short to be a genuine contract address (real ones are 26+ chars,
    # EVM 0x... or Solana base58), so treated as "no contract" rather than
    # displaying/copying garbage.
    if len(contract_address) < 20:
        contract_address = ""
    contract_address_display = (
        f"{contract_address[:6]}...{contract_address[-4:]}" if len(contract_address) > 14 else contract_address
    )

    # Every OTHER chain this coin is genuinely deployed on with a real
    # contract address (same >=20-char validity filter as the primary one
    # above) — feeds the Contract row's "+N chains" dropdown so a coin
    # bridged/wrapped across several chains can show all of them, not just
    # whichever one happened to be flagged primary.
    other_chain_contracts = []
    for c in chains:
        if c is primary_chain or not c.contract_address or len(c.contract_address) < 20:
            continue
        addr = c.contract_address
        other_chain_contracts.append(
            {
                "platform_name": c.platform_name,
                "contract_address": addr,
                "contract_address_display": f"{addr[:6]}...{addr[-4:]}" if len(addr) > 14 else addr,
            }
        )

    # Ordered by the same priority _links_section always rendered them in —
    # only the platforms this coin actually declared. First 3 show inline,
    # the rest (if any) collapse into a dropdown, same pattern as chains.
    social_candidates = [
        ("twitter", coin.twitter_url),
        ("github", coin.source_code_url),
        ("telegram", coin.telegram_url),
        ("reddit", coin.reddit_url),
        ("facebook", coin.facebook_url),
    ]
    social_links = [{"platform": p, "url": u} for p, u in social_candidates if u]

    vol_mkt_cap_pct = (
        coin.volume_24h_usd / coin.market_cap_usd * 100
        if coin.volume_24h_usd and coin.market_cap_usd
        else None
    )

    return {
        "cmc_id": coin.cmc_id,
        "name": coin.name,
        "symbol": coin.symbol,
        "icon_url": f"https://s2.coinmarketcap.com/static/img/coins/64x64/{coin.cmc_id}.png",
        # CMC's own rank, real-time synced on every listings/quotes call —
        # used on the coin detail page's rank badge (its "rank" key above is
        # a market-cap-position computed fresh only in filtered_coins, which
        # selected_coin bypasses by reading straight out of all_coins).
        "cmc_rank": coin.cmc_rank or 0,
        "market_cap_usd": coin.market_cap_usd or 0.0,
        "price_raw": coin.price_usd or 0.0,
        "volume_raw": coin.volume_24h_usd or 0.0,
        "pct_1h_raw": coin.percent_change_1h or 0.0,
        "pct_24h_raw": coin.percent_change_24h or 0.0,
        "pct_7d_raw": coin.percent_change_7d or 0.0,
        "price_display": _price_display_with_fallback(coin.price_usd, coin.cached_market_pairs),
        "market_cap_display": _fmt_compact_usd(coin.market_cap_usd or 0.0),
        "volume_display": _fmt_compact_usd(coin.volume_24h_usd or 0.0),
        "change_1h_display": _fmt_pct(coin.percent_change_1h or 0.0),
        "change_1h_color": _pct_color(coin.percent_change_1h or 0.0),
        "change_24h_display": _fmt_pct(coin.percent_change_24h or 0.0),
        "change_24h_color": _pct_color(coin.percent_change_24h or 0.0),
        "change_7d_display": _fmt_pct(coin.percent_change_7d or 0.0),
        "change_7d_color": _pct_color(coin.percent_change_7d or 0.0),
        "narratives": ", ".join(names),
        "narrative_list": names,
        "primary_narrative": primary_narrative,
        # Use-case peer group (app/services/peer_groups.py) for the coin
        # page's Similar Coins slider.
        "peer_group": coin.peer_group or "",
        "primary_narrative_icon": _narrative_icon(primary_narrative),
        "main_chain": main_chain,
        "other_chains_display": "\n".join(other_chains),
        "has_other_chains": len(other_chains) > 0,
        "platform_list": [main_chain, *other_chains],
        "contract_address": contract_address,
        "contract_address_display": contract_address_display,
        "has_contract": bool(contract_address),
        "other_chain_contracts": other_chain_contracts,
        "has_other_chain_contracts": bool(other_chain_contracts),
        "social_links_primary": social_links[:3],
        "social_links_extra": social_links[3:],
        "has_extra_socials": len(social_links) > 3,
        # Real, already-fetched data (see MarketDataService._upsert_coins/
        # _upsert_quotes) that just wasn't persisted before now. Liq/Mkt Cap
        # and Holders still have no equivalent field on CMC's Basic tier
        # (Liquidity Score is a paid-tier metric; holder counts need a
        # separate blockchain-explorer API), so those two stay "—".
        "vol_mkt_cap_display": f"{vol_mkt_cap_pct:.2f}%" if vol_mkt_cap_pct is not None else "—",
        "fdv_display": (
            _fmt_compact_usd(coin.fully_diluted_market_cap)
            if coin.fully_diluted_market_cap
            else "—"
        ),
        "circulating_supply_display": (
            f"{_fmt_compact_number(coin.circulating_supply)} {coin.symbol}"
            if coin.circulating_supply
            else "—"
        ),
        "total_supply_display": (
            f"{_fmt_compact_number(coin.total_supply)} {coin.symbol}" if coin.total_supply else "—"
        ),
        "max_supply_display": (
            f"{_fmt_compact_number(coin.max_supply)} {coin.symbol}" if coin.max_supply else "—"
        ),
        # Locked Supply section (coin_detail.py) — no real vesting/unlock-
        # schedule data anywhere for free (CMC/CoinGecko/CryptoRank/
        # DeFiLlama all checked; real cliff/linear unlock *dates* are a paid
        # data category everywhere), so this is honest supply math instead
        # of a fabricated unlock calendar: max_supply - circulating_supply,
        # its $ value at the coin's own current price, and what % of max
        # supply that represents. Only shown when max_supply is actually
        # greater than circulating_supply — a coin with no max supply, or
        # one that's already fully circulating, has nothing to show here.
        "has_locked_supply": bool(
            coin.max_supply and coin.circulating_supply and coin.max_supply > coin.circulating_supply
        ),
        "locked_supply_display": (
            f"{_fmt_compact_number(coin.max_supply - coin.circulating_supply)} {coin.symbol}"
            if coin.max_supply and coin.circulating_supply and coin.max_supply > coin.circulating_supply
            else "—"
        ),
        "locked_supply_value_display": (
            _fmt_compact_usd((coin.max_supply - coin.circulating_supply) * (coin.price_usd or 0.0))
            if coin.max_supply and coin.circulating_supply and coin.max_supply > coin.circulating_supply
            else "—"
        ),
        "locked_supply_pct_display": (
            f"{(coin.max_supply - coin.circulating_supply) / coin.max_supply * 100:.2f}%"
            if coin.max_supply and coin.circulating_supply and coin.max_supply > coin.circulating_supply
            else "—"
        ),
        # Fill width (0-100) for the range meter below the Locked Supply
        # stats — the circulating portion of max supply, shown in green.
        "circulating_supply_pct_value": (
            round(min(coin.circulating_supply / coin.max_supply * 100, 100), 2)
            if coin.max_supply and coin.circulating_supply and coin.max_supply > coin.circulating_supply
            else 0.0
        ),
        "website_url": coin.website_url or "",
        "whitepaper_url": coin.whitepaper_url or "",
        "twitter_url": coin.twitter_url or "",
        "x_search_url": _x_search_url(coin.symbol, coin.name, main_chain, contract_address),
        "telegram_url": coin.telegram_url or "",
        "source_code_url": coin.source_code_url or "",
        "explorer_url": coin.explorer_url or "",
        "reddit_url": coin.reddit_url or "",
        "facebook_url": coin.facebook_url or "",
        "has_website": bool(coin.website_url),
        "has_whitepaper": bool(coin.whitepaper_url),
        "has_twitter": bool(coin.twitter_url),
        "has_telegram": bool(coin.telegram_url),
        "has_source_code": bool(coin.source_code_url),
        "has_explorer": bool(coin.explorer_url),
        "has_reddit": bool(coin.reddit_url),
        "has_facebook": bool(coin.facebook_url),
        "description": coin.description or "",
        "has_description": bool(coin.description),
        # Pre-tokenized for the keyword-underline highlight (see
        # coin_detail.py's _render_highlight_token) — computed once here
        # rather than as a live Var transform, since it's arbitrary string
        # processing.
        "description_tokens": _tokenize_highlights(coin.description or ""),
        # AI-generated business-model explainer (see
        # app/services/business_summary_service.py), refreshed on-demand via
        # CoinState.refresh_business_summary rather than by this row build.
        "business_summary": coin.business_summary or "",
        "has_business_summary": bool(coin.business_summary),
        "business_summary_sections": _parse_business_summary_sections(coin.business_summary or ""),
        # {provider, provider_display, model_display} for the attribution
        # badge (see coin_detail.py's _business_summary_section).
        "business_summary_model_badge": _format_model_badge(coin.business_summary_model or ""),
        # Short AI-generated business-model classification (see
        # business_summary_service.py's CATEGORY: line) shown as a badge
        # next to the live-chart heading (see coin_detail.py). Only ever set
        # on-demand the first time a coin's business summary is generated
        # (rate-limited by OpenRouter's free tier), so most coins never get
        # one within a session — category_badge_display below is what
        # coin_detail.py actually renders, falling back to this coin's real
        # CMC narrative tag so every coin's page still shows *some* badge
        # instead of the row next to the heading sometimes being empty.
        "business_model_category": coin.business_model_category or "",
        "has_business_model_category": bool(coin.business_model_category),
        "category_badge_display": _category_badge(coin.business_model_category, primary_narrative),
        "has_category_badge_display": bool(_category_badge(coin.business_model_category, primary_narrative)),
        # Cached CEX/DEX market pairs (see
        # app/services/market_pairs_service.py), refreshed on-demand via
        # CoinState.refresh_market_pairs rather than by this row build.
        "market_pairs": _format_market_pairs(coin.cached_market_pairs or []),
        "has_market_pairs": bool(coin.cached_market_pairs),
        # Distinguishes "never fetched yet" (None) from "fetched and this
        # coin genuinely has zero real listings" — see
        # CoinState.has_tradingview_chart/tradingview_chart_pending, which
        # need this to avoid ever guessing an unreliable bare chart symbol
        # while the real one is still loading.
        "market_pairs_fetched": coin.market_pairs_updated_at is not None,
        # Last-resort TradingView chart symbol for a coin with zero real CEX
        # pairs (see app/services/tradingview_symbol_service.py), refreshed
        # on-demand via CoinState.refresh_tradingview_dex_symbol. Same
        # fetched/not-yet-fetched distinction as market_pairs_fetched above,
        # for the same reason — CoinState._resolve_tradingview_symbol only
        # ever reads tradingview_dex_symbol as a fallback after its own
        # CEX-pairs path already came up empty.
        "tradingview_dex_symbol": coin.tradingview_dex_symbol or "",
        "tradingview_dex_symbol_fetched": coin.tradingview_dex_symbol_checked_at is not None,
        # Real per-coin "View live unlock data" deep link — see
        # _resolve_unlock_source_url's own docstring for the 3-tier
        # fallback (real DeFiLlama project match -> tokenomist.ai by
        # gecko_id -> DeFiLlama's own per-ticker Token page).
        "unlock_source_url": _resolve_unlock_source_url(coin.symbol, coin.defillama_unlocks_slug),
        # Cached X posts — the scraping backend that populated this (Apify,
        # app/services/social_service.py) was removed per explicit request
        # (cost/ToS concerns with every third-party scraping option tried),
        # so this is always empty now and _x_posts_section always renders
        # its "View on X" fallback slider instead of real post cards — that
        # fallback UI is kept intentionally, not dead code.
        "cached_tweets": coin.cached_tweets or [],
        "has_cached_tweets": bool(coin.cached_tweets),
        "trend_24h_data": trend_24h_data,
        "trend_24h_color": trend_24h_color,
        "trend_24h_shine": trend_24h_shine,
        "trend_7d_data": trend_7d_data,
        "trend_7d_color": trend_7d_color,
        "trend_7d_shine": trend_7d_shine,
    }


def _change_24h_display(cmc_id: int, market_cap_now: float, volume_now: float) -> dict[str, str]:
    """Coin page badges: this coin's market cap and 24h volume now vs. our own
    price snapshot from ~24h ago (app/services/price_snapshot_service.py,
    same lookback/tolerance as the 24h Gainers & Losers board). Blocking
    (DB); runs in a thread, at runtime only. A side with no usable snapshot
    (new coin, or history younger than ~20h) gets has_* = "" and shows
    nothing."""
    import sys
    from pathlib import Path

    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.core.database import SessionLocal as OldSessionLocal
    from app.services.price_snapshot_service import get_reference_values, pct_change

    db = OldSessionLocal()
    try:
        ref = get_reference_values(db, cmc_id)
    finally:
        db.close()

    out = {"cmc_id": str(cmc_id)}
    for key, now_value, then_key in (("mcap", market_cap_now, "market_cap"), ("vol", volume_now, "volume_24h")):
        change = pct_change(now_value or None, ref[then_key])
        out[f"{key}_has"] = "1" if change is not None else ""
        if change is None:
            out[f"{key}_text"] = out[f"{key}_color"] = out[f"{key}_title"] = ""
            continue
        arrow = "▲" if change > 0 else "▼" if change < 0 else ""
        out[f"{key}_text"] = f"{arrow} {abs(change):.2f}%".strip()
        out[f"{key}_color"] = (
            "var(--green-11)" if change > 0 else "var(--red-11)" if change < 0 else "var(--gray-11)"
        )
        then_at = ref[f"{then_key}_at"]
        out[f"{key}_title"] = (
            f"Change vs. {_fmt_compact_usd(ref[then_key])} at {then_at.strftime('%d %b %H:%M')} UTC (about 24h ago)"
        )
    return out


def _sync_and_rebuild_rows(cmc_ids: list[int]) -> dict[int, dict]:
    """Blocking work for the view-driven live sync: refreshes the given
    coins' quotes in Postgres (cross-package call into the FastAPI
    backend's own service, same pattern as reflex_cache_service.py's
    Postgres->Reflex mirror), mirrors just those rows into the Reflex
    SQLite cache, and returns freshly-built row dicts keyed by cmc_id.
    Runs in a thread (see CoinState.sync_visible_page) since it's all
    synchronous network/DB calls.
    """
    import sys
    from pathlib import Path

    from sqlalchemy import select as sa_select

    # Reflex's own process runs with only frontend/ on sys.path — the
    # project root (parent of both app/ and frontend/) needs adding before
    # `app.*` can be imported, same cross-package pattern as
    # reflex_cache_service.py uses in the other direction.
    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.core.database import SessionLocal as OldSessionLocal
    from app.models.coin import Coin as OldCoin
    from app.models.sync_log import SyncStatus
    from app.services.market_data_service import MarketDataService

    old_db = OldSessionLocal()
    try:
        sync_log = MarketDataService(old_db).sync_ids(cmc_ids)
        if sync_log.status != SyncStatus.SUCCESS:
            # Transient CMC/network hiccup — skip this cycle rather than
            # mirroring stale Postgres data into Reflex's cache; the next
            # tick (60s, or the next page/filter change) tries again.
            return {}
        fresh_by_id = {
            c.cmc_id: c
            for c in old_db.scalars(sa_select(OldCoin).where(OldCoin.cmc_id.in_(cmc_ids))).all()
        }
    finally:
        old_db.close()

    with rx.session() as session:
        rows = session.exec(select(Coin).where(Coin.cmc_id.in_(cmc_ids))).all()
        for row in rows:
            fresh = fresh_by_id.get(row.cmc_id)
            if fresh is None:
                continue
            row.cmc_rank = fresh.cmc_rank
            row.price_usd = float(fresh.price_usd) if fresh.price_usd is not None else None
            row.market_cap_usd = float(fresh.market_cap_usd) if fresh.market_cap_usd is not None else None
            row.volume_24h_usd = float(fresh.volume_24h_usd) if fresh.volume_24h_usd is not None else None
            row.percent_change_1h = (
                float(fresh.percent_change_1h) if fresh.percent_change_1h is not None else None
            )
            row.percent_change_24h = (
                float(fresh.percent_change_24h) if fresh.percent_change_24h is not None else None
            )
            row.percent_change_7d = (
                float(fresh.percent_change_7d) if fresh.percent_change_7d is not None else None
            )
            row.last_synced_at = fresh.last_synced_at
            session.add(row)
        session.commit()

        updated_coins = session.exec(
            select(Coin)
            .where(Coin.cmc_id.in_(cmc_ids))
            .options(selectinload(Coin.categories), selectinload(Coin.contracts))
        ).all()
        return {coin.cmc_id: _build_row(coin) for coin in updated_coins}


def _fetch_better_description(symbol: str) -> tuple[int, str] | None:
    """Blocking work for the on-demand description upgrade (see CoinState.
    refresh_coin_description) — same lookup-by-ticker-in-Postgres pattern as
    _fetch_business_summary below. Two independent, one-time-per-coin steps, each
    gated by its own service (so most calls here are a no-op — already
    attempted, or was never boilerplate to begin with):
    1. coingecko_service.upgrade_description — CoinGecko's own real project
       write-up, resolved via contract address.
    2. If STILL boilerplate after that (typical for memecoins/newly-listed
       tokens with no whitepaper or curated listing anywhere),
       description_ai_service.generate_description_from_sources — an
       AI-generated summary grounded in the coin's own website text and/or
       cached X posts, the only two public sources such a coin actually has.
    Returns None if no coin matches this ticker or neither step changed
    anything.
    """
    import sys
    from pathlib import Path

    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.core.database import SessionLocal as OldSessionLocal
    from app.models.coin import Coin as OldCoin
    from app.services.coingecko_service import upgrade_description
    from app.services.description_ai_service import generate_description_from_sources

    old_db = OldSessionLocal()
    try:
        matches = old_db.scalars(
            sa_select(OldCoin).where(OldCoin.symbol.ilike(symbol)).options(selectinload(OldCoin.contracts))
        ).all()
        if not matches:
            return None
        coin = max(matches, key=lambda c: c.market_cap_usd or 0.0)
        original = coin.description
        upgrade_description(old_db, coin)
        generate_description_from_sources(old_db, coin)
        if coin.description == original:
            return None
        fresh = coin.description
        cmc_id = coin.cmc_id
    finally:
        old_db.close()

    with rx.session() as session:
        row = session.exec(select(Coin).where(Coin.cmc_id == cmc_id)).first()
        if row is not None:
            row.description = fresh
            session.add(row)
            session.commit()

    return cmc_id, fresh


def _format_market_pairs(pairs: list[dict]) -> list[dict]:
    """Adds display-formatted fields to market_pairs_service.py's raw
    {exchange_name, exchange_icon_url, market_pair, is_dex, price,
    volume_24h, volume_pct, last_updated_display} dicts — same division of
    labor as everywhere else in this file: Postgres/the service layer keeps
    raw numbers, formatting for display happens here.
    """
    return [
        {
            **p,
            "price_display": _fmt_usd(p["price"]),
            "volume_display": _fmt_compact_usd(p["volume_24h"]),
            "volume_pct_display": f"{p['volume_pct']:.2f}%",
            "market_type_label": "DEX" if p["is_dex"] else "CEX",
            "market_type_color": "purple" if p["is_dex"] else "blue",
        }
        for p in pairs
    ]


def _fetch_market_pairs(symbol: str) -> tuple[int, list[dict]] | None:
    """Blocking work for the on-demand Markets-section refresh (see
    CoinState.refresh_market_pairs) — same lookup-by-ticker-in-Postgres
    pattern as _fetch_business_summary above, delegating
    to market_pairs_service's own TTL gate (settings.
    market_pairs_cache_ttl_hours), so most calls here just replay the
    already-cached pairs rather than re-hitting CoinGecko. Returns None if no
    coin matches this ticker.
    """
    import sys
    from pathlib import Path

    from sqlalchemy import select as sa_select

    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.core.database import SessionLocal as OldSessionLocal
    from app.models.coin import Coin as OldCoin
    from app.services.market_pairs_service import get_market_pairs

    old_db = OldSessionLocal()
    try:
        matches = old_db.scalars(sa_select(OldCoin).where(OldCoin.symbol.ilike(symbol))).all()
        if not matches:
            return None
        coin = max(matches, key=lambda c: c.market_cap_usd or 0.0)
        pairs = get_market_pairs(old_db, coin)
        cmc_id = coin.cmc_id
        market_pairs_updated_at = coin.market_pairs_updated_at
    finally:
        old_db.close()

    with rx.session() as session:
        row = session.exec(select(Coin).where(Coin.cmc_id == cmc_id)).first()
        if row is not None:
            row.cached_market_pairs = pairs
            # Mirrors Postgres's own market_pairs_updated_at onto this
            # reflex-sqlite row too — this used to be left unset here,
            # which permanently stuck CoinState.tradingview_chart_pending
            # (see "market_pairs_fetched" in _build_row) at True even long
            # after a real fetch had already completed and been cached.
            row.market_pairs_updated_at = market_pairs_updated_at
            session.add(row)
            session.commit()

    return cmc_id, pairs


def _fetch_tradingview_dex_symbol(symbol: str) -> tuple[int, str | None] | None:
    """Blocking work for CoinState.refresh_tradingview_dex_symbol — same
    lookup-by-ticker-in-Postgres pattern as _fetch_market_pairs above,
    delegating to tradingview_symbol_service's own "skip unless this coin
    has zero real CEX pairs" gate and TTL (settings.
    tradingview_symbol_ttl_hours), so most calls here are a fast no-op.
    Returns None if no coin matches this ticker.
    """
    import sys
    from pathlib import Path

    from sqlalchemy import select as sa_select

    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.core.database import SessionLocal as OldSessionLocal
    from app.models.coin import Coin as OldCoin
    from app.services.tradingview_symbol_service import resolve_dex_chart_symbol

    old_db = OldSessionLocal()
    try:
        matches = old_db.scalars(sa_select(OldCoin).where(OldCoin.symbol.ilike(symbol))).all()
        if not matches:
            return None
        coin = max(matches, key=lambda c: c.market_cap_usd or 0.0)
        dex_symbol = resolve_dex_chart_symbol(old_db, coin)
        cmc_id = coin.cmc_id
        checked_at = coin.tradingview_dex_symbol_checked_at
    finally:
        old_db.close()

    with rx.session() as session:
        row = session.exec(select(Coin).where(Coin.cmc_id == cmc_id)).first()
        if row is not None:
            row.tradingview_dex_symbol = dex_symbol
            row.tradingview_dex_symbol_checked_at = checked_at
            session.add(row)
            session.commit()

    return cmc_id, dex_symbol


def _fetch_defillama_unlocks_slug(symbol: str) -> tuple[int, str | None] | None:
    """Blocking work for CoinState.refresh_defillama_unlocks_slug — same
    lookup-by-ticker-in-Postgres pattern as _fetch_tradingview_dex_symbol
    above, delegating to defillama_unlocks_service's own TTL (settings.
    defillama_unlocks_ttl_hours). Returns None if no coin matches this
    ticker.
    """
    import sys
    from pathlib import Path

    from sqlalchemy import select as sa_select

    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.core.database import SessionLocal as OldSessionLocal
    from app.models.coin import Coin as OldCoin
    from app.services.defillama_unlocks_service import resolve_unlocks_slug

    old_db = OldSessionLocal()
    try:
        matches = old_db.scalars(sa_select(OldCoin).where(OldCoin.symbol.ilike(symbol))).all()
        if not matches:
            return None
        coin = max(matches, key=lambda c: c.market_cap_usd or 0.0)
        slug = resolve_unlocks_slug(old_db, coin)
        cmc_id = coin.cmc_id
        checked_at = coin.defillama_unlocks_checked_at
    finally:
        old_db.close()

    with rx.session() as session:
        row = session.exec(select(Coin).where(Coin.cmc_id == cmc_id)).first()
        if row is not None:
            row.defillama_unlocks_slug = slug
            row.defillama_unlocks_checked_at = checked_at
            session.add(row)
            session.commit()

    return cmc_id, slug


def _fetch_business_summary(symbol: str) -> tuple[int, str, str | None, str] | None:
    """Blocking work for the on-demand business-summary refresh (see
    CoinState.refresh_business_summary) — same lookup-by-ticker-in-Postgres
    pattern as _fetch_better_description above,
    delegating to business_summary_service's own TTL gate (settings.
    business_summary_ttl_days), so most calls here just replay the already-
    cached summary rather than re-hitting OpenRouter. Returns None if no
    coin matches this ticker or nothing was generated.
    """
    import sys
    from pathlib import Path

    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.core.database import SessionLocal as OldSessionLocal
    from app.models.coin import Coin as OldCoin
    from app.services.business_summary_service import get_business_summary

    old_db = OldSessionLocal()
    try:
        matches = old_db.scalars(
            sa_select(OldCoin).where(OldCoin.symbol.ilike(symbol)).options(selectinload(OldCoin.categories))
        ).all()
        if not matches:
            return None
        coin = max(matches, key=lambda c: c.market_cap_usd or 0.0)
        summary = get_business_summary(old_db, coin)
        if not summary:
            return None
        cmc_id = coin.cmc_id
        model = coin.business_summary_model
        category = coin.business_model_category or ""
    finally:
        old_db.close()

    with rx.session() as session:
        row = session.exec(select(Coin).where(Coin.cmc_id == cmc_id)).first()
        if row is not None:
            row.business_summary = summary
            row.business_summary_model = model
            row.business_model_category = category
            session.add(row)
            session.commit()

    return cmc_id, summary, model, category


class CoinState(rx.State):
    all_coins: list[dict] = []
    # Small dict, keyed by cmc_id, holding only the fields that periodically
    # get refreshed for an individual coin (price/volume/% changes from the
    # sync loops, cached tweets, description, business summary, market
    # pairs, TradingView chart symbol) — kept separate from the full,
    # rarely-changing all_coins list specifically so a background refresh
    # only ever needs to re-serialize and resend THIS small dict over the
    # websocket, not the entire ~8,000-coin universe. Confirmed live this
    # split was necessary: all_coins serializes to ~32MB, and every one of
    # these refreshers used to reassign it wholesale on every single
    # update (even a single coin's business summary finishing), which was
    # the dominant cause of "every click/search/sync tick feels slow" —
    # see _row_with_overrides/_merged_row below for how a display-facing
    # computed var (filtered_coins, selected_coin) merges this back in.
    coin_overrides: dict[int, dict] = {}
    # cmc_ids the viewer has starred, in-session (not tied to any account —
    # this app has no real user/auth system, just the one hardcoded "Fyqq"
    # profile pill). Toggled from the coin-detail page's star icon
    # (toggle_watchlist) and read back by watchlist_table.py's /watchlist
    # page via watchlist_coins below.
    watchlist_ids: list[int] = []
    categories: list[str] = []
    # Every narrative (no top-20 cap) — "More Narrative" toggles
    # narratives_expanded to swap the sidebar's pill list over to this full
    # set instead of firing a second query for the rest.
    all_categories: list[str] = []
    narratives_expanded: bool = False
    selected_category: str = "All narratives"
    # Drives just the pill's active/blue highlight. Kept separate from
    # selected_category (which drives the actual re-filter/re-sort of up to
    # 8154 coins) so the clicked pill highlights instantly instead of
    # waiting on that heavier computation to finish.
    active_category: str = "All narratives"
    chains: list[str] = []
    all_chains: list[str] = []
    chains_expanded: bool = False
    selected_chain: str = "All chains"
    active_chain: str = "All chains"
    is_loading: bool = True
    is_filtering: bool = False
    page: int = 1
    # Drives just the pagination number's active/blue highlight, same
    # instant-highlight-then-load pattern as active_category above — updated
    # before the sleep so the clicked page number turns blue immediately
    # instead of waiting on the skeleton's artificial delay.
    active_page: int = 1
    page_size: int = 100

    # Search-by-name/ticker across every coin (not just the current page) —
    # search_open toggles the magnifying-glass icon into the input field.
    search_open: bool = False
    search_query: str = ""

    # Header-level global search (separate from the homepage table's own
    # search_query above — this one lives in _header_bar, works from every
    # page, and drives a CMC-style autocomplete dropdown instead of
    # re-filtering a table). global_search_limit caps how many coin matches
    # render before "Show more" is clicked; reset to the default every time
    # the query changes so a new search always starts collapsed.
    global_search_query: str = ""
    global_search_limit: int = 5
    # Recently opened coins from the search dropdown (newest first, max 5),
    # comma-separated cmc_ids in the browser's localStorage so it survives the
    # full page reloads every navigation does. The key is also written by
    # assets/chain_pills.js on a result click (an event handler could be lost
    # to the navigation), and shown when the empty box is focused.
    global_search_history_raw: str = rx.LocalStorage("", name="repace_search_history")
    global_search_focused: bool = False

    # Header profile-pill dropdown (frontend.py::_profile_pill) — holds the
    # dark/light mode toggle now that the header no longer has room for it
    # as a separate always-visible button on every screen size. Click the
    # pill to open, click it again (or click outside — same
    # click-outside-close pattern global search already uses) to close.
    profile_menu_open: bool = False
    # No real auth yet (login form is a dummy): everyone is logged out, so the
    # header pill hides the name/plan text and leads to /login.
    is_logged_in: bool = False
    user_name: str = ""
    user_email: str = ""
    # DB id of the logged-in account; set server-side at login, never from the browser.
    user_id: int = 0
    # "Stay logged in" cookie: a random token whose SHA-256 is stored in user_sessions (30 days).
    session_token: str = rx.Cookie("", name="repace_session", path="/", max_age=30 * 24 * 3600, same_site="strict")

    # Floating-logo chatbot popup (frontend.py::_floating_logo/_chat_widget)
    # — click the floating logo to open, click it again or click the popup's
    # own "x" to close. UI shell only (static demo messages) — no real
    # chatbot backend wired up yet.
    chat_widget_open: bool = False

    # Floating star button's watchlist popup (frontend.py::_watchlist_widget).
    # While open, watchlist_live_loop polls each watched coin's chart
    # exchange every few seconds into watchlist_live_prices ({cmc_id: price}).
    watchlist_popup_open: bool = False
    watchlist_live_prices: dict[int, float] = {}
    _watchlist_live_running: bool = False

    # Price alerts (coin page "Alerts" section) — logged-in accounts only
    # (_login_required); saved in price_alerts (DB) and loaded at login.
    # {str(cmc_id): [{"id", "price", "direction", "display"}]}; checked by
    # start_alert_watch.
    price_alerts: dict[str, list[dict]] = {}
    alert_dialog_open: bool = False
    alert_price_input: str = ""
    alert_error: str = ""
    editing_alert_id: int = 0  # 0 = the dialog creates a new alert
    # Triggered alerts: floating popups (stacked, shown ~1 min, slide in from
    # the top) and the history list shown on /alerts.
    alert_popups: list[dict] = []
    alert_popup_visible: bool = False
    alert_history: list[dict] = []
    _alert_popup_deadline: float = 0.0
    _alert_watch_running: bool = False

    # In-page sort only: reorders the current page's rows, never re-ranks
    # across the full coin list. sort_key is one of the raw numeric fields
    # in each row dict (e.g. "pct_1h_raw"), or "" for the default (market-cap)
    # order. sort_direction cycles "desc" (1st click, biggest -> smallest, top
    # arrow active) -> "asc" (2nd click, smallest -> biggest, bottom arrow
    # active) -> neutral (3rd click, both "", back to default order).
    # Changing page also resets both, per spec.
    sort_key: str = ""
    sort_direction: str = ""

    # Backend-only (not sent to the client): guards live_sync_loop against
    # starting twice for the same session (e.g. on_load firing again).
    _is_live_syncing: bool = False
    # Same guard as _is_live_syncing above, for detail_sync_loop.
    _is_detail_syncing: bool = False
    # Coin page 24h market cap / volume change badges (_change_24h_display),
    # tagged with the cmc_id they were computed for.
    coin_change_24h: dict[str, str] = {}

    # Drives the coin detail page's centered "Copied to clipboard" popup —
    # set true right when the Contract pill is clicked (see coin_detail.py's
    # on_click list, chained after the actual rx.set_clipboard), then flips
    # back after 3s below.
    contract_copied: bool = False

    # Drives the About section's fixed-height/expand-to-read-more toggle
    # (see coin_detail.py's _about_section) — reset in load_coins so
    # navigating from one coin's page to another's doesn't carry over a
    # previous coin's expanded state.
    about_expanded: bool = False

    # Drives the Markets section's CEX/DEX filter tabs (see
    # coin_detail.py's _market_pairs_section) — purely a client-side filter
    # over the already-fetched top-10-CEX + top-10-DEX list, no new fetch.
    # No "All" option (removed per explicit request — CEX and DEX are shown
    # as two separate lists, never combined), so this defaults to "cex".
    # Reset in load_coins for the same reason about_expanded is.
    market_pairs_filter: str = "cex"

    # Current page (1-indexed) within whichever side (CEX/DEX)
    # effective_market_pairs_filter is showing — see market_pairs_total_pages/
    # paged_market_pairs below. Reset to 1 on every filter switch (below) and
    # on load_coins, same reset spirit as market_pairs_filter itself.
    market_pairs_page: int = 1

    @rx.event
    def toggle_about_expanded(self):
        self.about_expanded = not self.about_expanded

    @rx.event
    def set_market_pairs_filter(self, value: str):
        self.market_pairs_filter = value
        self.market_pairs_page = 1

    @rx.event
    def market_pairs_prev_page(self):
        self.market_pairs_page = max(1, self.market_pairs_page - 1)

    @rx.event
    def market_pairs_next_page(self):
        self.market_pairs_page = min(self.market_pairs_total_pages, self.market_pairs_page + 1)

    @rx.event
    def load_coins(self):
        # Per-page-visit resets always run, regardless of the guard below —
        # these are cheap and must never carry over between two different
        # coins' pages (e.g. an expanded About section, or a DEX tab
        # selection) regardless of whether the full universe gets re-fetched
        # this time.
        self.about_expanded = False
        self.market_pairs_filter = "cex"
        self.market_pairs_page = 1

        if self.all_coins:
            # Confirmed live this was the main cause of "every click/page-
            # switch feels slow": this on_load fires on EVERY single
            # navigation (homepage <-> any /coin/[symbol] page, and between
            # different coins), and re-querying + rebuilding all ~8,000
            # coins from scratch (eager-loading categories AND contracts for
            # every one) took ~2 full seconds of *blocking* server time on
            # its own, every single time — before the page could even start
            # rendering. The full universe barely changes within one
            # session (new listings are caught by the next full page
            # visit's on_load anyway, once all_coins has been cleared by a
            # fresh browser session), and individual coins' prices already
            # stay fresh via live_sync_loop/detail_sync_loop — so once
            # loaded, there's nothing this full rebuild would catch that
            # those don't already handle. Skipping the redundant work here
            # is the actual fix; switching from client-side routing to full
            # browser reloads would NOT have helped, since the exact same
            # expensive on_load would still re-run on every fresh page load
            # either way — confirmed by timing the query+build directly.
            return

        self.is_loading = True
        with rx.session() as session:
            coins = session.exec(
                select(Coin)
                .options(selectinload(Coin.categories), selectinload(Coin.contracts))
                .order_by(Coin.cmc_rank)
            ).all()

            rows: list[dict] = []
            narrative_counts: Counter[str] = Counter()
            chain_counts: Counter[str] = Counter()
            for coin in coins:
                narrative_counts.update(category.name for category in coin.categories)
                row = _build_row(coin)
                chain_counts.update([row["main_chain"]])
                rows.append(row)

        self.all_coins = rows
        # Top 20 by number of coins carrying that tag — out of ~600 dynamic
        # CMC categories, this keeps the default filter pill bar to the
        # narratives that actually matter for most coins shown, not an
        # alphabetical cut. all_categories holds every narrative (no cap) so
        # "More Narrative" (see filters.py/narratives_expanded below) can
        # reveal the rest without a second query.
        all_narrative_names = [name for name, _ in narrative_counts.most_common()]
        self.categories = ["All narratives", *all_narrative_names[:20]]
        self.all_categories = ["All narratives", *all_narrative_names]
        # Same split for chains — top 20 by default, all_chains holds the
        # full "most common" ranking for "More Chain" to expand into.
        all_chain_names = [name for name, _ in chain_counts.most_common()]
        self.chains = ["All chains", *all_chain_names[:20]]
        self.all_chains = ["All chains", *all_chain_names]
        self.is_loading = False

    @rx.event
    async def set_category(self, value: str):
        # active_category has no dependent computed vars, so this first
        # flush (pill turns blue + skeleton shows) is instant. The sleep
        # below is what keeps the skeleton visible — re-filtering an
        # in-memory list is itself instant, so without it the second flush
        # (updating selected_category) would follow within a millisecond
        # and the skeleton would never actually be perceptible.
        self.active_category = value
        self.active_page = 1
        self.is_filtering = True
        yield
        await asyncio.sleep(0.25)
        self.selected_category = value
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""
        self.is_filtering = False
        yield CoinState.sync_visible_page

    @rx.event
    async def set_chain(self, value: str):
        # Same instant-highlight-then-refilter pattern as set_category. The
        # two filters combine with AND (see filtered_coins) — narrative +
        # chain together, e.g. "Memes" + "BNB Smart Chain (BEP20)".
        self.active_chain = value
        self.active_page = 1
        self.is_filtering = True
        yield
        await asyncio.sleep(0.25)
        self.selected_chain = value
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""
        self.is_filtering = False
        yield CoinState.sync_visible_page

    @rx.event
    def toggle_narratives_expanded(self):
        # "More Narrative"/"Show less" (filters.py::_more_narratives_pill) —
        # swaps the sidebar's pill list between the default top-20 (categories)
        # and every narrative (all_categories), no re-query either way since
        # both were already computed once in load_coins.
        self.narratives_expanded = not self.narratives_expanded

    @rx.event
    def toggle_chains_expanded(self):
        self.chains_expanded = not self.chains_expanded

    @rx.event
    async def toggle_search(self):
        self.search_open = not self.search_open
        if self.search_open:
            # The desktop input stays permanently mounted (only a CSS class
            # toggles its width/opacity — see coin_table.py's _coin_search
            # docstring), so a static auto_focus prop never refires on
            # reopen. rx.call_script explicitly focuses it by id instead.
            yield rx.call_script("document.getElementById('coin-search-input-field')?.focus()")
            return
        if self.search_query:
            self.active_page = 1
            self.is_filtering = True
            yield
            await asyncio.sleep(0.25)
            self.search_query = ""
            self.page = 1
            self.is_filtering = False
            yield CoinState.sync_visible_page

    @rx.event
    async def set_search_query(self, value: str):
        # search_query updates immediately (keeps the input's own value in
        # sync). The skeleton — not the new, already-filtered rows — is
        # what actually renders until the flush below. Re-filtering an
        # in-memory list is itself instant, so without the artificial
        # delay the skeleton would flash for under a millisecond and never
        # actually be visible; the sleep is what makes the loading state
        # perceptible at all.
        self.search_query = value
        self.active_page = 1
        self.is_filtering = True
        yield
        await asyncio.sleep(0.25)
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""
        self.is_filtering = False
        yield CoinState.sync_visible_page

    @rx.event
    async def next_page(self):
        if self.page < self.total_pages:
            self.active_page = self.page + 1
            self.is_filtering = True
            yield
            await asyncio.sleep(0.25)
            self.page += 1
            self.sort_key = ""
            self.sort_direction = ""
            self.is_filtering = False
            yield CoinState.sync_visible_page

    @rx.event
    async def prev_page(self):
        if self.page > 1:
            self.active_page = self.page - 1
            self.is_filtering = True
            yield
            await asyncio.sleep(0.25)
            self.page -= 1
            self.sort_key = ""
            self.sort_direction = ""
            self.is_filtering = False
            yield CoinState.sync_visible_page

    @rx.event
    async def go_to_page(self, page_str: str):
        page = int(page_str)
        if 1 <= page <= self.total_pages:
            self.active_page = page
            self.is_filtering = True
            yield
            await asyncio.sleep(0.25)
            self.page = page
            self.sort_key = ""
            self.sort_direction = ""
            self.is_filtering = False
            yield CoinState.sync_visible_page

    @rx.event
    async def set_page_size(self, value: str):
        self.active_page = 1
        self.is_filtering = True
        yield
        await asyncio.sleep(0.25)
        self.page_size = int(value)
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""
        self.is_filtering = False
        yield CoinState.sync_visible_page

    @rx.event(background=True)
    async def sync_visible_page(self):
        """One-shot view-driven refresh: re-fetches quotes for just the
        coins on whichever page/filter is on screen right now (called
        immediately after pagination/filter changes; live_sync_loop below
        covers the same page while it stays open, every 60s).
        """
        async with self:
            cmc_ids = [row["cmc_id"] for row in self.sorted_paged_coins]
        if not cmc_ids:
            return
        updated_rows = await asyncio.to_thread(_sync_and_rebuild_rows, cmc_ids)
        async with self:
            self._apply_updates(updated_rows)

    @rx.event(background=True)
    async def live_sync_loop(self):
        """Keeps the global top 100 coins (by market cap, regardless of
        whatever page/filter is on screen) fresh every 60s for as long as
        that browser tab stays open — started once via on_load — plus
        whichever page/filter the session is actually looking at right now,
        if that's a different set (e.g. a user parked on page 3). Top 100
        coins are the ones every session cares about most (Bitcoin, Ethereum,
        etc.), so those stay live even while someone's browsing deeper pages,
        not just whatever happens to be on screen. Rule 4 (API Optimization &
        Cost Control) still holds for the full ~8,000-coin universe (24h
        cadence, sync_hot_listings' top-500/1h cadence); this only ever
        touches <=200 coins, one lightweight quotes/latest call at a time.
        """
        async with self:
            if self._is_live_syncing:
                return
            self._is_live_syncing = True

        from frontend.frontend import app as reflex_app

        try:
            while True:
                # Sync runs before the connection check (not after) — right
                # after on_load fires, the websocket handshake that
                # registers this client_token in token_to_sid may not have
                # completed yet, and checking first would break out before
                # ever syncing anything.
                async with self:
                    top_100_ids = [
                        row["cmc_id"]
                        for row in sorted(
                            (self._row_with_overrides(r) for r in self.all_coins),
                            key=lambda r: r["market_cap_usd"],
                            reverse=True,
                        )[:100]
                    ]
                    visible_ids = [row["cmc_id"] for row in self.sorted_paged_coins]
                    # dict.fromkeys dedupes while preserving order — avoids a
                    # duplicate CMC API lookup for coins in both sets (the
                    # common case: page 1 IS the top 100).
                    cmc_ids = list(dict.fromkeys([*top_100_ids, *visible_ids]))
                if cmc_ids:
                    updated_rows = await asyncio.to_thread(_sync_and_rebuild_rows, cmc_ids)
                    async with self:
                        self._apply_updates(updated_rows)
                await asyncio.sleep(60)
                if self.router.session.client_token not in reflex_app.event_namespace.token_to_sid:
                    break
        finally:
            async with self:
                self._is_live_syncing = False

    def _row_with_overrides(self, row: dict) -> dict:
        """Merges row (from the rarely-changing all_coins) with whatever's
        currently in coin_overrides for its cmc_id, if anything — the read
        side of the all_coins/coin_overrides split. Every computed var that
        exposes rows to a component (filtered_coins, selected_coin) applies
        this before returning, so overrides stay invisible from the
        frontend's perspective — it's still "just the coin's current
        data," merged server-side on every read rather than kept fresh by
        reassigning the giant list itself.
        """
        override = self.coin_overrides.get(row["cmc_id"])
        return {**row, **override} if override else row

    @rx.event
    async def toggle_watchlist(self, cmc_id: int):
        """Star icon handler, called from both the coin-detail page (add/
        remove the currently viewed coin) and the /watchlist page's own
        table rows (always a remove there, since every row shown is
        already-watchlisted). Reassigns the whole list rather than
        mutating in place, matching this class's existing
        coin_overrides convention. When logged in the change is also saved
        to the database under this account (user_watchlist); logged out it
        only lives in this browser session.
        """
        if cmc_id in self.watchlist_ids:
            self.watchlist_ids = [i for i in self.watchlist_ids if i != cmc_id]
            watched = False
        else:
            self.watchlist_ids = [*self.watchlist_ids, cmc_id]
            watched = True
        if self.user_id:
            uid = self.user_id
            if _ROOT_FOR_APP not in sys.path:
                sys.path.insert(0, _ROOT_FOR_APP)
            from app.services import watchlist_service

            await asyncio.to_thread(watchlist_service.set_watched, uid, int(cmc_id), watched)

    @rx.var(cache=True)
    def watchlist_count(self) -> int:
        return len(self.watchlist_ids)

    @rx.var(cache=True)
    def has_watchlist_coins(self) -> bool:
        return self.watchlist_count > 0

    @rx.var(cache=True)
    def watchlist_coins(self) -> list[dict]:
        """The /watchlist page's own row list — same _row_with_overrides
        merge every other display-facing computed var uses (so a live-
        synced price shows up here too), filtered to watchlist_ids. Rank is
        each coin's real global market-cap position across every coin (same
        convention filtered_coins' own search branch uses), not a 1..N
        renumbering within just this watched subset.
        """
        watched = set(self.watchlist_ids)
        if not watched:
            return []
        full_rows = [self._row_with_overrides(r) for r in self.all_coins]
        global_rank_by_id = {
            row["cmc_id"]: i
            for i, row in enumerate(
                sorted(full_rows, key=lambda r: r["market_cap_usd"], reverse=True),
                start=1,
            )
        }
        rows = [
            {**row, "rank": global_rank_by_id[row["cmc_id"]]}
            for row in full_rows
            if row["cmc_id"] in watched
        ]
        return sorted(rows, key=lambda r: r["market_cap_usd"], reverse=True)

    def _merged_row(self, cmc_id: int) -> dict | None:
        """Finds cmc_id's row in all_coins and merges in any existing
        override — used by the one-shot background refreshers below to
        read a coin's current values (e.g. primary_narrative, price_raw)
        before computing a new patch, without needing all_coins itself to
        ever carry live data. A linear scan over all_coins, but only ever
        called once per refresh (not per-render), so this is negligible
        next to the cost it replaces (a full list reassignment + resend).
        """
        base = next((r for r in self.all_coins if r["cmc_id"] == cmc_id), None)
        return self._row_with_overrides(base) if base is not None else None

    def _apply_updates(self, updated_rows: dict[int, dict]) -> None:
        """Used by sync_visible_page/live_sync_loop/detail_sync_loop — each
        already-fresh row from _sync_and_rebuild_rows becomes this coin's
        entire override (a full replacement is still just a merge: any
        stale prior override fields get superseded by the fresh row's own
        values for the same keys).
        """
        if not updated_rows:
            return
        self.coin_overrides = {
            **self.coin_overrides,
            **{
                cmc_id: {**self.coin_overrides.get(cmc_id, {}), **fresh_row}
                for cmc_id, fresh_row in updated_rows.items()
            },
        }

    @rx.event
    def go_to_coin(self, symbol: str):
        return rx.call_script(f"window.location.assign({json.dumps('/coin/' + symbol.lower())})")

    @rx.event
    def set_global_search_query(self, value: str):
        self.global_search_query = value
        self.global_search_limit = 5

    @rx.event
    def focus_global_search(self):
        self.global_search_focused = True

    @rx.event
    def expand_global_search_results(self):
        self.global_search_limit += 10

    @rx.event
    def go_to_coin_from_search(self, symbol: str):
        self.global_search_query = ""
        self.global_search_limit = 5
        return rx.call_script(f"window.location.assign({json.dumps('/coin/' + symbol.lower())})")

    @rx.event
    def reset_global_search(self):
        """Fired by a real click outside the header search's own container
        (see assets/chain_pills.js's global-search-container click-outside
        listener, which clicks a hidden trigger element bound to this
        handler). An on_blur-based close was tried first but raced "Show
        more"/a result click: blur fires before the click's own event
        finishes dispatching, so a delayed clear on blur alone would wipe
        the query — and close the dropdown — out from under a click that
        was never meant to leave it. A real outside click has no such race.
        """
        self.global_search_query = ""
        self.global_search_limit = 5
        self.global_search_focused = False

    @rx.event
    def profile_pill_click(self):
        if self.is_logged_in:
            self.profile_menu_open = not self.profile_menu_open
            return
        # Logged out: read the viewport width. lg+ (1280px) goes straight to
        # /login; below that the dropdown opens (it holds the nav links too).
        return rx.call_script("window.innerWidth", callback=CoinState.profile_pill_click_width)

    @rx.event
    async def restore_session(self):
        """Runs first on every page load: if the browser sent a valid 'stay logged in'
        cookie, log this browser session back in (name, account id and saved watchlist)."""
        # Search results are real links now, so the typed query isn't cleared by a
        # handler on click; drop it on the next page load instead.
        if self.global_search_query or self.global_search_focused:
            self.global_search_query = ""
            self.global_search_limit = 5
            self.global_search_focused = False
        if self.is_logged_in or not self.session_token:
            if self.is_logged_in and self.router.url.path.rstrip("/") in ("/login", "/signup"):
                return rx.call_script("window.location.assign('/')")
            return
        if _ROOT_FOR_APP not in sys.path:
            sys.path.insert(0, _ROOT_FOR_APP)
        from app.services import auth_service, watchlist_service

        result = await asyncio.to_thread(auth_service.resume_session, self.session_token)
        if not result.ok:
            self.session_token = ""  # expired or unknown: forget it
            return
        self.is_logged_in = True
        self.user_id = result.user_id
        self.user_name = result.user_name
        self.user_email = result.user_email
        self.watchlist_ids = await asyncio.to_thread(watchlist_service.get_watchlist_ids, result.user_id)
        await self._load_user_alerts()
        if self.router.url.path.rstrip("/") in ("/login", "/signup"):
            return rx.call_script("window.location.assign('/')")

    @rx.event
    async def logout(self):
        token = self.session_token
        if token:
            if _ROOT_FOR_APP not in sys.path:
                sys.path.insert(0, _ROOT_FOR_APP)
            from app.services import auth_service

            await asyncio.to_thread(auth_service.delete_session, token)
        self.session_token = ""
        self.is_logged_in = False
        self.user_name = ""
        self.user_email = ""
        self.user_id = 0
        self.watchlist_ids = []
        self.price_alerts = {}
        self.alert_history = []
        self.alert_popups = []
        self.alert_popup_visible = False
        self.profile_menu_open = False
        return rx.call_script("window.location.assign('/')")

    @rx.event
    def profile_pill_click_width(self, width: int):
        if width >= 1280:
            return rx.call_script("window.location.assign('/login')")
        self.profile_menu_open = not self.profile_menu_open

    @rx.event
    def toggle_profile_menu(self):
        self.profile_menu_open = not self.profile_menu_open

    @rx.event
    def close_profile_menu(self):
        # Fired by a real click outside .profile-pill-trigger (same
        # delegated click-outside JS pattern as global search's
        # #global-search-close-trigger — see assets/chain_pills.js).
        self.profile_menu_open = False

    @rx.event
    def toggle_chat_widget(self):
        # Bound to the floating logo's own on_click — a 2nd click on the
        # logo closes it again, per explicit request.
        self.chat_widget_open = not self.chat_widget_open
        if self.chat_widget_open:
            self.watchlist_popup_open = False  # the two popups share a spot

    @rx.event
    @_login_required
    async def open_alert_dialog(self):
        # Prefilled with the coin's current price.
        price = float((self.selected_coin or {}).get("price_raw") or 0)
        self.alert_price_input = _plain_price(price) if price > 0 else ""
        self.editing_alert_id = 0
        self.alert_error = ""
        self.alert_dialog_open = True

    @rx.event
    @_login_required
    async def open_edit_alert(self, alert_id: int):
        alert = next((a for a in self.coin_alerts if a["id"] == alert_id), None)
        if alert is None:
            return
        self.alert_price_input = _plain_price(alert["price"])
        self.editing_alert_id = alert_id
        self.alert_error = ""
        self.alert_dialog_open = True

    @rx.var
    def is_editing_alert(self) -> bool:
        return self.editing_alert_id != 0

    @rx.event
    def set_alert_dialog_open(self, is_open: bool):
        self.alert_dialog_open = is_open

    @rx.event
    def set_alert_price_input(self, value: str):
        self.alert_price_input = value
        self.alert_error = ""

    @rx.event
    @_login_required
    async def create_alert(self):
        coin = self.selected_coin
        if not coin:
            return
        raw = self.alert_price_input.strip().replace("$", "").replace(",", "")
        try:
            target = float(raw)
        except ValueError:
            self.alert_error = "Enter a valid price, e.g. 0.25"
            return
        if not math.isfinite(target) or target <= 0 or target >= 1e12:
            self.alert_error = "Price must be greater than 0."
            return
        key = str(coin["cmc_id"])
        editing = self.editing_alert_id
        existing = [a for a in self.price_alerts.get(key, []) if a["id"] != editing]
        if not editing and len(existing) >= 10:
            self.alert_error = "You can have up to 10 alerts per coin."
            return
        current = float(coin.get("price_raw") or 0)
        direction = "below" if current > 0 and target < current else "above"
        if any(a["price"] == target for a in existing):
            self.alert_error = "You already have an alert at this price."
            return
        if _ROOT_FOR_APP not in sys.path:
            sys.path.insert(0, _ROOT_FOR_APP)
        from app.services import alert_service

        if editing:
            await asyncio.to_thread(alert_service.update_alert, self.user_id, editing, target, direction)
            alert_id = editing
        else:
            alert_id = await asyncio.to_thread(
                alert_service.add_alert, self.user_id, int(coin["cmc_id"]), coin["name"], coin["symbol"], direction, target
            )
        alert = {"id": alert_id, "price": target, "direction": direction, "display": _fmt_usd(target)}
        current_list = self.price_alerts.get(key, [])
        if editing:
            new_list = [alert if a["id"] == editing else a for a in current_list]
        else:
            new_list = [*current_list, alert]
        self.price_alerts = {**self.price_alerts, key: new_list}
        self.editing_alert_id = 0
        self.alert_dialog_open = False

    @rx.event
    @_login_required
    async def delete_alert(self, alert_id: int):
        coin = self.selected_coin
        if not coin:
            return
        key = str(coin["cmc_id"])
        self.price_alerts = {
            **self.price_alerts,
            key: [a for a in self.price_alerts.get(key, []) if a["id"] != alert_id],
        }
        if _ROOT_FOR_APP not in sys.path:
            sys.path.insert(0, _ROOT_FOR_APP)
        from app.services import alert_service

        await asyncio.to_thread(alert_service.delete_alert, self.user_id, alert_id)

    async def _load_user_alerts(self) -> None:
        """Logged-in only: replaces the session's alerts with this account's saved active ones."""
        if _ROOT_FOR_APP not in sys.path:
            sys.path.insert(0, _ROOT_FOR_APP)
        from app.services import alert_service

        rows = await asyncio.to_thread(alert_service.list_active, self.user_id)
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            grouped.setdefault(str(r["cmc_id"]), []).append(
                {"id": r["id"], "price": r["price"], "direction": r["direction"], "display": _fmt_usd(r["price"])}
            )
        self.price_alerts = grouped

    @rx.event
    async def require_login(self):
        """Page guard (on_load, after restore_session): logged-out visitors go to /login."""
        if not (self.is_logged_in and self.user_id):
            return rx.call_script("window.location.assign('/login')")

    @rx.event
    @_login_required
    async def load_alert_history(self):
        """/alerts on_load: this account's saved history of triggered alerts."""
        if _ROOT_FOR_APP not in sys.path:
            sys.path.insert(0, _ROOT_FOR_APP)
        from app.services import alert_service

        rows = await asyncio.to_thread(alert_service.list_history, self.user_id)
        self.alert_history = [
            {
                "id": r["id"],
                "name": r["name"],
                "symbol": r["symbol"],
                "icon_url": f"https://s2.coinmarketcap.com/static/img/coins/64x64/{r['cmc_id']}.png",
                "direction": r["direction"],
                "target_display": _fmt_usd(r["target"]),
                "price_display": _fmt_usd(r["price"]),
                "time_display": _fmt_alert_time(r["at"]),
            }
            for r in rows
        ]

    @rx.event
    def dismiss_alert_popup(self, alert_id: int):
        self.alert_popups = [p for p in self.alert_popups if p["id"] != alert_id]
        if not self.alert_popups:
            self.alert_popup_visible = False

    @rx.event(background=True)
    async def start_alert_watch(self):
        """Every 4s checks this session's active alerts against live exchange prices
        (frontend/live_prices.py; falls back to the synced price) and, when one is hit,
        stacks a popup, records it in the history (and in the database when logged in) and
        shows the popup for a minute. Runs for as long as the tab stays open."""
        async with self:
            if self._alert_watch_running or not self.user_id:
                return  # alerts are for logged-in accounts only
            self._alert_watch_running = True

        from frontend.frontend import app as reflex_app
        from frontend.live_prices import fetch_live_prices

        try:
            while True:
                items: list[dict] = []
                async with self:
                    if not self.user_id:
                        break  # logged out
                    for key, alerts in self.price_alerts.items():
                        row = self._merged_row(int(key)) if alerts else None
                        if row:
                            items.append({
                                "cmc_id": row["cmc_id"], "symbol": row["symbol"],
                                "chart_symbol": _resolve_chart_symbol(row["symbol"], row) or "",
                                "ref_price": row.get("price_raw", 0),
                            })
                live: dict[int, float] = {}
                if items:
                    live = await asyncio.to_thread(fetch_live_prices, items)
                triggered: list[tuple[int, int, float]] = []
                spoken: dict[int, str] = {}
                async with self:
                    now_ts = time.time()
                    new_alerts = dict(self.price_alerts)
                    popups = list(self.alert_popups)
                    history = list(self.alert_history)
                    for key, alerts in self.price_alerts.items():
                        row = self._merged_row(int(key)) if alerts else None
                        if not row:
                            continue
                        price = live.get(row["cmc_id"]) or float(row.get("price_raw") or 0)
                        if price <= 0:
                            continue
                        remaining = []
                        for a in alerts:
                            hit = price >= a["price"] if a["direction"] == "above" else price <= a["price"]
                            if not hit:
                                remaining.append(a)
                                continue
                            entry = {
                                "id": a["id"], "name": row["name"], "symbol": row["symbol"],
                                "icon_url": row["icon_url"], "direction": a["direction"],
                                "target_display": a["display"], "price_display": _fmt_usd(price),
                                "time_display": _fmt_alert_time(None),
                            }
                            popups.append(entry)
                            history.insert(0, entry)
                            triggered.append((self.user_id, a["id"], price))
                            spoken[a["id"]] = (
                                f"{row['name']} ({row['symbol']}) crossed {a['direction']} {a['display']}, "
                                f"now at {_fmt_usd(price)}"
                            )
                        new_alerts[key] = remaining
                    if triggered:
                        self.price_alerts = new_alerts
                        self.alert_popups = popups[-5:]
                        self.alert_history = history[:200]
                        self.alert_popup_visible = True
                        self._alert_popup_deadline = now_ts + 60
                    elif self.alert_popup_visible and now_ts > self._alert_popup_deadline:
                        self.alert_popup_visible = False
                if triggered:
                    if _ROOT_FOR_APP not in sys.path:
                        sys.path.insert(0, _ROOT_FOR_APP)
                    from app.services import alert_service

                    for uid, alert_id, price in triggered:
                        if await asyncio.to_thread(alert_service.mark_triggered, uid, alert_id, price):
                            yield CoinState.speak_alert(spoken[alert_id])
                await asyncio.sleep(4)
                async with self:
                    # after the slide-out transition, drop the finished popups
                    if not self.alert_popup_visible and self.alert_popups:
                        self.alert_popups = []
                if self.router.session.client_token not in reflex_app.event_namespace.token_to_sid:
                    break
        finally:
            async with self:
                self._alert_watch_running = False

    @rx.event(background=True)
    async def speak_alert(self, event: str):
        """Gemini quip + voice for a triggered alert, played by assets/alert_voice.js."""
        if _ROOT_FOR_APP not in sys.path:
            sys.path.insert(0, _ROOT_FOR_APP)
        from app.services.alert_voice_service import generate_alert_voice

        voice = await asyncio.to_thread(generate_alert_voice, event)
        if voice:
            yield rx.call_script(
                f"window.repacePlayAlertVoice?.({json.dumps(voice['audio_b64'])}, {int(voice['sample_rate'])})"
            )

    @rx.var(cache=True)
    def coin_alerts(self) -> list[dict]:
        coin = self.selected_coin
        return self.price_alerts.get(str(coin["cmc_id"]), []) if coin else []

    @rx.var(cache=True)
    def active_alerts_all(self) -> list[dict]:
        """Every active alert of this account across all coins (for /alerts),
        with the coin's name/icon and current price."""
        out: list[dict] = []
        for key, alerts in self.price_alerts.items():
            row = next((r for r in self.all_coins if str(r["cmc_id"]) == key), None)
            if row is None:
                continue
            row = self._row_with_overrides(row)
            for a in alerts:
                out.append({
                    "id": a["id"], "cmc_id": row["cmc_id"], "name": row["name"], "symbol": row["symbol"],
                    "icon_url": row["icon_url"], "direction": a["direction"], "display": a["display"],
                    "current_display": row["price_display"], "coin_url": f"/coin/{row['symbol'].lower()}",
                })
        return sorted(out, key=lambda x: (x["symbol"], x["id"]))

    @rx.event
    @_login_required
    async def delete_alert_by_id(self, cmc_id: int, alert_id: int):
        """Delete from the /alerts page (not tied to the selected coin)."""
        key = str(cmc_id)
        self.price_alerts = {
            **self.price_alerts,
            key: [a for a in self.price_alerts.get(key, []) if a["id"] != alert_id],
        }
        if _ROOT_FOR_APP not in sys.path:
            sys.path.insert(0, _ROOT_FOR_APP)
        from app.services import alert_service

        await asyncio.to_thread(alert_service.delete_alert, self.user_id, alert_id)

    @rx.var(cache=True)
    def has_coin_alerts(self) -> bool:
        return len(self.coin_alerts) > 0

    @rx.event
    def toggle_watchlist_popup(self):
        self.watchlist_popup_open = not self.watchlist_popup_open
        if self.watchlist_popup_open:
            self.chat_widget_open = False
            return CoinState.watchlist_live_loop

    @rx.event
    def close_watchlist_popup(self):
        self.watchlist_popup_open = False

    @rx.event(background=True)
    async def watchlist_live_loop(self):
        """While the watchlist popup is open, refreshes each watched coin's
        price from its chart exchange every 3s (frontend/live_prices.py)."""
        async with self:
            if self._watchlist_live_running:
                return
            self._watchlist_live_running = True

        from frontend.frontend import app as reflex_app
        from frontend.live_prices import fetch_live_prices

        try:
            while True:
                async with self:
                    if not self.watchlist_popup_open:
                        break
                    items = [
                        {
                            "cmc_id": r["cmc_id"],
                            "symbol": r["symbol"],
                            "chart_symbol": _resolve_chart_symbol(r["symbol"], r) or "",
                            "ref_price": r.get("price_raw", 0),
                        }
                        for r in self.watchlist_coins[:30]
                    ]
                if items:
                    prices = await asyncio.to_thread(fetch_live_prices, items)
                    if prices:
                        async with self:
                            self.watchlist_live_prices = {**self.watchlist_live_prices, **prices}
                await asyncio.sleep(3)
                if self.router.session.client_token not in reflex_app.event_namespace.token_to_sid:
                    break
        finally:
            async with self:
                self._watchlist_live_running = False

    @rx.var(cache=True)
    def watchlist_popup_rows(self) -> list[dict]:
        """watchlist_coins with price_display replaced by the live exchange
        price once one has arrived (formatted through _fmt_usd)."""
        live = self.watchlist_live_prices
        return [
            {**r, "price_display": _fmt_usd(live[r["cmc_id"]])} if r["cmc_id"] in live else r
            for r in self.watchlist_coins
        ]

    @rx.event
    def close_chat_widget(self):
        # Bound to the popup's own "x" icon.
        self.chat_widget_open = False

    @rx.event(background=True)
    async def show_copied_toast(self):
        """Shows the centered "Copied to clipboard" popup for exactly 3s.
        Chained after rx.set_clipboard on the Contract pill's on_click (see
        coin_detail.py) — that copy itself is a client-only special event,
        so this is what actually confirms it happened.
        """
        async with self:
            self.contract_copied = True
        await asyncio.sleep(3)
        async with self:
            self.contract_copied = False

    @rx.var(cache=True)
    def selected_coin(self) -> dict:
        """Looks up the coin for the current /coin/[symbol] route straight
        out of the already-cached all_coins list — no extra DB query needed
        since load_coins (shared on_load with the homepage) already loaded
        the full universe.

        `self.symbol` is not declared anywhere on this class — Reflex
        auto-injects it as a computed var on the root State once
        app.add_page registers the "/coin/[symbol]" dynamic route (see
        BaseState.setup_dynamic_args), the same mechanism the framework
        docs describe for a `[pid]`-style route.

        Tickers aren't unique on CMC — plenty of low-cap/scam tokens reuse a
        popular symbol — so ties are broken by market cap. Someone visiting
        "/coin/eth" almost always means Ethereum, not an obscure same-ticker
        micro-cap.
        """
        symbol = self.symbol.strip().lower()
        if not symbol:
            return {}
        matches = [
            self._row_with_overrides(row)
            for row in self.all_coins
            if row["symbol"].lower() == symbol
        ]
        if not matches:
            return {}
        return max(matches, key=lambda r: r["market_cap_usd"])

    def _similar_coin_rows(self) -> list[dict]:
        """Every coin with the same use case as the open coin (its peer
        group — e.g. SAND -> MANA, WILD, ATLAS…), largest market cap first.
        Coins without a peer group fall back to sharing its CMC narrative tag."""
        coin = self.selected_coin
        if not coin:
            return []
        group = coin.get("peer_group") or ""
        narrative = coin.get("primary_narrative") or ""
        if group:
            match = lambda r: r.get("peer_group") == group  # noqa: E731
        elif narrative:
            match = lambda r: r.get("primary_narrative") == narrative  # noqa: E731
        else:
            return []
        peers = [
            self._row_with_overrides(r)
            for r in self.all_coins
            if r["cmc_id"] != coin["cmc_id"] and (r.get("market_cap_usd") or 0) > 0 and match(r)
        ]
        peers.sort(key=lambda r: r["market_cap_usd"], reverse=True)
        return peers

    @rx.var(cache=True)
    def similar_coins(self) -> list[dict]:
        """The top 10 for the coin page's Similar Coins slider."""
        return self._similar_coin_rows()[:10]

    @rx.var(cache=True)
    def all_similar_coins(self) -> list[dict]:
        """All of them, for the /coin/[symbol]/similar page."""
        return self._similar_coin_rows()

    @rx.var(cache=True)
    def similar_coins_count(self) -> int:
        return len(self._similar_coin_rows())

    @rx.var(cache=True)
    def similar_page_title(self) -> str:
        name = self.selected_coin.get("name")
        return f"Repace — {name} Similar Coins" if name else "Repace — Similar Coins"

    @rx.var(cache=True)
    def has_similar_coins(self) -> bool:
        return len(self.similar_coins) > 0

    @rx.var(cache=True)
    def selected_coin_found(self) -> bool:
        return bool(self.selected_coin)

    @rx.var(cache=True)
    def page_title(self) -> str:
        """Drives the browser tab / meta title for /coin/[symbol] (see
        frontend.py's app.add_page) — the coin's real name (e.g. "Repace —
        Fartcoin"), not its ticker, per explicit request. Falls back to the
        old static title before all_coins has loaded (selected_coin is {}
        for the first render, since load_coins hasn't populated it yet).
        """
        name = self.selected_coin.get("name")
        return f"Repace — {name}" if name else "Repace — Coin Detail"

    @rx.var(cache=True)
    def current_nav_path(self) -> str:
        """Drives the header nav links' active-color highlight
        (frontend.py::_nav_links) — the route the visitor is actually on,
        so the matching link (News/Narrative/Chains/Tools) stays visibly
        highlighted after navigating there, not just for the instant of the
        click. router.url.path (not the deprecated router.page.path) is the
        actual resolved browser path — confirmed live it carries a trailing
        slash for these static routes (e.g. "/narrative/") even though
        their own registered route and each nav link's `href` don't
        ("/narrative"), so that trailing slash is stripped here rather than
        on every comparison site.
        """
        return self.router.url.path.rstrip("/") or "/"

    @rx.var(cache=True)
    def effective_market_pairs_filter(self) -> str:
        """market_pairs_filter, auto-corrected when the selected tab's side
        has no real listings but the other side does — e.g. a coin with
        zero real top-15 CEX listings but real DEX pairs (or vice versa)
        now auto-shows whichever side actually has data instead of
        defaulting to an empty CEX table (market_pairs_filter's own
        hardcoded "cex" default, reset on every load_coins). Falls back to
        the raw filter once the viewer has explicitly picked a tab that
        does have rows, or when both/neither side has data.
        """
        pairs = self.selected_coin.get("market_pairs", [])
        has_cex = any(not p["is_dex"] for p in pairs)
        has_dex = any(p["is_dex"] for p in pairs)
        if self.market_pairs_filter == "cex" and not has_cex and has_dex:
            return "dex"
        if self.market_pairs_filter == "dex" and not has_dex and has_cex:
            return "cex"
        return self.market_pairs_filter

    @rx.var(cache=True)
    def filtered_market_pairs(self) -> list[dict]:
        """selected_coin's market_pairs, narrowed by
        effective_market_pairs_filter — purely in-memory (the full
        top-10-CEX + top-10-DEX list is already fetched), same instant-
        filter spirit as filtered_coins. Only "cex"/"dex" are valid values
        (no "all" — see market_pairs_filter), so anything else falls back
        to the CEX list.
        """
        pairs = self.selected_coin.get("market_pairs", [])
        if self.effective_market_pairs_filter == "dex":
            return [p for p in pairs if p["is_dex"]]
        return [p for p in pairs if not p["is_dex"]]

    _MARKET_PAIRS_PAGE_SIZE = 10

    @rx.var(cache=True)
    def market_pairs_total_pages(self) -> int:
        """At most 2 pages in practice (each side is already capped to 15
        real rows — see market_pairs_service.py), but computed generically
        rather than hardcoded in case that cap ever changes.
        """
        total = len(self.filtered_market_pairs)
        return max(1, -(-total // self._MARKET_PAIRS_PAGE_SIZE))

    @rx.var(cache=True)
    def paged_market_pairs(self) -> list[dict]:
        """filtered_market_pairs, sliced to the current
        market_pairs_page's 10 rows — clamps the page itself (rather than
        just the slice) so switching from a longer DEX list to a shorter
        CEX list on page 2 doesn't silently show an empty table; the "#"
        column (see _market_pair_row) reads this dict's own "rank" field
        instead of rx.foreach's per-page index, so numbering continues
        across pages (e.g. page 2 starts at #11) instead of restarting at
        #1 every page.
        """
        pairs = self.filtered_market_pairs
        page = max(1, min(self.market_pairs_page, self.market_pairs_total_pages))
        start = (page - 1) * self._MARKET_PAIRS_PAGE_SIZE
        return [
            {**p, "rank": start + i + 1}
            for i, p in enumerate(pairs[start : start + self._MARKET_PAIRS_PAGE_SIZE])
        ]

    @rx.event(background=True)
    async def detail_sync_loop(self):
        """Keeps just the single coin shown on this /coin/[symbol] page
        fresh every 60s for as long as the tab stays open — same sync
        primitive as live_sync_loop (rule 4: cheap, targeted quotes/latest
        calls only), just scoped to the one coin being viewed instead of the
        homepage's top-100/visible-page set.
        """
        async with self:
            if self._is_detail_syncing:
                return
            self._is_detail_syncing = True

        from frontend.frontend import app as reflex_app

        try:
            while True:
                async with self:
                    cmc_id = self.selected_coin.get("cmc_id")
                if cmc_id:
                    updated_rows = await asyncio.to_thread(_sync_and_rebuild_rows, [cmc_id])
                    async with self:
                        self._apply_updates(updated_rows)
                    await self._refresh_change_24h()
                await asyncio.sleep(60)
                async with self:
                    still_connected = (
                        self.router.session.client_token in reflex_app.event_namespace.token_to_sid
                    )
                if not still_connected:
                    break
        finally:
            async with self:
                self._is_detail_syncing = False

    async def _refresh_change_24h(self) -> None:
        """Recomputes the 24h market cap / volume badges from the coin's
        current (live, 60s-synced) values. Called from background events."""
        async with self:
            coin = self.selected_coin
            cmc_id = coin.get("cmc_id")
            mcap, vol = coin.get("market_cap_usd"), coin.get("volume_raw")
        if not cmc_id:
            return
        try:
            display = await asyncio.to_thread(_change_24h_display, cmc_id, mcap, vol)
        except Exception:  # noqa: BLE001 - badges are optional; never break the page
            return
        async with self:
            self.coin_change_24h = display

    @rx.event(background=True)
    async def refresh_change_24h(self):
        """One-shot on page load, so the badges show without waiting for the
        detail loop's first tick."""
        await self._refresh_change_24h()

    @rx.var
    def change_24h_view(self) -> dict[str, str]:
        """coin_change_24h, but only when it belongs to the coin on screen."""
        coin_id = str(self.selected_coin.get("cmc_id", ""))
        if self.coin_change_24h.get("cmc_id") != coin_id:
            return {"mcap_has": "", "mcap_text": "", "mcap_color": "", "mcap_title": "",
                    "vol_has": "", "vol_text": "", "vol_color": "", "vol_title": ""}
        return self.coin_change_24h

    @rx.event(background=True)
    async def refresh_coin_description(self):
        """One-shot, on-demand upgrade of this coin's About-section text —
        fired once per page view (see frontend.py's /coin/[symbol] on_load).
        Almost always a fast no-op: both of _fetch_better_description's steps
        (coingecko_service.upgrade_description, description_ai_service.
        generate_description_from_sources) only ever do real work once per
        coin, ever. The AI-inference step grounds itself in the coin's own
        website text — the "and/or already-cached X posts" half of that
        grounding is permanently unavailable now that the X-scraping backend
        has been removed (coin.cached_tweets is always empty). Still worth
        running: website-text-only grounding is a real improvement over
        boilerplate on its own, and every later visitor benefits from
        whichever description that attempt produced.
        """
        symbol = self.symbol.strip()
        if not symbol:
            return
        result = await asyncio.to_thread(_fetch_better_description, symbol)
        if result is None:
            return
        cmc_id, description = result
        async with self:
            self.coin_overrides = {
                **self.coin_overrides,
                cmc_id: {
                    **self.coin_overrides.get(cmc_id, {}),
                    "description": description,
                    "has_description": True,
                    "description_tokens": _tokenize_highlights(description),
                },
            }

    @rx.event(background=True)
    async def refresh_business_summary(self):
        """One-shot, on-demand refresh of this coin's AI business-model
        summary — fired once per page view (see frontend.py's
        /coin/[symbol] on_load), same pattern as refresh_coin_description
        above. Usually a fast no-op: business_summary_service only
        regenerates once per settings.business_summary_ttl_days (60d
        default), or immediately skips if OPENROUTER_API_KEY isn't set.
        """
        symbol = self.symbol.strip()
        if not symbol:
            return
        result = await asyncio.to_thread(_fetch_business_summary, symbol)
        if result is None:
            return
        cmc_id, summary, model, category = result
        async with self:
            base = self._merged_row(cmc_id)
            primary_narrative = base["primary_narrative"] if base else ""
            self.coin_overrides = {
                **self.coin_overrides,
                cmc_id: {
                    **self.coin_overrides.get(cmc_id, {}),
                    "business_summary": summary,
                    "has_business_summary": True,
                    "business_summary_sections": _parse_business_summary_sections(summary),
                    "business_summary_model_badge": _format_model_badge(model or ""),
                    "business_model_category": category,
                    "has_business_model_category": bool(category),
                    # Real AI category now overrides whatever narrative-tag
                    # fallback category_badge_display was showing (see
                    # _build_row) — falls back again to that same
                    # already-computed narrative if this generation didn't
                    # produce one.
                    "category_badge_display": _category_badge(category, primary_narrative),
                    "has_category_badge_display": bool(_category_badge(category, primary_narrative)),
                },
            }

    @rx.event(background=True)
    async def refresh_market_pairs(self):
        """One-shot, on-demand refresh of this coin's Markets section — fired
        once per page view (see frontend.py's /coin/[symbol] on_load), same
        pattern as refresh_business_summary above. Usually a fast no-op:
        market_pairs_service only re-hits CoinGecko once per settings.
        market_pairs_cache_ttl_hours (1h default).
        """
        symbol = self.symbol.strip()
        if not symbol:
            return
        result = await asyncio.to_thread(_fetch_market_pairs, symbol)
        if result is None:
            return
        cmc_id, pairs = result
        formatted = _format_market_pairs(pairs)
        async with self:
            base = self._merged_row(cmc_id)
            price_raw = base["price_raw"] if base else 0.0
            self.coin_overrides = {
                **self.coin_overrides,
                cmc_id: {
                    **self.coin_overrides.get(cmc_id, {}),
                    "market_pairs": formatted,
                    "has_market_pairs": bool(formatted),
                    "market_pairs_fetched": True,
                    # Recomputes price_display now that real pairs exist —
                    # see _price_display_with_fallback. Only actually
                    # changes anything for a coin whose canonical CMC price
                    # was zero/missing at the time _build_row first ran
                    # (this fetch hadn't completed yet); a coin with a real
                    # CMC price is untouched (price_usd truthy short-
                    # circuits the fallback).
                    "price_display": _price_display_with_fallback(price_raw, pairs),
                },
            }

    @rx.event(background=True)
    async def refresh_tradingview_dex_symbol(self):
        """One-shot, on-demand last-resort chart-symbol lookup — fired once
        per page view (see frontend.py's /coin/[symbol] on_load), same
        pattern as refresh_market_pairs above. Almost always a fast no-op:
        tradingview_symbol_service skips its own external call entirely
        whenever this coin already has a real CEX pair (the vastly more
        common case — this only ever does real work for a coin like zKML
        with zero CEX listings anywhere).
        """
        symbol = self.symbol.strip()
        if not symbol:
            return
        result = await asyncio.to_thread(_fetch_tradingview_dex_symbol, symbol)
        if result is None:
            return
        cmc_id, dex_symbol = result
        async with self:
            self.coin_overrides = {
                **self.coin_overrides,
                cmc_id: {
                    **self.coin_overrides.get(cmc_id, {}),
                    "tradingview_dex_symbol": dex_symbol or "",
                    "tradingview_dex_symbol_fetched": True,
                },
            }

    @rx.event(background=True)
    async def refresh_defillama_unlocks_slug(self):
        """One-shot, on-demand DeFiLlama-protocol-slug lookup — fired once
        per page view (see frontend.py's /coin/[symbol] on_load). Patches
        unlock_source_url in place once a real slug resolves (or confirms
        there's none), rather than waiting on a fresh full-row rebuild.
        """
        symbol = self.symbol.strip()
        if not symbol:
            return
        result = await asyncio.to_thread(_fetch_defillama_unlocks_slug, symbol)
        if result is None:
            return
        cmc_id, slug = result
        async with self:
            self.coin_overrides = {
                **self.coin_overrides,
                cmc_id: {
                    **self.coin_overrides.get(cmc_id, {}),
                    "unlock_source_url": _resolve_unlock_source_url(symbol, slug),
                },
            }

    def _resolve_tradingview_symbol(self) -> str | None:
        """Picks the real, exchange-prefixed TradingView symbol for this
        coin (e.g. "MEXC:ZKMLUSDT") — never a bare, unprefixed
        "{SYMBOL}USDT" guess. Confirmed live that a bare guess is
        unreliable in two different ways: it shows "This symbol doesn't
        exist" for coins whose only real USDT listing is on a smaller-but-
        still-top-15 exchange (MEXC, Gate, HTX, ...) rather than Binance/
        Coinbase, AND — worse — TradingView's own fuzzy auto-resolution for
        an unprefixed symbol can silently latch onto a completely unrelated
        coin's listing (confirmed live: a bare "SHIBUSDT" query, requested
        before this coin's own market pairs had finished their first fetch,
        resolved to "KUCOIN:SHIBA INUUSDT" — a malformed, nonexistent
        symbol). Returning None here (see has_tradingview_chart/
        tradingview_chart_pending below) instead of guessing keeps the
        chart from ever advertising a symbol that isn't actually real.

        Sources from the coin's own already-fetched real CEX market pairs
        (see market_pairs_service.py / CoinState.refresh_market_pairs),
        filtered to exchanges TradingView actually recognizes a prefix for
        (_TRADINGVIEW_EXCHANGE_PREFIXES) and ranked by that pair's own real
        24h volume — the same highest-confidence real listing already shown
        in this page's own Markets section.

        The base ticker always comes from `self.symbol` (this coin's own
        real ticker), NOT the pair's own "market_pair" base — confirmed
        live that CoinGecko's raw per-ticker base field is sometimes the
        coin's full display name instead of its ticker (Shiba Inu's own
        KuCoin listing reported base "SHIBA INU", not "SHIB"), which built
        a symbol ("KUCOIN:SHIBA INUUSDT") that isn't real. Every pair here
        is already known to be this same coin's own listing (that's what
        "this coin's market pairs" means), so the base is never actually in
        question — only the quote side varies, and that's still validated
        against a plain ticker pattern (letters/digits only) before use.

        This reads `self.selected_coin` (and therefore `self.all_coins`)
        rather than only `self.symbol` — safe now that the iframe itself is
        a real typed rx.el.iframe(src=...) (see _chart_column), not the
        dangerouslySetInnerHTML string that used to force a full reload on
        every recompute. Market pairs only change on their own hourly TTL
        (not on detail_sync_loop's 60s price-only resync), so this resolves
        to the same string between syncs and the iframe still won't reload.

        Ranked by real 24h volume, but a USD-equivalent-quoted pair
        (_USD_EQUIVALENT_QUOTES) always outranks a foreign-fiat one
        regardless of volume — confirmed live for Ondo and Stellar that
        Upbit's own real, high-volume ONDO/KRW and XLM/KRW pairs otherwise
        won the ranking outright over either coin's own real USDT pair
        (lower volume, but still real), producing a Korean-Won-denominated
        chart next to this page's own USD-denominated price header — not a
        wrong-coin or fake-listing bug, just the wrong currency, but it
        reads exactly like a wrong price. This isn't Upbit-specific either:
        the same ranking-by-raw-volume-alone would just as readily pick a
        real JPY/EUR/GBP/... pair over a real USD one for any other coin
        with a high-volume foreign-fiat listing.

        Manual exchange priority, per explicit request: whichever of MEXC,
        KuCoin, HTX, or Bybit (_EXCHANGE_PRIORITY, in that order) this coin
        actually has a real pair on wins outright, overriding the volume/
        USD-equivalent ranking above entirely — Binance otherwise wins on
        raw volume for most coins, which is what this exists to override.
        Only Binance/Coinbase/any other real exchange fall through to the
        usual volume/USD-equivalent ranking below, and only when a coin has
        none of those four at all.

        Falls back to `tradingview_dex_symbol` (see
        app/services/tradingview_symbol_service.py /
        CoinState.refresh_tradingview_dex_symbol) when this coin has no
        real CEX pair at all — confirmed live that some real coins
        genuinely only have a DEX pool listing (zKML: Uniswap v2 on
        Ethereum, no CEX anywhere), and TradingView itself tracks a real,
        chartable symbol for many of those pools directly. That fallback
        symbol is pre-resolved and cached in Postgres (never computed here),
        so this stays a fast, purely-local lookup either way — no network
        call inside a cached var.
        """
        return _resolve_chart_symbol(self.symbol, self.selected_coin)

    @rx.var(cache=True)
    def has_tradingview_chart(self) -> bool:
        return self._resolve_tradingview_symbol() is not None

    @rx.var(cache=True)
    def tradingview_chart_pending(self) -> bool:
        """True while this coin's real chart symbol isn't resolved yet AND
        we haven't confirmed (via a completed market-pairs fetch — see
        "market_pairs_fetched" in _build_row/refresh_market_pairs) that it
        genuinely has none. Drives _chart_column's loading state instead of
        either an unreliable bare-symbol guess or a premature "no chart"
        message on the very first render, before refresh_market_pairs'
        one-shot background fetch (see frontend.py's on_load) completes.

        Also waits on "tradingview_dex_symbol_fetched" (see
        CoinState.refresh_tradingview_dex_symbol) — only actually relevant
        when this coin turns out to have zero CEX pairs (has_tradingview_
        chart already short-circuits this to False the instant a CEX pair
        resolves, regardless of that second flag's value), so a CEX-only
        coin's chart never waits on the DEX-symbol lookup that a coin with
        a real CEX pair never even triggers.
        """
        if self.has_tradingview_chart:
            return False
        return not (
            self.selected_coin.get("market_pairs_fetched", False)
            and self.selected_coin.get("tradingview_dex_symbol_fetched", False)
        )

    def _tradingview_iframe_src(self, theme: str) -> str:
        """Public, no-API-key TradingView "widgetembed" iframe URL. CMC's
        Basic tier has no historical OHLCV endpoint (see the _TREND_UP/
        _TREND_DOWN note above), so this is the only way to show a genuinely
        real, live-updating candlestick chart without a paid CMC plan or a
        custom price-history pipeline.

        Symbol comes from _resolve_tradingview_symbol (see its own
        docstring) — a real exchange-prefixed pair, or None. Returns ""
        (empty src) when None — _chart_column only mounts this iframe when
        CoinState.has_tradingview_chart is true, so an empty src here is
        just a defensive no-op, never actually rendered.
        allow_symbol_change=1 keeps TradingView's own exchange switcher
        available so a viewer can manually pick a different venue if this
        default still doesn't have full history.

        Split into light/dark variants (see tradingview_iframe_src_light/
        _dark below) rather than one var, since the app's color mode is a
        client-side (next-themes) preference this server-cached var can't
        see — the component picks between the two via rx.color_mode_cond,
        which is a real frontend-reactive Var, not a server computation.

        interval="60" (1 hour) is the default candle granularity, per
        explicit request. No "range" param — confirmed live that TradingView
        silently overrides an explicit interval to a much coarser one ("M")
        whenever range="ALL" is also set, which was the real cause of the
        chart looking "locked" to a weekly/monthly view regardless of this
        interval value. Without it, the widget honors interval="60" and
        opens on real 1h candles. withdateranges=1 still shows the 1h/4h/
        24h/1W/1M row so a viewer can pick a different interval afterward,
        and since the src no longer regenerates on its own, that manual pick
        now actually sticks instead of being reset on the next background
        sync.

        backgroundColor/gridColor force a solid plot pane with no visible
        grid lines (grid color matches the background exactly, so lines
        blend in) — these are real top-level options on TradingView's free
        embeddable widget. (The nested "overrides" param used by their
        paid/self-hosted Charting Library, e.g. "paneProperties.background",
        was tried first and confirmed live to have zero effect here — this
        free widget strips that key entirely, so it silently does nothing
        rather than erroring. backgroundColor/gridColor are the ones this
        widget tier actually reads.) Follows `theme` now (black in dark
        mode, white in light mode) rather than a fixed black regardless of
        theme — matches the rest of the page's own light/dark switching.
        """
        symbol = self._resolve_tradingview_symbol()
        if symbol is None:
            return ""
        pane_color = "#000000" if theme == "dark" else "#ffffff"
        params = {
            "symbol": symbol,
            "interval": "60",
            "theme": theme,
            "style": "1",
            "locale": "en",
            # Kuala Lumpur time (UTC+8) instead of the widget's own UTC
            # default, per explicit request — Singapore ("Asia/Singapore")
            # is the same UTC+8 offset and would be an equally valid
            # fallback if TradingView ever drops "Asia/Kuala_Lumpur" from
            # its supported IANA timezone list.
            "timezone": "Asia/Kuala_Lumpur",
            "toolbarbg": "131722" if theme == "dark" else "f1f3f6",
            "backgroundColor": pane_color,
            "gridColor": pane_color,
            # Underscored key is the one this widget actually reads — the
            # earlier "hidesidetoolbar" (no underscore) was silently
            # ignored, leaving the drawing-tools sidebar hidden (its
            # default) regardless of its "0" value. Confirmed live that
            # this one shows the left toolbar while the black background/
            # grid above stay intact.
            "hide_side_toolbar": "0",
            "saveimage": "0",
            "withdateranges": "1",
            "studies": "[]",
            "hideideas": "1",
            "allow_symbol_change": "1",
        }
        return f"https://www.tradingview.com/widgetembed/?{urlencode(params)}"

    @rx.var(cache=True)
    def tradingview_iframe_src_light(self) -> str:
        return self._tradingview_iframe_src("light")

    @rx.var(cache=True)
    def tradingview_iframe_src_dark(self) -> str:
        return self._tradingview_iframe_src("dark")

    @rx.event
    def set_sort(self, key: str):
        if self.sort_key != key:
            self.sort_key = key
            self.sort_direction = "desc"
        elif self.sort_direction == "desc":
            self.sort_direction = "asc"
        else:
            # Third click on the same column: back to neutral/default order.
            self.sort_key = ""
            self.sort_direction = ""

    @rx.var(cache=True)
    def filtered_coins(self) -> list[dict]:
        # Merges coin_overrides in once, up front, for the full universe —
        # see _row_with_overrides. Everything below (category/chain filter,
        # search, ranking) reads this already-fresh list rather than the
        # static all_coins directly, so a live-synced price or a just-
        # arrived business summary shows up here immediately.
        full_rows = [self._row_with_overrides(r) for r in self.all_coins]
        rows = full_rows
        if self.selected_category != "All narratives":
            rows = [r for r in rows if self.selected_category in r["narratives"]]
        # AND'd with the narrative filter — e.g. "Memes" + "BNB Smart Chain
        # (BEP20)" narrows to memecoins whose primary chain is BNB Smart Chain.
        if self.selected_chain != "All chains":
            rows = [r for r in rows if r["main_chain"] == self.selected_chain]
        # Search runs against every coin in all_coins (not just the current
        # page) by name/ticker only — finds a coin regardless of which page
        # it would otherwise land on.
        if self.search_query:
            query = self.search_query.strip().lower()
            # A search is a lookup for one specific, known coin, so its rank
            # should be the coin's real global position by market cap across
            # every coin (e.g. XRP is #5) — not its position within the
            # arbitrarily narrowed search-result list, which previously
            # showed "1" for a single match regardless of that coin's actual
            # standing.
            global_rank_by_id = {
                row["cmc_id"]: i
                for i, row in enumerate(
                    sorted(full_rows, key=lambda r: r["market_cap_usd"], reverse=True),
                    start=1,
                )
            }
            rows = [
                {**r, "rank": global_rank_by_id[r["cmc_id"]]}
                for r in rows
                if query in r["name"].lower() or query in r["symbol"].lower()
            ]
            return sorted(rows, key=lambda r: r["market_cap_usd"], reverse=True)
        rows = sorted(rows, key=lambda r: r["market_cap_usd"], reverse=True)
        # Rank reflects position by market cap in the current view (1..N),
        # not CMC's own cmc_rank field, which has gaps/different methodology
        # (e.g. staked derivatives) that don't match a strict market-cap order.
        return [{**row, "rank": i} for i, row in enumerate(rows, start=1)]

    @rx.var(cache=True)
    def total_shown(self) -> int:
        return len(self.filtered_coins)

    @rx.var(cache=True)
    def displayed_categories(self) -> list[str]:
        return self.all_categories if self.narratives_expanded else self.categories

    @rx.var(cache=True)
    def displayed_chains(self) -> list[str]:
        return self.all_chains if self.chains_expanded else self.chains

    @rx.var(cache=True)
    def global_search_matches(self) -> list[dict]:
        """Every coin matching the header search box's query, ranked by
        market cap — the full match list before global_search_limit trims
        it for display. Independent of the homepage table's own
        search_query/filtered_coins (different box, different page-wide
        use), but the same name-or-ticker substring match.
        """
        query = self.global_search_query.strip().lower()
        if not query:
            return []
        full_rows = [self._row_with_overrides(r) for r in self.all_coins]
        matches = [
            r for r in full_rows if query in r["name"].lower() or query in r["symbol"].lower()
        ]
        return sorted(matches, key=lambda r: r["market_cap_usd"], reverse=True)

    @rx.var(cache=True)
    def global_search_history(self) -> list[dict]:
        """The last (up to) 5 coins opened from the search dropdown, newest
        first, as live rows (price/change stay current)."""
        ids: list[int] = []
        for part in self.global_search_history_raw.split(","):
            part = part.strip()
            if part.isdigit() and int(part) not in ids:
                ids.append(int(part))
        by_id = {r["cmc_id"]: r for r in self.all_coins}
        return [self._row_with_overrides(by_id[i]) for i in ids[:5] if i in by_id]

    @rx.var(cache=True)
    def global_search_has_history(self) -> bool:
        return len(self.global_search_history) > 0

    @rx.var(cache=True)
    def global_search_results(self) -> list[dict]:
        return self.global_search_matches[: self.global_search_limit]

    @rx.var(cache=True)
    def global_search_has_more(self) -> bool:
        return len(self.global_search_matches) > len(self.global_search_results)

    @rx.var(cache=True)
    def global_search_has_matches(self) -> bool:
        return len(self.global_search_matches) > 0

    @rx.var(cache=True)
    def total_pages(self) -> int:
        return max(1, -(-self.total_shown // self.page_size))

    @rx.var(cache=True)
    def skeleton_rows(self) -> list[int]:
        """One entry per skeleton row to render while is_filtering is true
        — sized to page_size (not a fixed count) so the skeleton matches
        whatever row count the real table is about to show. Errs toward
        page_size even on a short last page/search result rather than a
        smaller count, so the page height never visibly collapses then
        re-expands once the real (possibly shorter) rows replace it.
        """
        return list(range(self.page_size))

    @rx.var(cache=True)
    def page_top_n(self) -> int:
        """The table title's "Top N" — page 1 is 100, page 2 is 200, and so
        on, capped to how many coins are actually in view (so a narrow
        narrative filter doesn't claim "Top 100" when there are only 20).
        """
        return min(self.page * self.page_size, self.total_shown)

    @rx.var(cache=True)
    def paged_coins(self) -> list[dict]:
        start = (self.page - 1) * self.page_size
        return self.filtered_coins[start : start + self.page_size]

    @rx.var(cache=True)
    def sorted_paged_coins(self) -> list[dict]:
        """The current page's rows, optionally re-sorted by one column.
        Only ever reorders within this page (top 100, or whichever 100
        the current page is) — never re-ranks across the full coin list.
        """
        rows = self.paged_coins
        if not self.sort_key:
            return rows
        return sorted(
            rows, key=lambda r: r[self.sort_key], reverse=self.sort_direction == "desc"
        )

    @rx.var(cache=True)
    def page_str(self) -> str:
        return str(self.page)

    @rx.var(cache=True)
    def active_page_str(self) -> str:
        return str(self.active_page)

    @rx.var(cache=True)
    def page_size_str(self) -> str:
        return str(self.page_size)

    @rx.var(cache=True)
    def showing_start(self) -> int:
        return 0 if self.total_shown == 0 else (self.page - 1) * self.page_size + 1

    @rx.var(cache=True)
    def showing_end(self) -> int:
        return min(self.page * self.page_size, self.total_shown)

    @rx.var(cache=True)
    def page_window(self) -> list[str]:
        """Page numbers to render, e.g. ["1","2","3","4","5","...","117"] —
        a leading run around the current page, plus the last page, with
        "..." marking any gap. "..." entries render as plain text, not
        buttons (see coin_table.py::_page_number).
        """
        total = self.total_pages
        current = self.page
        if total <= 7:
            window = list(range(1, total + 1))
        elif current <= 5:
            window = list(range(1, 6))
        elif current >= total - 4:
            window = list(range(total - 4, total + 1))
        else:
            window = list(range(current - 2, current + 3))

        pages: list[str] = []
        if window[0] > 1:
            pages.append("1")
            if window[0] > 2:
                pages.append("...")
        pages.extend(str(p) for p in window)
        if window[-1] < total:
            if window[-1] < total - 1:
                pages.append("...")
            pages.append(str(total))
        return pages
