"""Real per-coin deep link to DeFiLlama's "View live unlock data" page —
see frontend/frontend/components/coin_detail.py's _unlock_source_link.

No free API anywhere (CMC/CoinGecko/CryptoRank/DeFiLlama's own /api/emissions)
exposes real unlock dates/schedules — that's a paid data category industry-
wide (see the Locked Supply section's own docstring). What IS free is
DeFiLlama's own website: https://defillama.com/protocol/unlocks/<slug> is a
real, public, no-auth page showing a project's real unlock schedule/chart —
we just can't pull that data programmatically for free, only link a user to
go look at it themselves.

The hard part is <slug>. Three real, verified data sources feed it, tried in
order:

1. Contract-address match (app/data/defillama_unlocks_slugs.json's
   "contracts_by_chain_address") — DeFiLlama's own /unlocks page embeds its
   full ~370-entry unlock-tracked dataset (each entry's own governance-token
   contract address, as "<chain>:<address>") directly in that page's own
   __NEXT_DATA__, for every anonymous visitor. Extracted once via a real
   browser session (defillama.com itself sits behind Cloudflare
   bot-protection — confirmed live, a plain server-side request gets a 403
   "Just a moment..." challenge page, not the real content — but a real
   browser session isn't blocked). Matched against this app's own already-
   synced CoinContract rows (chain + address), the most reliable identity
   match there is: no external call, no ambiguity. This is also the only
   path that finds governance-only entities with no TVL at all (e.g.
   Arbitrum's real entry is "arbitrum-foundation", which never appears in
   the free /protocols TVL list below).
2. gecko_id match (that same file's "slugs_by_gecko_id") — a secondary path
   for entries with no on-chain contract (native L1 assets like Bitcoin/
   Solana, or off-chain-governed tokens), resolved via
   coingecko_service._get_top_coin_symbol_map(). Depends on CoinGecko's own
   public API being reachable (confirmed it can itself be rate-limited/
   blocked independent of this app), so this is best-effort, not guaranteed.
3. DeFiLlama's free, no-auth `https://api.llama.fi/protocols` endpoint —
   each of its ~8,400 entries includes both `slug` and `cmcId` fields,
   matched against this coin's own CMC id. Only covers DeFiLlama's
   TVL-tracked protocols (a different, mostly-overlapping set from the
   Unlocks feature's own list above), so this is a last-resort fallback.

Never guesses a slug from the coin's own name — confirmed live that a naive
kebab-case guess breaks even for coins where the *identity* match is
unambiguous (e.g. "Arbitrum" -> "arbitrum" 404s; the real page is
"arbitrum-foundation"). No match from any source falls back to the general
https://defillama.com/unlocks dashboard (see coin_state.py's
unlock_source_url) — never a guessed/broken per-coin URL.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.coin import Coin

logger = logging.getLogger(__name__)

_PROTOCOLS_URL = "https://api.llama.fi/protocols"
_SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "defillama_unlocks_slugs.json"

# CMC's own chain-name spelling (CoinContract.platform_name) -> DeFiLlama's
# own short chain code (as used in that "<chain>:<address>" token field) —
# a different convention from coingecko_service's own
# _CHAIN_TO_COINGECKO_PLATFORM (e.g. DeFiLlama uses "bsc"/"avax"/"era", not
# CoinGecko's "binance-smart-chain"/"avalanche"/"zksync"). Only the chains
# actually observed in the extracted snapshot are listed — an unmapped
# platform_name just means this path can't match that coin, never a false
# positive.
_CHAIN_TO_DEFILLAMA_CODE = {
    "Ethereum": "ethereum",
    "BNB Smart Chain (BEP20)": "bsc",
    "Solana": "solana",
    "Base": "base",
    "Arbitrum": "arbitrum",
    "Polygon": "polygon",
    "Avalanche C-Chain": "avax",
    "Optimism": "optimism",
    "Sui Network": "sui",
    "Fantom": "fantom",
    "Mantle": "mantle",
    "Cronos": "cronos",
    "Linea": "linea",
    "zkSync Era": "era",
    "Celo": "celo",
    "Sonic": "sonic",
    "Aptos": "aptos",
    "Tron20": "tron",
    "Ronin": "ronin",
    "Manta Pacific": "manta",
}

# Process-wide cache of the whole {cmcId: slug} map from /protocols — one
# ~8,400-row fetch shared across every coin's own per-coin TTL below, not
# refetched per coin.
_slug_by_cmc_id: dict[str, str] | None = None
_fetched_at: float = 0.0
_MAP_TTL_SECONDS = 6 * 3600

_snapshot: dict | None = None


def _load_snapshot() -> dict:
    global _snapshot
    if _snapshot is not None:
        return _snapshot
    try:
        with open(_SNAPSHOT_PATH, encoding="utf-8") as f:
            _snapshot = json.load(f)
    except Exception:
        logger.warning("defillama_unlocks_service: failed to load %s", _SNAPSHOT_PATH, exc_info=True)
        _snapshot = {"contracts_by_chain_address": {}, "slugs_by_gecko_id": {}}
    return _snapshot


def _load_protocols_map() -> dict[str, str]:
    global _slug_by_cmc_id, _fetched_at
    now = time.monotonic()
    if _slug_by_cmc_id is not None and (now - _fetched_at) < _MAP_TTL_SECONDS:
        return _slug_by_cmc_id

    try:
        resp = requests.get(_PROTOCOLS_URL, timeout=15)
        resp.raise_for_status()
        protocols = resp.json()
    except Exception:
        logger.warning("defillama_unlocks_service: failed to fetch %s", _PROTOCOLS_URL, exc_info=True)
        return _slug_by_cmc_id or {}

    mapping: dict[str, str] = {}
    for protocol in protocols:
        cmc_id = protocol.get("cmcId")
        slug = protocol.get("slug")
        if cmc_id and slug:
            mapping[str(cmc_id)] = slug

    _slug_by_cmc_id = mapping
    _fetched_at = now
    return mapping


def _match_by_contract(coin: Coin) -> str | None:
    contracts = _load_snapshot().get("contracts_by_chain_address", {})
    if not contracts:
        return None
    for contract in coin.contracts:
        chain = _CHAIN_TO_DEFILLAMA_CODE.get(contract.platform_name)
        if not chain or not contract.contract_address:
            continue
        slug = contracts.get(f"{chain}:{contract.contract_address.lower()}")
        if slug:
            return slug
    return None


def _match_by_gecko_id(coin: Coin) -> str | None:
    from app.services.coingecko_service import _get_top_coin_symbol_map

    gecko_id = _get_top_coin_symbol_map().get(coin.symbol.upper())
    if not gecko_id:
        return None
    return _load_snapshot().get("slugs_by_gecko_id", {}).get(gecko_id)


def needs_refresh(coin: Coin) -> bool:
    """Same checked_at-gates-refresh shape as tradingview_symbol_service's
    own needs_refresh — a coin confirmed to have no matching protocol
    shouldn't be re-checked every single page view either.
    """
    if coin.defillama_unlocks_checked_at is None:
        return True
    ttl = timedelta(hours=settings.defillama_unlocks_ttl_hours)
    return datetime.utcnow() - coin.defillama_unlocks_checked_at > ttl


def resolve_unlocks_slug(db: Session, coin: Coin) -> str | None:
    """Returns this coin's cached DeFiLlama protocol slug (refreshing first
    if the cache is stale), or None if this coin isn't found in any of the
    three real data sources above. Never raises.
    """
    if not needs_refresh(coin):
        return coin.defillama_unlocks_slug

    slug = _match_by_contract(coin) or _match_by_gecko_id(coin) or _load_protocols_map().get(str(coin.cmc_id))

    coin.defillama_unlocks_slug = slug
    coin.defillama_unlocks_checked_at = datetime.utcnow()
    db.add(coin)
    db.commit()
    return slug
