"""Keeps each coin's business-model category (the blue badge on
/coin/[symbol]) accurate over time, using OpenRouter.

The top 1,500 coins were labelled by hand once (scripts/apply_coin_categories.py,
source 'claude-code'). Projects pivot and websites change, so this re-checks
every coin weekly: a batch of coins (largest market cap first) whose category
is missing or older than _RECHECK_DAYS is sent to OpenRouter with each coin's
CMC description, tags and its own website text, and the model returns a short
"what the project actually does" label (e.g. "Open-World Metaverse Game",
"Decentralized GPU Rendering"). New listings get labelled the same way.

Budget: one batch call per run, at most one run per _RUN_INTERVAL_SECONDS
(see frontend/news_catchup.py), counted by ai_budget's hourly cap; a failed
batch backs off via ai_budget's cooldown. A coin whose answer is missing or
invalid keeps its old category and is retried next run.
"""

import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_, select

from app.core.database import SessionLocal
from app.models.coin import Coin
from app.services import ai_budget
from app.services.description_ai_service import _fetch_website_text
from app.services.news_summary_service import _call_openrouter
from app.services.peer_groups import PEER_GROUPS, peer_group

logger = logging.getLogger(__name__)

_RECHECK_DAYS = 7
_BATCH_SIZE = 8
_WEBSITE_CHARS = 1200
_REFLEX_DB = Path(__file__).resolve().parent.parent.parent / "frontend" / "reflex.db"
_COOLDOWN_KEY = "coin-category-batch"

_SYSTEM = (
    "You classify crypto projects by their real business model. For each coin you get its "
    "name, ticker, CMC tags, CMC description and text from its own website. Answer with ONE "
    "short category (2-6 words, Title Case) that says what the project actually does, in the "
    "style of: 'Decentralized Machine Learning', 'Autonomous AI Agents', 'Decentralized GPU "
    "Rendering', 'Open-World Metaverse Game', 'Perpetuals DEX', 'Liquid Staked ETH', "
    "'Fiat-Backed USD Stablecoin', 'Tokenized Tesla Stock', 'Solana Meme Coin'. Never use "
    "exchange listings, investors, launchpads or chain ecosystems as the category (no "
    "'Binance Alpha', 'Coinbase Ventures Portfolio', 'Solana Ecosystem'). If the current "
    "category is still accurate, repeat it exactly. Also pick the coin's peer group (coins with "
    "the same use case, used for 'similar coins') from exactly this list: "
    + "; ".join(PEER_GROUPS)
    + ". Output one line per coin: <id>|<category>|<peer group>"
)

_LINE_RE = re.compile(r"^\s*(\d+)\s*\|\s*([^|]+?)\s*(?:\|\s*(.+?)\s*)?$")
_GROUP_BY_LOWER = {g.lower(): g for g in PEER_GROUPS}
_BAD_RE = re.compile(r"binance|coinbase|portfolio|ecosystem|listing|alpha|ventures|unknown|n/a", re.I)


def _valid(category: str) -> bool:
    words = category.split()
    return 2 <= len(words) <= 6 and len(category) <= 60 and not _BAD_RE.search(category)


def _due_coins(db, limit: int) -> list[Coin]:
    cutoff = datetime.utcnow() - timedelta(days=_RECHECK_DAYS)
    return list(
        db.scalars(
            select(Coin)
            .where(Coin.market_cap_usd > 0)
            .where(or_(Coin.category_checked_at.is_(None), Coin.category_checked_at < cutoff))
            .order_by(Coin.market_cap_usd.desc())
            .limit(limit)
        )
    )


def _prompt(coins: list[Coin]) -> str:
    blocks = []
    for coin in coins:
        tags = ", ".join(c.name for c in coin.categories[:8])
        website = _fetch_website_text(coin.website_url)[:_WEBSITE_CHARS] if coin.website_url else ""
        blocks.append(
            f"id: {coin.cmc_id}\nname: {coin.name}\nticker: {coin.symbol}\ntags: {tags}\n"
            f"current category: {coin.business_model_category or '-'}\n"
            f"description: {(coin.description or '')[:600]}\nwebsite: {website}"
        )
    return "\n\n---\n\n".join(blocks)


def refresh_batch() -> int:
    """Re-checks one batch of due coins. Returns how many were updated."""
    if ai_budget.in_cooldown(_COOLDOWN_KEY):
        return 0
    db = SessionLocal()
    try:
        coins = _due_coins(db, _BATCH_SIZE)
        if not coins:
            return 0
        result = _call_openrouter(_prompt(coins), system=_SYSTEM, max_tokens=300)
        if result is None:
            ai_budget.mark_failed(_COOLDOWN_KEY)
            return 0
        raw, model = result
        answers: dict[int, tuple[str, str | None]] = {}
        for line in raw.splitlines():
            m = _LINE_RE.match(line)
            if m and _valid(m.group(2).strip("'\" ")):
                category = m.group(2).strip("'\" ")
                # The AI's group if it named one from the list, else the rules'.
                group = _GROUP_BY_LOWER.get((m.group(3) or "").strip("'\" ").lower()) or peer_group(category)
                answers[int(m.group(1))] = (category, group)

        now = datetime.utcnow()
        changed: list[tuple[str, str | None, int]] = []
        for coin in coins:
            answer = answers.get(coin.cmc_id)
            if not answer:
                continue
            category, group = answer
            if category != coin.business_model_category or group != coin.peer_group:
                coin.business_model_category = category
                coin.peer_group = group
                coin.category_source = "openrouter"
                changed.append((category, group, coin.cmc_id))
            coin.category_checked_at = now
        db.commit()
    finally:
        db.close()

    if changed:
        conn = sqlite3.connect(_REFLEX_DB, timeout=30)
        conn.executemany("UPDATE coin SET business_model_category = ?, peer_group = ? WHERE cmc_id = ?", changed)
        conn.commit()
        conn.close()
    logger.info("coin categories: %d checked, %d changed (%s)", len(answers), len(changed), model)
    return len(changed)
