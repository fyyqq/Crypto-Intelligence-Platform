"""One-time, on-demand upgrade of a coin's `description` from CMC's own
auto-generated boilerplate ("<name> is a cryptocurrency and operates on the
<platform> platform...") to a real, human-written project description —
confirmed live that CMC's public `/v2/cryptocurrency/info` API never returns
anything but that template for most non-major coins (e.g. Pythia), even
though CMC's own website shows a real write-up for the same coin. That real
text isn't exposed anywhere in CMC's API (checked every field, including
every `aux` variant) — it lives only in CMC's website CMS layer.

CoinGecko's free, keyless public API does carry the same real description
for many of these coins, resolvable unambiguously via a direct contract-
address lookup (no fuzzy symbol/name matching, so no risk of pulling in an
unrelated same-ticker project) — confirmed live for Pythia, which returned
the exact real bio CMC's website shows.

Gated to run at most once per coin (Coin.description_synced_at) rather than
on every page view, since CoinGecko not having a listing for some coin now
doesn't change from one visit to the next, and CoinGecko's free tier is
rate-limited without a key.
"""

import logging
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from app.models.coin import Coin

logger = logging.getLogger(__name__)

# CMC's own chain-name spelling (CoinContract.platform_name, straight off
# /v2/info) -> CoinGecko's asset_platform_id, confirmed against CoinGecko's
# own /api/v3/asset_platforms listing. Only chains where a contract-address
# lookup is meaningful (EVM/SVM/Move/etc. token contracts) are included —
# non-contract chains (Cardano, Stellar, XRP Ledger, ICP, ...) are simply
# left unmapped, so those coins just keep whatever CMC gave them.
_CHAIN_TO_COINGECKO_PLATFORM = {
    "Ethereum": "ethereum",
    "BNB Smart Chain (BEP20)": "binance-smart-chain",
    "Solana": "solana",
    "Base": "base",
    "Arbitrum": "arbitrum-one",
    "Polygon": "polygon-pos",
    "Avalanche C-Chain": "avalanche",
    "TON": "the-open-network",
    "Optimism": "optimistic-ethereum",
    "Ink": "ink",
    "X Layer": "x-layer",
    "HyperEVM": "hyperevm",
    "Tron20": "tron",
    "Sui Network": "sui",
    "Fantom": "fantom",
    "Mantle": "mantle",
    "Gnosis Chain": "xdai",
    "Cronos": "cronos",
    "Chiliz Chain": "chiliz",
    "KAIA": "klay-token",
    "Linea": "linea",
    "zkSync Era": "zksync",
    "Celo": "celo",
    "Sonic": "sonic",
    "Terra Classic": "terra",
    "Harmony": "harmony-shard-0",
    "Aurora": "aurora",
    "Hyperliquid": "hyperliquid",
    "Blast": "blast",
    "Robinhood Chain": "robinhood",
}

# CMC's boilerplate always contains this exact three-phrase fingerprint
# (verified live against several coins) — a real, human-written description
# would essentially never contain all three verbatim, so this is a safe,
# cheap way to tell "needs upgrading" from "already has a real one" without
# hand-listing every coin. An empty/missing description also counts as
# needing an upgrade.
_BOILERPLATE_MARKERS = ("is a cryptocurrency", "current supply of", "last known price of")


def is_boilerplate_description(description: str | None) -> bool:
    if not description:
        return True
    text = description.lower()
    return all(marker in text for marker in _BOILERPLATE_MARKERS)


# Root/native coins (BTC, ETH, BNB, ...) have no real deployed contract of
# their own — confirmed live that even these get CMC's boilerplate
# description, and their CoinContract.contract_address is either absent or a
# placeholder native-asset marker (e.g. "0xeeee...eeee" for BNB), so the
# contract-lookup path above always misses them. Resolved instead via
# CoinGecko's bulk /coins/markets listing (one-time per process, not a
# per-coin call) rather than a symbol search, since a bare symbol lookup
# would be ambiguous — plenty of low-cap copycat tokens reuse a major
# ticker (e.g. "BNB AI", "BNBTiger Inu" in our own data). Gating this
# fallback to coins CMC itself ranks in the top 500 (see upgrade_description)
# keeps that ambiguity from ever mattering in practice: no copycat reaches
# that rank tier, so a symbol match there is effectively unambiguous.
_TOP_COIN_RANK_CUTOFF = 500
_top_coin_symbol_to_id: dict[str, str] | None = None


def _get_top_coin_symbol_map() -> dict[str, str]:
    global _top_coin_symbol_to_id
    if _top_coin_symbol_to_id is not None:
        return _top_coin_symbol_to_id
    mapping: dict[str, str] = {}
    try:
        for page in (1, 2):
            response = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": page},
                timeout=10,
            )
            response.raise_for_status()
            for entry in response.json():
                symbol = (entry.get("symbol") or "").upper()
                coingecko_id = entry.get("id")
                # Results are already market-cap-ordered, so the first hit
                # per symbol is always the legitimate major coin, never a
                # smaller same-ticker project appearing later in the list.
                if symbol and coingecko_id and symbol not in mapping:
                    mapping[symbol] = coingecko_id
    except (requests.RequestException, ValueError) as exc:
        logger.warning("CoinGecko top-coin symbol map fetch failed: %s", exc)
    _top_coin_symbol_to_id = mapping
    return mapping


def _fetch_from_coingecko_by_id(coingecko_id: str) -> str | None:
    url = f"https://api.coingecko.com/api/v3/coins/{coingecko_id}"
    try:
        response = requests.get(
            url,
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "false",
                "community_data": "false",
                "developer_data": "false",
            },
            timeout=10,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("CoinGecko description fetch failed for id=%s: %s", coingecko_id, exc)
        return None

    description = ((data.get("description") or {}).get("en") or "").strip()
    return description or None


def _fetch_from_coingecko(platform_id: str, contract_address: str) -> str | None:
    url = f"https://api.coingecko.com/api/v3/coins/{platform_id}/contract/{contract_address}"
    try:
        response = requests.get(
            url,
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "false",
                "community_data": "false",
                "developer_data": "false",
            },
            timeout=10,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("CoinGecko description fetch failed for %s/%s: %s", platform_id, contract_address, exc)
        return None

    description = ((data.get("description") or {}).get("en") or "").strip()
    return description or None


def upgrade_description(db: Session, coin: Coin) -> str | None:
    """Attempts the one-time CoinGecko upgrade for this coin, persisting the
    result (success or not) so it never runs again for it. Returns the new
    description on success, or None if nothing changed (already attempted,
    already real, unmapped chain, or CoinGecko has no listing for it).
    """
    if coin.description_synced_at is not None:
        return None
    if not is_boilerplate_description(coin.description):
        return None

    primary = next((c for c in coin.contracts if c.is_primary), None)
    platform_id = _CHAIN_TO_COINGECKO_PLATFORM.get(primary.platform_name) if primary else None

    fresh = None
    if platform_id and primary.contract_address:
        fresh = _fetch_from_coingecko(platform_id, primary.contract_address)

    if not fresh and coin.cmc_rank is not None and coin.cmc_rank <= _TOP_COIN_RANK_CUTOFF:
        coingecko_id = _get_top_coin_symbol_map().get(coin.symbol.upper())
        if coingecko_id:
            fresh = _fetch_from_coingecko_by_id(coingecko_id)

    coin.description_synced_at = datetime.utcnow()
    if fresh:
        coin.description = fresh
    db.add(coin)
    db.commit()
    return fresh
