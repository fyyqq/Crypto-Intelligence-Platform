"""Price alerts checked on the server, 24/7, whether or not a tab is open.

Every CHECK_SECONDS: load every account's active alerts; if there are none,
stop there (no price calls at all). Otherwise price each alerted coin from
the shared exchange price list (app/services/price_hub.py, ~30s fresh, free)
when it is plausible against the coin's stored price, else from the stored
price itself (hourly CoinMarketCap sync), and trigger every alert whose
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


def check_once() -> int:
    """One pass over every active alert. Returns how many triggered."""
    from frontend.state.coin_state import _fmt_usd

    SessionLocal, Coin, PriceAlert, alert_service, price_hub = _services()
    db = SessionLocal()
    try:
        alerts = db.query(PriceAlert).filter(PriceAlert.triggered_at.is_(None)).all()
        if not alerts:
            return 0
        ids = {a.cmc_id for a in alerts}
        stored = {c.cmc_id: (c.symbol, float(c.price_usd or 0)) for c in db.query(Coin).filter(Coin.cmc_id.in_(ids))}
        pending = [(a.user_id, a.id, a.cmc_id, a.direction, float(a.target_price)) for a in alerts]
    finally:
        db.close()

    prices = price_hub.get_prices()
    fired = 0
    for user_id, alert_id, cmc_id, direction, target in pending:
        symbol, ref = stored.get(cmc_id, ("", 0.0))
        quote = prices.get((symbol or "").upper())
        price = quote["price"] if quote and price_hub.plausible(quote["price"], ref) else ref
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
            if fired:
                logger.info("server alert watch: %d alert(s) triggered", fired)
        except Exception:  # noqa: BLE001 - never let one bad pass stop the watcher
            logger.exception("server alert watch pass failed")
        await asyncio.sleep(CHECK_SECONDS)
