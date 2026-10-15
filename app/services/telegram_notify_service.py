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
                          "Commands: /alerts (all active alerts), /alert ETH (one coin).")
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
    {"command": "view_all_command", "description": "Show all commands, incl. the ones that need a {coin} or {date}"},
    {"command": "clear_chat", "description": "Delete this chat's messages (last 48 hours)"},
    {"command": "site_health", "description": "Site and data health check"},
    {"command": "fear_greed_index", "description": "Fear & Greed Index: now and yesterday"},
    {"command": "forex_factory", "description": "This month's CPI, FOMC, jobs report & Fed speeches"},
    {"command": "alerts", "description": "Show list of active alerts"},
    {"command": "alert", "description": "Show active alerts for one coin, e.g. /alert ETH"},
]


OVERVIEW_COMMANDS = ("view_all_command", "view_all_commands", "help")  # all show the same list


def commands_overview() -> str:
    """The /view_all_command text. {coin} and {date} are the parts the user fills in."""
    return "\n".join([
        "📖 <b>All commands</b>",
        "",
        "<b>Price alerts</b>",
        "/alerts - all your active alerts",
        "<code>/alert {coin}</code> - active alerts of one coin, e.g. /alert ETH",
        "",
        "<b>Market</b>",
        "/fear_greed_index - Fear &amp; Greed Index, now and yesterday",
        "/forex_factory - this month's US CPI, FOMC, Non-Farm Employment and Fed speeches (Kuala Lumpur time). /forex-factory works too",
        "",
        "<b>System</b>",
        "/site_health - is the site and its data (prices, news, CoinMarketCap, alerts, server) healthy?",
        "/clear_chat - deletes this chat's messages (Telegram lets a bot delete only the last 48 hours)",
        "",
        "<b>Gainers &amp; Losers</b> (Top 100, 10 gainers + 10 losers)",
        "/gainers_losers_24h",
        "/gainers_losers_7d",
        "/gainers_losers_1m",
        "",
        "<b>Other rank bands</b>: add _top200 (ranks 101-200), _top300, _top400 or _top500",
        "/gainers_losers_24h_top200",
        "/gainers_losers_7d_top300",
        "/gainers_losers_1m_top500",
        "",
        "<b>Past days</b> (saved boards, UTC days since 11 Oct 2026)",
        "<code>/gainers_losers_{date}</code> - 24H, Top 100, e.g. /gainers_losers_13_10_2026",
        "<code>/gainers_losers_7d_top200_{date}</code> - timeframe (24h, 7d, 1m) and band (top100...top500) are optional, the date is always last",
        "{date} = day_month_year, e.g. 13_10_2026",
        "",
        "Boards update once an hour. Sent automatically every day at 08:00 (Kuala Lumpur): the 24H Top 100 board and the Fear &amp; Greed Index. Other boards only when you ask.\n"
        "Reminders 7 days, 3 days and 1 hour before every CPI release, Non-Farm Employment report, FOMC event and Fed Chair speech are sent automatically.",
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


def _user_for_chat(chat_id: int) -> int | None:
    db = SessionLocal()
    try:
        return db.query(User.id).filter(User.telegram_chat_id == chat_id).scalar()
    finally:
        db.close()


def format_alerts(user_id: int, symbol: str | None = None) -> str:
    db = SessionLocal()
    try:
        q = db.query(PriceAlert).filter(PriceAlert.user_id == user_id, PriceAlert.triggered_at.is_(None))
        if symbol:
            q = q.filter(PriceAlert.symbol.ilike(symbol))
        rows = q.order_by(PriceAlert.symbol, PriceAlert.target_price).all()
    finally:
        db.close()
    if not rows:
        return f"No active alerts for <b>{html.escape(symbol.upper())}</b>." if symbol else "You have no active alerts."
    by_coin: dict[str, list[str]] = {}
    for r in rows:
        arrow = "🟢 above" if r.direction == "above" else "🔴 below"
        by_coin.setdefault(r.symbol.upper(), []).append(f"{arrow} {_fmt_price(r.target_price)}")
    head = f"🔔 <b>{html.escape(symbol.upper())} alerts ({len(rows)})</b>" if symbol else f"🔔 <b>Active alerts ({len(rows)})</b>"
    lines = [head]
    for sym, items in by_coin.items():
        if not symbol:
            lines.append(f"<b>{html.escape(sym)}</b>")
        lines.extend(f"   {i}" for i in items)
    return "\n".join(lines)[:4000]


def handle_message(msg: dict) -> None:
    """One incoming bot message: /start <code> links, /alerts and /alert <COIN> reply."""
    chat = msg.get("chat") or {}
    text = (msg.get("text") or "").strip()
    if chat.get("type") != "private" or not text.startswith("/"):
        return
    parts = text.split()
    cmd = parts[0][1:].split("@")[0].lower()
    if cmd == "forex-factory":  # Telegram's menu cannot hold a hyphen; typed by hand it is fine
        cmd = "forex_factory"
    arg = parts[1] if len(parts) > 1 else ""
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
    past = digest.parse_date_command(cmd)
    if cmd not in ("alerts", "command1", "alert", "fear_greed_index", "site_health", "forex_factory") and not parsed and not past:
        return
    user_id = _user_for_chat(chat["id"])
    if not user_id:
        _send(chat["id"], "This chat is not connected. Open Repace > Notifications > Connect Telegram.")
    elif cmd == "site_health":
        from app.services import site_health_service

        _send(chat["id"], site_health_service.build_message())
    elif cmd == "fear_greed_index":
        digest.handle_fng(chat["id"])
    elif cmd == "forex_factory":
        from app.services import macro_reminder_service

        macro_reminder_service.handle_command(chat["id"])
    elif parsed:
        digest.handle_command(chat["id"], parsed[0], arg, parsed[1])
    elif past:
        digest.handle_past(chat["id"], *past)
    elif cmd == "alert":
        sym = arg.lstrip("$").strip()
        if not re.fullmatch(r"[A-Za-z0-9]{1,20}", sym):
            _send(chat["id"], "Usage: /alert ETH")
        else:
            _send(chat["id"], format_alerts(user_id, sym))
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
