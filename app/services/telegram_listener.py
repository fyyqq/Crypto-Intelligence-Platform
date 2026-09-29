"""Real-time Telegram ingestion: a standalone, always-on process.

Keeps one connection open to Telegram, which pushes every new post in the
groups listed in telegram_pipeline.TELEGRAM_GROUPS the moment it's
published — stored within seconds, instead of polling every group on a
timer (polling 17 groups every minute from a personal account would be
~24k requests/day, exactly the aggressive pattern that gets accounts
rate-limited).

A catch-up pass (telegram_pipeline.sync_all_groups) also runs once on
startup and then every 30 minutes, in this same process: it fetches
anything missed while the listener was down or disconnected, and retries
any image download that failed. Both paths share one client because the
session file is SQLite — two processes opening it at once fail with
"database is locked". Don't run `python app/services/telegram_pipeline.py`
while this is running.

Run from the repo root (needs the one-time login from
scripts/telegram_login.py first):

    source .venv/bin/activate
    python -m app.services.telegram_listener
"""

from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient, events, utils

from app.services.telegram_pipeline import (
    TELEGRAM_GROUPS,
    TelegramNewsDB,
    _group_display_title,
    connect_client,
    store_message,
    sync_all_groups,
)

logger = logging.getLogger("telegram_listener")

CATCH_UP_INTERVAL_SECONDS = 30 * 60


async def _catch_up(client: TelegramClient) -> None:
    try:
        stats = await sync_all_groups(client)
        logger.info(
            "Catch-up done: inserted=%d skipped=%d images=%d",
            stats.inserted,
            stats.skipped,
            stats.images_backfilled,
        )
    except Exception:  # noqa: BLE001 — a failed catch-up must not stop the live listener
        logger.exception("Catch-up pass failed")


async def _catch_up_forever(client: TelegramClient) -> None:
    while True:
        await asyncio.sleep(CATCH_UP_INTERVAL_SECONDS)
        await _catch_up(client)


async def _run() -> None:
    client = await connect_client()
    # Telegram only pushes a channel's new posts to a client that has loaded
    # its dialog list — confirmed live: without this, the listener stayed
    # connected but stored nothing, and posts only arrived via the 30-min
    # catch-up.
    await client.get_dialogs()

    # Marked peer id (e.g. -100123...) -> group info. event.chat_id uses the
    # marked form, so utils.get_peer_id (not entity.id) is the matching key.
    groups: dict[int, tuple[str, str, str]] = {}
    entities = []
    for username, category in TELEGRAM_GROUPS:
        try:
            entity = await client.get_entity(username)
        except Exception as exc:  # noqa: BLE001 — one bad group must not stop the others
            logger.warning("SKIP group (could not resolve @%s: %s)", username, exc)
            continue
        groups[utils.get_peer_id(entity)] = (username, category, _group_display_title(entity))
        entities.append(entity)

    @client.on(events.NewMessage(chats=entities))
    async def on_new_message(event) -> None:
        group = groups.get(event.chat_id)
        if group is None:
            return
        username, category, display_title = group
        db = TelegramNewsDB()
        try:
            if await store_message(client, db, event.message, username, category, display_title):
                logger.info("Stored @%s/%s", username, event.message.id)
        except Exception:  # noqa: BLE001 — one bad message must not stop the listener
            logger.exception("Failed to store @%s/%s", username, event.message.id)
        finally:
            db.close()

    logger.info("Listening to %d groups", len(entities))
    # Handler is registered before the startup catch-up, so a post published
    # during the catch-up is still stored (the url UNIQUE constraint makes a
    # double-store from both paths harmless).
    await _catch_up(client)
    catch_up_task = asyncio.create_task(_catch_up_forever(client))
    try:
        await client.run_until_disconnected()
    finally:
        catch_up_task.cancel()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # Telethon logs every media-download chunk and DC hop at INFO.
    logging.getLogger("telethon").setLevel(logging.WARNING)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
