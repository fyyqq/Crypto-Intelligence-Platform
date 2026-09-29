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
import re

import reflex as rx

_PAGE_SIZE = 12  # 4 columns x 3 rows per page, per explicit request

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


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
                SELECT source_name, category_or_query, title, url, published_date, full_body_text
                FROM news_articles
                WHERE published_date >= NOW() - INTERVAL '90 days'
                ORDER BY published_date DESC NULLS LAST, id DESC
                """
            )
        ).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []
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

_NEWS_TYPE_COLORS = {
    "Cryptocurrency": "amber",
    "Artificial Intelligence": "purple",
    "Markets & Finance": "green",
    "Technology": "cyan",
    "General News": "gray",
}

_NEWS_TYPE_ORDER = {
    "Cryptocurrency": 0,
    "Artificial Intelligence": 1,
    "Markets & Finance": 2,
    "Technology": 3,
    "General News": 4,
}


def _normalize_news_type(category_or_query: str | None, source_name: str) -> str:
    label = (category_or_query or "").strip().lower()
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


def _build_article_row(row: dict) -> dict:
    published = row.get("published_date")
    body = row.get("full_body_text") or ""
    snippet = body[:220].strip()
    if len(body) > 220:
        snippet = snippet.rsplit(" ", 1)[0] + "…"
    source_name = row.get("source_name") or "Unknown"
    news_type = _normalize_news_type(row.get("category_or_query"), source_name)
    return {
        "source_name": source_name,
        "badge_color": _BADGE_COLORS[hash(source_name) % len(_BADGE_COLORS)],
        "news_type": news_type,
        "news_type_color": _NEWS_TYPE_COLORS[news_type],
        "title": row.get("title") or "",
        "url": row.get("url") or "",
        "time_display": _relative_time(published),
        "snippet": snippet,
        "has_snippet": bool(snippet),
    }


class NewsState(rx.State):
    all_articles: list[dict] = []
    is_loading: bool = True
    # news type -> current page (1-indexed) — each section's own
    # independent pagination, keyed dynamically since the set of real
    # categories may grow as the ingestion taxonomy expands.
    category_pages: dict[str, int] = {}
    # news type -> selected real source name, or "All" (default, no filter).
    category_source_filter: dict[str, str] = {}

    @rx.event(background=True)
    async def load_news(self):
        async with self:
            if self.all_articles or not self.is_loading:
                return  # already loaded this session — on_load can re-fire on nav
        # DB access is blocking (psycopg2/SQLAlchemy sync session) — runs in
        # a thread so it doesn't block this app's single asyncio event loop
        # the way every other on-demand DB refresh in this codebase already
        # avoids (see coin_state.py's own asyncio.to_thread(...) calls).
        rows = await asyncio.to_thread(_fetch_articles)
        articles = [_build_article_row(r) for r in rows]
        async with self:
            self.all_articles = articles
            self.is_loading = False

    @rx.event
    def set_category_page(self, news_type: str, page: int):
        self.category_pages = {**self.category_pages, news_type: page}

    @rx.event
    def prev_page(self, news_type: str):
        current = self.category_pages.get(news_type, 1)
        self.category_pages = {**self.category_pages, news_type: max(1, current - 1)}

    @rx.event
    def next_page(self, news_type: str):
        current = self.category_pages.get(news_type, 1)
        total = self._total_pages_for(news_type)
        self.category_pages = {**self.category_pages, news_type: min(total, current + 1)}

    @rx.event
    def first_page(self, news_type: str):
        self.category_pages = {**self.category_pages, news_type: 1}

    @rx.event
    def last_page(self, news_type: str):
        total = self._total_pages_for(news_type)
        self.category_pages = {**self.category_pages, news_type: total}

    @rx.event
    def set_category_source(self, news_type: str, source: str):
        self.category_source_filter = {**self.category_source_filter, news_type: source}
        self.category_pages = {**self.category_pages, news_type: 1}

    def _category_articles(self, news_type: str) -> list[dict]:
        return [a for a in self.all_articles if a["news_type"] == news_type]

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
        if selected_source == "All":
            return category_articles
        return [a for a in category_articles if a["source_name"] == selected_source]

    def _total_pages_for(self, news_type: str) -> int:
        count = len(self._filtered_category_articles(news_type))
        return max(1, -(-count // _PAGE_SIZE))

    @rx.var(cache=True)
    def has_articles(self) -> bool:
        return len(self.all_articles) > 0

    @rx.var(cache=True)
    def news_sections(self) -> list[dict]:
        """One dict per normalized news type present in all_articles,
        already sliced to that category's own current page — see this module's
        docstring for why this bakes the per-category pagination fully into
        one server-side computed var rather than trying to parameterize a
        computed var per dynamic source name (Reflex Vars can't easily be
        sliced per-`rx.foreach`-item that way).
        """
        grouped: dict[str, list[dict]] = {}
        for article in self.all_articles:
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
            articles = (
                category_articles
                if selected_source == "All"
                else [a for a in category_articles if a["source_name"] == selected_source]
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
                    "article_count": len(articles),
                    "page": page,
                    "total_pages": total_pages,
                    "has_pagination": total_pages > 1,
                    "articles": articles[start : start + _PAGE_SIZE],
                    "sources": sources,
                    "selected_source": selected_source,
                }
            )
        return sections
