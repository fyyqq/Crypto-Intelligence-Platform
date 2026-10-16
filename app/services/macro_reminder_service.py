"""Forex Factory events in Telegram: reminders before the big US events and the /forex_factory month list.

Reminders (to every account with Telegram connected): 7 days, 3 days and 1 hour before each CPI and PPI release,
jobs report (Non-Farm Employment Change), FOMC event (rate decision, statement, press conference, minutes)
and Fed Chair speech. Single FOMC members' speeches (about ten a week, low impact) are only in the month
list, not reminded. Events that happen at the same time (the four CPI numbers) are one reminder.

Each reminder is sent once: the offsets already sent per event are kept in logs/macro_reminders_sent.json,
so a restart never repeats one. An event first seen late (the free feed shows an event only in its own
week, so a CPI the feed does not publish early is only known from FRED's calendar, see
macro_calendar_service) gets ONE message for the tightest offset already reached, not three at once.
It runs in the Reflex process only where settings.telegram_digest is true (live): local and live share
one bot, so a second sender would duplicate.
"""
import asyncio
import html
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.services import macro_calendar_service as mc
from app.services import telegram_digest_service as dg
from app.services import telegram_notify_service as tg

log = logging.getLogger(__name__)

OFFSETS = (("7d", timedelta(days=7), "in 7 days"), ("3d", timedelta(days=3), "in 3 days"), ("1h", timedelta(hours=1), "in 1 hour"))
ON_TIME = timedelta(minutes=15)  # a reminder this close to its moment still says "in 7 days"; later it says the real time left
_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "macro_reminders_sent.json"
_MEMBER = re.compile(r"FOMC Member", re.I)
_ICON = {"CPI": "📈", "PPI": "🏭", "NFP": "👷", "FOMC": "🏦"}


def remindable(e: dict) -> bool:
    """USD CPI / PPI / NFP / FOMC events except single members' speeches (the Fed Chair is kept)."""
    return e["currency"] == "USD" and not _MEMBER.search(e["title"])


def units(events: list[dict]) -> list[dict]:
    """One reminder unit per group and start time: {"key", "group", "start", "rows": [events]}."""
    by: dict[str, dict] = {}
    for e in events:
        if remindable(e):
            u = by.setdefault(f'{e["group"]}|{e["start"].isoformat()}', {"group": e["group"], "start": e["start"], "rows": []})
            u["rows"].append(e)
    return sorted(({"key": k, **u} for k, u in by.items()), key=lambda u: u["start"])


def due(unit: dict, sent: list[str], now: datetime) -> tuple[str, list[str]] | None:
    """(offset to send now, offsets to mark as sent) for one unit, or None. The tightest offset whose moment
    has passed and that was not sent is the one sent; the looser ones that passed are marked as skipped."""
    if unit["start"] <= now:
        return None
    passed = [o for o, delta, _ in OFFSETS if unit["start"] - delta <= now]
    todo = [o for o in passed if o not in sent]
    if not todo or passed[-1] in sent:
        return None
    return passed[-1], todo


def _when(unit: dict, offset: str, now: datetime) -> str:
    delta, label = next((d, lbl) for o, d, lbl in OFFSETS if o == offset)
    if now - (unit["start"] - delta) <= ON_TIME:
        return label
    return "in " + mc.countdown((unit["start"] - now).total_seconds())


def _title(unit: dict) -> str:
    rows = unit["rows"]
    if unit["group"] == "CPI":
        return "US CPI"
    if unit["group"] == "PPI":
        return "US PPI"
    if unit["group"] == "NFP":
        return "US Non-Farm Employment Change"
    return html.escape(rows[0]["title"] if len(rows) == 1 else rows[0]["title"] + f" (+{len(rows) - 1})")


def _numbers(e: dict) -> str:
    bits = [f"forecast {e['forecast']}" if e["forecast"] else "", f"previous {e['previous']}" if e["previous"] else ""]
    return " · ".join(b for b in bits if b)


def reminder_message(unit: dict, offset: str, now: datetime) -> str:
    kl, et = unit["start"].astimezone(mc.KL), unit["start"].astimezone(mc.ET)
    lines = [
        f"⏰ <b>{_title(unit)} {_when(unit, offset, now)}</b>",
        f"{_ICON.get(unit['group'], '🗓')} {kl:%A, %d %b %Y} · <b>{kl:%H:%M}</b> Kuala Lumpur ({et:%H:%M} New York)",
    ]
    for e in unit["rows"]:
        if e.get("scheduled"):
            continue  # a placeholder row has no numbers yet
        nums = _numbers(e)
        lines.append(f"   {html.escape(e['title'])}" + (f"  ·  {nums}" if nums else ""))
    return "\n".join(lines)


def _load_sent() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_sent(state: dict, now: datetime) -> None:
    cutoff = (now.astimezone(timezone.utc) - timedelta(days=3)).isoformat()
    state = {k: v for k, v in state.items() if k.split("|", 1)[1] >= cutoff}
    _STATE_FILE.parent.mkdir(exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state))


def check_and_send(now: datetime | None = None, events: list[dict] | None = None) -> list[str]:
    """One scheduler pass. Returns "<key>#<offset>" for every reminder sent. A reminder that reached no
    chat (Telegram down) is retried on the next pass."""
    now = now or datetime.now(timezone.utc)
    if events is None:
        events = mc.get_schedule(now)["events"]
    state = _load_sent()
    done = []
    for u in units(events):
        hit = due(u, state.get(u["key"], []), now)
        if not hit:
            continue
        offset, mark = hit
        try:
            sent = dg._deliver(reminder_message(u, offset, now), None)
        except Exception:  # noqa: BLE001
            log.exception("macro reminder failed")
            continue
        if sent or not dg.connected_chats():
            state[u["key"]] = sorted(set(state.get(u["key"], [])) | set(mark))
            _save_sent(state, now)
            done.append(f'{u["key"]}#{offset}')
    return done


async def run_reminder_loop() -> None:
    """Checks every minute (Reflex lifespan task) where settings.telegram_digest."""
    if not (settings.telegram_digest and tg.configured()):
        return
    log.info("forex factory reminder scheduler started")
    while True:
        try:
            await asyncio.to_thread(check_and_send)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("macro reminder pass failed")
        await asyncio.sleep(60)


# ---- /forex_factory: the calendar month's events --------------------------------------------------

MSG_LIMIT = 3800  # Telegram allows 4096 characters per message


def month_messages(events: list[dict], now: datetime) -> list[str]:
    """The current calendar month (Kuala Lumpur) as one or more messages: every CPI, jobs report, FOMC event and
    speech, by day. Past events carry ✅ and the actual when known; single members' speeches are one line a day."""
    month = mc.month_events([e for e in events if e["currency"] == "USD"], now)
    kl_now = now.astimezone(mc.KL)
    head = f"📅 <b>Forex Factory · {kl_now:%B %Y}</b>\n<i>US events, Kuala Lumpur time</i>"
    if not month:
        return [head + "\n\nNo CPI, PPI, FOMC or Non-Farm Employment events found for this month yet."]
    days: dict = {}
    for e in month:
        days.setdefault(e["start"].astimezone(mc.KL).date(), []).append(e)
    blocks = []
    for day, rows in sorted(days.items()):
        lines = [f"<b>{day:%a %d %b}</b>"]
        speeches = [e for e in rows if _MEMBER.search(e["title"])]
        stamps: dict = {}
        for e in rows:
            if e not in speeches:
                stamps.setdefault(e["start"], []).append(e)
        for start, group in stamps.items():
            done = "✅" if start <= now else "▫️"
            t = f"{start.astimezone(mc.KL):%H:%M}"
            names = []
            for e in group:
                extra = f" {html.escape(e['actual'])}" if e["actual"] else (f" ({html.escape(e['forecast'])})" if e["forecast"] else "")
                names.append(html.escape(e["title"]) + extra)
            lines.append(f"{done} {t}  " + " · ".join(names))
        if speeches:
            who = ", ".join(
                f"{html.escape(re.sub(r'FOMC Member |Speaks', '', e['title']).strip())} {e['start'].astimezone(mc.KL):%H:%M}" for e in speeches
            )
            lines.append(f"💬 Members: {who}")
        blocks.append("\n".join(lines))
    out, cur = [], head
    for b in blocks:
        if len(cur) + len(b) + 2 > MSG_LIMIT:
            out.append(cur)
            cur = f"📅 <b>Forex Factory · {kl_now:%B %Y}</b> (continued)"
        cur += "\n\n" + b
    out.append(cur + "\n\n<i>✅ happened (actual shown) · ▫️ upcoming (forecast in brackets)</i>")
    return out


def handle_command(chat_id: int) -> None:
    now = datetime.now(timezone.utc)
    try:
        texts = month_messages(mc.get_schedule(now)["events"], now)
    except Exception:  # noqa: BLE001
        log.exception("forex factory month list failed")
        texts = ["Could not load the Forex Factory calendar right now. Try again in a moment."]
    for text in texts:
        tg._send(chat_id, text)
