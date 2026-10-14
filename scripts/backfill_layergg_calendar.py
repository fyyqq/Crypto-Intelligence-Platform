"""One-off backfill of the @layergg monthly "Crypto + Market Calendar" posts.

The news pipeline only keeps a 30-day window, so the calendar posts of earlier
months are not stored. The Crypto Calendar page (/tools/crypto-calendar) shows
January 2026 onward, so this stores just those posts, through the pipeline's own
store_message (same row format as the listener). Read-only on Telegram.

Stop the Telegram listener first (one process may hold telegram_session.session),
run from the repo root, then start the listener again:
    python -m scripts.backfill_layergg_calendar [YYYY-MM-DD]     # default 2025-12-01
"""
import asyncio
import datetime
import logging
import re
import sys

from app.services import telegram_pipeline as tp

USERNAME = "layergg"
_CALENDAR = re.compile(r"calendar|캘린더|달력", re.I)


def is_monthly_calendar_post(text: str) -> bool:
    """What every monthly post of the group shares: it starts with the 🗓 emoji and is a calendar
    (the word in its title, or the #Calendar hashtag). The title wording varies ("2026 Crypto January
    Calendar", "2026 Market May Calendar", "2026 June Crypto + Market Calendar", Korean "캘린더"), so no
    "Crypto"/"Market" requirement. Weekly highlights start with 🤡 instead and are skipped."""
    text = (text or "").strip()
    first = text.split("\n", 1)[0]
    return text.startswith("🗓") and bool(_CALENDAR.search(first) or re.search(r"#calendar", text, re.I))


async def main(since: datetime.datetime) -> None:
    client = await tp.connect_client()
    db = tp.TelegramNewsDB()
    try:
        entity = await client.get_entity(USERNAME)
        title = tp._group_display_title(entity, USERNAME)
        seen = found = stored = 0
        async for message in client.iter_messages(entity, limit=None):
            if message.date < since:
                break
            seen += 1
            first_line = (message.raw_text or "").strip().split("\n", 1)[0]
            if not is_monthly_calendar_post(message.raw_text):
                continue
            found += 1
            new = await tp.store_message(client, db, message, USERNAME, "Crypto", title)
            stored += bool(new)
            print(f"{message.date:%Y-%m-%d} #{message.id} {'stored' if new else 'already stored'}: {first_line[:70]}")
            await asyncio.sleep(0.5)
        print(f"scanned {seen} posts since {since:%Y-%m-%d}; {found} calendar posts, {stored} newly stored")
    finally:
        db.close()
        await client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    start = sys.argv[1] if len(sys.argv) > 1 else "2025-12-01"  # a January post can be published on 31 Dec
    asyncio.run(main(datetime.datetime.fromisoformat(start).replace(tzinfo=datetime.timezone.utc)))
