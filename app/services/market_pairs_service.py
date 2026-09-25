"""On-demand, cached CEX/DEX market-pair listing per coin (see coin_detail.py's
Markets section) — real exchanges, pairs, prices and volumes from CoinGecko's
free, keyless public API.

Not CoinMarketCap: confirmed live that CMC's own /v2/cryptocurrency/
market-pairs/latest 403s on this project's Basic (free) CMC key with
error_code 1006 "Your API Key subscription plan doesn't support this
endpoint" — that endpoint needs a paid CMC plan (Hobbyist tier or above).
CoinGecko's /coins/{id} (tickers=true) is the free equivalent, and reuses the
exact same coin-id resolution this project already built for the description
upgrade (see coingecko_service.py): a contract-address lookup for tokens, a
top-500-market-cap symbol map for native/root coins with no contract.

Only spot markets: CoinGecko's ticker objects have no Open Interest/Funding
Rate/Spread fields — those are derivatives-specific and aren't part of this
free ticker data on any provider we use.

Gated behind a Postgres cache per coin (settings.market_pairs_cache_ttl_hours,
default 1h — much shorter than description/business_summary's TTLs, since
real exchange price/volume goes stale within the hour) so a burst of coin
detail page visits never re-fetches more than once per coin per window —
same cost-control spirit as SocialService/business_summary_service, and
doubly important here since CoinGecko's free tier is IP-rate-limited
(no key).
"""

import logging
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.coin import Coin
from app.services.coingecko_service import (
    _CHAIN_TO_COINGECKO_PLATFORM,
    _TOP_COIN_RANK_CUTOFF,
    _get_top_coin_symbol_map,
)

logger = logging.getLogger(__name__)

# CoinGecko's ticker objects have no per-entry "is this a DEX" boolean —
# same situation as CMC's market-pairs (see the module docstring). DEX
# market identifiers are matched by substring rather than an exact set,
# since CoinGecko suffixes the same DEX's identifier differently per chain/
# version (confirmed live: Ondo's Ethereum-side Uniswap entries were
# "uniswap_v3" AND "uniswap-v4-ethereum" — an exact-match allowlist would
# have missed the second one). Anything that doesn't match is treated as a
# CEX, which is correct for the overwhelming majority of exchange
# identifiers CoinGecko actually returns.
_DEX_KEYWORDS = (
    "uniswap", "pancakeswap", "sushiswap", "curve", "balancer",
    "raydium", "orca", "meteora", "quickswap", "trader_joe", "traderjoe",
    "aerodrome", "velodrome", "camelot", "thena", "shibaswap", "biswap",
    "apeswap", "spookyswap", "spiritswap", "kyberswap", "dodo", "bancor",
    "pangolin", "honeyswap", "osmosis", "jupiter", "gmx", "dydx",
    "syncswap", "izumi", "ambient", "1inch", "0x_protocol", "hyperliquid",
    "pumpswap", "pump_fun", "fluid_dex", "aave",
)

# Real top-15 spot exchanges per coinmarketcap.com/rankings/exchanges/
# (snapshot; that page's own ranking already accounts for traffic/liquidity/
# reported-volume confidence — CMC-listed but lower-trust exchanges like
# BTCC or CoinUp, which routinely rank high on a single coin's *own*
# CoinGecko ticker volume, are deliberately excluded here even though
# they'd otherwise pass the top-N-by-volume cut below). Matched
# case-insensitively against each ticker's own exchange_name (see
# _normalize) — CoinGecko's market.name values line up with these almost
# verbatim (confirmed live: "OKX", "MEXC", "HTX", "Coinbase Exchange" all
# appear exactly as CoinGecko ticker names despite differing from those
# exchanges' own CoinGecko *identifiers*, e.g. "okex"/"mxc"/"huobi"/"gdax").
# "Binance Alpha" is included per explicit request even though it isn't one
# of CMC's ranked top-15 spot exchanges (it's Binance's separate early-access
# venue for newly-listed tokens) — CoinGecko's tracked exchange list has no
# such distinct entity as of this writing (checked /exchanges/list; those
# tokens' tickers, if tracked at all, report under plain "Binance"), so this
# entry is a forward-compatible no-op today rather than a verified live one.
_CEX_ALLOWED_NAMES = {
    "binance", "coinbase exchange", "upbit", "okx", "bybit",
    "bitget", "gate", "gate.io", "kucoin", "mexc", "htx",
    "crypto.com exchange", "bitfinex", "bingx", "kraken", "binance tr",
    "binance alpha",
}

# CoinGecko's ticker `target` field is a raw quote-asset ticker (see
# _normalize/_display_symbol) — USDC pairs are excluded from the CEX side
# per explicit request (a coin's USDT pair is what most viewers actually
# want; a same-exchange USDC pair alongside it is redundant noise), unless
# excluding them would leave the CEX list empty (see _fetch_from_coingecko),
# in which case that single USDC listing is kept rather than showing nothing.
_EXCLUDED_CEX_QUOTES = {"USDC"}

# Real top-15 DEXs per coingecko.com/en/exchanges/decentralized/<chain>,
# keyed by this app's own CoinContract.platform_name spelling (same keys as
# coingecko_service._CHAIN_TO_COINGECKO_PLATFORM) so a coin's actual chain
# picks the right ranking rather than one global "top DEX" list dominated by
# whichever chain happens to have the highest wash-trading-prone volume that
# day. Snapshot data — DEX volume rankings shift often, but re-scraping
# coingecko.com per request isn't viable (that page is client-rendered, so a
# plain HTTP GET returns an empty shell, not the ranked table).
_DEX_ALLOWED_BY_CHAIN = {
    "Solana": {
        "orca", "meteora", "raydium (clmm)", "manifest", "humidifi",
        "pumpswap", "raydium", "alphaq", "zerofi", "pancakeswap v3 (solana)",
        "byreal", "meteora damm v2", "metadao (futarchy amm)", "defituna",
        "omnipair",
    },
    "Ethereum": {
        "uniswap v3 (ethereum)", "uniswap v4 (ethereum)", "fluid (ethereum)",
        "alphax", "curve (ethereum)", "native core", "origin arm",
        "uniswap v2 (ethereum)", "tokenlon", "lighter (spot)",
        "ekubo v2 (ethereum)", "pancakeswap v3 (ethereum)", "yellow pro",
        "dodo (ethereum)", "maverick protocol v2 (ethereum)",
    },
    "BNB Smart Chain (BEP20)": {
        "pancakeswap v3 (bsc)", "pancakeswap infinity clmm (bsc)",
        "uniswap v3 (bsc)", "uniswap v4 (bsc)", "pancakeswap (v2)",
        "topaz", "de¹", "aster", "thena v3", "nomiswap (stable)",
        "pancakeswap v1 (bsc)", "unchain x", "biswap", "thena fusion",
        "maverick protocol v2 (bsc)",
    },
    "Base": {
        "hydrex integral", "aerodrome slipstream 3", "aerodrome slipstream",
        "uniswap v3 (base)", "pancakeswap v3 (base)", "uniswap v4 (base)",
        "aerodrome (base)", "aerodrome slipstream 2", "uniswap v2 (base)",
        "quickswap v4 (base)", "solidly v3 (base)",
        "maverick protocol v2 (base)", "balancer v2 (base)", "fluid (base)",
        "o1 launchpad",
    },
    "Arbitrum": {
        "uniswap v3 (arbitrum one)", "uniswap v4 (arbitrum)",
        "fluid (arbitrum)", "pancakeswap v3 (arbitrum)", "camelot v3",
        "curve (arbitrum)", "sushiswap v3 (arbitrum)", "camelot",
        "maverick protocol v2 (arbitrum)", "balancer v3 (arbitrum)",
        "balancer v2 (arbitrum)", "wombat (arbitrum)", "solidly v3 (arbitrum)",
        "sushiswap (arbitrum one)", "ramses v2",
    },
    "Polygon": {
        "uniswap v4 (polygon)", "uniswap v3 (polygon)", "ramses v3 (polygon)",
        "quickswap", "quickswap (v3)", "balancer v2 (polygon)",
        "uniswap v2 (polygon)", "w-dex (polygon)", "sushiswap v3 (polygon)",
        "curve (polygon)", "sushiswap (polygon pos)",
        "quickswap v4 (polygon)", "dooar (polygon)", "fluid (polygon)",
        "apeswap (polygon)",
    },
}

# Any chain not curated above (long tail — this app tracks 30 CMC chain
# mappings, only the highest-volume handful have their own list) falls back
# to CoinGecko's own cross-chain top 15, rather than showing an unfiltered
# DEX list for those coins.
_DEX_ALLOWED_FALLBACK = {
    "voltswap (meter)", "hydrex integral", "pancakeswap v3 (bsc)",
    "uniswap v3 (robinhood)", "uniswap v4 (ethereum)", "uniswap v3 (ethereum)",
    "orca", "aerodrome slipstream 3", "kuru", "meteora",
    "uniswap v3 (arbitrum one)", "uniswap v4 (robinhood)",
    "aerodrome slipstream", "uniswap v3 (base)", "raydium (clmm)",
}

# A native/root asset (ETH, SOL, BNB...) has no CoinContract row of its own
# (see _fetch_raw_tickers' fallback path below) — this maps its ticker
# straight to the chain whose gas token it is, so e.g. ETH's own Markets
# section still uses Ethereum's DEX ranking instead of falling back to the
# generic cross-chain list.
_NATIVE_ASSET_CHAINS = {
    "ETH": "Ethereum", "BNB": "BNB Smart Chain (BEP20)", "SOL": "Solana",
    "MATIC": "Polygon", "POL": "Polygon", "AVAX": "Avalanche C-Chain",
}

# Bulk-fetched once per process (same lazy-module-global caching pattern as
# coingecko_service._get_top_coin_symbol_map) — CoinGecko's per-ticker
# `market` object carries a name/identifier but no logo, so exchange icons
# come from this separate, one-time /exchanges listing instead of a call
# per unique exchange per coin. Only covers centralized exchanges (that
# endpoint's own scope) — a DEX identifier simply won't be in this map, and
# the UI falls back to a generic icon for those rather than a broken image.
_exchange_logo_by_identifier: dict[str, str] | None = None


def _get_exchange_logo_map() -> dict[str, str]:
    global _exchange_logo_by_identifier
    if _exchange_logo_by_identifier is not None:
        return _exchange_logo_by_identifier
    mapping: dict[str, str] = {}
    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/exchanges",
            params={"per_page": 250, "page": 1},
            timeout=10,
        )
        response.raise_for_status()
        for entry in response.json():
            identifier, image = entry.get("id"), entry.get("image")
            if identifier and image:
                mapping[identifier] = image
    except (requests.RequestException, ValueError) as exc:
        logger.warning("CoinGecko exchange logo map fetch failed: %s", exc)
    _exchange_logo_by_identifier = mapping
    return mapping


def needs_refresh(coin: Coin) -> bool:
    if not coin.cached_market_pairs:
        return True
    if coin.market_pairs_updated_at is None:
        return True
    ttl = timedelta(hours=settings.market_pairs_cache_ttl_hours)
    return datetime.utcnow() - coin.market_pairs_updated_at > ttl


def _relative_time(iso_str: str | None) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return ""
    minutes = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    if minutes < 1:
        return "Just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


# DEX tickers' base/target fields hold the raw token contract address, not
# a ticker symbol (confirmed live: Ondo's Uniswap V3 entry had base
# "0xfaba6f...269be3") — coin_id/target_coin_id carry CoinGecko's own id for
# each side instead, which is what this maps to a real symbol. Only the
# handful of ids that commonly appear as the OTHER side of a DEX pair need
# a correction here (a CoinGecko id like "usd-coin" or "wrapped-bitcoin"
# doesn't read as its own ticker); anything else just gets its id
# uppercased, which is still far more readable than a raw hex address.
_COMMON_ID_SYMBOLS = {
    "ethereum": "ETH", "weth": "WETH", "wrapped-ether": "WETH",
    "tether": "USDT", "usd-coin": "USDC", "dai": "DAI",
    "bitcoin": "BTC", "wrapped-bitcoin": "WBTC",
    "binancecoin": "BNB", "matic-network": "MATIC",
    "solana": "SOL", "wrapped-solana": "WSOL",
}


def _display_symbol(raw: str | None, coin_id: str | None) -> str:
    if coin_id:
        return _COMMON_ID_SYMBOLS.get(coin_id, coin_id.replace("-", " ").upper())
    return (raw or "?").upper()


def _normalize(ticker: dict, logo_map: dict[str, str]) -> dict:
    market = ticker.get("market") or {}
    identifier = market.get("identifier") or ""
    converted_last = ticker.get("converted_last") or {}
    converted_volume = ticker.get("converted_volume") or {}
    base = _display_symbol(ticker.get("base"), ticker.get("coin_id"))
    target = _display_symbol(ticker.get("target"), ticker.get("target_coin_id"))
    return {
        "exchange_name": market.get("name") or "Unknown",
        "exchange_icon_url": logo_map.get(identifier, ""),
        "market_pair": f"{base}/{target}",
        "is_dex": any(keyword in identifier for keyword in _DEX_KEYWORDS),
        "price": converted_last.get("usd") or 0.0,
        "volume_24h": converted_volume.get("usd") or 0.0,
        "last_updated_display": _relative_time(ticker.get("last_traded_at") or ticker.get("timestamp")),
    }


_TICKER_PARAMS = {
    "tickers": "true",
    "market_data": "false",
    "community_data": "false",
    "developer_data": "false",
    "localization": "false",
}


def _fetch_raw_tickers(coin: Coin) -> list[dict] | None:
    """Same id-resolution path as coingecko_service.upgrade_description
    (contract address for tokens, top-500 symbol map for native/root
    coins) — both requests ask for tickers=true directly, so no separate
    id-lookup call is needed on top of it.
    """
    primary = next((c for c in coin.contracts if c.is_primary), None)
    platform_id = _CHAIN_TO_COINGECKO_PLATFORM.get(primary.platform_name) if primary else None

    if platform_id and primary.contract_address:
        url = f"https://api.coingecko.com/api/v3/coins/{platform_id}/contract/{primary.contract_address}"
        try:
            response = requests.get(url, params=_TICKER_PARAMS, timeout=15)
            if response.status_code == 200:
                tickers = response.json().get("tickers") or []
                if tickers:
                    return tickers
        except (requests.RequestException, ValueError) as exc:
            logger.warning("CoinGecko tickers fetch failed for %s (contract): %s", coin.symbol, exc)

    if coin.cmc_rank is not None and coin.cmc_rank <= _TOP_COIN_RANK_CUTOFF:
        coingecko_id = _get_top_coin_symbol_map().get(coin.symbol.upper())
        if coingecko_id:
            url = f"https://api.coingecko.com/api/v3/coins/{coingecko_id}"
            try:
                response = requests.get(url, params=_TICKER_PARAMS, timeout=15)
                if response.status_code == 200:
                    return response.json().get("tickers") or []
            except (requests.RequestException, ValueError) as exc:
                logger.warning("CoinGecko tickers fetch failed for %s (id): %s", coin.symbol, exc)

    return None


def _fetch_from_coingecko(coin: Coin) -> list[dict] | None:
    raw_tickers = _fetch_raw_tickers(coin)
    if not raw_tickers:
        return None

    logo_map = _get_exchange_logo_map()
    normalized = [_normalize(t, logo_map) for t in raw_tickers]

    # CEX side: only exchanges CMC itself ranks top-15 (see
    # _CEX_ALLOWED_NAMES) — a coin whose only listings are on lower-trust
    # venues (e.g. BTCC, CoinUp) simply shows fewer than 15 CEX rows rather
    # than padding the list with them. USDC pairs are then dropped in favor
    # of USDT/native-fiat pairs (_EXCLUDED_CEX_QUOTES) — unless that would
    # empty the list entirely, in which case the USDC row(s) are kept so the
    # tab isn't blank.
    cex_candidates = [p for p in normalized if not p["is_dex"] and p["exchange_name"].lower() in _CEX_ALLOWED_NAMES]
    cex_non_usdc = [p for p in cex_candidates if p["market_pair"].rsplit("/", 1)[-1] not in _EXCLUDED_CEX_QUOTES]
    cex_final = cex_non_usdc or cex_candidates
    cex_rows = sorted(cex_final, key=lambda p: p["volume_24h"], reverse=True)[:15]

    # DEX side: only the top 15 for the chain this coin is actually deployed
    # on (see _DEX_ALLOWED_BY_CHAIN) — same "show fewer, never pad" rule.
    primary = next((c for c in coin.contracts if c.is_primary), None)
    chain_name = primary.platform_name if primary else _NATIVE_ASSET_CHAINS.get(coin.symbol.upper())
    dex_allowlist = _DEX_ALLOWED_BY_CHAIN.get(chain_name, _DEX_ALLOWED_FALLBACK)
    dex_candidates = [p for p in normalized if p["is_dex"] and p["exchange_name"].lower() in dex_allowlist]
    dex_rows = sorted(dex_candidates, key=lambda p: p["volume_24h"], reverse=True)[:15]

    combined = cex_rows + dex_rows

    # Volume % is this exchange's share of the coin's real, already-known
    # total 24h volume across every market (coin.volume_24h_usd, synced by
    # MarketDataService) — not just the share among these <=30 shown rows,
    # which would overstate each one's real weight.
    total_volume = float(coin.volume_24h_usd) if coin.volume_24h_usd else sum(p["volume_24h"] for p in combined)
    for p in combined:
        p["volume_pct"] = (p["volume_24h"] / total_volume * 100) if total_volume else 0.0
    return combined


def get_market_pairs(db: Session, coin: Coin) -> list[dict]:
    """Returns this coin's cached market pairs — up to 15 CEX rows (only
    exchanges CMC itself ranks top-15, see _CEX_ALLOWED_NAMES, and USDT/
    native-fiat pairs over USDC where both exist) and up to 15 DEX rows
    (only that coin's chain's top-15 DEX, see _DEX_ALLOWED_BY_CHAIN) —
    refreshing from CoinGecko first if the cache is empty or older than
    settings.market_pairs_cache_ttl_hours. Never raises — a fetch failure
    just falls back to whatever's already cached (or an empty list if this
    coin has never successfully synced), same fallback spirit as
    SocialService.get_tweets.
    """
    if not needs_refresh(coin):
        return coin.cached_market_pairs or []

    fresh = _fetch_from_coingecko(coin)
    if fresh is None:
        return coin.cached_market_pairs or []

    coin.cached_market_pairs = fresh
    coin.market_pairs_updated_at = datetime.utcnow()
    db.add(coin)
    db.commit()
    return fresh
