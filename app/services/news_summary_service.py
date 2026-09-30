"""On-demand AI summary for one /news article, shown above the article body
in the reader. Grounded in the article's own title and extracted text, plus a
few headlines about the same story from other outlets (a Google News RSS
search on the title — free, no API key) so the model can cross-check and add
context. Generated via OpenRouter with the same free model the coin
"AI Summarizations" section uses, cached on the news_articles row (ai_summary
/ ai_summary_model) so each article is only ever summarized once.

Text-only: the configured free OpenRouter model can't read images, so the
article's picture is not part of the input.
"""

import logging
import re
import time
import urllib.parse

import feedparser
import requests
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.services import ai_budget

logger = logging.getLogger(__name__)

_MAX_BODY_CHARS = 4000
_MAX_RELATED = 6
_MAX_ATTEMPTS = 2  # per model
_RETRY_DELAY_SECONDS = 4

_SYSTEM_PROMPT = (
    "You summarize news for a general reader. You get one article's headline "
    "and text, plus headlines from other outlets covering what looks like the "
    "same story. Write a short, neutral summary in 2-3 short paragraphs, each "
    "covering one distinct topic (for example: what happened, the context or "
    "background, why it matters). Prefix EVERY paragraph, with no exceptions, "
    "with a line reading exactly `TITLE: <a 2-4 word heading>` on its own "
    "line, then the paragraph's plain prose on the next line(s) — no bullet "
    "points, no other markdown. Only state facts supported by the provided "
    "text or headlines; never invent numbers, quotes, names or outcomes. If "
    "the article text is missing or thin, say plainly what is and isn't known "
    "instead of guessing. Do not give investment advice."
)


_columns_ready = False


def _ensure_columns() -> None:
    """Adds the cache columns once per process, in its own short session so
    the ALTER never waits on (or blocks) a transaction of ours."""
    global _columns_ready
    if _columns_ready:
        return
    db = SessionLocal()
    try:
        db.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS ai_summary TEXT"))
        db.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS ai_summary_model TEXT"))
        db.commit()
        _columns_ready = True
    finally:
        db.close()


def _related_headlines(title: str, own_url: str) -> list[str]:
    """Headlines from other outlets about the same story, via Google News RSS."""
    query = re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", title)).strip()[:120]
    if not query:
        return []
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
    except Exception as exc:  # network / parse failure just means no extra context
        logger.info("Related-headline search failed: %s", exc)
        return []
    headlines = []
    for entry in feed.entries[: _MAX_RELATED + 2]:
        headline = (entry.get("title") or "").strip()
        if headline and headline.lower() != title.strip().lower():
            headlines.append(headline)
    return headlines[:_MAX_RELATED]


# Free-tier models are often overloaded upstream; try these in turn.
_FALLBACK_MODELS = ["google/gemma-4-31b-it:free", "qwen/qwen3.8-27b:free"]


def _call_openrouter(prompt: str) -> tuple[str, str] | None:
    for model in [settings.openrouter_model, *_FALLBACK_MODELS]:
        result = _call_model(prompt, model)
        if result is not None:
            return result
    return None


def _call_model(prompt: str, model: str) -> tuple[str, str] | None:
    if not settings.openrouter_api_key:
        logger.info("OPENROUTER_API_KEY not configured — skipping news summary")
        return None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if not ai_budget.allow_call():
            logger.warning("OpenRouter hourly call budget reached — skipping news summary")
            return None
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 600,
                    "reasoning": {"enabled": False},
                },
                timeout=40,
            )
            if response.status_code == 429 and attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("News summary generation failed: %s", exc)
            return None
        if data.get("error"):
            # OpenRouter reports upstream overload as HTTP 200 with an error body.
            logger.info("OpenRouter upstream error (attempt %d/%d): %s", attempt, _MAX_ATTEMPTS, data["error"].get("message"))
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            return None
        choices = data.get("choices") or []
        content = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
        if content:
            return content, data.get("model") or settings.openrouter_model
    return None


def get_news_summary(article_id: int) -> tuple[str, str] | None:
    """Returns (summary_text, model) for this article — cached if present,
    otherwise generated and stored. None if it can't be produced."""
    _ensure_columns()
    cooldown_key = f"news:{article_id}"
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT title, url, full_body_text, category_or_query, ai_summary, ai_summary_model "
                "FROM news_articles WHERE id = :id"
            ),
            {"id": article_id},
        ).mappings().first()
        if row is None:
            return None
        if row["ai_summary"]:
            return row["ai_summary"], row["ai_summary_model"] or ""
        if ai_budget.in_cooldown(cooldown_key):
            return None  # failed recently — don't spend more calls on it yet

        body = (row["full_body_text"] or "").strip()[:_MAX_BODY_CHARS]
        related = _related_headlines(row["title"] or "", row["url"] or "")
        prompt = (
            f"Headline: {row['title']}\n\n"
            f"Article text: {body or '(not available)'}\n\n"
            "Headlines from other outlets on the same story:\n"
            + ("\n".join(f"- {h}" for h in related) if related else "(none found)")
        )
        result = _call_openrouter(prompt)
        if result is None:
            ai_budget.mark_failed(cooldown_key)
            return None
        summary, model = result
        db.execute(
            text("UPDATE news_articles SET ai_summary = :s, ai_summary_model = :m WHERE id = :id"),
            {"s": summary, "m": model, "id": article_id},
        )
        db.commit()
        return summary, model
    finally:
        db.close()
