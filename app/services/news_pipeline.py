"""Standalone, zero-API-key news aggregation pipeline.

Ingests two kinds of sources into one `news_articles` table:

1. Real-time RSS feeds (`feedparser`) — TechCrunch (Tech), Cointelegraph
   (Crypto), and WIRED's own AI-tagged feed (AI). The originally-specified
   "Artificial Intelligence News" (artificialintelligence-news.com) site is
   NOT used — confirmed live it now sits behind a hard captcha wall
   (SiteGround's "SG-Captcha", `X-Robots-Tag: noindex`) that returns a
   176-byte redirect stub to every scripted request regardless of User-
   Agent, so it can never yield real articles. WIRED's AI feed
   (https://www.wired.com/feed/tag/ai/latest/rss) was picked as a like-for-
   like replacement: a real, currently-reachable, AI-specific feed whose
   articles extract cleanly with trafilatura (confirmed live, no paywall
   block).

2. A dynamic 90-day historical lookback (`pygooglenews`) across a fixed set
   of market/AI/crypto keywords, with the search window's start/end dates
   always computed from `datetime.date.today()` at run time — never a
   hardcoded date string, so the same 90-day trailing window applies
   whether this runs today, next week, or next year.

Every article's full body text is extracted with `trafilatura` — free,
local, no API key, strips nav/ads/cookie-banners down to the real article
text.

DEPENDENCY NOTE beyond the originally-specified library list (feedparser,
pygooglenews, trafilatura, psycopg2-binary): `pygooglenews`'s own RSS
entries link to a Google redirect page
(news.google.com/rss/articles/<token>), not the real publisher URL —
confirmed live that page is a client-side-rendered SPA with no HTTP
redirect and no meta-refresh trafilatura (or anything else) could follow,
so the real URL must be decoded first. `googlenewsdecoder` (a small, actively
maintained pure-Python package) does exactly that by replaying Google
News's own internal decode request — confirmed live it correctly resolves a
real redirect link to its real publisher URL. Without this, every Google-
News-sourced row would have an empty `full_body_text` and a URL that's
useless to a reader (it opens Google's own JS shell, not the article).

DUAL-DATABASE CONFIGURATION
----------------------------
Controlled by two environment variables, read once at import time:

    NEWS_DB_BACKEND     "postgres" (default) or "sqlite"
    NEWS_DATABASE_DSN   backend-specific connection string:
                          - postgres: a libpq DSN string, e.g.
                            "dbname=crypto_intelligence user=crypto
                            password=crypto host=localhost port=5432"
                            Defaults to this project's own local Postgres
                            (matching app/core/config.py's own default
                            database_url) if unset.
                          - sqlite: a file path, e.g. "news_fallback.db"
                            (relative to wherever this script is run from).
                            Defaults to "news_fallback.db" if unset.

Examples:
    # Default — Postgres, this project's own local dev database:
    python app/services/news_pipeline.py

    # Local fallback with no Postgres running at all:
    NEWS_DB_BACKEND=sqlite python app/services/news_pipeline.py

    # A different Postgres instance (e.g. production):
    NEWS_DB_BACKEND=postgres \
    NEWS_DATABASE_DSN="dbname=... user=... password=... host=... port=5432" \
    python app/services/news_pipeline.py

This module is intentionally self-contained (no imports from the rest of
`app/`) so it can be copied out and run anywhere Python + these four/five
packages are installed — genuinely standalone, not just "lives in this
repo." It manages its own raw psycopg2 (Postgres) / sqlite3 (SQLite)
connections directly, per the original spec's library list, rather than
going through this project's own SQLAlchemy models.

APPEND-ONLY / PERMANENT ARCHIVAL POLICY
-----------------------------------------
This module contains no DELETE, TRUNCATE, or any other data-expiration
statement anywhere, on purpose — do not add one. An article that scrolls
past the 90-day Google News lookback window as time moves forward is NOT
removed; it simply stops being re-discovered by future runs' searches,
and stays in the database forever as history. The 90-day window only
controls how far back a NEW run searches, never what an OLD run already
found.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

import feedparser
import psycopg2
import psycopg2.errors
import trafilatura
from googlenewsdecoder import gnewsdecoder
from pygooglenews import GoogleNews

logger = logging.getLogger("news_pipeline")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_BACKEND = os.environ.get("NEWS_DB_BACKEND", "postgres").strip().lower()
POSTGRES_DSN = os.environ.get(
    "NEWS_DATABASE_DSN",
    "dbname=crypto_intelligence user=crypto password=crypto host=localhost port=5432",
)
SQLITE_PATH = os.environ.get("NEWS_DATABASE_DSN") if DB_BACKEND == "sqlite" else None
SQLITE_PATH = SQLITE_PATH or "news_fallback.db"

# (display category, outlet name, RSS URL) — outlet name is what the /news
# page groups articles by (see coin-intelligence-platform's NewsState).
#
# Every URL below was confirmed live (feedparser + a real HTTP GET, not
# guessed) to be a genuinely public, unauthenticated RSS feed before being
# added — see the request that added the second batch for the full set of
# candidates that were tried and rejected (CryptoSlate: 403 bot-blocked;
# aimagazine.com: no feed at any standard path; artificialintelligence-news.com:
# SG-Captcha wall, see this module's own top docstring; Reuters: no public
# feed exists anywhere on reuters.com as of this check; Bloomberg/WSJ: their
# feeds themselves respond, but individual article pages are hard paywalled
# (confirmed via this pipeline's own live 401/403 logs), so they'd only ever
# yield a title/link/date with no real body text — not added by default).
RSS_FEEDS: list[tuple[str, str, str]] = [
    ("Tech", "TechCrunch", "https://techcrunch.com/feed/"),
    ("Crypto", "Cointelegraph", "https://cointelegraph.com/rss"),
    ("AI", "WIRED", "https://www.wired.com/feed/tag/ai/latest/rss"),
    ("Crypto", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Crypto", "The Block", "https://www.theblock.co/rss.xml"),
    ("Crypto", "Decrypt", "https://decrypt.co/feed"),
    ("Tech", "The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Tech", "MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("Tech", "Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("AI", "CNBC", "https://www.cnbc.com/id/19854910/device/rss/rss.html"),
    ("Finance", "CNBC", "https://www.cnbc.com/id/100727362/device/rss/rss.html"),
    ("Finance", "MarketWatch", "https://www.marketwatch.com/rss/topstories"),
]

# Dynamic historical lookback queries — real outlet name per article comes
# from Google News's own <source> tag (feedparser exposes it as
# entry.source.title), not from this list; this list only drives which
# stories get found. The leading (category, query) tag mirrors RSS_FEEDS'
# own (category, outlet, url) shape — it's what gets stored as this row's
# category_or_query (see ingest_historical_google_news below), NOT the raw
# search text, so /news's own NewsState._normalize_news_type can reliably
# bucket every query (e.g. "eth"/"defi"/"stablecoin" don't themselves
# contain the word "crypto" and would otherwise fall through to General
# News) — each tag must be one of "Crypto"/"AI"/"Finance"/"Tech" to match
# that function's existing keyword checks.
GOOGLE_NEWS_QUERIES: list[tuple[str, str]] = [
    ("Crypto", "cryptocurrency"),
    ("Crypto", "bitcoin"),
    ("Crypto", "eth"),
    ("Crypto", "real world asset"),
    ("Crypto", "defi"),
    ("Crypto", "stablecoin"),
    ("Crypto", "web3"),
    ("Crypto", "crypto regulation"),
    ("Crypto", "crypto ETF"),
    ("AI", "artificial intelligence"),
    ("AI", "machine learning"),
    ("AI", "generative AI"),
    ("AI", "AI regulation"),
    ("Finance", "global stock market"),
    ("Finance", "federal reserve interest rates"),
    ("Finance", "inflation report"),
    ("Tech", "big tech layoffs"),
    ("Tech", "semiconductor industry"),
]

# Real-world ceiling per query — pygooglenews' search() can return up to
# ~100 entries per query; fetching+extracting all of them (one polite
# REQUEST_DELAY_SECONDS-spaced request each) across all queries could take
# a very long time and hit target sites hard. This caps each run to a
# reasonable, still-substantial slice of the most relevant (Google's own
# ranking) results per query, per run — a later run naturally picks up
# different top results over time since already-seen URLs are skipped.
MAX_RESULTS_PER_QUERY = 100

# Used only by ingest_historical_backfill_for_named_outlets below (a
# one-time, manually-triggered deep backfill, never the recurring cron
# path) — Google's own realistic per-query ceiling, confirmed live.
BACKFILL_RESULTS_PER_QUERY_CAP = 100

# Polite crawling delay between each page fetch (RSS article pages AND
# Google-News-resolved article pages alike).
REQUEST_DELAY_SECONDS = 1.0

_HISTORICAL_WINDOW_DAYS = 90


# ---------------------------------------------------------------------------
# Database layer
# ---------------------------------------------------------------------------

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(20) NOT NULL,
    source_name VARCHAR(120) NOT NULL,
    category_or_query VARCHAR(255) NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    published_date TIMESTAMP,
    full_body_text TEXT,
    image_url TEXT
)
"""

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    category_or_query TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    published_date TEXT,
    full_body_text TEXT,
    image_url TEXT
)
"""


class NewsDB:
    """Thin dual-backend (Postgres/SQLite) manager. Picks its dialect once
    at construction based on `backend`, then exposes the same three
    methods either way — callers never branch on backend themselves.
    """

    def __init__(self, backend: str = DB_BACKEND):
        self.backend = backend
        if backend == "sqlite":
            self._conn = sqlite3.connect(SQLITE_PATH)
            self._param = "?"
        elif backend == "postgres":
            self._conn = psycopg2.connect(POSTGRES_DSN)
            self._param = "%s"
        else:
            raise ValueError(f"Unknown NEWS_DB_BACKEND {backend!r} — must be 'postgres' or 'sqlite'")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        schema = _SQLITE_SCHEMA if self.backend == "sqlite" else _POSTGRES_SCHEMA
        cur = self._conn.cursor()
        cur.execute(schema)
        # CREATE TABLE IF NOT EXISTS never adds a column to an already-
        # existing table from an earlier pipeline version — this ALTER
        # covers that upgrade path for image_url specifically, since this
        # column was added after the table already existed in real usage.
        try:
            cur.execute("ALTER TABLE news_articles ADD COLUMN image_url TEXT")
            self._conn.commit()
        except (psycopg2.errors.DuplicateColumn, sqlite3.OperationalError):
            self._conn.rollback()
        cur.close()

    def article_exists(self, url: str) -> bool:
        """Checked BEFORE scraping/extracting a candidate article — the
        idempotency gate that makes re-running this pipeline cheap and
        avoids re-hitting (and rate-limiting against) a target site for a
        URL already on file.
        """
        p = self._param
        cur = self._conn.cursor()
        cur.execute(f"SELECT 1 FROM news_articles WHERE url = {p} LIMIT 1", (url,))
        found = cur.fetchone() is not None
        cur.close()
        return found

    def insert_article(
        self,
        *,
        source_type: str,
        source_name: str,
        category_or_query: str,
        title: str,
        url: str,
        published_date: datetime.datetime | None,
        full_body_text: str | None,
        image_url: str | None = None,
    ) -> bool:
        """Returns True if a new row was actually written, False if a
        UNIQUE-constraint race lost to a concurrent/prior insert (belt-and-
        suspenders alongside article_exists' own pre-check — two pipeline
        runs overlapping in time can't still double-insert the same URL).
        Never deletes or updates an existing row.
        """
        p = self._param
        published_value = published_date.isoformat() if published_date else None
        try:
            cur = self._conn.cursor()
            cur.execute(
                f"""
                INSERT INTO news_articles
                    (source_type, source_name, category_or_query, title, url, published_date, full_body_text, image_url)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                """,
                (source_type, source_name, category_or_query, title, url, published_value, full_body_text, image_url),
            )
            self._conn.commit()
            cur.close()
            return True
        except (psycopg2.errors.UniqueViolation, sqlite3.IntegrityError):
            self._conn.rollback()
            return False

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _parse_published(entry: Any) -> datetime.datetime | None:
    """feedparser (both real RSS and pygooglenews, which is itself
    feedparser under the hood) exposes a pre-parsed `published_parsed`
    struct_time in UTC whenever the source's own date string was
    recognized — always prefer that over re-parsing the raw string
    ourselves.
    """
    parsed = getattr(entry, "published_parsed", None)
    if not parsed:
        return None
    try:
        return datetime.datetime(*parsed[:6])
    except (TypeError, ValueError):
        return None


def _rss_entry_image(entry: Any) -> str | None:
    """An RSS entry's own declared featured image, when the feed provides
    one — confirmed live that roughly half of RSS_FEEDS' outlets expose
    this (Cointelegraph/WIRED/CoinDesk/The Block/Decrypt/Ars Technica/
    MarketWatch via media:content or media:thumbnail), the rest don't
    (TechCrunch/The Verge/MIT Tech Review/CNBC) — those fall through to
    the in-page image tiers below instead. Prefers media_content (the
    outlet's own primary image) over media_thumbnail.
    """
    for field in ("media_content", "media_thumbnail"):
        items = getattr(entry, field, None)
        if items:
            url = items[0].get("url")
            if url:
                return url
    return None


# Non-content image URL fragments — author headshots/avatars/site icons
# that trafilatura's include_images pass will still pick up alongside real
# in-article photos, confirmed live (e.g. The Verge embeds the byline
# author's own headshot as a second <graphic> right after the real lead
# image) — filtered out so the "1st section image"/backup tiers below
# never select someone's tiny profile photo instead of real article art.
_NON_CONTENT_IMAGE_MARKERS = ("avatar", "gravatar", "headshot", "author-photo", "profile-pic", "favicon", "sprite")


def _extract_content_images(downloaded: str) -> list[str]:
    """The article's own in-body images, in the order they appear —
    "1st section image" is candidates[0], "other image as backup" is
    whatever follows. Confirmed live via trafilatura's own include_images
    pass (emits <graphic src="..."/> tags in its XML output) that the
    first tag is reliably the real lead/content image and a later one is
    sometimes a byline headshot — hence the marker-based filter above.
    """
    try:
        xml = trafilatura.extract(downloaded, include_images=True, output_format="xml")
    except Exception:  # noqa: BLE001 — a bonus extraction pass, never fatal
        return []
    if not xml:
        return []
    import html as _html

    urls = re.findall(r'<graphic src="([^"]+)"', xml)
    urls = [_html.unescape(u) for u in urls]
    return [u for u in urls if not any(marker in u.lower() for marker in _NON_CONTENT_IMAGE_MARKERS)] or urls


def _resolve_article_image(
    *,
    rss_image: str | None,
    page_images: list[str],
    title: str,
    category: str,
) -> str | None:
    """The full priority chain, in the order requested: (1) the outlet's
    own declared featured image (RSS media field or og:image — both are
    "featured image" sources, so tried together as one tier), (2) the
    article's own first in-content image, (3) any other in-content image
    on the same page. Articles without a verified publisher image remain
    image-free rather than receiving unrelated generic artwork.
    """
    for candidate in (rss_image, *page_images):
        if candidate:
            return candidate
    return None


_PAGE_FETCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_META_TAG_RE = re.compile(r"<meta[^>]*>", re.IGNORECASE)
_META_CONTENT_RE = re.compile(r'content=["\']([^"\']+)["\']', re.IGNORECASE)


def is_fallback_image(image_url: str | None) -> bool:
    """Whether an image is a generic Commons fallback."""
    return bool(image_url) and "wikimedia.org" in image_url.lower()


def quick_page_image(url: str, timeout: float = 6.0) -> str | None:
    """Fetch an article's own meta or first content image without retries."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _PAGE_FETCH_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read(300_000).decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001 — best-effort, caller has its own fallback
        return None

    for tag in _META_TAG_RE.findall(html):
        lowered = tag.lower()
        if "og:image" not in lowered and "twitter:image" not in lowered:
            continue
        match = _META_CONTENT_RE.search(tag)
        if not match:
            continue
        candidate = urllib.parse.urljoin(url, match.group(1))
        if not any(marker in candidate.lower() for marker in _NON_CONTENT_IMAGE_MARKERS):
            return candidate

    content_images = _extract_content_images(html)
    if content_images:
        return urllib.parse.urljoin(url, content_images[0])
    return None


def _safe_extract_full_text(url: str) -> tuple[str | None, list[str]]:
    """Wraps both the page fetch and the trafilatura extraction in one
    try/except per the resilience requirement — a Cloudflare/anti-bot wall,
    a hard paywall, a dead link, or a timeout all just log and return
    (None, []) here rather than raising and stalling the whole pipeline
    run. Also recovers every usable image already on the SAME downloaded
    page — the site's own og:image (via trafilatura's metadata parser)
    first, then any real in-content images (see _extract_content_images)
    — at no extra network cost beyond the one fetch already needed for the
    body text itself.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            logger.warning("SKIP body extraction (could not download): %s", url)
            return None, []
        text = trafilatura.extract(downloaded)
        images: list[str] = []
        try:
            meta = trafilatura.extract_metadata(downloaded)
            og_image = getattr(meta, "image", None) if meta else None
            if og_image:
                images.append(og_image)
        except Exception:  # noqa: BLE001 — metadata is a bonus, never fatal
            pass
        images.extend(_extract_content_images(downloaded))
        if not text:
            logger.warning("SKIP body extraction (no extractable article text): %s", url)
            return None, images
        return text, images
    except Exception as exc:  # noqa: BLE001 — deliberately broad, see docstring
        logger.warning("SKIP body extraction (error: %s): %s", exc, url)
        return None, []


def _resolve_google_news_url(google_url: str) -> str | None:
    """Decodes a pygooglenews RSS entry's link (a Google redirect page,
    news.google.com/rss/articles/<token>) into the real publisher URL. See
    this module's own docstring for why this extra step is required.
    Returns None (never the still-useless redirect URL) on any failure.
    """
    try:
        result = gnewsdecoder(google_url, interval=REQUEST_DELAY_SECONDS)
        if not result or not result.get("success") or not result.get("decoded_url"):
            logger.warning("SKIP (could not decode Google News redirect): %s", google_url)
            return None
        return result["decoded_url"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("SKIP (error decoding Google News redirect %s): %s", google_url, exc)
        return None


@dataclass
class IngestStats:
    inserted: int = 0
    skipped: int = 0

    def __add__(self, other: "IngestStats") -> "IngestStats":
        return IngestStats(self.inserted + other.inserted, self.skipped + other.skipped)


# ---------------------------------------------------------------------------
# Ingestion: real-time RSS feeds
# ---------------------------------------------------------------------------


def ingest_rss_feeds(db: NewsDB) -> IngestStats:
    stats = IngestStats()
    for category, outlet_name, feed_url in RSS_FEEDS:
        parsed = feedparser.parse(feed_url)
        if parsed.bozo and not parsed.entries:
            logger.warning("SKIP feed (unparseable, 0 entries): %s (%s)", outlet_name, feed_url)
            continue
        logger.info("RSS %s (%s): %d entries", outlet_name, feed_url, len(parsed.entries))
        for entry in parsed.entries:
            article_url = entry.get("link")
            title = entry.get("title", "").strip()
            if not article_url or not title:
                continue
            if db.article_exists(article_url):
                stats.skipped += 1
                continue
            body, page_images = _safe_extract_full_text(article_url)
            image_url = _resolve_article_image(
                rss_image=_rss_entry_image(entry),
                page_images=page_images,
                title=title,
                category=category,
            )
            time.sleep(REQUEST_DELAY_SECONDS)
            inserted = db.insert_article(
                source_type="rss",
                source_name=outlet_name,
                category_or_query=category,
                title=title,
                url=article_url,
                published_date=_parse_published(entry),
                full_body_text=body,
                image_url=image_url,
            )
            if inserted:
                stats.inserted += 1
            else:
                stats.skipped += 1
    return stats


# ---------------------------------------------------------------------------
# Ingestion: dynamic 90-day historical Google News lookback
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def _clean_source_name(raw: str | None, fallback_query: str) -> str:
    name = _WHITESPACE_RE.sub(" ", (raw or "")).strip()
    return name or fallback_query.title()


def ingest_historical_google_news(db: NewsDB) -> IngestStats:
    """Dynamic date rule: start/end are computed fresh from
    datetime.date.today() every single run — never a fixed string — so the
    trailing 90-day search window moves forward automatically on every
    future run, whether that's tomorrow, next month, or next year.
    """
    stats = IngestStats()
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=_HISTORICAL_WINDOW_DAYS)
    gn = GoogleNews(lang="en", country="US")

    for category, query in GOOGLE_NEWS_QUERIES:
        search_query = f"{query} after:{start_date.isoformat()} before:{today.isoformat()}"
        try:
            result = gn.search(search_query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SKIP query (search failed: %s): %s", exc, search_query)
            continue
        entries = result.get("entries", [])[:MAX_RESULTS_PER_QUERY]
        logger.info("Google News %r: %d entries (capped at %d)", query, len(entries), MAX_RESULTS_PER_QUERY)
        for entry in entries:
            google_url = entry.get("link")
            title = entry.get("title", "").strip()
            if not google_url or not title:
                continue
            # Resolved BEFORE the article_exists check — the raw Google
            # redirect URL changes shape often enough that checking it
            # directly would rarely dedupe against a previously-stored
            # (real) URL. This costs one small decode request even for an
            # article we've already stored, but never the expensive full-
            # page fetch+extract below, which the check right after this
            # still guards.
            real_url = _resolve_google_news_url(google_url)
            if not real_url:
                stats.skipped += 1
                continue
            if db.article_exists(real_url):
                stats.skipped += 1
                continue
            source_field = entry.get("source")
            source_title = source_field.get("title") if isinstance(source_field, dict) else None
            source_name = _clean_source_name(source_title, query)
            body, page_images = _safe_extract_full_text(real_url)
            image_url = _resolve_article_image(
                rss_image=None,
                page_images=page_images,
                title=title,
                category=category,
            )
            time.sleep(REQUEST_DELAY_SECONDS)
            inserted = db.insert_article(
                source_type="google_news",
                source_name=source_name,
                category_or_query=category,
                title=title,
                url=real_url,
                published_date=_parse_published(entry),
                full_body_text=body,
                image_url=image_url,
            )
            if inserted:
                stats.inserted += 1
            else:
                stats.skipped += 1
    return stats


# ---------------------------------------------------------------------------
# One-time backfill: full 90-day history for each NAMED outlet (RSS_FEEDS)
# ---------------------------------------------------------------------------
#
# ingest_rss_feeds above only ever sees a feed's current "latest N" items —
# an RSS feed is not an archive, so it structurally cannot backfill history
# no matter how it's called. Google News's own search index, though, can
# be scoped to a single real domain with the "site:" operator (confirmed
# live: "site:techcrunch.com after:X before:Y" returns 100 real TechCrunch
# results spanning the requested window) — this is how a genuine 90-day
# history for each of RSS_FEEDS' three named outlets gets populated, in one
# deliberate manual run, rather than waiting for ingest_rss_feeds to build
# it up organically one "latest N" snapshot per daily cron tick.
#
# NOT part of the recurring cron job (app/scheduler/jobs.py::
# run_news_pipeline_sync calls ingest_rss_feeds/ingest_historical_google_news
# directly, never this function) — run it once manually (see main()'s
# --backfill-outlets flag) whenever a fresh 90-day seed is wanted; the daily
# cron job's own ingest_rss_feeds already takes over from there for
# genuinely new/latest articles as each outlet actually publishes them.


def _outlet_domain(feed_url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(feed_url).netloc.removeprefix("www.")


def ingest_historical_backfill_for_named_outlets(db: NewsDB) -> IngestStats:
    stats = IngestStats()
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=_HISTORICAL_WINDOW_DAYS)
    gn = GoogleNews(lang="en", country="US")

    for category, outlet_name, feed_url in RSS_FEEDS:
        domain = _outlet_domain(feed_url)
        search_query = f"site:{domain} after:{start_date.isoformat()} before:{today.isoformat()}"
        try:
            result = gn.search(search_query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SKIP outlet backfill (search failed: %s): %s", exc, search_query)
            continue
        entries = result.get("entries", [])[:BACKFILL_RESULTS_PER_QUERY_CAP]
        logger.info("Backfill %s (site:%s): %d entries", outlet_name, domain, len(entries))
        for entry in entries:
            google_url = entry.get("link")
            title = entry.get("title", "").strip()
            if not google_url or not title:
                continue
            real_url = _resolve_google_news_url(google_url)
            if not real_url:
                stats.skipped += 1
                continue
            if db.article_exists(real_url):
                stats.skipped += 1
                continue
            body, page_images = _safe_extract_full_text(real_url)
            image_url = _resolve_article_image(
                rss_image=None,
                page_images=page_images,
                title=title,
                category=category,
            )
            time.sleep(REQUEST_DELAY_SECONDS)
            # source_name is forced to this RSS_FEEDS entry's own outlet
            # name (not Google's own <source> attribution, which for a
            # site: query is always the same outlet anyway, just spelled
            # inconsistently across articles — e.g. "TechCrunch" vs.
            # "TechCrunch " vs. a byline) — this guarantees every backfilled
            # article lands in the exact same /news section its own
            # ingest_rss_feeds-sourced siblings do, not a near-duplicate
            # section with a slightly different name.
            inserted = db.insert_article(
                source_type="google_news_backfill",
                source_name=outlet_name,
                category_or_query=category,
                title=title,
                url=real_url,
                published_date=_parse_published(entry),
                full_body_text=body,
                image_url=image_url,
            )
            if inserted:
                stats.inserted += 1
            else:
                stats.skipped += 1
    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backfill-outlets",
        action="store_true",
        help=(
            "One-time deep 90-day historical backfill for each RSS_FEEDS outlet "
            "(via Google News's site: search), in addition to the normal run. "
            "Never run automatically by the cron job — see "
            "ingest_historical_backfill_for_named_outlets's own docstring."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Starting news pipeline (backend=%s)", DB_BACKEND)

    db = NewsDB(DB_BACKEND)
    try:
        rss_stats = ingest_rss_feeds(db)
        google_stats = ingest_historical_google_news(db)
        backfill_stats = ingest_historical_backfill_for_named_outlets(db) if args.backfill_outlets else IngestStats()
    finally:
        db.close()

    total = rss_stats + google_stats + backfill_stats
    print("--- News pipeline run complete ---")
    print(f"RSS feeds      — inserted: {rss_stats.inserted:>4}  skipped: {rss_stats.skipped:>4}")
    print(f"Google News    — inserted: {google_stats.inserted:>4}  skipped: {google_stats.skipped:>4}")
    if args.backfill_outlets:
        print(f"Outlet backfill— inserted: {backfill_stats.inserted:>4}  skipped: {backfill_stats.skipped:>4}")
    print(f"TOTAL          — inserted: {total.inserted:>4}  skipped: {total.skipped:>4}")


if __name__ == "__main__":
    main()
