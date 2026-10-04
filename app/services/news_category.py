"""Accurate category for each AI-targeted news article, and whether that
category is shared with every coin in the same use case.

Each targeted article (news_targeting_service.py) gets:

* target_narrative  — the label shown on its card (e.g. "AI Agents",
  "Fiat-Backed Stablecoins", "Regulation & Policy", "Macro & Markets").
* target_group      — a peer group (app/services/peer_groups.py) when the
  story is about a whole use case rather than one coin, else NULL.

A coin page (NewsState.coin_news) shows the articles tied to that coin, plus
the shared ones of its own peer group with the ticker swapped to that coin
(so a generic "AI agents" story picked for FET also shows on VIRTUAL, KITE…).
The Narrative Radar slider and /narrative keep the original top coin.

Rules, written by Claude Code (2026-10-05) after reading the 848 targeted
articles that don't name their coin:
  * story names its coin                  -> label = that coin's peer group, not shared
  * AI agents                             -> "AI Agents", shared
  * other AI (models, labs, AI policy)    -> "Decentralized AI & Machine Learning", shared
  * GPUs / data centres / compute          -> "Decentralized GPU & Compute", shared
  * stablecoins (not one issuer's story)  -> "Fiat-Backed Stablecoins", shared
  * tokenized stocks / treasuries / RWA   -> the matching tokenized group, shared
  * derivatives, privacy, lending, NFTs, memes, ZK, restaking, DeFi/DEX -> that group, shared
  * one exchange's hack / news            -> "Exchange News", not shared
  * Fed, rates, market cap, liquidations  -> "Macro & Markets", not shared
  * SEC/CFTC/Congress/laws                -> "Regulation & Policy", not shared
  * hacks/exploits                        -> "Security & Hacks", not shared
New articles get the same treatment right after they are targeted.
"""

import re

_AI_GROUPS = {"AI Agents", "Decentralized AI & Machine Learning", "Decentralized GPU & Compute", "AI Applications"}

_RX = {k: re.compile(v, re.I) for k, v in {
    "agents": r"\bai agents?\b|\bagentic\b|agent swarms?|autonomous agents?|\bagents?\b.*\b(payments?|stablecoins?)\b|rogue (ai|agents?)",
    "ai": r"\bai\b|openai|anthropic|chatgpt|\bgpt|claude|gemini|\bllm|artificial intelligence|superintelligence|frontier model|machine learning|altman|amodei",
    "compute": r"nvidia|\bgpus?\b|data cent(er|re)s?|compute|chips?|miners?.*\bai\b|jensen huang",
    "ai_media": r"video generation|image generation|text-to-",
    "stable": r"stablecoins?|genius act",
    "issuer": r"\btether\b|\bcircle\b|paypal|\busdt\b|\busdc\b",
    "tok_stock": r"tokenized (us )?(stocks?|equit|etfs?|options?)|stocks? on-?chain|tokenized trading",
    "tok_fund": r"tokenized (funds?|treasur|money market|collateral)|treasury fund|money market",
    "tokenized": r"tokeni[sz]|real-world assets?|\brwas?\b|tokenized deposits?",
    "deriv": r"derivatives?|perpetuals?|\bperps?\b|futures|options|liquidat",
    "privacy": r"privacy|anonym|shielded|mixer|tornado",
    "lending": r"lending|borrow",
    "nft": r"\bnfts?\b",
    "meme": r"meme ?coins?|\bmemes?\b",
    "political": r"official|governor|newsom|trump|politic|congress|senat",
    "zk": r"zero-knowledge|\bzk\b",
    "restaking": r"restak",
    "defi": r"\bdefi\b|decentralized exchange|\bdex\b",
    "hack": r"\bhack|exploit|stolen|drain|breach|attacker",
    "macro": r"\bfed\b|federal reserve|fomc|interest rates?|rate (hike|cut)s?|inflation|yields?|treasury (yield|buyback)|mortgage|\bcpi\b|jobs report|employment|market cap|liquidat|fear & greed|fear and greed|altseason|altcoin season|sentiment|rally|recession|\bgdp\b|tariff",
    "reg": r"\bsec\b|cftc|senate|senator|congress|house committee|clarity act|regulat|legislation|\blaw\b|\bbill\b|\btax(es)?\b|sanction|\bdoj\b|attorney general|guidance|exemption|ministry|government|lawmakers|white house|treasury secretary|central bank|\becb\b|license|mica",
}.items()}


def _hit(key: str, blob: str) -> bool:
    return bool(_RX[key].search(blob))


def classify(title: str, body: str, *, names_coin: bool, coin_group: str | None, coin_is_exchange: bool) -> tuple[str, str | None]:
    """(label, shared peer group or None) for one targeted article."""
    # Sector keywords are read from the headline and the start of the body
    # only: long bodies mention stablecoins, AI, etc. in passing.
    blob = f"{title or ''} {(body or '')[:200]}"
    if names_coin and coin_group:
        # The story is about this coin: label it with the coin's use case,
        # but don't spread it to other coins.
        if _hit("hack", blob) and coin_is_exchange:
            return "Security & Hacks", None
        return coin_group, None

    if coin_group in _AI_GROUPS or _hit("agents", blob):
        if _hit("agents", blob):
            return "AI Agents", "AI Agents"
        if _hit("compute", blob):
            return "Decentralized GPU & Compute", "Decentralized GPU & Compute"
        if _hit("ai_media", blob):
            return "AI Applications", "AI Applications"
        if _hit("ai", blob):
            return "Decentralized AI & Machine Learning", "Decentralized AI & Machine Learning"
    if coin_group == "Exchange Tokens" or coin_is_exchange:
        if _hit("hack", blob):
            return "Security & Hacks", None
        return "Exchange News", None
    if _hit("tok_stock", blob):
        return "Tokenized Stocks & ETFs", "Tokenized Stocks & ETFs"
    if _hit("tok_fund", blob):
        return "Tokenized Treasuries & Bonds", "Tokenized Treasuries & Bonds"
    if _hit("stable", blob):
        if _hit("issuer", blob) and not _hit("reg", blob):
            return "Fiat-Backed Stablecoins", None  # one issuer's own story
        return "Fiat-Backed Stablecoins", "Fiat-Backed Stablecoins"
    if _hit("tokenized", blob):
        return "Tokenized Real-World Assets", "Tokenized Real-World Assets"
    if coin_group == "Privacy" and _hit("privacy", blob):
        return "Privacy", "Privacy"
    if coin_group == "Lending & Borrowing" and _hit("lending", blob):
        return "Lending & Borrowing", "Lending & Borrowing"
    if _hit("nft", blob):
        return "NFTs & Collectibles", "NFTs & Collectibles"
    if coin_group in ("Celebrity & Political Memes", "Meme Coins", "Animal Meme Coins", "AI Meme Coins") and _hit("meme", blob):
        group = "Celebrity & Political Memes" if _hit("political", blob) else "Meme Coins"
        return group, group
    if coin_group in ("Layer 2 Scaling", "Zero-Knowledge Infrastructure") and _hit("zk", blob):
        return "Zero-Knowledge Infrastructure", "Zero-Knowledge Infrastructure"
    if _hit("restaking", blob):
        return "Liquid Staking & Restaking Protocols", "Liquid Staking & Restaking Protocols"
    if coin_group == "Perpetuals & Derivatives" and _hit("deriv", blob) and not _hit("macro", blob):
        return "Perpetuals & Derivatives", "Perpetuals & Derivatives"
    if coin_group == "DEX & Liquidity" and _hit("defi", blob):
        return "DEX & Liquidity", "DEX & Liquidity"
    if _hit("hack", blob):
        return "Security & Hacks", None
    if _hit("reg", blob):
        return "Regulation & Policy", None
    if _hit("macro", blob):
        return "Macro & Markets", None
    # A generic story the AI still tied to a coin (e.g. a crypto-market note
    # pinned to BTC): keep it on that coin only.
    return "Macro & Markets" if coin_group == "Proof-of-Work Currencies" else (coin_group or "Crypto"), None


# Claude Code's corrections after reviewing every shared article the rules
# produced on 2026-10-05: {article id: (label, shared group or None)}.
_NONE_STABLE = ("Fiat-Backed Stablecoins", None)   # one issuer's own story
_REG = ("Regulation & Policy", None)
_MACRO = ("Macro & Markets", None)
_REVIEW_OVERRIDES: dict[int, tuple[str, str | None]] = {
    22: _NONE_STABLE, 2131: _NONE_STABLE, 5825: _NONE_STABLE, 5874: _NONE_STABLE, 5884: ("Payments", None),
    1640: _REG, 2030: _REG, 2039: _REG, 4972: _REG, 5163: _REG, 709: _REG, 848: _REG, 6134: _REG,
    887: _REG, 6019: _REG, 1915: _REG, 1931: _REG,
    2154: _MACRO, 2175: _MACRO, 3050: _MACRO, 3048: _MACRO, 3054: ("Privacy", None),
    1902: ("Perpetuals & Derivatives", "Perpetuals & Derivatives"),
    2107: ("Perpetuals & Derivatives", "Perpetuals & Derivatives"),
    2130: ("Perpetuals & Derivatives", "Perpetuals & Derivatives"),
    2275: ("Perpetuals & Derivatives", "Perpetuals & Derivatives"),
    2187: ("Tokenized Stocks & ETFs", "Tokenized Stocks & ETFs"),
    714: ("Decentralized AI & Machine Learning", "Decentralized AI & Machine Learning"),
    2439: ("Decentralized AI & Machine Learning", "Decentralized AI & Machine Learning"),
    2264: ("Decentralized AI & Machine Learning", "Decentralized AI & Machine Learning"),
    7100: ("Decentralized AI & Machine Learning", "Decentralized AI & Machine Learning"),
    2309: ("AI Applications", "AI Applications"),
    5170: ("AI Applications", "AI Applications"),
}


def ensure_columns() -> None:
    """target_group / target_categorized_at on news_articles (checked first,
    short lock timeout — see the lock-up note in CLAUDE.md)."""
    from sqlalchemy import text

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        have = db.execute(text(
            "SELECT count(*) FROM information_schema.columns WHERE table_name = 'news_articles' "
            "AND column_name IN ('target_group', 'target_categorized_at')"
        )).scalar()
        if have >= 2:
            return
        db.execute(text("SET lock_timeout = '3s'"))
        db.execute(text(
            "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS target_group TEXT, "
            "ADD COLUMN IF NOT EXISTS target_categorized_at TIMESTAMPTZ"
        ))
        db.commit()
    finally:
        db.close()


def categorize_pending(limit: int = 5000, *, dry_run: bool = False) -> list[tuple]:
    """Classifies targeted articles that haven't been categorized yet.
    Returns (id, symbol, label, group, title) rows."""
    from sqlalchemy import text

    from app.core.database import SessionLocal
    from app.services.news_targeting_service import _mentions

    ensure_columns()
    db = SessionLocal()
    out = []
    try:
        rows = db.execute(text(
            "SELECT a.id, a.title, a.full_body_text, a.target_symbol, c.name, c.peer_group "
            "FROM news_articles a LEFT JOIN coins c ON c.cmc_id = a.target_cmc_id "
            "WHERE a.target_symbol IS NOT NULL AND a.target_symbol <> '' AND a.target_categorized_at IS NULL "
            "ORDER BY a.id LIMIT :n"
        ), {"n": limit}).fetchall()
        for aid, title, body, sym, name, group in rows:
            blob = f"{title or ''} {(body or '')[:3000]}"
            names = _mentions(blob, sym, name or "")
            label, shared = classify(
                title or "", body or "", names_coin=names, coin_group=group,
                coin_is_exchange=group == "Exchange Tokens",
            )
            if aid in _REVIEW_OVERRIDES:
                label, shared = _REVIEW_OVERRIDES[aid]
            out.append((aid, sym, label, shared, (title or "")[:100]))
            if not dry_run:
                db.execute(text(
                    "UPDATE news_articles SET target_narrative = :l, target_group = :g, "
                    "target_categorized_at = NOW() WHERE id = :id"
                ), {"l": label, "g": shared, "id": aid})
        if not dry_run:
            db.commit()
    finally:
        db.close()
    return out
