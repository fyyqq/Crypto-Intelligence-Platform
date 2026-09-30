"""AI routing for posts from the mixed Telegram news groups (see
telegram_pipeline.AI_CLASSIFIED_GROUPS). Called once per NEW post as the
live listener stores it — never on page views, and never for the backlog
(existing posts were labelled once, offline). One short OpenRouter call per
post, counted against the shared hourly cap in ai_budget.

Returns one of: Crypto, AI, Finance, Tech, Excluded — or None if the model
was unavailable (rate-limited/overloaded/budget exhausted), in which case
the caller keeps the group's default category.
"""

import logging
import re

from app.services import ai_budget
from app.services.news_summary_service import _call_openrouter

logger = logging.getLogger(__name__)

LABELS = ("Crypto", "AI", "Finance", "Tech", "Excluded")

_SYSTEM_PROMPT = (
    "You route posts from crypto Telegram news channels into exactly one label. "
    "Reply with ONLY the label, nothing else.\n"
    "Crypto: cryptocurrency, blockchain, DeFi, exchanges, tokens, on-chain data, crypto regulation, crypto prices/charts/analysis.\n"
    "AI: artificial intelligence companies, models, products, chips for AI, AI policy.\n"
    "Finance: stocks, indices, bonds, commodities, forex, central banks, the economy and macro data, and government/war/geopolitics news (it moves markets).\n"
    "Tech: consumer or enterprise technology, software, hardware, chips, cybersecurity, space.\n"
    "Excluded: not news — trading signals (entries/targets/stop-losses), admin chat, greetings, personal opinions, "
    "promotions, ads, giveaways, referral links, memes.\n"
    "Pick the single best label by the post's main subject."
)

# Extra per-group rule appended to the prompt.
_GROUP_HINTS = {
    "sarjanacryptoindonesia": "This channel mixes news with the admin's chat and personal opinions: label admin chat/opinion-only posts Excluded.",
    "Coin_Signals": "This channel mostly posts trade signals: label signal posts Excluded; keep genuine news or chart analysis (Crypto).",
}


def classify_post(username: str, text: str) -> str | None:
    if not ai_budget.allow_call():
        logger.warning("Hourly OpenRouter budget reached — @%s post keeps its default category", username)
        return None
    system = _SYSTEM_PROMPT + ("\n" + _GROUP_HINTS[username] if username in _GROUP_HINTS else "")
    result = _call_openrouter(f"Post:\n{text[:1500]}", system=system, max_tokens=8)
    if result is None:
        return None
    match = re.search(r"\b(Crypto|AI|Finance|Tech|Excluded)\b", result[0], re.IGNORECASE)
    if not match:
        return None
    word = match.group(1).lower()
    return next(label for label in LABELS if label.lower() == word)
