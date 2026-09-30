"""State for the /news page — reads real articles from the news_articles
table (app/services/news_pipeline.py) and groups them by normalized news
type (Cryptocurrency, Artificial Intelligence, ...), each category its own
independently-paginated 4-column x 3-row grid section, further filterable
by real source (Cointelegraph, BBC, ...) via a per-section dropdown.

Reads the same Postgres database the FastAPI backend writes to, directly via
SQLAlchemy — the same "from app.core.database import SessionLocal as
OldSessionLocal" pattern CoinState's own background refreshers already use
elsewhere in this app, not the separate Reflex-only SQLite mirror (`rx.session`)
that CoinState.load_coins uses for the coin universe. No new SQLAlchemy model
was added for news_articles (the pipeline manages its own schema with plain
SQL, per its own module docstring), so this reads it with a raw SQL SELECT
instead of an ORM query.
"""

import asyncio
import datetime
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

import reflex as rx

from frontend.state.coin_state import _format_model_badge

_TELEGRAM_MEDIA_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "telegram_media"

_PAGE_SIZE = 15  # 5 columns x 3 rows per page (desktop), per explicit request
_VIEW_ALL_LIMIT = 100  # articles per page on a /news/<category> "View All" page
_HOME_NEWS_LIMIT = 50  # cards per homepage news slider
_TOP_SOURCE_PILLS = 10  # publishers shown as pills; the rest go in the "Other" dropdown

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'“‘A-Z0-9])")
_MAX_SOURCE_PARAGRAPH_CHARS = 620


def _slugify(name: str) -> str:
    """URL-fragment id for a section's outlet name, e.g. "24/7 Wall St."
    -> "24-7-wall-st" — used so each source's section is directly linkable
    (`/news#<slug>`). Non-ASCII outlet names (Google News occasionally
    attributes a result to a non-English-language source) fall back to a
    generic "source-N" id rather than an empty/unusable slug.
    """
    slug = _SLUG_STRIP_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "source"


def _relative_time(dt: datetime.datetime | None) -> str:
    if dt is None:
        return ""
    now = datetime.datetime.utcnow()
    minutes = int((now - dt).total_seconds() // 60)
    if minutes < 1:
        return "Just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks}w ago"
    months = days // 30
    return f"{months}mo ago"


def _published_date_display(dt: datetime.datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%B %d, %Y")


def _fetch_articles() -> list[dict]:
    """Blocking DB read — see NewsState.load_news for why this runs in a
    background thread rather than directly in an async event handler.
    Returns [] (never raises) if the news_articles table doesn't exist yet
    (the pipeline hasn't been run) or the query fails for any other reason
    — the page shows its own empty state for that case rather than crashing.
    """
    import sys
    from pathlib import Path

    from sqlalchemy import text

    # Reflex's own process runs with only frontend/ on sys.path — the
    # project root (parent of both app/ and frontend/) needs adding before
    # `app.*` can be imported, same cross-package pattern coin_state.py's
    # own background refreshers already use for this exact reason.
    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.core.database import SessionLocal as OldSessionLocal

    db = OldSessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT id, source_name, category_or_query, title, url, published_date, full_body_text, image_url, source_type, media
                FROM news_articles
                WHERE published_date >= NOW() - INTERVAL '90 days'
                  AND (source_type <> 'telegram' OR published_date >= NOW() - INTERVAL '30 days')
                  AND category_or_query IS DISTINCT FROM 'Telegram Excluded'
                ORDER BY published_date DESC NULLS LAST, id DESC
                """
            )
        ).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        db.close()


def _fetch_max_article_id() -> int:
    """Cheap change check for NewsState.watch_new_articles: rows only ever
    get appended (SERIAL ids), so a higher max id means something new."""
    import sys
    from pathlib import Path

    from sqlalchemy import text

    root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)

    from app.core.database import SessionLocal as OldSessionLocal

    db = OldSessionLocal()
    try:
        return db.execute(text("SELECT COALESCE(MAX(id), 0) FROM news_articles")).scalar() or 0
    except Exception:
        return 0
    finally:
        db.close()


def _fetch_article_by_path(news_category: str, article_slug: str) -> tuple[dict | None, list[dict]]:
    """Resolve one permanent archive record from its readable route.

    Title slugs are unique within their normalized category. Detail lookups
    intentionally include the whole append-only archive, not just the
    rolling grid window, so an in-app link stays valid after an item ages out.
    """
    import sys
    from pathlib import Path

    from sqlalchemy import text

    root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)

    from app.core.database import SessionLocal as OldSessionLocal

    db = OldSessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT id, source_name, category_or_query, title, url, published_date,
                       full_body_text, image_url, source_type, media
                FROM news_articles
                WHERE category_or_query IS DISTINCT FROM 'Telegram Excluded'
                ORDER BY published_date DESC NULLS LAST, id DESC
                """
            )
        ).mappings().all()
        raw_rows = [dict(row) for row in rows]
        articles = _build_article_rows(raw_rows)
        article = next(
            (item for item in articles if item["news_category"] == news_category and item["article_slug"] == article_slug),
            None,
        )
        if article is None:
            return None, []
        raw_article = next(row for row in raw_rows if row["id"] == article["id"])
        related_candidates = [
            item
            for item in articles
            if item["news_type"] == article["news_type"] and item["id"] != article["id"]
        ]
        # Keep the latest matching articles first, but favor records whose
        # extracted source text gives the reader a meaningful related-card
        # description rather than an empty second line.
        related = sorted(related_candidates, key=lambda item: not item["has_snippet"])[:3]
        return raw_article, related
    except Exception:
        return None, []
    finally:
        db.close()


# A small rotating palette for source badges — outlets are whatever the
# pipeline has actually ingested (dynamic), not a fixed small set, so this
# hashes the name to a stable color instead of a per-name lookup table.
# Computed here (server-side, once per row) rather than in the component,
# since a Reflex component function only ever runs once symbolically for
# an rx.foreach's Var, not once per real item — the same reason every other
# per-row display field in this codebase (e.g. coin_table.py's
# change_24h_color) is precomputed into the row dict, never derived inline
# in the component from the row's own other fields.
_BADGE_COLORS = ["blue", "green", "orange", "purple", "crimson", "cyan", "amber", "indigo"]

# Telegram posts (app/services/telegram_pipeline.py) are merged into the
# same category section as RSS/Google News articles; each card's own
# "Telegram News" badge still marks the source. INTENTIONAL, per the user's
# explicit request on 2026-09-30 — it supersedes the earlier separate
# "<Category> Telegram News" sections. Do not restore those sections (see
# CLAUDE.md's 2026-09-30 merge entry). The pipeline tags every Telegram
# row's category_or_query as "Telegram <tag>" (tag one of Crypto/AI/
# Finance/Tech); matched explicitly here because a tag like "AI" doesn't
# contain any keyword the generic matching below looks for.
_TELEGRAM_CATEGORY_MAP = {
    "Crypto": "Cryptocurrency",
    "AI": "Artificial Intelligence",
    "Finance": "Markets & Finance",
    "Tech": "Technology",
    "Memecoin": "Memecoins",
}

_NEWS_TYPE_COLORS = {
    "Cryptocurrency": "amber",
    "Artificial Intelligence": "purple",
    "Markets & Finance": "green",
    "Technology": "cyan",
    "Memecoins": "pink",
    "General News": "gray",
}

_NEWS_TYPE_ORDER = {
    "Cryptocurrency": 0,
    "Artificial Intelligence": 1,
    "Markets & Finance": 2,
    "Technology": 3,
    "Memecoins": 4,
    "General News": 5,
}

_FALLBACK_IMAGES_BY_TYPE = {
    "Cryptocurrency": (
        "/crypto-news-fallback-image/crypto-news-fallback-1.jpeg",
        "/crypto-news-fallback-image/crypto-news-fallback-2.webp",
        "/crypto-news-fallback-image/crypto-news-fallback-3.jpeg",
    ),
    "Artificial Intelligence": (
        "/ai-news-fallback-image/ai-fallback-image-1.jpeg",
        "/ai-news-fallback-image/ai-fallback-image-2.jpeg",
        "/ai-news-fallback-image/ai-fallback-image-3.png",
    ),
    "Markets & Finance": (
        "/financial-market-news-fallback-image/market-financial-fallback-image-1.webp",
        "/financial-market-news-fallback-image/market-financial-fallback-image-2.jpeg",
        "/financial-market-news-fallback-image/market-financial-fallback-image-3.webp",
    ),
}

_FALLBACK_TYPE_BY_NEWS_TYPE = {
    "Cryptocurrency": "Cryptocurrency",
    "Memecoins": "Cryptocurrency",
    "Artificial Intelligence": "Artificial Intelligence",
    "Technology": "Artificial Intelligence",
    "Markets & Finance": "Markets & Finance",
    "General News": "Markets & Finance",
}


def _fallback_image_for(url: str, news_type: str) -> str:
    """Choose a supplied category fallback consistently for each article URL."""
    image_pool = _FALLBACK_IMAGES_BY_TYPE[
        _FALLBACK_TYPE_BY_NEWS_TYPE.get(news_type, "Markets & Finance")
    ]
    image_index = (
        int.from_bytes(hashlib.sha256(url.encode()).digest()[:2], "big")
        % len(image_pool)
    )
    return image_pool[image_index]


_TELEGRAM_URL_RE = re.compile(r"^https://t\.me/([^/]+)/\d+$")


def _telegram_group_avatar(url: str) -> str:
    """URL of the Telegram group's downloaded profile picture (see
    telegram_pipeline.ensure_group_avatar), or "" if we have none. Shown on
    any Telegram post without a photo of its own, in place of the generic
    category fallback image.
    """
    match = _TELEGRAM_URL_RE.match(url)
    if not match:
        return ""
    name = f"_avatar_{match.group(1)}.jpg"
    return f"/telegram_media/{name}" if (_TELEGRAM_MEDIA_DIR / name).exists() else ""


def _card_media_image(media: list[dict] | None) -> str:
    """Image for a Telegram post's grid card: the first photo if the post has
    one (a post with a photo and a video shows the photo), otherwise the
    video's own thumbnail; "" when the post has no media."""
    items = media or []
    for item in items:
        if item.get("type") == "image" and item.get("src"):
            return item["src"]
    for item in items:
        if item.get("type") == "video" and item.get("poster"):
            return item["poster"]
    return ""


def _media_grid(media: list[dict] | None) -> dict:
    """Layout for the reader's media area when a post has more than one item
    or a video. With a video: the (first) video fills the full row as the
    large cell and every other item is a small square cell below it. Images
    only (2+): equal cells in two columns, the first spanning the row when
    the count is odd. A single photo isn't a grid (the normal hero image)."""
    items = [item for item in (media or []) if item.get("type") in ("image", "video") and (item.get("src") or item.get("poster"))]
    has_video = any(item["type"] == "video" for item in items)
    if not items or (len(items) == 1 and not has_video):
        return {"has_media_grid": False, "media_grid_items": [], "media_grid_columns": ""}
    if has_video:
        first_video = next(i for i, item in enumerate(items) if item["type"] == "video")
        items = [items[first_video]] + items[:first_video] + items[first_video + 1 :]
        featured = 0
    else:
        featured = 0 if len(items) % 2 else -1
    cells = []
    for index, item in enumerate(items):
        large = index == featured or len(items) == 1
        cells.append(
            {
                "src": item.get("src") or "",
                "poster": item.get("poster") or "",
                "is_video": item["type"] == "video",
                "playable": bool(item.get("src")) and item["type"] == "video",
                "col": "1 / -1" if large else "span 1",
                "ratio": "16 / 9" if large else ("1 / 1" if has_video else "4 / 3"),
            }
        )
    columns = "repeat(auto-fill, minmax(120px, 1fr))" if has_video else "repeat(2, minmax(0, 1fr))"
    return {"has_media_grid": True, "media_grid_items": cells, "media_grid_columns": columns}


def _normalize_news_type(category_or_query: str | None, source_name: str) -> str:
    label = (category_or_query or "").strip()
    if label.startswith("Telegram "):
        telegram_category = _TELEGRAM_CATEGORY_MAP.get(label[len("Telegram ") :].strip())
        if telegram_category:
            return telegram_category

    label = label.lower()
    if any(term in label for term in ("crypto", "blockchain", "token", "web3")):
        return "Cryptocurrency"
    if label == "ai" or any(term in label for term in ("artificial intelligence", "machine learning")):
        return "Artificial Intelligence"
    if any(term in label for term in ("stock market", "finance", "economy", "business")):
        return "Markets & Finance"
    if "tech" in label:
        return "Technology"

    source_lower = source_name.lower()
    if "cointelegraph" in source_lower:
        return "Cryptocurrency"
    if source_lower == "wired":
        return "Artificial Intelligence"
    if "techcrunch" in source_lower:
        return "Technology"
    return "General News"


def _article_excerpt(body: str, title: str) -> str:
    """Build a concise source excerpt without repeating the card headline."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in body.splitlines()]
    lines = [line for line in lines if line]
    normalized_title = re.sub(r"\s+", " ", title).strip().casefold()
    # Leading emoji-only lines (a decorative "💎💎💎" header) carry no text.
    while lines and not re.search(r"[^\W_]", lines[0]) and any(re.search(r"[^\W_]", l) for l in lines):
        lines.pop(0)
    if lines and lines[0].casefold() == normalized_title:
        lines.pop(0)
    excerpt = " ".join(lines)[:220].strip()
    return excerpt.rsplit(" ", 1)[0] + "…" if len(excerpt) == 220 else excerpt


def _build_article_row(row: dict) -> dict:
    published = row.get("published_date")
    body = row.get("full_body_text") or ""
    title = row.get("title") or ""
    snippet = _article_excerpt(body, title)
    source_name = row.get("source_name") or "Unknown"
    news_type = _normalize_news_type(row.get("category_or_query"), source_name)
    article_url = row.get("url") or ""
    fallback_image_url = _fallback_image_for(article_url, news_type)
    if row.get("source_type") == "telegram":
        # A Telegram post shows its group's profile picture instead of the
        # generic category fallback whenever it has no photo of its own (and
        # if its own photo ever fails to load).
        fallback_image_url = _telegram_group_avatar(article_url) or fallback_image_url
    image_url = row.get("image_url") or fallback_image_url
    card_media_image = _card_media_image(row.get("media"))
    if card_media_image:
        image_url = card_media_image
    return {
        "id": row.get("id"),
        "detail_url": "/news",
        "source_name": source_name,
        "badge_color": _BADGE_COLORS[hash(source_name) % len(_BADGE_COLORS)],
        "news_type": news_type,
        "news_type_color": _NEWS_TYPE_COLORS[news_type],
        "title": title,
        "url": article_url,
        "time_display": _relative_time(published),
        "snippet": snippet,
        "has_snippet": bool(snippet),
        "image_url": image_url,
        "fallback_image_url": fallback_image_url,
        "has_image": bool(image_url),
        # Marks a card sourced from app/services/telegram_pipeline.py (a
        # Telegram group post, not a web article) so the card can show a
        # distinguishing "Telegram News" badge, per explicit request.
        "is_telegram": row.get("source_type") == "telegram",
    }


def _build_article_rows(rows: list[dict]) -> list[dict]:
    """Attach stable human-readable URLs to article display rows.

    ID order means a later duplicate receives the next suffix without
    changing an already-published path. The used-set also handles a title
    that naturally ends in a numeric suffix (for example, "Report 1").
    """
    seen: dict[tuple[str, str], int] = {}
    used_paths: set[tuple[str, str]] = set()
    path_by_id: dict[int, tuple[str, str]] = {}
    for row in sorted(rows, key=lambda item: int(item.get("id") or 0)):
        source_name = row.get("source_name") or "Unknown"
        category_slug = _slugify(_normalize_news_type(row.get("category_or_query"), source_name))
        title_slug = _slugify(row.get("title") or "news")
        path_key = (category_slug, title_slug)
        duplicate_index = seen.get(path_key, 0)
        candidate = title_slug if duplicate_index == 0 else f"{title_slug}-{duplicate_index}"
        while (category_slug, candidate) in used_paths:
            duplicate_index += 1
            candidate = f"{title_slug}-{duplicate_index}"
        seen[path_key] = duplicate_index + 1
        used_paths.add((category_slug, candidate))
        path_by_id[row["id"]] = (category_slug, candidate)

    articles = []
    for row in rows:
        category_slug, article_slug = path_by_id[row["id"]]
        article = _build_article_row(row)
        articles.append(
            {
                **article,
                "news_category": category_slug,
                "article_slug": article_slug,
                "detail_url": f"/news/{category_slug}/{article_slug}",
            }
        )
    return articles


def _is_source_heading(line: str) -> bool:
    return 2 <= len(line.split()) <= 14 and len(line) <= 110 and not line.endswith((".", "!", "?", ":", ";"))


def _split_long_source_paragraph(paragraph: str) -> list[str]:
    if len(paragraph) <= _MAX_SOURCE_PARAGRAPH_CHARS:
        return [paragraph]
    sentences = _SENTENCE_BOUNDARY_RE.split(paragraph)
    if len(sentences) < 2:
        return [paragraph]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > _MAX_SOURCE_PARAGRAPH_CHARS:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_TRAILING_URL_PUNCT = ".,;:!?\u2019\u201d\u00bb"
# A URL is only linked when its host ends in a plausible TLD (letters only,
# up to 12 of them): extracted web article bodies sometimes contain garbled
# fragments like "https://www.beckershospitalreview." whose "TLD" would be a
# 20-letter word, or "https://investor" with no dot at all, and those would
# become dead links. Reserved names (RFC 2606) are never real.
_MAX_TLD_LENGTH = 12
_RESERVED_TLDS = {"invalid", "example", "test", "localhost"}
# Telegram group whose posts are replaced by the linked article's own text
# (see telegram_pipeline.expand_linked_article) — its bodies are not linkified.
_NO_LINKIFY_TELEGRAM_GROUPS = {"intradaydotmy"}


def _clean_url(raw: str) -> str:
    url = raw
    while url:
        if url[-1] in _TRAILING_URL_PUNCT:
            url = url[:-1]
        elif url[-1] in ")]}" and url.count(")") + url.count("]") + url.count("}") > url.count("(") + url.count("[") + url.count("{"):
            url = url[:-1]
        else:
            break
    return url


def _is_linkable_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    labels = host.split(".")
    return (
        len(labels) >= 2
        and all(re.fullmatch(r"[a-z0-9-]+", label) for label in labels)
        and re.fullmatch(r"[a-z]{2,%d}" % _MAX_TLD_LENGTH, labels[-1]) is not None
        and labels[-1] not in _RESERVED_TLDS
    )


def _link_segments(text: str, linkify: bool = True) -> list[dict]:
    """Splits one line of body text into plain and link segments so the
    reader can render each URL as a real link (new tab, with an icon)."""
    segments: list[dict] = []
    position = 0
    if linkify:
        for match in _URL_RE.finditer(text):
            url = _clean_url(match.group(0))
            if not url or not _is_linkable_url(url):
                continue
            if match.start() > position:
                segments.append({"text": text[position : match.start()], "url": "", "is_link": False})
            segments.append({"text": url, "url": url, "is_link": True})
            position = match.start() + len(url)
    if position < len(text):
        segments.append({"text": text[position:], "url": "", "is_link": False})
    return segments or [{"text": text, "url": "", "is_link": False}]


def _is_linkified_row(row: dict) -> bool:
    match = _TELEGRAM_URL_RE.match(row.get("url") or "")
    return not (match and match.group(1) in _NO_LINKIFY_TELEGRAM_GROUPS)


def _body_blocks(body: str, title: str, linkify: bool = True) -> list[dict]:
    """Preserve source sections while keeping unusually long runs readable."""
    blocks: list[dict] = []
    normalized_title = re.sub(r"\s+", " ", title).strip().casefold()
    for raw_line in body.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line.casefold() == normalized_title:
            continue
        if _is_source_heading(line):
            blocks.append({"text": line, "is_heading": True, "segments": _link_segments(line, linkify)})
            continue
        blocks.extend(
            {"text": paragraph, "is_heading": False, "segments": _link_segments(paragraph, linkify)}
            for paragraph in _split_long_source_paragraph(line)
        )
    if not blocks and body.strip():
        blocks = [
            {"text": paragraph, "is_heading": False, "segments": _link_segments(paragraph, linkify)}
            for paragraph in _split_long_source_paragraph(re.sub(r"\s+", " ", body).strip())
        ]
    return blocks


def _fetch_news_summary(article_id: int) -> tuple[str, str] | None:
    import sys

    root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    from app.services.news_summary_service import get_news_summary

    try:
        return get_news_summary(article_id)
    except Exception:
        return None


def _parse_summary_sections(raw: str) -> list[dict]:
    """Splits the model's `TITLE: <heading>` + paragraph output into sections."""
    parts = re.split(r"(?m)^TITLE:\s*(.+)$", raw.strip())
    if len(parts) == 1:
        return [{"title": "", "text": raw.strip()}] if raw.strip() else []
    sections = []
    if parts[0].strip():
        sections.append({"title": "", "text": parts[0].strip()})
    for i in range(1, len(parts), 2):
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            sections.append({"title": parts[i].strip(), "text": body})
    return sections


def _build_article_detail(row: dict | None, related_articles: list[dict]) -> dict:
    if row is None:
        return {}
    article = _build_article_row(row)
    body = (row.get("full_body_text") or "").strip()
    blocks = _body_blocks(body, article["title"], linkify=_is_linkified_row(row))
    return {
        **article,
        "published_display": _published_date_display(row.get("published_date")),
        **_media_grid(row.get("media")),
        "category_url": f"/news/{_slugify(article['news_type'])}",
        "body_blocks": blocks,
        "has_body": bool(blocks),
        "related_articles": related_articles,
    }


def _ensure_article_images(articles: list[dict]) -> dict[str, str]:
    """Prefer and persist real article images for one visible page."""
    candidates = {
        article["url"]: article
        for article in articles
        if article.get("url") and not article.get("is_telegram")
    }
    if not candidates:
        return {}

    import sys
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    from sqlalchemy import bindparam, text

    root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)

    from app.core.database import SessionLocal as OldSessionLocal
    from app.services.news_pipeline import (
        is_fallback_image,
        quick_page_image,
    )

    db = OldSessionLocal()
    try:
        statement = text(
            "SELECT url, image_url FROM news_articles WHERE url IN :urls"
        ).bindparams(bindparam("urls", expanding=True))
        stored = {
            row.url: row.image_url
            for row in db.execute(statement, {"urls": list(candidates)}).all()
        }
        updates: dict[str, str] = {}
        to_fetch: list[str] = []
        for url, image_url in stored.items():
            if image_url and not is_fallback_image(image_url):
                updates[url] = image_url
            else:
                to_fetch.append(url)
        for url in candidates:
            if url not in stored:
                to_fetch.append(url)

        if to_fetch:
            pool = ThreadPoolExecutor(max_workers=6)
            futures = {pool.submit(quick_page_image, url): url for url in to_fetch}
            for future, url in futures.items():
                try:
                    real_image = future.result(timeout=8)
                except Exception:  # noqa: BLE001 — timeout or fetch error, fall through
                    real_image = None
                if real_image:
                    updates[url] = real_image
                    db.execute(
                        text("UPDATE news_articles SET image_url = :image_url WHERE url = :url"),
                        {"image_url": real_image, "url": url},
                    )
                    continue
                existing_fallback = stored.get(url)
                if existing_fallback:
                    continue
            pool.shutdown(wait=False)
        db.commit()
        return updates
    except Exception:
        db.rollback()
        return {}
    finally:
        db.close()


def _merge_image_updates(articles: list[dict], updates: dict[str, str]) -> list[dict]:
    if not updates:
        return articles
    return [
        {
            **article,
            "image_url": updates.get(article["url"], article["image_url"]),
            "has_image": bool(updates.get(article["url"], article["image_url"])),
        }
        for article in articles
    ]


def _load_display_articles(enrich_after_id: int) -> tuple[list[dict], int]:
    """Blocking: every displayable article plus the table's current max id.

    Only first-page articles newer than enrich_after_id get the publisher-
    image lookup, so a periodic refresh doesn't re-fetch pages for articles
    it already tried on an earlier load. The max id is read *before* the
    rows, so anything inserted in between is picked up on the next check.
    """
    max_id = _fetch_max_article_id()
    articles = _build_article_rows(_fetch_articles())
    first_pages: list[dict] = []
    for news_type in dict.fromkeys(article["news_type"] for article in articles):
        first_pages.extend([
            article for article in articles if article["news_type"] == news_type
        ][:_PAGE_SIZE])
    new_first_page_articles = [article for article in first_pages if (article["id"] or 0) > enrich_after_id]
    updates = _ensure_article_images(new_first_page_articles)
    return _merge_image_updates(articles, updates), max_id


class NewsState(rx.State):
    # Backend-only (underscore prefix — never sent to the browser). The page
    # only renders news_sections' current page slices, so keeping the full
    # ~4k-article list server-side means each 60s refresh ships a few dozen
    # cards to the client, not every article.
    _all_articles: list[dict] = []
    # Highest news_articles.id as of the last load — watch_new_articles
    # reloads only when the table's max id moves past it.
    _last_seen_id: int = 0
    _is_watching: bool = False
    is_loading: bool = True
    # news type -> current page (1-indexed) — each section's own
    # independent pagination, keyed dynamically since the set of real
    # categories may grow as the ingestion taxonomy expands.
    category_pages: dict[str, int] = {}
    # news type -> selected real source name, or "All" (default, no filter).
    category_source_filter: dict[str, str] = {}
    # Per-section title search text (case-insensitive substring).
    category_search: dict[str, str] = {}
    # Current page of the /news/<category> "View All" list (100 per page).
    view_all_page: int = 1

    @rx.event(background=True)
    async def load_news(self):
        async with self:
            if self._all_articles or not self.is_loading:
                return  # already loaded this session — on_load can re-fire on nav
        # DB access is blocking (psycopg2/SQLAlchemy sync session) — runs in
        # a thread so it doesn't block this app's single asyncio event loop
        # the way every other on-demand DB refresh in this codebase already
        # avoids (see coin_state.py's own asyncio.to_thread(...) calls).
        articles, max_id = await asyncio.to_thread(_load_display_articles, 0)
        async with self:
            self._all_articles = articles
            self._last_seen_id = max_id
            self.is_loading = False

    @rx.event(background=True)
    async def watch_new_articles(self):
        """Every 60s while the tab is open, checks for new rows (e.g. a post
        telegram_listener.py just stored) and reloads the list if any
        arrived — so new posts appear without a page reload. Same
        started-once / stop-on-disconnect shape as CoinState.live_sync_loop.
        """
        async with self:
            if self._is_watching:
                return
            self._is_watching = True

        from frontend.frontend import app as reflex_app

        try:
            while True:
                await asyncio.sleep(60)
                if self.router.session.client_token not in reflex_app.event_namespace.token_to_sid:
                    break
                async with self:
                    last_seen = self._last_seen_id
                    loaded = not self.is_loading
                if not loaded or await asyncio.to_thread(_fetch_max_article_id) <= last_seen:
                    continue
                articles, max_id = await asyncio.to_thread(_load_display_articles, last_seen)
                async with self:
                    self._all_articles = articles
                    self._last_seen_id = max_id
        finally:
            async with self:
                self._is_watching = False

    @rx.event
    def set_category_page(self, news_type: str, page: int):
        self.category_pages = {**self.category_pages, news_type: page}

    async def _show_page_with_images(self, news_type: str, page: int):
        async with self:
            total = self._total_pages_for(news_type)
            page = max(1, min(total, page))
            self.category_pages = {**self.category_pages, news_type: page}
            articles = self._filtered_category_articles(news_type)
            start = (page - 1) * _PAGE_SIZE
            visible = articles[start : start + _PAGE_SIZE]
        updates = await asyncio.to_thread(_ensure_article_images, visible)
        if updates:
            async with self:
                self._all_articles = _merge_image_updates(self._all_articles, updates)

    @rx.event(background=True)
    async def prev_page(self, news_type: str):
        async with self:
            page = self.category_pages.get(news_type, 1) - 1
        await self._show_page_with_images(news_type, page)

    @rx.event(background=True)
    async def next_page(self, news_type: str):
        async with self:
            page = self.category_pages.get(news_type, 1) + 1
        await self._show_page_with_images(news_type, page)

    @rx.event(background=True)
    async def first_page(self, news_type: str):
        await self._show_page_with_images(news_type, 1)

    @rx.event(background=True)
    async def last_page(self, news_type: str):
        async with self:
            page = self._total_pages_for(news_type)
        await self._show_page_with_images(news_type, page)

    @rx.event
    def reset_view_all_page(self):
        self.view_all_page = 1

    @rx.event
    def view_all_first(self):
        self.view_all_page = 1

    @rx.event
    def view_all_prev(self):
        self.view_all_page = max(1, self.view_all["page"] - 1)

    @rx.event
    def view_all_next(self):
        self.view_all_page = min(self.view_all["total_pages"], self.view_all["page"] + 1)

    @rx.event
    def view_all_last(self):
        self.view_all_page = self.view_all["total_pages"]

    @rx.event(background=True)
    async def set_category_search(self, news_type: str, query: str):
        async with self:
            self.category_search = {**self.category_search, news_type: query}
            self.view_all_page = 1
        await self._show_page_with_images(news_type, 1)

    def _search_filter(self, news_type: str, articles: list[dict]) -> list[dict]:
        query = self.category_search.get(news_type, "").strip().lower()
        if not query:
            return articles
        return [a for a in articles if query in (a.get("title") or "").lower()]

    @rx.event(background=True)
    async def set_category_source(self, news_type: str, source: str):
        async with self:
            self.category_source_filter = {**self.category_source_filter, news_type: source}
            self.view_all_page = 1
        await self._show_page_with_images(news_type, 1)

    def _category_articles(self, news_type: str) -> list[dict]:
        return [a for a in self._all_articles if a["news_type"] == news_type]

    @staticmethod
    def _category_sources(category_articles: list[dict]) -> list[str]:
        counts: dict[str, int] = {}
        for article in category_articles:
            counts[article["source_name"]] = counts.get(article["source_name"], 0) + 1
        # "All" first (the default), then real sources ranked by how many
        # articles they contribute to this category, ties broken alphabetically.
        return ["All"] + sorted(counts, key=lambda name: (-counts[name], name))

    def _selected_source(self, news_type: str, sources: list[str]) -> str:
        selected = self.category_source_filter.get(news_type, "All")
        # A stale filter (the outlet no longer has any articles in this
        # category, e.g. after a fresh load) falls back to "All" rather
        # than silently showing zero results.
        return selected if selected in sources else "All"

    def _filtered_category_articles(self, news_type: str) -> list[dict]:
        category_articles = self._category_articles(news_type)
        sources = self._category_sources(category_articles)
        selected_source = self._selected_source(news_type, sources)
        if selected_source != "All":
            category_articles = [a for a in category_articles if a["source_name"] == selected_source]
        return self._search_filter(news_type, category_articles)

    def _total_pages_for(self, news_type: str) -> int:
        count = len(self._filtered_category_articles(news_type))
        return max(1, -(-count // _PAGE_SIZE))

    @rx.var(cache=True)
    def view_all(self) -> dict:
        """Data for /news/[news_category]: one category's newest
        _VIEW_ALL_LIMIT articles, with the same source-pill / search fields a
        /news section header uses (and the same per-category filter state)."""
        slug = (self.news_category or "").strip()
        news_type = next((t for t in _NEWS_TYPE_ORDER if _slugify(t) == slug), "")
        if not news_type:
            return {"found": False, "news_type": "", "article_count": 0, "range_start": 0, "range_end": 0,
                    "page": 1, "total_pages": 1, "has_pagination": False, "articles": [],
                    "top_sources": [], "other_sources": [], "has_other_sources": False, "other_selected": "",
                    "selected_source": "All", "search_text": ""}
        category_articles = self._category_articles(news_type)
        sources = self._category_sources(category_articles)
        selected_source = self._selected_source(news_type, sources)
        articles = self._search_filter(
            news_type,
            category_articles
            if selected_source == "All"
            else [a for a in category_articles if a["source_name"] == selected_source],
        )
        others = sources[1 + _TOP_SOURCE_PILLS :]
        total_pages = max(1, -(-len(articles) // _VIEW_ALL_LIMIT))
        page = max(1, min(self.view_all_page, total_pages))
        start = (page - 1) * _VIEW_ALL_LIMIT
        return {
            "found": True,
            "news_type": news_type,
            "article_count": len(articles),
            "range_start": start + 1 if articles else 0,
            "range_end": min(start + _VIEW_ALL_LIMIT, len(articles)),
            "page": page,
            "total_pages": total_pages,
            "has_pagination": total_pages > 1,
            "articles": articles[start : start + _VIEW_ALL_LIMIT],
            "selected_source": selected_source,
            "search_text": self.category_search.get(news_type, ""),
            "top_sources": sources[1 : 1 + _TOP_SOURCE_PILLS],
            "other_sources": others,
            "has_other_sources": bool(others),
            "other_selected": selected_source if selected_source in others else "",
        }

    @rx.var(cache=True)
    def view_all_title(self) -> str:
        news_type = self.view_all.get("news_type")
        return f"Repace - {news_type}" if news_type else "Repace - News"

    @rx.var(cache=True)
    def home_crypto_news(self) -> list[dict]:
        """Newest Cryptocurrency articles for the homepage slider (same rows
        and same live refresh as the /news Cryptocurrency section)."""
        return [a for a in self._all_articles if a["news_type"] == "Cryptocurrency"][:_HOME_NEWS_LIMIT]

    @rx.var(cache=True)
    def has_articles(self) -> bool:
        return len(self._all_articles) > 0

    @rx.var(cache=True)
    def news_sections(self) -> list[dict]:
        """One dict per normalized news type present in _all_articles,
        already sliced to that category's own current page — see this module's
        docstring for why this bakes the per-category pagination fully into
        one server-side computed var rather than trying to parameterize a
        computed var per dynamic source name (Reflex Vars can't easily be
        sliced per-`rx.foreach`-item that way).
        """
        grouped: dict[str, list[dict]] = {}
        for article in self._all_articles:
            grouped.setdefault(article["news_type"], []).append(article)

        ordered_categories = sorted(
            grouped.keys(),
            key=lambda news_type: (_NEWS_TYPE_ORDER.get(news_type, len(_NEWS_TYPE_ORDER)), news_type),
        )

        sections = []
        used_slugs: set[str] = set()
        for news_type in ordered_categories:
            category_articles = grouped[news_type]
            sources = self._category_sources(category_articles)
            selected_source = self._selected_source(news_type, sources)
            articles = self._search_filter(
                news_type,
                category_articles
                if selected_source == "All"
                else [a for a in category_articles if a["source_name"] == selected_source],
            )

            total_pages = max(1, -(-len(articles) // _PAGE_SIZE))
            page = max(1, min(self.category_pages.get(news_type, 1), total_pages))
            start = (page - 1) * _PAGE_SIZE
            # Disambiguate a slug collision (e.g. two non-ASCII outlet names
            # that both fall back to the generic "source" slug) by
            # appending a counter rather than silently sharing one anchor.
            slug = _slugify(news_type)
            if slug in used_slugs:
                i = 2
                while f"{slug}-{i}" in used_slugs:
                    i += 1
                slug = f"{slug}-{i}"
            used_slugs.add(slug)
            sections.append(
                {
                    "news_type": news_type,
                    "anchor_id": slug,
                    "view_all_url": f"/news/{_slugify(news_type)}",
                    "article_count": len(articles),
                    "page": page,
                    "total_pages": total_pages,
                    "has_pagination": total_pages > 1,
                    "articles": articles[start : start + _PAGE_SIZE],
                    "sources": sources,
                    "selected_source": selected_source,
                    "search_text": self.category_search.get(news_type, ""),
                    # Top publishers become pills; the rest go in an "Other" dropdown.
                    "top_sources": sources[1 : 1 + _TOP_SOURCE_PILLS],
                    "other_sources": sources[1 + _TOP_SOURCE_PILLS :],
                    "has_other_sources": len(sources) > 1 + _TOP_SOURCE_PILLS,
                    "other_selected": selected_source if selected_source in sources[1 + _TOP_SOURCE_PILLS :] else "",
                }
            )
        return sections


class NewsDetailState(rx.State):
    """State for one /news/[news_category]/[article_slug] reader page."""

    article: dict = {}
    is_loading: bool = True
    # AI summary above the body: "loading" while it's generated, then
    # "ready" (summary_sections filled) or "none" (couldn't be produced).
    summary_status: str = "none"
    summary_sections: list[dict] = []
    summary_model_badge: dict = {}

    @rx.event(background=True)
    async def load_article(self):
        async with self:
            news_category = self.news_category.strip()
            article_slug = self.article_slug.strip()
            self.article = {}
            self.is_loading = True
        row, related_articles = (
            await asyncio.to_thread(_fetch_article_by_path, news_category, article_slug)
            if news_category and article_slug
            else (None, [])
        )
        async with self:
            self.article = _build_article_detail(row, related_articles)
            self.is_loading = False
            self.summary_sections = []
            self.summary_model_badge = {}
            article_id = row.get("id") if row else None
            self.summary_status = "loading" if article_id else "none"
        if not article_id:
            return
        result = await asyncio.to_thread(_fetch_news_summary, int(article_id))
        async with self:
            if self.article.get("id") != article_id:
                return  # the viewer already moved to another article
            if result is None:
                self.summary_status = "none"
                return
            raw, model = result
            self.summary_sections = _parse_summary_sections(raw)
            self.summary_model_badge = _format_model_badge(model)
            self.summary_status = "ready" if self.summary_sections else "none"

    @rx.var(cache=True)
    def article_found(self) -> bool:
        return bool(self.article)

    @rx.var(cache=True)
    def page_title(self) -> str:
        title = self.article.get("title")
        return f"Repace - {title}" if title else "Repace - News"
