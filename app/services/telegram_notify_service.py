"""Telegram delivery of notifications (price alerts) through our own bot
(TELEGRAM_BOT_TOKEN, separate from the news listener's user session).

Linking: the account clicks "Connect Telegram" -> `start_link` makes a one-time
code and a t.me deep link; the user presses Start in the bot; `poll_link` reads
the bot's pending updates (on demand only, never a permanent poller, so local
and live can share one bot token) and stores the chat id on the account.
Sending: `send_channel` is registered with notification_service.register_channel."""
import html
import logging
import secrets
import time

import httpx
from sqlalchemy import update

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User

log = logging.getLogger(__name__)

_CODE_TTL = 600  # seconds a link code stays valid
_codes: dict[str, tuple[int, float]] = {}  # code -> (user_id, expires_at); single backend worker
_bot_username: str | None = None


def _token() -> str:
    return settings.telegram_bot_token.strip()


def configured() -> bool:
    return bool(_token())


def _api(method: str, **params) -> dict:
    r = httpx.post(f"https://api.telegram.org/bot{_token()}/{method}", json=params, timeout=10)
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


def poll_link(user_id: int) -> bool:
    """True once this account is connected. Reads the bot's pending /start
    updates and links whichever codes they carry (so another account's press
    is not lost), then acknowledges them so they are not read twice."""
    updates = _api("getUpdates", timeout=0, allowed_updates=["message"])
    for u in updates:
        msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat = msg.get("chat") or {}
        if not text.startswith("/start ") or chat.get("type") != "private":
            continue
        code = text.split(" ", 1)[1].strip()
        owner = _codes.get(code)
        if not owner or owner[1] < time.time():
            continue
        del _codes[code]
        _set_chat_id(owner[0], chat["id"])
        try:
            _send(chat["id"], "✅ <b>Repace alerts connected.</b> Triggered price alerts will arrive here.")
        except Exception:  # noqa: BLE001
            log.exception("telegram confirmation failed")
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
    _send(chat_id, "\n".join(lines))
