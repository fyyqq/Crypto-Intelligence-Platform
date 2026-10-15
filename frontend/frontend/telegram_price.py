"""The Telegram bot's /price command: the live price of every coin that has the typed ticker.

Each coin is priced from the same chart pair the coin page and its TradingView chart use (frontend/alert_watcher.py
chart_items -> live_prices.fetch_live_prices_with_source, the call behind the page's header price); only when that pair cannot be
read does it fall back to the exchange list / DEX pool, and last the stored (hourly synced) price, which is then
marked as not live. Registered in frontend.py with telegram_notify_service.set_price_command."""

from __future__ import annotations

import html
import sys
from pathlib import Path

MAX_COINS = 8  # more coins than this share one ticker only for junk tickers; keep the message short

_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def price_message(ticker: str) -> str:
    """HTML text for /price <ticker> (blocking: database + exchange calls)."""
    if _ROOT not in sys.path:
        sys.path.append(_ROOT)
    from sqlalchemy import func

    from app.core.database import SessionLocal
    from app.models.coin import Coin
    from frontend.alert_watcher import chart_items
    from frontend.live_prices import fetch_live_prices_with_source
    from frontend.state.coin_state import _fmt_usd

    symbol = ticker.lstrip("$").strip().upper()
    db = SessionLocal()
    try:
        ids = [
            cmc_id
            for (cmc_id,) in db.query(Coin.cmc_id)
            .filter(func.upper(Coin.symbol) == symbol)
            .order_by(Coin.cmc_rank.asc().nulls_last(), Coin.market_cap_usd.desc().nulls_last())
        ]
        items = chart_items(db, set(ids)) if ids else {}
    finally:
        db.close()
    if not ids:
        return f"No coin found with the ticker <b>{html.escape(symbol)}</b>."
    shown = [items[i] for i in ids if i in items][:MAX_COINS]
    live = fetch_live_prices_with_source(shown)
    head = f"💰 <b>{html.escape(symbol)}</b>" + (f" ({len(ids)} coins with this ticker)" if len(ids) > 1 else "")
    lines = [head]
    for it in shown:
        price, source_kind = live.get(it["cmc_id"], (None, ""))
        rank = f" #{it['rank']}" if it.get("rank") else ""
        title = f"<b>{html.escape(it['name'] or symbol)}</b>{rank}"
        if price:
            source = {
                "chart": f"TradingView chart: {html.escape(it['chart_symbol'])}",
                "exchange": "live exchange price",
                "dex": "live DEX pool price",
            }[source_kind]
            lines.append(f"\n{title}\n<b>{_fmt_usd(price)}</b>\n<i>{source}</i>")
        elif it.get("ref_price"):
            lines.append(f"\n{title}\n<b>{_fmt_usd(it['ref_price'])}</b>\n<i>last synced price (no live feed found)</i>")
        else:
            lines.append(f"\n{title}\nno price available")
    if len(ids) > MAX_COINS:
        lines.append(f"\n…and {len(ids) - MAX_COINS} more with this ticker.")
    return "\n".join(lines)[:4000]
