"""Gainers & Losers in Telegram: on demand (/gainers_losers_24h, _7d, _1m [band])
and as an automatic digest to every account with Telegram connected.

Digest schedule (Kuala Lumpur time, the app's display zone), 08:00:
  24H board every day, 7D board on Mondays, 1 Month board on the 1st.
A board is only sent once its window has enough history ("ready"); a window
still collecting is skipped silently (no "collecting" spam). Each period is
sent once: the last sent period per window is kept in
logs/telegram_digest_sent.json, so a restart never repeats or double-sends.
It runs in the Reflex process only where settings.telegram_digest is true
(live); local and live share one bot, so a second sender would duplicate.
"""
import asyncio
import html
import json
import logging
import re
from datetime import date, datetime, timedelta
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
    """The menu entries: each window's default board, then its per-band boards
    (/gainers_losers_24h_top200 = ranks 101-200)."""
    rows = []
    for suffix, window in _CMD_WINDOWS.items():
        label = LABELS[window]
        rows.append({"command": f"gainers_losers_{suffix}", "description": f"Top gainers & losers, {label} (Top 100)"})
        for band in ps.BUCKETS:
            low = ps.bucket_floor(band)
            span = f"ranks {low + 1}-{band}" if low else "ranks 1-100"
            rows.append({"command": f"gainers_losers_{suffix}_top{band}", "description": f"{label} gainers & losers, {span}"})
    return rows


COMMANDS = _menu()


def parse_command(cmd: str) -> tuple[str, int | None] | None:
    """/gainers_losers_24h -> ("24h", None); /gainers_losers_7d_top300 -> ("7d", 300).
    Also accepts the hyphenated spelling (/gainer-losers-24H) because Telegram
    does not allow hyphens in the menu. None when it is not one of these."""
    m = re.fullmatch(r"gainers?_losers?_(24h|7d|1m)(?:_top(\d+))?", cmd.lower().replace("-", "_"))
    if not m:
        return None
    band = int(m.group(2)) if m.group(2) else None
    return (_CMD_WINDOWS[m.group(1)], band) if band is None or band in ps.BUCKETS else None


def command_window(cmd: str) -> str | None:
    parsed = parse_command(cmd)
    return parsed[0] if parsed else None


def parse_band(arg: str) -> int | None:
    """"" -> Top 100; "200"/"top200" -> 101-200 band; anything else None."""
    arg = arg.lower().removeprefix("top").strip()
    if not arg:
        return DEFAULT_BAND
    return int(arg) if arg.isdigit() and int(arg) in ps.BUCKETS else None


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


# ---- Past days: /gainers_losers_13_10_2026[_7d][_top200] ------------------------------------

def parse_date_command(cmd: str) -> tuple[date | None, str, int | None] | None:
    """The date comes last: /gainers_losers_13_10_2026 -> (date(2026,10,13), "24h", None);
    /gainers_losers_7d_top200_13_10_2026 -> (.., "7d", 200); the window and the
    band are optional (default 24H, Top 100). The date is None when it is not a
    real calendar day. Hyphens work too (13-10-2026). None if not this command."""
    m = re.fullmatch(
        r"gainers?_losers?(?:_(24h|7d|1m))?(?:_top(\d+))?_(\d{1,2})_(\d{1,2})_(\d{4})", cmd.lower().replace("-", "_")
    )
    if not m:
        return None
    window = _CMD_WINDOWS[m.group(1) or "24h"]
    band = int(m.group(2)) if m.group(2) else None
    if band is not None and band not in ps.BUCKETS:
        return None
    try:
        day = date(int(m.group(5)), int(m.group(4)), int(m.group(3)))
    except ValueError:
        day = None
    return day, window, band


def build_past_message(day: date, window: str, bucket: int = DEFAULT_BAND, rows: int = ROWS) -> str:
    """A saved daily board (the site's calendar, UTC days)."""
    db = SessionLocal()
    try:
        saved = ps.load_daily_movers(db, day).get(window)
        first, last = ps.saved_days(db)
    finally:
        db.close()
    label, pretty = LABELS[window], f"{day.day} {day.strftime('%b %Y')}"
    if not saved:
        have = f" Saved boards exist from {first.day} {first.strftime('%b %Y')} to {last.day} {last.strftime('%b %Y')}." if first else ""
        return f"No saved {label} board for {pretty}.{have}"
    as_of = max(c["now_at"] for c in saved).strftime("%d %b %H:%M UTC")
    return _compose(
        label, bucket, ps.rank_movers(saved, bucket, "gainers", rows), ps.rank_movers(saved, bucket, "losers", rows),
        suffix=f" · {pretty}", note=f"<i>Saved board, as of {as_of}</i>",
    )


def handle_past(chat_id: int, day: date | None, window: str, band: int | None) -> None:
    if day is None:
        tg._send(chat_id, "That is not a valid date. Use /gainers_losers_13_10_2026 (day_month_year).")
        return
    tg._send(chat_id, build_past_message(day, window, band or DEFAULT_BAND))


def handle_command(chat_id: int, window: str, arg: str = "", band: int | None = None) -> None:
    """`band` comes from the command name (_top200); otherwise an optional
    argument (/gainers_losers_24h 200) picks it; default Top 100."""
    bucket = band or parse_band(arg)
    if bucket is None:
        tg._send(chat_id, "Usage: /gainers_losers_24h or /gainers_losers_24h_top200 (bands: top100, top200, top300, top400, top500)")
        return
    tg._send(chat_id, build_message(window, bucket)[0])


# ---- Automatic digest ----------------------------------------------------------------------

def _period_key(window: str, now: datetime) -> str:
    if window == "24h":
        return now.date().isoformat()
    if window == "7d":
        iso = now.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return f"{now.year}-{now.month:02d}"


def is_due(window: str, now: datetime) -> bool:
    """08:00 KL (up to GRACE later) on the window's day: every day / Monday / the 1st."""
    if window == "7d" and now.weekday() != 0:
        return False
    if window == "30d" and now.day != 1:
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


def send_digest(window: str, chats: list[int] | None = None) -> int:
    """Sends the window's Top 100 board now (ignoring the schedule) to every
    connected account; returns how many chats got it. Nothing is sent while
    the window is still collecting."""
    text, ready = build_message(window)
    if not ready:
        return 0
    sent = 0
    for chat_id in connected_chats() if chats is None else chats:
        try:
            tg._send(chat_id, text)
            sent += 1
        except Exception:  # noqa: BLE001
            log.exception("telegram digest to chat %s failed", chat_id)
    return sent


def check_and_send(now: datetime | None = None) -> list[str]:
    """One scheduler pass: sends every due, ready, not-yet-sent window. Returns
    the windows sent. A due window that is still collecting is retried on the
    next pass (until its grace period ends)."""
    now = now or datetime.now(TZ)
    state = _load_sent()
    done = []
    for window in ps.WINDOWS:
        key = _period_key(window, now)
        if not is_due(window, now) or state.get(window) == key:
            continue
        if send_digest(window) or not connected_chats():
            state[window] = key
            _save_sent(state)
            done.append(window)
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
