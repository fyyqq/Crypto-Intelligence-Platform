"""On-demand AI "business model" explainer — Feature 2's AI Business Model
Agent per ai-instructions.md, scoped down to a plain-language summary rather
than the full whitepaper-ingestion pipeline described there: whitepaper PDFs
aren't fetched/parsed here, since the request this fulfilled explicitly
wanted a short (2-3 paragraph), newcomer-friendly explainer, not a deep
technical breakdown — the coin's own name, category tags, and real
description (see coingecko_service.py) are already enough grounding for
that. Generated via OpenRouter (not a direct per-provider key) so the model
can be swapped via settings.openrouter_model without a code change.

Gated by Coin.business_summary_updated_at + settings.business_summary_ttl_days
(60d default) rather than once-forever, since a project's real business
model can change in ways its CMC/CoinGecko description won't reflect.
"""

import logging
import time
from datetime import datetime, timedelta

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.coin import Coin

logger = logging.getLogger(__name__)

# :free-suffixed OpenRouter models draw from a shared provider pool that
# returns 429 "temporarily rate-limited upstream" fairly often — confirmed
# live against several free models in a row, unrelated to OpenRouter's own
# per-account free-tier quota (checked separately via /api/v1/key, which
# showed 50/50 daily requests still available at the time). A couple of
# short retries clears most of these, since they're describing shared-
# capacity contention, not a hard block.
_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 4

_SYSTEM_PROMPT = (
    "You explain cryptocurrency projects to complete beginners who have never "
    "used crypto before. Given a coin's name, ticker, category tags, and its "
    "own project description, write a short, plain-language explainer in "
    "2-3 short paragraphs, each covering one distinct topic — typically "
    "what the project actually does, then its business model, then how it "
    "makes money or captures value (if it's a pure meme/community coin with "
    "no real business model, say so plainly in that last paragraph instead "
    "of inventing one). Prefix EVERY paragraph, with no exceptions, with a "
    "line reading exactly `TITLE: <a 2-4 word heading for that paragraph>` "
    "on its own line, then the paragraph's plain prose on the next line(s) — "
    "no bullet points, no other markdown formatting anywhere. Avoid jargon "
    "where possible, and briefly explain any technical term you do need to "
    "use. Example shape (do not copy the content, only the structure):\n"
    "TITLE: What It Does\n"
    "<paragraph>\n"
    "TITLE: Business Model\n"
    "<paragraph>"
)


def needs_refresh(coin: Coin) -> bool:
    if not coin.business_summary:
        return True
    if coin.business_summary_updated_at is None:
        return True
    ttl = timedelta(days=settings.business_summary_ttl_days)
    return datetime.utcnow() - coin.business_summary_updated_at > ttl


def _build_user_prompt(coin: Coin) -> str:
    tags = ", ".join(sorted(category.name for category in coin.categories)) or "none listed"
    description = (coin.description or "").strip() or "No project description available."
    return (
        f"Coin name: {coin.name}\n"
        f"Ticker: {coin.symbol}\n"
        f"Category tags: {tags}\n"
        f"Project's own description: {description}"
    )


def _fetch_from_openrouter(coin: Coin) -> str | None:
    if not settings.openrouter_api_key:
        logger.info("OPENROUTER_API_KEY not configured — skipping business summary for %s", coin.symbol)
        return None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json={
                    "model": settings.openrouter_model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": _build_user_prompt(coin)},
                    ],
                    "max_tokens": 500,
                    # Confirmed live: the default free model is a reasoning-
                    # capable one, and without this it sometimes spends the
                    # entire max_tokens budget on its visible chain-of-
                    # thought scratchpad (returned in `content` itself, cut
                    # off mid-thought) rather than ever emitting the actual
                    # TITLE:-formatted answer. Disabling reasoning fixes
                    # this — confirmed a clean, direct answer afterward.
                    "reasoning": {"enabled": False},
                },
                timeout=30,
            )
            if response.status_code == 429 and attempt < _MAX_ATTEMPTS:
                logger.info(
                    "OpenRouter rate-limited for %s (attempt %d/%d) — retrying",
                    coin.symbol, attempt, _MAX_ATTEMPTS,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Business summary generation failed for %s: %s", coin.symbol, exc)
            return None

        choices = data.get("choices") or []
        if not choices:
            logger.warning("Business summary generation for %s returned no choices: %r", coin.symbol, data)
            return None
        content = (choices[0].get("message") or {}).get("content", "").strip()
        return content or None
    return None


def get_business_summary(db: Session, coin: Coin) -> str | None:
    """Returns this coin's cached AI business summary, regenerating first if
    it's missing or older than settings.business_summary_ttl_days. Never
    raises — a generation failure just falls back to whatever's already
    cached (or None if it's never succeeded), same fallback spirit as
    SocialService.get_tweets.
    """
    if not needs_refresh(coin):
        return coin.business_summary

    fresh = _fetch_from_openrouter(coin)
    if fresh is None:
        return coin.business_summary

    coin.business_summary = fresh
    coin.business_summary_updated_at = datetime.utcnow()
    db.add(coin)
    db.commit()
    return fresh
