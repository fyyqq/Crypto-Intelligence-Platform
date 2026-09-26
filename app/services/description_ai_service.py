"""One-time, on-demand fallback for the About section's description when a
coin has no real write-up anywhere: CMC's own boilerplate ("<name> is a
cryptocurrency and operates on...") is the default, coingecko_service's
contract-address lookup upgrades many of them to a real project description,
but plenty of coins — memecoins especially, and anything newly listed with no
whitepaper — have no curated description on either provider. For those, this
generates a short plain-language "what is this" paragraph, grounded in the
coin's own website text and (when available) its cached X posts —
Coin.cached_tweets is always empty now that the X-scraping backend has been
removed (see coin_state.py's refresh_coin_description docstring), so in
practice this runs on website text alone, but the "and/or" grounding logic
is left intact in case a scraping backend is reintroduced later.

Generated via OpenRouter (not a direct per-provider key), same as
business_summary_service.py, so the model can be swapped via
settings.openrouter_model without a code change.

Gated to run at most once per coin (Coin.description_ai_generated_at),
independent of description_synced_at (which only gates the CoinGecko step) —
a project's website/socials can't be usefully re-diffed on every page view,
and OpenRouter's free tier is itself request-limited, so this follows the
same "one honest attempt" pattern as coingecko_service.upgrade_description
rather than a periodic TTL like business_summary_service's.
"""

import html
import logging
import re
import time
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.coin import Coin
from app.services.coingecko_service import is_boilerplate_description

logger = logging.getLogger(__name__)

# Same shared-provider-pool retry story as business_summary_service.py's
# :free-tier model — a 429 here is almost always transient contention, not a
# real quota block.
_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 4

# Enough website text for the model to work with without ballooning the
# prompt — a marketing/landing page's actual "what is this" content is
# almost always in the first few thousand characters (hero section, About,
# nav-adjacent copy); anything past this is usually footer boilerplate,
# repeated nav links, or unrelated page chrome.
_MAX_WEBSITE_CHARS = 4000
_MAX_TWEETS = 8

_TAG_STRIP_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")

_SYSTEM_PROMPT = (
    "You write short, plain-language \"About this project\" summaries for a "
    "cryptocurrency dashboard's coin detail page, for readers new to crypto. "
    "You are given a coin's name, ticker, and whatever public source text is "
    "available for it — raw text scraped from its own website and/or recent "
    "posts from its official X (Twitter) account. These are the ONLY two "
    "public sources this coin has (it has no whitepaper and no curated "
    "listing description), so ground everything you write strictly in what "
    "the source text actually says. Do not invent a business model, roadmap, "
    "tokenomics, or team details that aren't stated in the source text. If "
    "the source text is sparse, thin, or reads like a pure meme/community "
    "project with no stated utility, say so plainly and briefly rather than "
    "padding it out. Write 2-4 sentences of plain prose, no headings, no "
    "bullet points, no markdown formatting, in the same neutral descriptive "
    "tone an exchange listing page would use (third person, present tense). "
    "Output only the paragraph itself, nothing else."
)


def _strip_html(raw_html: str) -> str:
    text = _TAG_STRIP_RE.sub(" ", raw_html)
    text = _ANY_TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def _fetch_website_text(url: str) -> str:
    try:
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RepaceBot/1.0)"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.info("Website fetch failed for %s: %s", url, exc)
        return ""
    return _strip_html(response.text)[:_MAX_WEBSITE_CHARS]


def _build_user_prompt(coin: Coin, website_text: str, tweet_texts: list[str]) -> str:
    parts = [f"Coin name: {coin.name}", f"Ticker: {coin.symbol}"]
    if website_text:
        parts.append(f"Text scraped from the project's website ({coin.website_url}):\n{website_text}")
    else:
        parts.append("No website text available.")
    if tweet_texts:
        joined = "\n---\n".join(tweet_texts)
        parts.append(f"Recent posts from the project's official X account:\n{joined}")
    else:
        parts.append("No X posts available.")
    return "\n\n".join(parts)


def _fetch_from_openrouter(coin: Coin, website_text: str, tweet_texts: list[str]) -> str | None:
    if not settings.openrouter_api_key:
        logger.info("OPENROUTER_API_KEY not configured — skipping AI description for %s", coin.symbol)
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
                        {"role": "user", "content": _build_user_prompt(coin, website_text, tweet_texts)},
                    ],
                    "max_tokens": 300,
                    # Same fix as business_summary_service.py — the default
                    # free model otherwise burns the token budget on visible
                    # chain-of-thought instead of the actual paragraph.
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
            logger.warning("AI description generation failed for %s: %s", coin.symbol, exc)
            return None

        choices = data.get("choices") or []
        if not choices:
            logger.warning("AI description generation for %s returned no choices: %r", coin.symbol, data)
            return None
        content = (choices[0].get("message") or {}).get("content", "").strip()
        return content or None
    return None


def generate_description_from_sources(db: Session, coin: Coin) -> str | None:
    """Runs the one-time AI-inference fallback for `coin.description` when
    it's still boilerplate after coingecko_service.upgrade_description has
    already had its shot. Never raises — a failed attempt (no sources, no
    API key, OpenRouter error) just leaves the existing description alone.

    Marks description_ai_generated_at regardless of outcome, so a coin with
    genuinely no website/social presence isn't re-attempted on every future
    page view.
    """
    if coin.description_ai_generated_at is not None:
        return None
    if not is_boilerplate_description(coin.description):
        return None

    website_text = _fetch_website_text(coin.website_url) if coin.website_url else ""
    tweet_texts = [t["text"] for t in (coin.cached_tweets or [])[:_MAX_TWEETS] if t.get("text")]

    fresh = None
    if website_text or tweet_texts:
        fresh = _fetch_from_openrouter(coin, website_text, tweet_texts)

    coin.description_ai_generated_at = datetime.utcnow()
    if fresh:
        coin.description = fresh
    db.add(coin)
    db.commit()
    return fresh
