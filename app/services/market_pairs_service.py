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
    cex_top10 = sorted((p for p in normalized if not p["is_dex"]), key=lambda p: p["volume_24h"], reverse=True)[:10]
    dex_top10 = sorted((p for p in normalized if p["is_dex"]), key=lambda p: p["volume_24h"], reverse=True)[:10]
    combined = cex_top10 + dex_top10

    # Volume % is this exchange's share of the coin's real, already-known
    # total 24h volume across every market (coin.volume_24h_usd, synced by
    # MarketDataService) — not just the share among these 20 shown rows,
    # which would overstate each one's real weight.
    total_volume = float(coin.volume_24h_usd) if coin.volume_24h_usd else sum(p["volume_24h"] for p in combined)
    for p in combined:
        p["volume_pct"] = (p["volume_24h"] / total_volume * 100) if total_volume else 0.0
    return combined


def get_market_pairs(db: Session, coin: Coin) -> list[dict]:
    """Returns this coin's cached top-10-CEX + top-10-DEX market pairs,
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
