"""On-demand AI summary for one /news article, shown above the article body
in the reader. Grounded in the article's own title and extracted text, plus a
few headlines about the same story from other outlets (a Google News RSS
search on the title — free, no API key) so the model can cross-check and add
context. Generated via OpenRouter with the same free model the coin
"AI Summarizations" section uses, cached on the news_articles row (ai_summary
/ ai_summary_model) so each article is only ever summarized once.

Text-only: the configured free OpenRouter model can't read images, so the
article's picture is not part of the input.


The reader's EN | MY tabs: get_news_summary_translation() translates that same cached summary into Malay (Bahasa
Malaysia) on first request, with the local NLLB model (offline, no limit; the free AI models are only the fallback), and
caches it on the row too (ai_summary_ms / ai_summary_ms_model), so each article is translated at most once.
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
from app.services import ai_budget, local_translate_service

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


_TRANSLATE_SYSTEM_MS = (
    "You are a professional translator from English to Malay (Bahasa Malaysia, as written in Malaysia). You get a short "
    "news summary made of paragraphs, each introduced by a line reading exactly `TITLE: <heading>`. Translate the "
    "headings and the paragraphs into natural, neutral Malay. Keep the structure identical: the same number of "
    "sections, every heading still on its own line starting with exactly `TITLE:` (do NOT translate the word TITLE), "
    "then the paragraph prose. The heading text after `TITLE:` MUST be translated into Malay too, never left in "
    "English. Keep numbers, dates, names of people, companies, coins and tickers, currency codes and URLs unchanged. "
    "Plain prose only: no markdown, no notes, no explanations, nothing before or after the translation.\n\n"
    "Example input:\nTITLE: Market Rally\nBitcoin rose 5% today as traders returned.\n\n"
    "Example output:\nTITLE: Kenaikan Pasaran\nBitcoin naik 5% hari ini apabila pedagang kembali."
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
        # Only ALTER when missing (ALTER locks the table even if the column exists).
        have = db.execute(text(
            "SELECT count(*) FROM information_schema.columns WHERE table_name = 'news_articles' "
            "AND column_name IN ('ai_summary', 'ai_summary_model', 'ai_summary_ms', 'ai_summary_ms_model')"
        )).scalar()
        if have < 4:
            db.execute(text("SET lock_timeout = '3s'"))
            db.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS ai_summary TEXT"))
            db.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS ai_summary_model TEXT"))
            db.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS ai_summary_ms TEXT"))
            db.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS ai_summary_ms_model TEXT"))
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
_FALLBACK_MODELS = ["google/gemma-4-31b-it:free", "nvidia/nemotron-3-super-120b-a12b:free"]  # the old qwen3.8 id no longer exists (404)


def _call_openrouter(prompt: str, system: str | None = None, max_tokens: int = 600) -> tuple[str, str] | None:
    for model in [settings.openrouter_model, *_FALLBACK_MODELS]:
        result = _call_model(prompt, model, system, max_tokens)
        if result is not None:
            return result
        if ai_budget.blocked():  # daily limit: the other models share it
            break
    return None


def _call_model(prompt: str, model: str, system: str | None = None, max_tokens: int = 600) -> tuple[str, str] | None:
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
                        {"role": "system", "content": system or _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "reasoning": {"enabled": False},
                },
                timeout=40,
            )
            if ai_budget.note_response(response.status_code, response.text):
                logger.warning("OpenRouter daily free-tier limit reached — AI calls paused until it resets")
                return None
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


def translation_has_same_sections(source: str, translated: str) -> bool:
    """A locally made translation only has to keep the same number of `TITLE:` sections (every heading is translated by construction)."""
    return len(_titles(source)) == len(_titles(translated)) and len(translated.strip()) >= 20


def _titles(text_: str) -> list[str]:
    return [t.strip().lower() for t in re.findall(r"(?m)^TITLE:\s*(.+)$", text_ or "")]


def translation_is_valid(source: str, translated: str) -> bool:
    """A translation is kept only when it is non-trivial, still has the same `TITLE:` sections as the English summary,
    and its headings were really translated (a model that leaves every heading in English is rejected)."""
    translated = (translated or "").strip()
    if len(translated) < 20:
        return False
    src_titles, new_titles = _titles(source), _titles(translated)
    if len(new_titles) != len(src_titles):
        return False
    if src_titles and sum(1 for a, b in zip(src_titles, new_titles) if a != b) * 2 < len(src_titles):
        return False  # at least half of the headings must differ from the English ones
    return True


def _split_summary(source: str) -> list[tuple[str, str]]:
    """The summary as [(heading, paragraph), ...]: the `TITLE:` sections the model wrote (one ("", text) when there are none)."""
    parts = re.split(r"(?m)^TITLE:\s*(.+)$", source.strip())
    if len(parts) == 1:
        return [("", source.strip())] if source.strip() else []
    sections = [("", parts[0].strip())] if parts[0].strip() else []
    for i in range(1, len(parts), 2):
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            sections.append((parts[i].strip(), body))
    return sections


LOCAL_MODEL_NAME = "NLLB-200 (local)"


def _translate_local(source: str) -> tuple[str, str] | None:
    """Translates the summary to Malay with the local NLLB model (app/services/local_translate_service.py: offline, no key, no
    limit). Every heading and paragraph is translated on its own and put back in the same `TITLE:` format. None when the model
    is not installed or fails (the caller falls back to the AI models)."""
    sections = _split_summary(source)
    if not sections:
        return None
    strings = [s for heading, body in sections for s in ((heading, body) if heading else (body,))]
    translated = local_translate_service.translate_texts(strings, "ms")
    if translated is None or len(translated) != len(strings) or not all(t.strip() for t in translated):
        return None
    out, i = [], 0
    for heading, _body in sections:
        if heading:
            out.append(f"TITLE: {translated[i]}\n{translated[i + 1]}")
            i += 2
        else:
            out.append(translated[i])
            i += 1
    return "\n\n".join(out), LOCAL_MODEL_NAME


def summary_unavailable_reason(article_id: int) -> str:
    """Why this story has no AI summary right now, in one sentence for the reader (the card used to just vanish)."""
    if ai_budget.blocked():
        return "The free AI daily limit is used up, so new summaries are paused until 08:00 Malaysia time."
    if not settings.openrouter_api_key:
        return "AI summaries are not set up on this server."
    if ai_budget.in_cooldown(f"news:{article_id}"):
        return "The AI could not summarize this story a moment ago. It will try again in a few minutes."
    return "No AI summary could be made for this story right now."


def unavailable_reason() -> str:
    """Why a Malay translation could not be made, in one short sentence for the reader's note."""
    if not local_translate_service.is_available():
        if ai_budget.blocked():
            return "The local translation model is not installed on this server, and the free AI daily limit is used up (it resets at 08:00 Malaysia time)."
        return "The local translation model is not installed on this server."
    return "The Malay translation is not available right now."


def _translate(source: str) -> tuple[str, str] | None:
    """The local model first (free, offline, unlimited), then the AI models in turn, until one returns a valid Malay version."""
    local = _translate_local(source)
    if local is not None and translation_has_same_sections(source, local[0]):
        return local
    for model in [settings.openrouter_model, *_FALLBACK_MODELS]:
        result = _call_model(source, model, _TRANSLATE_SYSTEM_MS, 1400)
        if result is not None and translation_is_valid(source, result[0]):
            return result
        if ai_budget.blocked():  # daily limit: the other models share it
            break
    return None


def get_news_summary_translation(article_id: int, lang: str = "ms") -> tuple[str, str] | None:
    """Returns (malay_summary_text, model) for this article's cached English summary: cached if present, otherwise
    translated and stored. None if it can't be produced (no English summary yet, budget, model errors, bad output)."""
    if lang != "ms":
        return None
    _ensure_columns()
    cooldown_key = f"news-ms:{article_id}"
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT ai_summary, ai_summary_ms, ai_summary_ms_model FROM news_articles WHERE id = :id"),
            {"id": article_id},
        ).mappings().first()
        if row is None or not row["ai_summary"]:
            return None
        if row["ai_summary_ms"]:
            return row["ai_summary_ms"], row["ai_summary_ms_model"] or ""
        if ai_budget.in_cooldown(cooldown_key) and not local_translate_service.is_available():
            return None  # the AI models failed recently (the local model is not affected by that)
        result = _translate(row["ai_summary"])
        if result is None:
            ai_budget.mark_failed(cooldown_key)
            return None
        translated, model = result[0].strip(), result[1]
        db.execute(
            text("UPDATE news_articles SET ai_summary_ms = :s, ai_summary_ms_model = :m WHERE id = :id"),
            {"s": translated, "m": model, "id": article_id},
        )
        db.commit()
        return translated, model
    finally:
        db.close()
