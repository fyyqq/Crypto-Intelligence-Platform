"""AI coin targeting for Cryptocurrency news (homepage "Targeted Narrative + Coin").

For each recent Cryptocurrency article the AI (OpenRouter free model, the same
helper and fallbacks as the news summary) does a short due-diligence pass and
picks ONE coin:

* the article is about a specific coin (named or by ticker) -> that coin;
* otherwise it is about an industry / narrative / macro event -> the single
  narrative it affects most, and one coin from that narrative's top 10 by
  market cap (e.g. Apple Vision Pro -> GPU rendering -> RENDER; SEC chair who
  sued Ripple leaving -> XRP; BlackRock pushing tokenization -> ONDO);
* no reasonable crypto link -> nothing.

Answers are validated against the coins table (a narrative pick must be in the
list we sent, a direct pick must really be mentioned in the text), so a
hallucinated ticker is never shown. Results are stored on news_articles
(target_* columns, added on first use); an article is analysed once.

Runs from frontend/news_catchup.py's background loop, a small batch per pass,
counted against ai_budget's hourly cap.
"""

from __future__ import annotations

import logging
import re
import threading
import time

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services import ai_budget
from app.services.news_summary_service import _call_openrouter

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10
_LOOKBACK_HOURS = 72
_MAX_NARRATIVES = 45
_TOP_PER_NARRATIVE = 10
_MAP_TTL_SECONDS = 6 * 3600

# CMC tags that aren't a sector/narrative (VC portfolios, listings, chain
# ecosystems, consensus types, exchanges' own tags, ...).
_NOISE_RE = re.compile(
    r"portfolio|ecosystem|listing|estate|reserve|taxonomy|commodit|alt season|capital|labs|launch|ventures|"
    r"made in|\bpow\b|\bpos\b|\bdpos\b|\bdag\b|sha 256|mineable|state channel|binance|coinbase|robinhood|tron20|"
    r"bep-?20|erc-?20|holdings|\bvc\b|fund|bankruptcy|alliance|world liberty|hackathon|token sale|presale|airdrop|"
    r"wrapped|bridged|tokenized stock|xstocks|tokenized assets|pump|yearbook|alleged sec|rehypothecated|"
    r"discount token|research|spartan|doggone|cardano|medium of exchange|store of value|smart contracts|"
    r"move vm|marketplace|media|web3",
    re.I,
)
# Coins never used as a narrative pick outside their own category.
_EXCLUDED_COIN_RE = re.compile(r"stablecoin|wrapped|bridged|tokenized|liquid staking|xstocks", re.I)
# Wrapped / staked / bridged variants that CMC doesn't tag as such
# (AETHWETH, BTCB, LBTC, JUPSOL, SLISBNB, ...): a derivative of a bigger coin.
_DERIVATIVE_SYMBOL_RE = re.compile(r"^(AETH\w+|\w+BTC\w*|\w*BTC[A-Z]|\w{2,}(SOL|BNB|ETH))$")

_SYSTEM_PROMPT = (
    "You are a crypto research analyst. For each news item, do quick due diligence and pick the ONE coin "
    "whose price or narrative the story most affects.\n"
    "Rules:\n"
    "1. If the item is about a specific crypto project (named, or by $TICKER), pick that coin.\n"
    "2. Otherwise, if it is about an industry, technology, company, policy or macro event, pick the single "
    "narrative from the list it affects most, then ONE coin from that narrative's list that benefits most "
    "(think about the technology or the people involved).\n"
    "   Examples: Apple Vision Pro launch -> spatial/3D rendering needs GPU compute -> Distributed Computing: RENDER. "
    "SEC chair Gary Gensler (who sued Ripple) leaving after Trump wins -> ISO 20022: XRP. "
    "BlackRock CEO Larry Fink promoting tokenized real-world assets -> Real World Assets Protocols: ONDO.\n"
    "3. Broad crypto-market moves with no other angle -> Layer 1: BTC.\n"
    "4. If there is no reasonable crypto link, answer NONE.\n"
    "Answer with exactly one line per item, nothing else:\n"
    "<item number> | <TICKER or NONE> | <narrative name exactly as listed> | <reason, max 15 words>"
)

_map_lock = threading.Lock()
_map_cache: tuple[float, dict] | None = None
_columns_ready = False


def ensure_columns() -> None:
    """Adds the target_* columns once. Uses its own short session with a lock
    timeout so it can never block other news_articles queries for long."""
    global _columns_ready
    if _columns_ready:
        return
    db = SessionLocal()
    try:
        have = db.execute(text(
            "SELECT count(*) FROM information_schema.columns WHERE table_name = 'news_articles' "
            "AND column_name LIKE 'target%'"
        )).scalar()
        if have >= 6:
            _columns_ready = True
            return
        db.execute(text("SET lock_timeout = '3s'"))
        db.execute(text(
            "ALTER TABLE news_articles "
            "ADD COLUMN IF NOT EXISTS target_symbol TEXT, "
            "ADD COLUMN IF NOT EXISTS target_cmc_id INTEGER, "
            "ADD COLUMN IF NOT EXISTS target_narrative TEXT, "
            "ADD COLUMN IF NOT EXISTS target_reason TEXT, "
            "ADD COLUMN IF NOT EXISTS target_model TEXT, "
            "ADD COLUMN IF NOT EXISTS targeted_at TIMESTAMPTZ"
        ))
        db.commit()
        _columns_ready = True
    finally:
        db.close()


def _narrative_map() -> dict:
    """{"narratives": {name: [symbol, ...]}, "coins": {SYMBOL: {cmc_id, name, narratives}},
    "order": [narrative, ...]} — cached for a few hours."""
    global _map_cache
    with _map_lock:
        if _map_cache and time.monotonic() - _map_cache[0] < _MAP_TTL_SECONDS:
            return _map_cache[1]
    db = SessionLocal()
    try:
        cats = db.execute(text(
            "SELECT c.id, c.name FROM categories c JOIN coin_category cc ON cc.category_id = c.id "
            "JOIN coins co ON co.id = cc.coin_id WHERE co.market_cap_usd > 0 "
            "GROUP BY c.id, c.name HAVING COUNT(*) >= 6 ORDER BY SUM(co.market_cap_usd) DESC"
        )).fetchall()
        excluded_ids = {
            r[0] for r in db.execute(text(
                "SELECT DISTINCT cc.coin_id FROM coin_category cc JOIN categories c ON c.id = cc.category_id "
                "WHERE c.name ~* :pat"
            ), {"pat": _EXCLUDED_COIN_RE.pattern}).fetchall()
        }
        narratives: dict[str, list[str]] = {}
        coins: dict[str, dict] = {}
        seen_names: set[str] = set()
        for cat_id, name in cats:
            if _NOISE_RE.search(name) or name.lower() in seen_names:
                continue
            is_stable = bool(re.search(r"stablecoin", name, re.I))
            rows = db.execute(text(
                "SELECT co.id, co.cmc_id, co.symbol, co.name FROM coins co JOIN coin_category cc ON cc.coin_id = co.id "
                "WHERE cc.category_id = :cid AND co.market_cap_usd > 0 ORDER BY co.market_cap_usd DESC LIMIT 40"
            ), {"cid": cat_id}).fetchall()
            top: list[str] = []
            for coin_id, cmc_id, symbol, coin_name in rows:
                if not re.fullmatch(r"[A-Za-z0-9]{2,12}", symbol or "") or symbol.upper() in top:
                    continue
                sym = symbol.upper()
                if (coin_id in excluded_ids or _DERIVATIVE_SYMBOL_RE.match(sym)) and not is_stable:
                    continue
                top.append(sym)
                info = coins.setdefault(sym, {"cmc_id": cmc_id, "name": coin_name, "narratives": []})
                info["narratives"].append(name)
                if len(top) >= _TOP_PER_NARRATIVE:
                    break
            if len(top) >= 3 and top not in narratives.values():
                narratives[name] = top
                seen_names.add(name.lower())
            if len(narratives) >= _MAX_NARRATIVES:
                break
        result = {"narratives": narratives, "coins": coins, "order": list(narratives)}
    finally:
        db.close()
    with _map_lock:
        _map_cache = (time.monotonic(), result)
    return result


def _lookup_coin(db, symbol: str) -> tuple[int, str] | None:
    """Highest-market-cap coin with this ticker (tickers aren't unique on CMC)."""
    row = db.execute(text(
        "SELECT cmc_id, name FROM coins WHERE upper(symbol) = :s AND market_cap_usd > 0 "
        "ORDER BY market_cap_usd DESC LIMIT 1"
    ), {"s": symbol.upper()}).fetchone()
    return (row[0], row[1]) if row else None


def _coin_narratives(db, cmc_id: int) -> list[str]:
    """The coin's own CMC tags minus noise, biggest category first — the
    narrative badge for a directly-mentioned coin outside the curated list."""
    rows = db.execute(text(
        "SELECT c.name FROM categories c JOIN coin_category cc ON cc.category_id = c.id "
        "JOIN coins co ON co.id = cc.coin_id WHERE co.cmc_id = :c"
    ), {"c": cmc_id}).fetchall()
    return [r[0] for r in rows if not _NOISE_RE.search(r[0])]


def _mentions(text_blob: str, symbol: str, name: str) -> bool:
    blob = text_blob.lower()
    if re.search(rf"(?<![a-z0-9])\$?{re.escape(symbol.lower())}(?![a-z0-9])", blob):
        return True
    return bool(name) and name.lower() in blob


def _validate(answer: tuple[str, str, str], article: dict, nmap: dict, db) -> dict | None:
    symbol, narrative, reason = answer
    symbol = re.sub(r"[^A-Za-z0-9]", "", symbol).upper()
    if not symbol or symbol == "NONE":
        return None
    narratives = nmap["narratives"]
    # match the narrative name case-insensitively
    narrative = next((n for n in narratives if n.lower() == narrative.strip().lower()), "")
    blob = f"{article['title']} {article['body']}"
    if narrative and symbol in narratives[narrative]:
        info = nmap["coins"][symbol]
        return {"symbol": symbol, "cmc_id": info["cmc_id"], "narrative": narrative, "reason": reason}
    # direct pick: must exist and really be mentioned in the article
    found = _lookup_coin(db, symbol)
    if not found or not _mentions(blob, symbol, found[1]):
        return None
    coin_narratives = nmap["coins"].get(symbol, {}).get("narratives", []) or _coin_narratives(db, found[0])
    return {
        "symbol": symbol,
        "cmc_id": found[0],
        "narrative": narrative if narrative else (coin_narratives[0] if coin_narratives else ""),
        "reason": reason,
    }


def _parse(content: str, count: int) -> dict[int, tuple[str, str, str]]:
    out: dict[int, tuple[str, str, str]] = {}
    for line in content.splitlines():
        parts = [p.strip() for p in line.strip().strip("*`").split("|")]
        if len(parts) < 3:
            continue
        num = re.sub(r"\D", "", parts[0])
        if not num or not (1 <= int(num) <= count):
            continue
        out[int(num)] = (parts[1], parts[2], parts[3] if len(parts) > 3 else "")
    return out


def target_recent_articles(limit: int = _BATCH_SIZE) -> int:
    """Analyses up to `limit` untargeted recent Cryptocurrency articles in one
    OpenRouter call. Returns how many got a coin."""
    ensure_columns()
    if ai_budget.in_cooldown("news-targeting"):
        return 0
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT id, title, full_body_text FROM news_articles "
            "WHERE targeted_at IS NULL AND lower(category_or_query) LIKE '%crypto%' "
            "AND published_date >= NOW() - make_interval(hours => :h) "
            "AND title ~ '[A-Za-z]' ORDER BY published_date DESC LIMIT :n"
        ), {"h": _LOOKBACK_HOURS, "n": limit}).fetchall()
    finally:
        db.close()
    if not rows:
        return 0
    articles = [
        {"id": r[0], "title": (r[1] or "").strip(), "body": re.sub(r"\s+", " ", r[2] or "")[:400]}
        for r in rows
    ]
    nmap = _narrative_map()
    listing = "\n".join(f"{n}: {', '.join(nmap['narratives'][n])}" for n in nmap["order"])
    items = "\n".join(f"[{i}] {a['title']} — {a['body'][:300]}" for i, a in enumerate(articles, 1))
    result = _call_openrouter(
        f"Narratives (top coins by market cap):\n{listing}\n\nNews items:\n{items}",
        system=_SYSTEM_PROMPT,
        max_tokens=60 * len(articles),
    )
    if result is None:
        ai_budget.mark_failed("news-targeting")
        logger.info("News targeting: AI unavailable, will retry later")
        return 0
    content, model = result
    answers = _parse(content, len(articles))
    if not answers:
        ai_budget.mark_failed("news-targeting")
        logger.warning("News targeting: unparseable AI answer: %s", content[:300])
        return 0
    hits = 0
    db = SessionLocal()
    try:
        for i, article in enumerate(articles, 1):
            if i not in answers:
                continue  # model skipped it: leave untargeted, retried next pass
            picked = _validate(answers[i], article, nmap, db)
            db.execute(text(
                "UPDATE news_articles SET target_symbol = :s, target_cmc_id = :c, target_narrative = :n, "
                "target_reason = :r, target_model = :m, targeted_at = NOW() WHERE id = :id"
            ), {
                "s": picked["symbol"] if picked else None,
                "c": picked["cmc_id"] if picked else None,
                "n": picked["narrative"] if picked else None,
                "r": (picked["reason"] if picked else answers[i][2])[:300],
                "m": model,
                "id": article["id"],
            })
            hits += bool(picked)
        db.commit()
    finally:
        db.close()
    logger.info("News targeting: %d/%d articles got a coin (%s)", hits, len(articles), model)
    return hits
