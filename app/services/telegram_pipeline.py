"""Standalone Telegram-group ingestion pipeline — feeds the same
`news_articles` table app/services/news_pipeline.py writes to, so a
Telegram post shows up in /news's existing Cryptocurrency section
alongside RSS/Google News articles, not a separate feature.

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
# link) — every one confirmed to be a group the user is already a member
# of, not something this pipeline joins on its own.
TELEGRAM_GROUPS: list[str] = [
    "WatcherGuru",
    "cryptocurrency_media",
    "lookonchainchannel",
    "bitcoin",
    "cointelegraph",
    "wublockchainenglish",
    "Cryptocurrency_Inside",
    "news_crypto",
    "sarjanacryptoindonesia",
    "layergg",
    "Fin_Watch",
    "whalebotalerts",
    "cryptoquant_official",
    "Coin_Signals",
    "crypto_memes",
]

# category_or_query stored for every row here — contains "crypto" so
# NewsState._normalize_news_type (frontend/frontend/state/news_state.py)
# reliably buckets every Telegram post into the "Cryptocurrency" section,
# per explicit request.
CATEGORY_LABEL = "Telegram Crypto"

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
                (source_name, CATEGORY_LABEL, title, url, published_date, full_body_text, image_url),
            )
            self._conn.commit()
            cur.close()
            return True
        except psycopg2.errors.UniqueViolation:
            self._conn.rollback()
            return False

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


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

    def __add__(self, other: "IngestStats") -> "IngestStats":
        return IngestStats(self.inserted + other.inserted, self.skipped + other.skipped)


def _group_display_title(entity) -> str:
    """The group/channel's real display name (what /news shows as
    `source_name`), not the @username slug — matches how every other
    source in news_articles is named (e.g. "TechCrunch", not
    "techcrunch.com").
    """
    if isinstance(entity, (Channel, Chat)):
        return entity.title or entity.username or "Telegram"
    return getattr(entity, "title", None) or getattr(entity, "username", None) or "Telegram"


async def _ingest_group(client: TelegramClient, db: TelegramNewsDB, username: str) -> IngestStats:
    stats = IngestStats()
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
            text = (message.text or message.raw_text or "").strip()
            if not text:
                stats.skipped += 1
                continue
            url = f"https://t.me/{username}/{message.id}"
            image_url = None
            if getattr(message, "photo", None) is not None:
                # Telethon exposes the photo object itself, not a URL —
                # downloading/re-hosting it is out of scope for this
                # pipeline (news_pipeline.py's own RSS/Google-News rows
                # only ever store a URL the source already publishes, never
                # bytes this app re-hosts itself), so photo posts are
                # ingested with their real text/link but no image_url.
                image_url = None
            published = message.date.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            inserted = db.insert_article(
                source_name=display_title,
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
    try:
        for username in TELEGRAM_GROUPS:
            stats = await _ingest_group(client, db, username)
            total += stats
            logger.info("Telegram @%s: inserted=%d skipped=%d", username, stats.inserted, stats.skipped)
            time.sleep(REQUEST_DELAY_SECONDS)
    finally:
        db.close()
        await client.disconnect()

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
    print(f"TOTAL — inserted: {stats.inserted:>4}  skipped: {stats.skipped:>4}")


if __name__ == "__main__":
    main()
