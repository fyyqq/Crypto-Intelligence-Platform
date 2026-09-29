"""Standalone Telegram-group ingestion pipeline — feeds the same
`news_articles` table app/services/news_pipeline.py writes to. Each group
in TELEGRAM_GROUPS is tagged with which of the four /news categories
(Crypto/AI/Finance/Tech) it belongs to; NewsState buckets every Telegram
post into its own dedicated "<Category> Telegram News" section — e.g.
"Cryptocurrency Telegram News" — directly below that category's regular
RSS/Google News section, per explicit request to keep the two sources
visually separated rather than merged into one section.

Reads via Telethon (the MTProto *client* API — logs in as the user's own
Telegram account, not a bot) rather than the Bot API, specifically because
the user is a member of every group below but NOT an admin of any of
them: a bot can only ever see messages posted after it's added as a
member, and adding a bot at all requires the "Add Members" permission,
which some groups restrict to admins. Reading as an already-joined member
via Telethon needs no group-side permission at all and gets full history,
not just from-now-on.

ONE-TIME MANUAL LOGIN REQUIRED FIRST — see scripts/telegram_login.py.
Telegram's login flow needs a verification code sent live to the
account's own phone/Telegram app, which nothing automated can supply;
run that script yourself once, and it saves a local session file
(telegram_session.session, at the repo root, gitignored) that this
pipeline then reuses non-interactively forever after.

SAFETY / BAN-RISK NOTE (see the session's own prior discussion): this
only ever reads (iter_messages), never joins a channel, sends a message,
or performs any write action — the lowest-risk use of a personal
account's session. REQUEST_DELAY_SECONDS below adds a polite pause
between groups on top of that, consistent with news_pipeline.py's own
crawling etiquette for RSS/Google News fetches.

IDEMPOTENT / INCREMENTAL, same guarantee as news_pipeline.py: each
group's permalink (https://t.me/<username>/<message_id>) is UNIQUE in
news_articles, and on every run after the first, Telethon's own
`min_id` parameter is used to fetch only messages newer than the
highest message id already stored for that group — no need to re-walk
or re-check messages already on file.

Not part of news_pipeline.py itself (kept as a separate module) since it
has a genuinely different transport (Telethon vs. feedparser/pygooglenews)
and a genuinely different dependency (a live, authenticated user
session vs. stateless HTTP) — but it is wired into the exact same
recurring cadence via app/scheduler/jobs.py::run_telegram_pipeline_sync,
reusing settings.news_pipeline_sync_interval_hours rather than
introducing a second interval setting, per explicit request to treat
"real-time" here the same way the rest of this app already does (a
periodic re-sync, not a separate always-on listener process).
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg2
import psycopg2.errors
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Channel, Chat

logger = logging.getLogger("telegram_pipeline")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_PATH = str(_REPO_ROOT / "telegram_session")

# Real photo/video-thumbnail downloads land here and are served at
# /telegram_media/<file> the same way frontend/assets/floating_logo.png is
# served at /floating_logo.png — Reflex serves the whole assets/ directory
# (including subdirectories) as static files, no rebuild needed for a new
# file to become reachable. Per explicit request: only a real image the
# post itself actually has is ever shown — no generic/topic-matched search
# fallback for text-only posts (a near-identical fallback was just removed
# from the RSS/Google News side of this same app for being "misleading" —
# see CLAUDE.md's own dated entry — so Telegram intentionally doesn't
# reintroduce the same pattern).
_TELEGRAM_MEDIA_DIR = _REPO_ROOT / "frontend" / "assets" / "telegram_media"

# Unlike news_pipeline.py (which only reads a DSN string with a safe
# built-in default), this module needs real Telegram API credentials that
# only ever live in .env — load it explicitly so this works both when run
# directly (`python app/services/telegram_pipeline.py`) and when imported
# by app/scheduler/jobs.py inside the FastAPI process (which loads .env
# itself already, but a second load_dotenv() here is a harmless no-op in
# that case, not a conflict).
load_dotenv(_REPO_ROOT / ".env")

API_ID = int(os.environ.get("API_ID_TELEGRAM", "0") or "0")
API_HASH = os.environ.get("API_HASH_TELEGRAM", "")

POSTGRES_DSN = os.environ.get(
    "NEWS_DATABASE_DSN",
    "dbname=crypto_intelligence user=crypto password=crypto host=localhost port=5432",
)

# Public group/channel usernames (from each group's own t.me/<username>
# link) paired with which of the four /news reader-facing categories each
# group's posts belong to — every group confirmed to be one the user is
# already a member of, not something this pipeline joins on its own. The
# category tag must be one of "Crypto"/"AI"/"Finance"/"Tech" (matches
# news_pipeline.py's own RSS_FEEDS/GOOGLE_NEWS_QUERIES category vocabulary)
# so NewsState._normalize_news_type's "Telegram <tag>" special-case (see
# that module) can bucket it into the matching "<Category> Telegram News"
# section, kept separate from that category's own RSS/Google News section
# per explicit request.
TELEGRAM_GROUPS: list[tuple[str, str]] = [
    ("WatcherGuru", "Crypto"),
    ("cryptocurrency_media", "Crypto"),
    ("lookonchainchannel", "Crypto"),
    ("bitcoin", "Crypto"),
    ("cointelegraph", "Crypto"),
    ("wublockchainenglish", "Crypto"),
    ("Cryptocurrency_Inside", "Crypto"),
    ("news_crypto", "Crypto"),
    ("sarjanacryptoindonesia", "Crypto"),
    ("layergg", "Crypto"),
    ("Fin_Watch", "Finance"),  # switched from Crypto per explicit request
    ("whalebotalerts", "Crypto"),
    ("cryptoquant_official", "Crypto"),
    ("Coin_Signals", "Crypto"),
    ("crypto_memes", "Crypto"),
    ("intradaydotmy", "Finance"),  # new, per explicit request
    ("aipost", "AI"),  # new, per explicit request
]

# How far back a group with NO prior stored messages backfills on its
# first-ever run — matches the rest of /news's own rolling display window
# rather than pulling a group's entire history.
_HISTORICAL_WINDOW_DAYS = 90

# Safety ceiling per group on a first-time backfill, independent of the
# 90-day window — a very high-volume group could otherwise return
# thousands of messages in one run.
_MAX_BACKFILL_MESSAGES = 300

# Polite pause between groups, same crawling-etiquette convention
# news_pipeline.py already uses between article fetches.
REQUEST_DELAY_SECONDS = 1.0


# ---------------------------------------------------------------------------
# Database layer — same news_articles table/schema news_pipeline.py owns;
# this module never runs its own CREATE TABLE (that table is guaranteed to
# already exist by the time this pipeline is ever invoked, since it's only
# ever run alongside/after news_pipeline.py in this app), it only inserts.
# ---------------------------------------------------------------------------


class TelegramNewsDB:
    def __init__(self, dsn: str = POSTGRES_DSN):
        self._conn = psycopg2.connect(dsn)

    def last_message_id(self, username: str) -> int:
        """Highest Telegram message id already stored for this group,
        parsed back out of its own permalink — used as Telethon's
        `min_id` so an incremental run only asks for genuinely new
        messages. Returns 0 (fetch from the start of the backfill window)
        when this group has never been ingested before.
        """
        prefix = f"https://t.me/{username}/"
        cur = self._conn.cursor()
        cur.execute(
            "SELECT url FROM news_articles WHERE source_type = 'telegram' AND url LIKE %s",
            (prefix + "%",),
        )
        rows = cur.fetchall()
        cur.close()
        max_id = 0
        for (url,) in rows:
            try:
                msg_id = int(url.rsplit("/", 1)[-1])
            except ValueError:
                continue
            max_id = max(max_id, msg_id)
        return max_id

    def insert_article(
        self,
        *,
        source_name: str,
        category_label: str,
        title: str,
        url: str,
        published_date: datetime.datetime | None,
        full_body_text: str,
        image_url: str | None,
    ) -> bool:
        """Same insert-and-catch-UniqueViolation idempotency pattern as
        news_pipeline.py's own insert_article — returns True only for a
        genuinely new row.
        """
        try:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO news_articles
                    (source_type, source_name, category_or_query, title, url, published_date, full_body_text, image_url)
                VALUES ('telegram', %s, %s, %s, %s, %s, %s, %s)
                """,
                (source_name, category_label, title, url, published_date, full_body_text, image_url),
            )
            self._conn.commit()
            cur.close()
            return True
        except psycopg2.errors.UniqueViolation:
            self._conn.rollback()
            return False

    def missing_image_ids_by_group(self) -> dict[str, list[int]]:
        """Every already-stored Telegram row with no image_url yet, grouped
        by username and parsed back to a real message id — used by
        backfill_missing_images to re-fetch just those specific messages
        (not the whole group's history again) and check whether each one
        actually has real media worth downloading. Text-only rows are
        included too but will simply have no media on re-fetch, so they're
        cheap no-ops rather than something worth filtering out here.
        """
        cur = self._conn.cursor()
        cur.execute("SELECT url FROM news_articles WHERE source_type = 'telegram' AND image_url IS NULL")
        rows = cur.fetchall()
        cur.close()
        by_group: dict[str, list[int]] = {}
        for (url,) in rows:
            match = _TELEGRAM_URL_RE.match(url)
            if not match:
                continue
            username, msg_id = match.group(1), int(match.group(2))
            by_group.setdefault(username, []).append(msg_id)
        return by_group

    def update_image(self, url: str, image_url: str) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "UPDATE news_articles SET image_url = %s WHERE url = %s AND image_url IS NULL",
            (image_url, url),
        )
        self._conn.commit()
        cur.close()

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")
_TELEGRAM_URL_RE = re.compile(r"^https://t\.me/([^/]+)/(\d+)$")

# Telethon's get_messages accepts at most this many ids in one batched call.
_GET_MESSAGES_BATCH_SIZE = 100


def _title_from_text(text: str) -> str:
    """First non-empty line of the message, truncated — same "first line
    as the headline" convention this session settled on, since a Telegram
    post has no separate headline/body split the way an RSS article does.
    """
    for line in text.splitlines():
        cleaned = _WHITESPACE_RE.sub(" ", line).strip()
        if cleaned:
            return cleaned[:200].rstrip() + ("…" if len(cleaned) > 200 else "")
    # No real line-break structure (single long paragraph) — fall back to
    # the first 200 chars of the whole message.
    cleaned = _WHITESPACE_RE.sub(" ", text).strip()
    return cleaned[:200].rstrip() + ("…" if len(cleaned) > 200 else "")


@dataclass
class IngestStats:
    inserted: int = 0
    skipped: int = 0
    images_backfilled: int = 0

    def __add__(self, other: "IngestStats") -> "IngestStats":
        return IngestStats(self.inserted + other.inserted, self.skipped + other.skipped)


async def _download_message_image(client: TelegramClient, message, username: str) -> str | None:
    """Downloads a real preview image straight from the message's own
    media (photo, or a video's own thumbnail — `thumb=-1` picks the
    largest available thumbnail for either, which is plenty for a
    160px-tall card and far cheaper than a full-resolution photo/video
    download) — never anything the post doesn't actually have. Returns
    None (not a fallback) for a text-only message, or if the download
    itself fails for any reason.
    """
    if not getattr(message, "media", None):
        return None
    try:
        _TELEGRAM_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        existing = list(_TELEGRAM_MEDIA_DIR.glob(f"{username}_{message.id}.*"))
        if existing:
            return f"/telegram_media/{existing[0].name}"
        dest_prefix = str(_TELEGRAM_MEDIA_DIR / f"{username}_{message.id}")
        saved_path = await client.download_media(message, file=dest_prefix, thumb=-1)
        if not saved_path:
            return None
        return f"/telegram_media/{Path(saved_path).name}"
    except Exception as exc:  # noqa: BLE001 — an image is a bonus, never fatal to ingestion
        logger.warning("SKIP image download for @%s/%s: %s", username, message.id, exc)
        return None


def _group_display_title(entity) -> str:
    """The group/channel's real display name (what /news shows as
    `source_name`), not the @username slug — matches how every other
    source in news_articles is named (e.g. "TechCrunch", not
    "techcrunch.com").
    """
    if isinstance(entity, (Channel, Chat)):
        return entity.title or entity.username or "Telegram"
    return getattr(entity, "title", None) or getattr(entity, "username", None) or "Telegram"


async def _ingest_group(client: TelegramClient, db: TelegramNewsDB, username: str, category: str) -> IngestStats:
    stats = IngestStats()
    category_label = f"Telegram {category}"
    try:
        entity = await client.get_entity(username)
    except Exception as exc:  # noqa: BLE001 — one bad group must not kill the whole run
        logger.warning("SKIP group (could not resolve @%s: %s)", username, exc)
        return stats

    display_title = _group_display_title(entity)
    min_id = db.last_message_id(username)
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=_HISTORICAL_WINDOW_DAYS)

    kwargs = {"limit": _MAX_BACKFILL_MESSAGES} if min_id == 0 else {"limit": None, "min_id": min_id}

    try:
        async for message in client.iter_messages(entity, **kwargs):
            if min_id == 0 and message.date < cutoff:
                break  # newest-first iteration — anything older than the window ends a first-time backfill
            # message.raw_text is the message's own plain text with all
            # formatting entities simply dropped; message.text instead
            # re-serializes those entities back into literal Markdown
            # syntax (Telethon's default parse mode) — e.g. a real bold
            # run becomes the literal characters "**bold**". Since this
            # card is plain rx.text (no Markdown renderer), that syntax
            # showed up as literal asterisks/underscores/backticks on the
            # page instead of being rendered — raw_text avoids the syntax
            # entirely rather than requiring it to be stripped back out.
            text = (message.raw_text or message.text or "").strip()
            if not text:
                stats.skipped += 1
                continue
            url = f"https://t.me/{username}/{message.id}"
            image_url = await _download_message_image(client, message, username)
            published = message.date.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            inserted = db.insert_article(
                source_name=display_title,
                category_label=category_label,
                title=_title_from_text(text),
                url=url,
                published_date=published,
                full_body_text=text,
                image_url=image_url,
            )
            if inserted:
                stats.inserted += 1
            else:
                stats.skipped += 1
    except FloodWaitError as exc:
        logger.warning("SKIP rest of group @%s (Telegram flood-wait, %ss): %s", username, exc.seconds, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SKIP rest of group @%s (error: %s)", username, exc)

    return stats


async def backfill_missing_images(client: TelegramClient, db: TelegramNewsDB) -> int:
    """One-time-per-message catch-up for rows ingested before real image
    downloads existed (every Telegram row up to this feature shipping has
    image_url NULL, regardless of whether the original post actually had a
    photo/video) — re-fetches each such message by id (batched up to 100
    per Telethon get_messages call, not one request per message) and
    downloads a real image only for the ones that genuinely have media.
    Returns the count of rows actually updated with a real image.
    """
    updated = 0
    for username, msg_ids in db.missing_image_ids_by_group().items():
        try:
            entity = await client.get_entity(username)
        except Exception as exc:  # noqa: BLE001 — one bad group must not kill the whole backfill
            logger.warning("SKIP image backfill (could not resolve @%s: %s)", username, exc)
            continue
        for i in range(0, len(msg_ids), _GET_MESSAGES_BATCH_SIZE):
            batch = msg_ids[i : i + _GET_MESSAGES_BATCH_SIZE]
            try:
                messages = await client.get_messages(entity, ids=batch)
            except FloodWaitError as exc:
                logger.warning("SKIP rest of @%s image backfill (flood-wait, %ss)", username, exc.seconds)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("SKIP @%s image backfill batch (error: %s)", username, exc)
                continue
            for message in messages:
                if message is None:  # deleted since it was first ingested
                    continue
                image_url = await _download_message_image(client, message, username)
                if image_url:
                    db.update_image(f"https://t.me/{username}/{message.id}", image_url)
                    updated += 1
        time.sleep(REQUEST_DELAY_SECONDS)
    return updated


async def _run_async() -> IngestStats:
    if not API_ID or not API_HASH:
        raise RuntimeError("API_ID_TELEGRAM / API_HASH_TELEGRAM not set — see .env")

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            f"No authorized Telegram session at {SESSION_PATH}.session — run "
            "`python scripts/telegram_login.py` yourself first (needs a live login "
            "code from your own phone/Telegram app, so it can't be done non-interactively)."
        )

    db = TelegramNewsDB()
    total = IngestStats()
    images_backfilled = 0
    try:
        for username, category in TELEGRAM_GROUPS:
            stats = await _ingest_group(client, db, username, category)
            total += stats
            logger.info("Telegram @%s (%s): inserted=%d skipped=%d", username, category, stats.inserted, stats.skipped)
            time.sleep(REQUEST_DELAY_SECONDS)
        # Catches up any row still missing a real image — every row ingested
        # before this feature shipped, plus any single message whose own
        # download failed transiently above. Self-limiting: once a row has
        # an image (or has been confirmed to have none), it's never
        # re-checked again, so this shrinks to near-zero cost on later runs.
        images_backfilled = await backfill_missing_images(client, db)
        if images_backfilled:
            logger.info("Image backfill: %d rows updated with a real image", images_backfilled)
    finally:
        db.close()
        await client.disconnect()

    total.images_backfilled = images_backfilled
    return total


def run_telegram_pipeline() -> IngestStats:
    """Synchronous entry point — what app/scheduler/jobs.py calls, same
    shape as news_pipeline.py's ingest_* functions so the scheduler job
    doesn't need to know this one happens to be async under the hood.
    """
    return asyncio.run(_run_async())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Starting Telegram pipeline (%d groups)", len(TELEGRAM_GROUPS))
    stats = run_telegram_pipeline()
    print("--- Telegram pipeline run complete ---")
    print(f"TOTAL — inserted: {stats.inserted:>4}  skipped: {stats.skipped:>4}  images backfilled: {stats.images_backfilled:>4}")


if __name__ == "__main__":
    main()
