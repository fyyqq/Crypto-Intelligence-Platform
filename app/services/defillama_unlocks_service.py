"""Real per-coin deep link to DeFiLlama's "View live unlock data" page —
see frontend/frontend/components/coin_detail.py's _unlock_source_link.

No free API anywhere (CMC/CoinGecko/CryptoRank/DeFiLlama's own /api/emissions)
exposes real unlock dates/schedules — that's a paid data category industry-
wide (see the Locked Supply section's own docstring). What IS free is
DeFiLlama's own website: https://defillama.com/protocol/unlocks/<slug> is a
real, public, no-auth page showing a project's real unlock schedule/chart —
we just can't pull that data programmatically for free, only link a user to
go look at it themselves.

The hard part is <slug> — DeFiLlama's protocol *name* often differs from
this app's own coin name (confirmed live: Arbitrum's real DefiLlama entity
is "Arbitrum Foundation", not "Arbitrum"), so naively kebab-casing our own
coin name would silently 404 for many coins. DeFiLlama's free, no-auth
`https://api.llama.fi/protocols` endpoint solves this properly — each entry
includes both a `slug` and a `cmcId` field, and cmcId is the exact same
CoinMarketCap ID this app already keys every coin by. Matching on cmcId
(confirmed live for Virtuals Protocol: cmcId "29420" -> slug
"virtuals-protocol", which really works) is a real identity match, not a
name guess.

This endpoint only lists DeFiLlama's ~8,400 TVL-tracked "protocols" — a
governance-token-only entity with no TVL (e.g. Arbitrum Foundation itself)
won't appear here at all, since DeFiLlama's Unlocks feature draws from a
broader, paid-only list (confirmed live: /api/emissions and
/emission/{protocol} both 402). So this only resolves a real deep link for
coins that happen to also be a tracked protocol — every other coin falls
back to the general https://defillama.com/unlocks dashboard (see
coin_state.py's unlock_source_url), never a guessed/broken per-coin URL.
"""

import logging
import time
from datetime import datetime, timedelta

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.coin import Coin

logger = logging.getLogger(__name__)

_PROTOCOLS_URL = "https://api.llama.fi/protocols"

# Process-wide cache of the whole {cmcId: slug} map — one ~8,400-row fetch
# shared across every coin's own per-coin TTL below, not refetched per coin.
_slug_by_cmc_id: dict[str, str] | None = None
_fetched_at: float = 0.0
_MAP_TTL_SECONDS = 6 * 3600


def _load_slug_map() -> dict[str, str]:
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
    """Returns this coin's cached DeFiLlama protocol slug (refreshing from
    the free /protocols map first if the cache is stale), or None if this
    coin genuinely isn't a DeFiLlama-tracked protocol. Never raises.
    """
    if not needs_refresh(coin):
        return coin.defillama_unlocks_slug

    slug = _load_slug_map().get(str(coin.cmc_id))

    coin.defillama_unlocks_slug = slug
    coin.defillama_unlocks_checked_at = datetime.utcnow()
    db.add(coin)
    db.commit()
    return slug
