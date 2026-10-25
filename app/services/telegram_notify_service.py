"""Telegram delivery of notifications (price alerts) through our own bot
(TELEGRAM_BOT_TOKEN, separate from the news listener's user session).

Linking: the account clicks "Connect Telegram" -> `start_link` makes a one-time
code and a t.me deep link; the user presses Start in the bot; `poll_link` reads
the bot's pending updates (on demand only, never a permanent poller, so local
and live can share one bot token) and stores the chat id on the account.
Sending: `send_channel` is registered with notification_service.register_channel."""
import asyncio
import html
import logging
import re
import secrets
import time

import httpx
from sqlalchemy import update

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.price_alert import PriceAlert
from app.models.user import User

log = logging.getLogger(__name__)

_CODE_TTL = 600  # seconds a link code stays valid
_codes: dict[str, tuple[int, float]] = {}  # code -> (user_id, expires_at); single backend worker
_bot_username: str | None = None


def _token() -> str:
    return settings.telegram_bot_token.strip()


def configured() -> bool:
    return bool(_token())


# IPv4 only: from the live server (Contabo) Telegram's IPv6 address is flaky
# (TLS handshakes hang 10s+ or time out) while IPv4 answers in ~0.1s, and
# Python tries IPv6 first. Binding the local address to 0.0.0.0 forces IPv4.
_sync_client = httpx.Client(transport=httpx.HTTPTransport(local_address="0.0.0.0"), timeout=10)
_async_client = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0"), timeout=40)


def _api(method: str, **params) -> dict:
    r = _sync_client.post(f"https://api.telegram.org/bot{_token()}/{method}", json=params)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description')}")
    return data["result"]


def bot_username() -> str:
    global _bot_username
    if not _bot_username:
        _bot_username = _api("getMe")["username"]
    return _bot_username


def chat_id_for(user_id: int) -> int | None:
    db = SessionLocal()
    try:
        return db.query(User.telegram_chat_id).filter(User.id == user_id).scalar()
    finally:
        db.close()


def _set_chat_id(user_id: int, chat_id: int | None) -> None:
    db = SessionLocal()
    try:
        db.execute(update(User).where(User.id == user_id).values(telegram_chat_id=chat_id))
        db.commit()
    finally:
        db.close()


def start_link(user_id: int) -> tuple[str, str]:
    """Returns (code, t.me deep link). Old codes of that account are dropped."""
    now = time.time()
    for c in [c for c, (u, exp) in _codes.items() if u == user_id or exp < now]:
        _codes.pop(c, None)
    code = secrets.token_urlsafe(8)
    _codes[code] = (user_id, now + _CODE_TTL)
    return code, f"https://t.me/{bot_username()}?start={code}"


def _handle_start(msg: dict) -> None:
    """`/start <code>` in a private chat links that chat to the code's account."""
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    code = text.split(" ", 1)[1].strip() if text.startswith("/start ") else ""
    owner = _codes.get(code)
    if not owner or owner[1] < time.time() or chat.get("type") != "private":
        return
    del _codes[code]
    _set_chat_id(owner[0], chat["id"])
    try:
        _send(chat["id"], "✅ <b>Repace alerts connected.</b> Triggered price alerts will arrive here.\n"
                          "Commands: /alerts (all active alerts). Send /view_all_command for the full list.")
    except Exception:  # noqa: BLE001
        log.exception("telegram confirmation failed")


def poll_link(user_id: int) -> bool:
    """True once this account is connected. With the command listener running
    (settings.telegram_bot_polling) it already links /start presses, so this
    only checks the account. Otherwise (local dev) it reads the bot's pending
    updates itself, links whichever codes they carry and acknowledges them."""
    if not settings.telegram_bot_polling:
        updates = _api("getUpdates", timeout=0, allowed_updates=["message"])
        for u in updates:
            _handle_start(u.get("message") or {})
        if updates:
            _api("getUpdates", offset=updates[-1]["update_id"] + 1, timeout=0)
    return chat_id_for(user_id) is not None


def disconnect(user_id: int) -> None:
    _set_chat_id(user_id, None)


def _send(chat_id: int, text: str) -> None:
    _api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)


def send_test(user_id: int) -> bool:
    chat_id = chat_id_for(user_id)
    if not chat_id:
        return False
    _send(chat_id, "🔔 <b>Test message</b>\nTelegram alerts are working.")
    return True


def send_channel(user_id: int, payload: dict) -> None:
    """notification_service channel: sends every notification of a connected account."""
    if not configured():
        return
    chat_id = chat_id_for(user_id)
    if not chat_id:
        return
    icon = {"up": "🟢", "down": "🔴"}.get(payload.get("tone"), "🔔")
    lines = [f"{icon} <b>{html.escape(payload['title'])}</b>"]
    if payload.get("body"):
        lines.append(html.escape(payload["body"]))
    link = payload.get("link_url")
    if link and link.startswith("/"):
        base = settings.public_site_url.rstrip("/")
        lines.append(f'<a href="{html.escape(base + link)}">Open on Repace</a>')
    text = "\n".join(lines)
    for attempt in range(1, SEND_ATTEMPTS + 1):  # a network hiccup must not lose a triggered alert
        try:
            _send(chat_id, text)
            return
        except Exception:  # noqa: BLE001
            if attempt == SEND_ATTEMPTS:
                raise
            log.warning("telegram alert to chat %s failed (attempt %d), retrying", chat_id, attempt)
            time.sleep(SEND_RETRY_SECONDS * attempt)


SEND_ATTEMPTS = 3
SEND_RETRY_SECONDS = 2


# ---- Commands (/alerts, /alert ETH) -------------------------------------------------------

COMMANDS = [
    {"command": "view_all_command", "description": "Show all commands"},
    {"command": "clear_chat", "description": "Delete this chat's messages (last 48 hours)"},
    {"command": "site_health", "description": "Site and data health check"},
    {"command": "ai", "description": "AI usage today and the free AI limit left"},
    {"command": "fear_greed_index", "description": "Fear & Greed Index: now and yesterday"},
    {"command": "forex_factory", "description": "This month's CPI, PPI, FOMC, jobs report & Fed speeches"},
    {"command": "alerts", "description": "Show list of active alerts"},
    {"command": "price", "description": "Live price of a coin by ticker, e.g. /price $meme"},
    {"command": "portfolio", "description": "Your MEXC portfolio: balance, P/L, holdings, limit & stop orders"},
    {"command": "currency_converter", "description": "Convert $ to RM or RM to $, e.g. /currency_converter $1000"},
    {"command": "pnl_calculator", "description": "Profit / loss calculator, e.g. /pnl_calculator $1000 + 50%"},
]


OVERVIEW_COMMANDS = ("view_all_command", "view_all_commands", "help")  # all show the same list


def commands_overview() -> str:
    """The /view_all_command text."""
    return "\n".join([
        "📖 <b>All commands</b>",
        "",
        "<b>Price alerts</b>",
        "/alerts - all your active alerts",
        "",
        "<b>Calculators</b> (USD and MYR, live rate)",
        "<code>/currency-converter $1000</code> - dollars to ringgit; <code>/currency-converter RM1000</code> - ringgit to dollars",
        "<code>/pnl-calculator $1000 + 50%</code> - profit: $1,000 + 50% = $1,500",
        "<code>/pnl-calculator $1000 - 50%</code> - loss: $1,000 - 50% = $500. RM works too: /pnl-calculator RM4000 - 25%",
        "",
        "<b>Portfolio</b>",
        "/portfolio - your MEXC balance, profit/loss, holdings and open limit / stop orders (only for the account owner)",
        "",
        "<b>Market</b>",
        "<code>/price ${ticker}</code> - live price from the TradingView chart pair, every coin with that ticker, e.g. /price $meme",
        "/fear_greed_index - Fear &amp; Greed Index, now and yesterday",
        "/forex_factory - this month's US CPI, PPI, FOMC, Non-Farm Employment and Fed speeches (Kuala Lumpur time). /forex-factory works too",
        "",
        "<b>System</b>",
        "/site_health - is the site and its data (prices, news, CoinMarketCap, alerts, server) healthy?",
        "/ai - how many free AI calls are used today, how many are left and when the limit resets (08:00 KL)",
        "/clear_chat - deletes this chat's messages (Telegram lets a bot delete only the last 48 hours)",
        "",
        "<b>Gainers &amp; Losers</b> (Top 100, 10 gainers + 10 losers)",
        "/gainers_losers_24h",
        "/gainers_losers_7d",
        "/gainers_losers_1m",
        "",
        "",
        "Boards update once an hour. Sent automatically every day at 08:00 (Kuala Lumpur): the 24H Top 100 board and the Fear &amp; Greed Index. Other boards only when you ask.\n"
        "Reminders 7 days, 3 days and 1 hour before every CPI and PPI release, Non-Farm Employment report, FOMC event and Fed Chair speech are sent automatically.",
    ])


# /clear_chat: Telegram's deleteMessages takes up to 100 message ids per call and silently skips ids that do
# not exist or cannot be deleted. A bot may delete a message only if it is under 48 hours old (its own
# messages anywhere, and the user's messages in a private chat); older ones stay, Telegram's own "Clear
# history" removes those. Ids in a private chat are sequential, so the command walks back from its own id.
CLEAR_MAX_IDS = 3000
CLEAR_BATCH = 100


def clear_chat(chat_id: int, from_message_id: int, max_ids: int | None = None) -> int:
    """Deletes message ids from_message_id, from_message_id-1, ... (up to max_ids of them) in this chat,
    newest first, 100 per request. Returns the number of ids tried (Telegram does not say how many
    existed). A failing batch (e.g. a rate limit) is skipped, never raised."""
    low = max(1, from_message_id - (max_ids or CLEAR_MAX_IDS) + 1)
    tried = 0
    top = from_message_id
    while top >= low:
        ids = list(range(top, max(low, top - CLEAR_BATCH + 1) - 1, -1))
        try:
            _api("deleteMessages", chat_id=chat_id, message_ids=ids)
        except Exception:  # noqa: BLE001
            log.warning("deleteMessages batch %s..%s failed", ids[0], ids[-1], exc_info=True)
        tried += len(ids)
        top -= CLEAR_BATCH
        if top >= low:
            time.sleep(0.15)  # stay well inside Telegram's rate limits
    return tried


def menu_commands() -> list[dict]:
    from app.services import telegram_digest_service

    return COMMANDS + telegram_digest_service.COMMANDS

_fmt_price = lambda v: f"${v:g}"  # noqa: E731  (replaced by the frontend's _fmt_usd, Core rule 1)


def set_price_formatter(fn) -> None:
    global _fmt_price
    _fmt_price = fn


_price_command = None  # frontend/telegram_price.py::price_message, registered by frontend.py


def set_price_command(fn) -> None:
    global _price_command
    _price_command = fn


def _user_for_chat(chat_id: int) -> int | None:
    db = SessionLocal()
    try:
        return db.query(User.id).filter(User.telegram_chat_id == chat_id).scalar()
    finally:
        db.close()


def format_alerts(user_id: int) -> str:
    db = SessionLocal()
    try:
        rows = (
            db.query(PriceAlert)
            .filter(PriceAlert.user_id == user_id, PriceAlert.triggered_at.is_(None))
            .order_by(PriceAlert.symbol, PriceAlert.target_price)
            .all()
        )
    finally:
        db.close()
    if not rows:
        return "You have no active alerts."
    by_coin: dict[str, list[str]] = {}
    for r in rows:
        arrow = "🟢 above" if r.direction == "above" else "🔴 below"
        by_coin.setdefault(r.symbol.upper(), []).append(f"{arrow} {_fmt_price(r.target_price)}")
    lines = [f"🔔 <b>Active alerts ({len(rows)})</b>"]
    for sym, items in by_coin.items():
        lines.append(f"<b>{html.escape(sym)}</b>")
        lines.extend(f"   {i}" for i in items)
    return "\n".join(lines)[:4000]


_PORTFOLIO_MAX_CHARS = 3900  # Telegram's limit is 4096


def _sign_icon(v: float) -> str:
    return "🟢" if v > 0 else "🔴" if v < 0 else "⚪"


def _money_fns(rate: float, currency: str):
    """(money, signed money) formatters for a USD amount in `currency` (MYR at `rate`, else USD)."""
    from app.services import fx_service as fx

    return (
        lambda v: fx.format_amount(v * rate, currency),
        lambda v: fx.format_amount(v * rate, currency, signed=True),
    )


def format_portfolio(user_id: int) -> str:
    """The /portfolio reply: total balance, 24h change, profit/loss, every holding and every open limit / stop
    order of the MEXC account (read-only, app/services/mexc_service.py). Money amounts (total balance, 24h change,
    profit/loss, holding values, stablecoins, locked in orders) are in MYR at the live rate, like the Portfolio page;
    COIN prices (current, average buy, order prices) stay in USD. Only an account listed in MEXC_VIEWER_EMAILS gets
    it; anyone else gets one neutral line and MEXC is not called."""
    from app.services import fx_service as fx
    from app.services import mexc_service as m

    db = SessionLocal()
    try:
        email = db.query(User.email).filter(User.id == user_id).scalar() or ""
    finally:
        db.close()
    if not m.can_view(email):
        return "Portfolio is not available for this account."
    snap = m.portfolio(user_id)
    if not snap.get("ok"):
        return "💼 <b>Portfolio</b> is unavailable right now: " + html.escape(snap.get("error") or "no data yet.")
    info = fx.get_rate("MYR")  # blocking, cached 60 s, never raises
    currency, rate = ("MYR", info["rate"]) if info else ("USD", 1.0)
    money, signed = _money_fns(rate, currency)

    def pnl(v: float, pct: float) -> str:
        return f"{_sign_icon(v)} {signed(v)} ({pct:+.2f}%)"

    lines = ["💼 <b>MEXC portfolio</b>" + (" (demo data)" if snap.get("demo") else "")]
    if snap.get("error"):
        lines.append("⚠️ " + html.escape(snap["error"]) + " (showing the last data)")
    lines.append(
        f"<i>Amounts in MYR (1 USD = {rate:.4f} MYR); coin prices in USD</i>" if currency == "MYR"
        else "<i>The live MYR rate is unavailable right now, so amounts are in USD</i>"
    )
    lines += [
        f"Total balance: <b>{money(snap['total_value'])}</b>",
        f"24h: {pnl(snap['change_24h'], snap['change_24h_pct'])}",
    ]
    if snap["with_cost"]:
        lines.append(f"P/L: {pnl(snap['pnl'], snap['pnl_pct'])}")
    lines.append(f"Stablecoins: {money(snap['stable_value'])} · In open orders: {money(snap['locked_value'])}")
    lines += ["", f"<b>Holdings ({sum(1 for h in snap['holdings'] if not h['is_stable'])} coins)</b>"]
    for h in snap["holdings"]:
        row = f"• <b>{html.escape(h['asset'])}</b> {m.fmt_qty(h['amount'])}"
        if h["is_stable"]:
            row += f" = {money(h['value'])}"
        else:
            row += f" @ {_fmt_price(h['price'])} = {money(h['value'])}"
            if h["avg_price"] > 0:
                row += f" · avg {_fmt_price(h['avg_price'])} · P/L {pnl(h['pnl'], h['pnl_pct'])}"
        lines.append(row)
    if snap["dust_count"]:
        lines.append(f"<i>+ {snap['dust_count']} small balances ({money(snap['dust_value'])})</i>")
    lines += ["", f"<b>Open orders ({len(snap['orders'])})</b>"]
    if not snap["orders"]:
        lines.append("None.")
    for o in snap["orders"]:
        icon = "🟢 Buy" if o["side"] == "BUY" else "🔴 Sell"
        row = f"{icon} <b>{html.escape(o['asset'])}</b> · {o['type_label']} " + (_fmt_price(o["price"]) if o["price"] else "market")
        if o["stop_price"]:
            row += f" (trigger {_fmt_price(o['stop_price'])})"
        row += f" · {m.fmt_qty(o['qty'])}"
        if o["distance_pct"]:
            row += f" · {abs(o['distance_pct']):.2f}% {'above' if o['distance_pct'] > 0 else 'below'} market"
        lines.append(row)
    text = "\n".join(lines)
    if len(text) > _PORTFOLIO_MAX_CHARS:  # cut at a line end, never inside an HTML tag
        text = text[:_PORTFOLIO_MAX_CHARS].rsplit("\n", 1)[0] + "\n…"
    return text


def handle_message(msg: dict) -> None:
    """One incoming bot message: /start <code> links, /alerts and the other commands reply."""
    chat = msg.get("chat") or {}
    text = (msg.get("text") or "").strip()
    if chat.get("type") != "private" or not text.startswith("/"):
        return
    parts = text.split()
    cmd = parts[0][1:].split("@")[0].lower()
    if cmd in ("forex-factory", "currency-converter", "pnl-calculator"):  # Telegram's menu cannot hold a hyphen; typed by hand it is fine
        cmd = cmd.replace("-", "_")
    arg = parts[1] if len(parts) > 1 else ""
    rest = text.split(None, 1)[1] if len(parts) > 1 else ""  # everything after the command (the calculators take several words)
    if cmd == "start":
        if arg:
            _handle_start(msg)
        else:
            _send(chat["id"], "Repace price alerts. Connect your account from Repace > Notifications > Connect Telegram.")
        return
    if cmd == "clear_chat":  # acts only on the chat that sent it, so it needs no linked account
        clear_chat(chat["id"], int(msg.get("message_id") or 0))
        _send(chat["id"], "🧹 Chat cleared. Telegram lets a bot delete only messages from the last 48 hours; "
                          "for anything older use Telegram's own Clear history.")
        return
    from app.services import telegram_digest_service as digest

    if cmd in OVERVIEW_COMMANDS:  # needs no account, shows no private data
        _send(chat["id"], commands_overview())
        return
    parsed = digest.parse_command(cmd)
    if cmd == "ai_usage":  # a longer name that works too
        cmd = "ai"
    if cmd not in ("alerts", "command1", "fear_greed_index", "site_health", "ai", "forex_factory", "price", "portfolio", "currency_converter", "pnl_calculator") and not parsed:
        return
    user_id = _user_for_chat(chat["id"])
    if not user_id:
        _send(chat["id"], "This chat is not connected. Open Repace > Notifications > Connect Telegram.")
    elif cmd == "site_health":
        from app.services import site_health_service

        _send(chat["id"], site_health_service.build_message())
    elif cmd == "ai":
        from app.services import ai_usage_service

        _send(chat["id"], ai_usage_service.build_message())
    elif cmd == "portfolio":
        _send(chat["id"], format_portfolio(user_id))
    elif cmd in ("currency_converter", "pnl_calculator"):
        from app.services import calc_service

        _send(chat["id"], calc_service.converter_message(rest) if cmd == "currency_converter" else calc_service.pnl_message(rest))
    elif cmd == "fear_greed_index":
        digest.handle_fng(chat["id"])
    elif cmd == "price":
        sym = arg.lstrip("$").strip()
        if not re.fullmatch(r"[A-Za-z0-9]{1,20}", sym) or _price_command is None:
            _send(chat["id"], "Usage: /price $meme (a coin's ticker)")
        else:
            _send(chat["id"], _price_command(sym))
    elif cmd == "forex_factory":
        from app.services import macro_reminder_service

        macro_reminder_service.handle_command(chat["id"])
    elif parsed:
        digest.handle_command(chat["id"], parsed)
    else:  # /alerts (and the old /command1 name)
        _send(chat["id"], format_alerts(user_id))


async def run_poller() -> None:
    """Long-polls the bot for commands, only when settings.telegram_bot_polling
    (one server). Runs inside the Reflex process as a lifespan task."""
    if not (configured() and settings.telegram_bot_polling):
        return
    try:
        await asyncio.to_thread(_api, "setMyCommands", commands=menu_commands())
    except Exception:  # noqa: BLE001
        log.exception("telegram setMyCommands failed")
    offset = None
    log.info("telegram command listener started")
    while True:
        try:
            params = {"timeout": 25, "allowed_updates": ["message"]}
            if offset is not None:
                params["offset"] = offset
            r = await _async_client.post(f"https://api.telegram.org/bot{_token()}/getUpdates", json=params)
            data = r.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("description"))
            for u in data["result"]:
                offset = u["update_id"] + 1
                try:
                    await asyncio.to_thread(handle_message, u.get("message") or {})
                except Exception:  # noqa: BLE001
                    log.exception("telegram command failed")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.warning("telegram poll failed, retrying in 5s", exc_info=True)
            await asyncio.sleep(5)
