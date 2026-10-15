"""Price alerts checked on the server, 24/7, whether or not a tab is open.

Every CHECK_SECONDS: load every account's active alerts; if there are none,
stop there (no price calls at all). Otherwise price each alerted coin the
way its coin page does, from the very pair the TradingView chart streams:
the hand-picked chart symbol (chart_symbol_override) or else the same
CEX/DEX pair CoinState picks for the chart (_resolve_chart_symbol over the
coin's cached market pairs), read through frontend/live_prices.py (the same
call as the header price). Only when that cannot be priced: the shared
exchange price list (app/services/price_hub.py, plausible vs. the stored
price), then the DEX pool by contract, and last the stored price (hourly
CoinMarketCap sync). Then trigger every alert whose
target was crossed through alert_service.mark_triggered, which marks it
once (atomically, so an open tab's own 4s check and this one never both
fire) and creates the account's notification (bell + /notifications) and
hands it to any external channel (Telegram/WhatsApp later; see
notification_service.register_channel).

Started at server start by frontend.py (lifespan task), so it keeps running
with no browser open. An open tab still shows its popup/voice for alerts it
sees itself (CoinState.start_alert_watch).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CHECK_SECONDS = 10

_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def _services():
    if _ROOT not in sys.path:
        sys.path.append(_ROOT)
    from app.core.database import SessionLocal
    from app.models.coin import Coin
    from app.models.price_alert import PriceAlert
    from app.services import alert_service, price_hub

    return SessionLocal, Coin, PriceAlert, alert_service, price_hub


_FETCH_CACHE_SECONDS = 10.0
_fetch_cache: dict[int, tuple[float, float | None]] = {}


def _fetched_price(item: dict) -> float | None:
    """Chart pair / exchange tickers / DEX contract for one coin (the coin
    page's own price path, frontend/live_prices.py), cached 10s per coin so a
    coin nothing can price isn't re-queried on every pass."""
    import time

    from frontend.live_prices import fetch_live_prices

    hit = _fetch_cache.get(item["cmc_id"])
    if hit and time.monotonic() - hit[0] < _FETCH_CACHE_SECONDS:
        return hit[1]
    price = fetch_live_prices([item]).get(item["cmc_id"])
    _fetch_cache[item["cmc_id"]] = (time.monotonic(), price)
    return price


def chart_items(db, cmc_ids: set[int]) -> dict[int, dict]:
    """{cmc_id: price item} for fetch_live_prices: each coin's chart pair (hand-picked override, else the pair the
    coin page picks), its main contract and stored price, plus name/rank for display. Shared with the Telegram
    /price command so both read the same TradingView pair."""
    from app.models.coin import Coin
    from app.models.coin_contract import CoinContract
    from app.services.chart_override_service import all_overrides
    from frontend.state.coin_state import _resolve_chart_symbol

    contracts: dict[int, str] = {}
    for cmc_id, address in (
        db.query(Coin.cmc_id, CoinContract.contract_address)
        .join(CoinContract, CoinContract.coin_id == Coin.id)
        .filter(Coin.cmc_id.in_(cmc_ids), CoinContract.contract_address.is_not(None))
        .order_by(CoinContract.is_primary.desc(), CoinContract.sort_order)
    ):
        contracts.setdefault(cmc_id, address)
    overrides = all_overrides()
    items: dict[int, dict] = {}
    for c in db.query(Coin).filter(Coin.cmc_id.in_(cmc_ids)):
        ref = float(c.price_usd or 0)
        row = {
            "market_pairs": c.cached_market_pairs or [], "price_raw": ref,
            "tradingview_dex_symbol": c.tradingview_dex_symbol or "",
            "chart_symbol_override": overrides.get(c.cmc_id, ""),
        }
        items[c.cmc_id] = {
            "cmc_id": c.cmc_id, "symbol": c.symbol or "", "chart_symbol": _resolve_chart_symbol(c.symbol or "", row) or "",
            "ref_price": ref, "contract": contracts.get(c.cmc_id, ""), "name": c.name, "rank": c.cmc_rank,
        }
    return items


def check_once() -> int:
    """One pass over every active alert. Returns how many triggered."""
    from frontend.state.coin_state import _fmt_usd

    SessionLocal, Coin, PriceAlert, alert_service, price_hub = _services()
    db = SessionLocal()
    try:
        alerts = db.query(PriceAlert).filter(PriceAlert.triggered_at.is_(None)).all()
        if not alerts:
            return 0
        items = chart_items(db, {a.cmc_id for a in alerts})
        pending = [(a.user_id, a.id, a.cmc_id, a.direction, float(a.target_price)) for a in alerts]
    finally:
        db.close()

    prices = price_hub.get_prices()
    fired = 0
    for user_id, alert_id, cmc_id, direction, target in pending:
        item = items.get(cmc_id) or {"cmc_id": cmc_id, "symbol": "", "chart_symbol": "", "ref_price": 0.0, "contract": ""}
        symbol, ref = item["symbol"], item["ref_price"]
        quote = prices.get(symbol.upper())
        hub = quote["price"] if quote and price_hub.plausible(quote["price"], ref) else None
        # The chart's own pair first (what the coin page and TradingView show).
        price = _fetched_price(item) or hub or ref
        if price <= 0:
            continue
        hit = price >= target if direction == "above" else price <= target
        if hit and alert_service.mark_triggered(user_id, alert_id, price, _fmt_usd(target), _fmt_usd(price)):
            fired += 1
    return fired


async def run_forever() -> None:
    """Lifespan task: check every CHECK_SECONDS until the server stops."""
    while True:
        try:
            fired = await asyncio.to_thread(check_once)
            from app.services import heartbeat  # repo root is on sys.path after the first check_once

            heartbeat.beat("alert_watcher")  # read by the bot's /site_health
            if fired:
                logger.info("server alert watch: %d alert(s) triggered", fired)
        except Exception:  # noqa: BLE001 - never let one bad pass stop the watcher
            logger.exception("server alert watch pass failed")
        await asyncio.sleep(CHECK_SECONDS)
