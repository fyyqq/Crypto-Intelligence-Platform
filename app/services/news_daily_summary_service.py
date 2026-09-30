"""Per-category "what happened today" summary shown in the popup on each
/news/<category> page.

Storage: one row per (category, day) in `news_daily_summaries`, where "day" is
the Asia/Kuala_Lumpur calendar date. The first request of a day that finds no
row generates one from the last 24 hours of that category's headlines with
OpenRouter (so it costs at most one call per category per day, on a button
click, and counts against ai_budget's hourly cap); every later request that
day reads the stored row. Today's (2026-10-01) summaries were written by hand
by Claude Code and stored with model = "claude-code" — no OpenRouter call.

Payload returned to the UI:
    {"available": bool, "overview": str, "sections": [{"title", "points": [str]}],
     "model_label": str, "article_count": int, "day": "1 Oct 2026", "message": str}
"""

import datetime
import json
import logging
import re
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services import ai_budget
from app.services.news_summary_service import _call_openrouter

logger = logging.getLogger(__name__)

KL = ZoneInfo("Asia/Kuala_Lumpur")
_MAX_HEADLINES = 120

_SYSTEM_PROMPT = (
    "You summarize a day of news headlines for one news category. You get "
    "headlines from the last 24 hours (time | source | headline). Reply with "
    "ONLY a JSON object: {\"overview\": \"2-3 sentence summary of what "
    "happened\", \"sections\": [{\"title\": \"short theme heading\", \"points\": "
    "[\"one factual sentence\", ...]}]} with 3-6 sections of 2-5 points each, "
    "most important first. Merge duplicate reports of the same event. Only "
    "state what the headlines say; never invent facts, numbers or outcomes. "
    "No investment advice."
)


def today_kl() -> datetime.date:
    return datetime.datetime.now(KL).date()


def _ensure_table() -> None:
    db = SessionLocal()
    try:
        db.execute(text(
            """CREATE TABLE IF NOT EXISTS news_daily_summaries (
                   category_slug TEXT NOT NULL,
                   day DATE NOT NULL,
                   summary JSONB NOT NULL,
                   model TEXT NOT NULL,
                   article_count INTEGER NOT NULL DEFAULT 0,
                   created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                   PRIMARY KEY (category_slug, day)
               )"""
        ))
        db.commit()
    finally:
        db.close()


def _model_label(model: str) -> str:
    if model == "claude-code":
        return "Claude Code"
    slug = model.split(":")[0].rpartition("/")[2]
    return f"OpenRouter · {slug}"


def _payload(summary: dict, model: str, article_count: int, day: datetime.date) -> dict:
    return {
        "available": True,
        "overview": str(summary.get("overview", "")),
        "sections": [
            {"title": str(s.get("title", "")), "points": [str(p) for p in s.get("points", [])]}
            for s in summary.get("sections", [])
        ],
        "model_label": _model_label(model),
        "article_count": article_count,
        "day": f"{day.day} {day.strftime('%b %Y')}",
        "message": "",
    }


def _unavailable(message: str, day: datetime.date) -> dict:
    return {"available": False, "overview": "", "sections": [], "model_label": "", "article_count": 0,
            "day": f"{day.day} {day.strftime('%b %Y')}", "message": message}


def store_summary(category_slug: str, day: datetime.date, summary: dict, model: str, article_count: int) -> None:
    _ensure_table()
    db = SessionLocal()
    try:
        db.execute(
            text(
                """INSERT INTO news_daily_summaries (category_slug, day, summary, model, article_count)
                   VALUES (:s, :d, CAST(:j AS JSONB), :m, :n)
                   ON CONFLICT (category_slug, day) DO UPDATE
                   SET summary = EXCLUDED.summary, model = EXCLUDED.model,
                       article_count = EXCLUDED.article_count, created_at = NOW()"""
            ),
            {"s": category_slug, "d": day, "j": json.dumps(summary), "m": model, "n": article_count},
        )
        db.commit()
    finally:
        db.close()


def _parse_json(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) and data.get("sections") else None


def get_daily_summary(category_slug: str, news_type: str, headlines: list[tuple[str, str, str]]) -> dict:
    """headlines: (time "HH:MM", source, title) for the last 24h, newest first."""
    day = today_kl()
    _ensure_table()
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT summary, model, article_count FROM news_daily_summaries WHERE category_slug = :s AND day = :d"),
            {"s": category_slug, "d": day},
        ).first()
    finally:
        db.close()
    if row:
        return _payload(row[0], row[1], row[2], day)
    if not headlines:
        return {**_unavailable("", day), "available": True, "overview": "No news in the last 24 hours.", "model_label": "", "article_count": 0}

    seen: set[str] = set()
    lines = []
    for when, source, title in headlines:
        key = re.sub(r"\W+", " ", title.lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{when} | {source} | {title[:160]}")
        if len(lines) >= _MAX_HEADLINES:
            break
    if ai_budget.in_cooldown(f"daily-summary:{category_slug}"):
        return _unavailable("The summary isn't available right now — please try again in a few minutes.", day)
    result = _call_openrouter(
        f"Category: {news_type}\n\nHeadlines:\n" + "\n".join(lines), system=_SYSTEM_PROMPT, max_tokens=1100
    )
    summary = _parse_json(result[0]) if result else None
    if not summary:
        ai_budget.mark_failed(f"daily-summary:{category_slug}")
        return _unavailable("The summary isn't available right now — please try again in a few minutes.", day)
    store_summary(category_slug, day, summary, result[1], len(headlines))
    return _payload(summary, result[1], len(headlines), day)
