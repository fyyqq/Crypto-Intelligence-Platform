"""Telegram reminders before the Contabo server subscription ends: 5, 3 and 1 day before.

Contabo's billing is not readable from the server (its API needs the account's own credentials and does not publish
the renewal date), so the one fact the reminder needs is typed into the live `.env`:
    CONTABO_RENEWAL_DATE=2026-11-11     (any day the monthly term ends / renews on, past or future)
    CONTABO_TERM_MONTHS=1               (the term length; default 1)
The next end date is that date moved forward by whole terms (a 31st clamps to the month's last day), so it needs
editing only if the contract changes. Each reminder is sent once per term (logs/contabo_reminders_sent.json), at
09:00 Kuala Lumpur or the first check after that; a missed offset is caught up with ONE message for the tightest one.
Runs where settings.telegram_digest is true (live): local and live share one bot.
"""
import asyncio
import calendar
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.services import telegram_digest_service as dg
from app.services import telegram_notify_service as tg

log = logging.getLogger(__name__)

KL = ZoneInfo("Asia/Kuala_Lumpur")
OFFSETS = (5, 3, 1)  # days before the end
SEND_HOUR = 9
_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "contabo_reminders_sent.json"


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def next_end(anchor: date, today: date, term_months: int = 1) -> date:
    """The first term end on or after `today`: the anchor moved forward by whole terms. The anchor's own day is kept
    for every term (a 31st clamps to 30 / 28 in a short month but comes back to the 31st)."""
    term = max(1, term_months)
    n = 0
    end = anchor
    while end < today:
        n += term
        end = _add_months(anchor, n)
    return end


def due_offset(days_left: int, sent: list[int]) -> tuple[int, list[int]] | None:
    """(the offset to announce now, offsets to mark as sent) or None. Announces the tightest offset reached (days_left <=
    offset) that was not sent; the looser ones that were reached are marked sent so they are never sent late."""
    reached = [o for o in OFFSETS if days_left <= o]
    todo = [o for o in reached if o not in sent]
    if days_left < 0 or not todo or reached[-1] in sent:
        return None
    return reached[-1], todo


def message(end: date, days_left: int) -> str:
    when = "today" if days_left == 0 else "tomorrow" if days_left == 1 else f"in {days_left} days"
    return (
        f"⚠️ <b>Contabo server subscription ends {when}</b>\n"
        f"📅 {end:%A, %d %b %Y}\n"
        "Renew it in the Contabo Customer Control Panel so repace.fyqqflow.com keeps running "
        "(ignore this if it renews automatically and the card on file is good)."
    )


def _load() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def check_and_send(now: datetime | None = None) -> str | None:
    """One pass. Returns the end date announced ("YYYY-MM-DD") or None. Nothing is sent before 09:00 KL."""
    now = (now or datetime.now(timezone.utc)).astimezone(KL)
    raw = (settings.contabo_renewal_date or "").strip()
    if not raw:
        return None
    try:
        anchor = date.fromisoformat(raw)
    except ValueError:
        log.warning("CONTABO_RENEWAL_DATE %r is not YYYY-MM-DD: contabo reminders are off", raw)
        return None
    if now.hour < SEND_HOUR:
        return None
    end = next_end(anchor, now.date(), settings.contabo_term_months)
    days_left = (end - now.date()).days
    state = _load()
    key = end.isoformat()
    hit = due_offset(days_left, state.get(key, []))
    if not hit:
        return None
    offset, mark = hit
    sent = dg._deliver(message(end, days_left), None)
    if sent or not dg.connected_chats():
        state = {k: v for k, v in state.items() if k >= (end - timedelta(days=62)).isoformat()}  # drop old terms
        state[key] = sorted(set(state.get(key, [])) | set(mark))
        _STATE_FILE.parent.mkdir(exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state))
        return key
    return None


async def run_loop() -> None:
    """Checks every 30 minutes (Reflex lifespan task) where settings.telegram_digest and a renewal date is set."""
    if not (settings.telegram_digest and tg.configured() and (settings.contabo_renewal_date or "").strip()):
        return
    log.info("contabo subscription reminders started (renewal date %s)", settings.contabo_renewal_date)
    while True:
        try:
            await asyncio.to_thread(check_and_send)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("contabo reminder pass failed")
        await asyncio.sleep(1800)
