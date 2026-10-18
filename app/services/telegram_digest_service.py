"""Gainers & Losers in Telegram: on demand (/gainers_losers_24h, _7d, _1m [band])
and as an automatic digest to every account with Telegram connected.

Digest schedule (Kuala Lumpur time, the app's display zone): every day at 08:00
the 24H Top 100 board and the Fear & Greed Index. Nothing else is sent
automatically (7D, 1 Month, other bands and past days are on-demand only).
A board is only sent once its window has enough history ("ready"); the Fear &
Greed message only once the index shows today's value (it is published at
00:00 UTC = 08:00 KL). Each period is sent once: the last sent day per item is kept in
logs/telegram_digest_sent.json, so a restart never repeats or double-sends.
It runs in the Reflex process only where settings.telegram_digest is true
(live); local and live share one bot, so a second sender would duplicate.
"""
import asyncio
import html
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User
from app.services import price_snapshot_service as ps
from app.services import telegram_notify_service as tg

log = logging.getLogger(__name__)

TZ = ZoneInfo("Asia/Kuala_Lumpur")
SEND_HOUR = 8
GRACE = timedelta(hours=12)  # still sent if the server was down at 08:00
ROWS = 10
DEFAULT_BAND = 100
_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "telegram_digest_sent.json"

# command suffix -> snapshot window name (price_snapshot_service.WINDOWS)
_CMD_WINDOWS = {"24h": "24h", "7d": "7d", "1m": "30d"}
LABELS = {"24h": "24H", "7d": "7D", "30d": "1 Month"}


def _menu() -> list[dict]:
    """The menu entries: each window's Top 100 board."""
    return [
        {"command": f"gainers_losers_{suffix}", "description": f"Top gainers & losers, {LABELS[window]} (Top 100)"}
        for suffix, window in _CMD_WINDOWS.items()
    ]


COMMANDS = _menu()


def parse_command(cmd: str) -> str | None:
    """/gainers_losers_24h -> "24h"; /gainers_losers_7d -> "7d"; /gainers_losers_1m -> "30d".
    Also accepts the hyphenated spelling (/gainer-losers-24H) because Telegram does not allow hyphens in the menu.
    None when it is not one of these (the other rank bands and the past-day boards were removed 2026-10-18)."""
    m = re.fullmatch(r"gainers?_losers?_(24h|7d|1m)", cmd.lower().replace("-", "_"))
    return _CMD_WINDOWS[m.group(1)] if m else None


def command_window(cmd: str) -> str | None:
    return parse_command(cmd)


def _band_label(bucket: int) -> str:
    low = ps.bucket_floor(bucket)
    return f"Top {bucket}" if not low else f"Rank {low + 1}-{bucket}"


def _rows(coins: list[dict]) -> list[str]:
    if not coins:
        return ["   none"]
    return [
        f"{i}. <b>{html.escape(c['symbol'])}</b>  {c['pct_change']:+.2f}%  ·  {tg._fmt_price(c['price_now'])}"
        for i, c in enumerate(coins, 1)
    ]


def _compose(label: str, bucket: int, gainers: list[dict], losers: list[dict], suffix: str = "", note: str = "") -> str:
    head = f"📊 <b>Top Gainers &amp; Losers · {label} · {_band_label(bucket)}{suffix}</b>"
    lines = [head, *([note] if note else []), "", "🟢 <b>Gainers</b>", *_rows(gainers), "", "🔴 <b>Losers</b>", *_rows(losers)]
    return "\n".join(lines)


def build_message(window: str, bucket: int = DEFAULT_BAND, rows: int = ROWS) -> tuple[str, bool]:
    """(HTML text, ready). When the window is still collecting, the text says
    how long is left and ready is False."""
    db = SessionLocal()
    try:
        gainers = ps.get_movers(db, bucket, window, "gainers", rows)
        losers = ps.get_movers(db, bucket, window, "losers", rows)
    finally:
        db.close()
    label = LABELS[window]
    if gainers["status"] != "ready":
        left = gainers["days_remaining"]
        eta = f"about {left} day(s)" if left >= 1 else f"about {gainers['hours_remaining']} hour(s)"
        return f"⏳ The {label} board is still collecting data, ready in {eta}.", False
    return _compose(label, bucket, gainers["coins"], losers["coins"]), True


def handle_command(chat_id: int, window: str) -> None:
    """/gainers_losers_24h | _7d | _1m: the Top 100 board of that window."""
    tg._send(chat_id, build_message(window, DEFAULT_BAND)[0])


# ---- Automatic digest ----------------------------------------------------------------------

def _period_key(now: datetime) -> str:
    return now.date().isoformat()


AUTO_ITEMS = ("24h", "fng")  # the only things sent automatically, once a day


def is_due(item: str, now: datetime) -> bool:
    """08:00 KL (up to GRACE later), every day, for the items in AUTO_ITEMS only."""
    if item not in AUTO_ITEMS:
        return False
    at = now.replace(hour=SEND_HOUR, minute=0, second=0, microsecond=0)
    return at <= now < at + GRACE


def _load_sent() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_sent(state: dict) -> None:
    _STATE_FILE.parent.mkdir(exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state))


def connected_chats() -> list[int]:
    db = SessionLocal()
    try:
        return [r[0] for r in db.query(User.telegram_chat_id).filter(User.telegram_chat_id.is_not(None)).all()]
    finally:
        db.close()


def _deliver(text: str, chats: list[int] | None) -> int:
    sent = 0
    for chat_id in connected_chats() if chats is None else chats:
        try:
            tg._send(chat_id, text)
            sent += 1
        except Exception:  # noqa: BLE001
            log.exception("telegram digest to chat %s failed", chat_id)
    return sent


def send_digest(window: str, chats: list[int] | None = None) -> int:
    """Sends the window's Top 100 board now (ignoring the schedule) to every
    connected account; returns how many chats got it. Nothing is sent while
    the window is still collecting."""
    text, ready = build_message(window)
    return _deliver(text, chats) if ready else 0


# ---- Fear & Greed Index ----------------------------------------------------------------------
# Same free source and labels as the /tools page (Alternative.me), fetched fresh every time.

def fetch_fng() -> dict:
    from app.services import market_tools_service as mts

    mts._cache.pop("fng:alternative", None)  # the command is a manual refresh: skip the 15-minute cache
    return mts.get_fear_greed("alternative_me")


def _fng_dot(value: int) -> str:
    return "🔴" if value < 25 else "🟠" if value < 45 else "🟡" if value < 55 else "🟢"  # the /tools gauge zones


def fng_message(data: dict) -> str:
    now, yesterday = data["value"], data["yesterday"]
    lines = [
        "🧭 <b>Fear &amp; Greed Index</b>",
        "",
        f"{_fng_dot(now)} <b>Now: {now}</b> · {html.escape(data['label'])}",
    ]
    if yesterday["value"] >= 0:
        delta = now - yesterday["value"]
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "="
        change = f"  ({arrow} {abs(delta)})" if delta else "  (no change)"
        lines.append(f"{_fng_dot(yesterday['value'])} Yesterday: {yesterday['value']} · {html.escape(yesterday['label'])}{change}")
    lines += ["", f"<i>{html.escape(data['source'])} · updated {data['updated']} (UTC)</i>"]
    return "\n".join(lines)


def handle_fng(chat_id: int) -> None:
    try:
        text = fng_message(fetch_fng())
    except Exception:  # noqa: BLE001
        log.exception("fear & greed fetch failed")
        text = "Could not load the Fear & Greed Index right now. Try again in a moment."
    tg._send(chat_id, text)


def send_fng_digest(now: datetime, chats: list[int] | None = None) -> int:
    """Sends the index to every connected account, but only once it shows
    today's (UTC) value, so a lagging source never sends yesterday's number as
    "now". Returns how many chats got it."""
    data = fetch_fng()
    if datetime.fromtimestamp(data["ts"], timezone.utc).date() != now.astimezone(timezone.utc).date():
        return 0
    return _deliver(fng_message(data), chats)


def check_and_send(now: datetime | None = None) -> list[str]:
    """One scheduler pass: sends every due, ready, not-yet-sent item of
    AUTO_ITEMS (the 24H board and the Fear & Greed Index). Returns the items
    sent. An item that is not ready yet is retried on the next pass (until its
    grace period ends)."""
    now = now or datetime.now(TZ)
    state = _load_sent()
    key = _period_key(now)
    done = []
    for item in AUTO_ITEMS:
        if not is_due(item, now) or state.get(item) == key:
            continue
        try:
            sent = send_fng_digest(now) if item == "fng" else send_digest(item)
        except Exception:  # noqa: BLE001  (one failing source must not block the other item)
            log.exception("telegram digest item %s failed", item)
            continue
        if sent or not connected_chats():
            state[item] = key
            _save_sent(state)
            done.append(item)
    return done


async def run_digest_loop() -> None:
    """Checks every minute (Reflex lifespan task) where settings.telegram_digest."""
    if not (settings.telegram_digest and tg.configured()):
        return
    log.info("telegram gainers/losers digest scheduler started")
    while True:
        try:
            await asyncio.to_thread(check_and_send)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("telegram digest pass failed")
        await asyncio.sleep(60)
