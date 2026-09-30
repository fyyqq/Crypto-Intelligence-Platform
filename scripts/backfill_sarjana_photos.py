"""One-time backfill for the Sarjana Crypto Telegram group: keep every post
with a photo, whatever its text (see telegram_pipeline.IMAGE_ALWAYS_GROUPS).

1. Restores photo posts earlier hidden as "Telegram Excluded" (chat, opinion,
   signals) into Crypto — or Finance for stock/macro ones (FINANCE_IDS,
   picked by hand from their titles).
2. Stores photo-only posts (no text at all) from the last 30 days that were
   never saved, via the normal store_message path (title "📷 Photo").

USES THE TELETHON SESSION, so stop the live listener first (one process at a
time on telegram_session.session), then start it again afterwards.

Usage:
    source .venv/bin/activate
    python scripts/backfill_sarjana_photos.py
"""

import asyncio
import datetime

import psycopg2

from app.services.telegram_pipeline import (
    POSTGRES_DSN,
    TelegramNewsDB,
    _group_display_title,
    connect_client,
    store_message,
)

USERNAME = "sarjanacryptoindonesia"
WINDOW_DAYS = 30
FINANCE_IDS = {2913, 2924, 2929, 2934, 2935, 2958, 2964, 2997, 3001, 3041, 3056, 3064, 3072, 3073, 3096}


def restore_excluded_photo_posts() -> int:
    conn = psycopg2.connect(POSTGRES_DSN)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM news_articles
                   WHERE split_part(url, '/', 4) = %s AND category_or_query = 'Telegram Excluded'
                     AND published_date >= NOW() - INTERVAL '30 days'
                     AND (image_url IS NOT NULL OR (media IS NOT NULL AND media::text <> '[]'))""",
                (USERNAME,),
            )
            ids = [row[0] for row in cur.fetchall()]
            for row_id in ids:
                label = "Telegram Finance" if row_id in FINANCE_IDS else "Telegram Crypto"
                cur.execute("UPDATE news_articles SET category_or_query = %s WHERE id = %s", (label, row_id))
            return len(ids)
    finally:
        conn.close()


async def store_photo_only_posts() -> tuple[int, int]:
    client = await connect_client()
    db = TelegramNewsDB()
    inserted = seen = 0
    try:
        entity = await client.get_entity(USERNAME)
        display_title = _group_display_title(entity, USERNAME)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=WINDOW_DAYS)
        async for message in client.iter_messages(entity, limit=None):
            if message.date < cutoff:
                break
            if message.photo and not (message.raw_text or message.text or "").strip():
                seen += 1
                if await store_message(client, db, message, USERNAME, "Crypto", display_title):
                    inserted += 1
    finally:
        await client.disconnect()
    return seen, inserted


def main() -> None:
    print(f"Restored {restore_excluded_photo_posts()} previously excluded photo posts")
    seen, inserted = asyncio.run(store_photo_only_posts())
    print(f"Photo-only posts found: {seen}, newly stored: {inserted}")


if __name__ == "__main__":
    main()
