"""State for the /news page — reads real articles from the news_articles
table (app/services/news_pipeline.py) and groups them by their real outlet
name (TechCrunch, Cointelegraph, Reuters, ...), each outlet its own
independently-paginated 3-column x 2-row grid section.

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

import reflex as rx

_PAGE_SIZE = 6  # 3 columns x 2 rows per page, per explicit request


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
                SELECT source_name, title, url, published_date, full_body_text
                FROM news_articles
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


def _build_article_row(row: dict) -> dict:
    published = row.get("published_date")
    body = row.get("full_body_text") or ""
    snippet = body[:220].strip()
    if len(body) > 220:
        snippet = snippet.rsplit(" ", 1)[0] + "…"
    source_name = row.get("source_name") or "Unknown"
    return {
        "source_name": source_name,
        "badge_color": _BADGE_COLORS[hash(source_name) % len(_BADGE_COLORS)],
        "title": row.get("title") or "",
        "url": row.get("url") or "",
        "time_display": _relative_time(published),
        "snippet": snippet,
        "has_snippet": bool(snippet),
    }


class NewsState(rx.State):
    all_articles: list[dict] = []
    is_loading: bool = True
    # outlet name -> current page (1-indexed) — each section's own
    # independent pagination, keyed dynamically since the set of real
    # outlets in the database isn't fixed/hardcoded.
    source_pages: dict[str, int] = {}

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
    def set_source_page(self, source_name: str, page: int):
        self.source_pages = {**self.source_pages, source_name: page}

    @rx.event
    def prev_page(self, source_name: str):
        current = self.source_pages.get(source_name, 1)
        self.source_pages = {**self.source_pages, source_name: max(1, current - 1)}

    @rx.event
    def next_page(self, source_name: str):
        current = self.source_pages.get(source_name, 1)
        total = self._total_pages_for(source_name)
        self.source_pages = {**self.source_pages, source_name: min(total, current + 1)}

    def _total_pages_for(self, source_name: str) -> int:
        count = sum(1 for a in self.all_articles if a["source_name"] == source_name)
        return max(1, -(-count // _PAGE_SIZE))

    @rx.var(cache=True)
    def has_articles(self) -> bool:
        return len(self.all_articles) > 0

    @rx.var(cache=True)
    def news_sections(self) -> list[dict]:
        """One dict per real outlet present in all_articles, already
        sliced to that outlet's own current page — see this module's
        docstring for why this bakes the per-source pagination fully into
        one server-side computed var rather than trying to parameterize a
        computed var per dynamic source name (Reflex Vars can't easily be
        sliced per-`rx.foreach`-item that way).
        """
        grouped: dict[str, list[dict]] = {}
        for article in self.all_articles:
            grouped.setdefault(article["source_name"], []).append(article)

        # Most-articles-first, not alphabetical — the historical Google
        # News lookback surfaces dozens of real but single-article outlets
        # (a state library site, a university newsroom, ...) alongside the
        # three curated, substantial RSS feeds (TechCrunch/Cointelegraph/
        # WIRED); alphabetical order buried those three under an "A"/"1"-
        # heavy wall of one-off sources, confirmed live. Ties broken
        # alphabetically for a stable order.
        ordered_sources = sorted(grouped.keys(), key=lambda name: (-len(grouped[name]), name))

        sections = []
        for source_name in ordered_sources:
            articles = grouped[source_name]
            total_pages = max(1, -(-len(articles) // _PAGE_SIZE))
            page = max(1, min(self.source_pages.get(source_name, 1), total_pages))
            start = (page - 1) * _PAGE_SIZE
            sections.append(
                {
                    "source_name": source_name,
                    "article_count": len(articles),
                    "page": page,
                    "total_pages": total_pages,
                    "has_pagination": total_pages > 1,
                    "articles": articles[start : start + _PAGE_SIZE],
                }
            )
        return sections
