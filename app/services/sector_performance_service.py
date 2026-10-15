"""24h performance of every narrative and chain, for the /narrative and /chains pages.

A sector's score is the plain average 24h % change of its TOP_N largest coins by market cap that have a 24h change.
The changes are our own (price_snapshot_service.compute_changes, the same hourly snapshots as Gainers & Losers:
the top 500 coins, dust under $50K volume left out), so this costs no API call at all; it is recomputed at most
once an hour because the snapshots only change hourly. Top 20 by market cap keeps the score about the coins that
carry each sector instead of thousands of illiquid tails; a sector needs MIN_COINS such coins, otherwise one coin
would decide its score and it is shown without a number."""
from statistics import mean

TOP_N = 20
MIN_COINS = 3


def sector_scores(rows: list[dict], changes: dict[int, float], names_of, top_n: int = TOP_N, min_coins: int = MIN_COINS) -> dict[str, dict]:
    """{sector: {"pct": average %, "coins": how many were averaged}} for every sector with at least min_coins coins
    that have a change. `rows` are coin rows with cmc_id and market_cap_usd; `names_of(row)` lists that coin's
    sectors (its narratives, or its one chain); `changes` maps cmc_id -> 24h % change."""
    members: dict[str, list[tuple[float, float]]] = {}
    for r in rows:
        pct = changes.get(r["cmc_id"])
        if pct is None:
            continue
        cap = float(r.get("market_cap_usd") or 0)
        for name in names_of(r):
            if name:
                members.setdefault(name, []).append((cap, pct))
    out = {}
    for name, coins in members.items():
        top = sorted(coins, key=lambda c: c[0], reverse=True)[:top_n]
        if len(top) >= min_coins:
            out[name] = {"pct": mean(p for _, p in top), "coins": len(top)}
    return out


TOP_COINS = 10
MOVERS = 3


def sector_table(rows: list[dict], changes: dict[int, float], names_of, min_coins: int = MIN_COINS) -> dict[str, dict]:
    """Everything the /narrative and /chains tables show, per sector (every sector, scored or not):
    {"pct": score or None, "coins": n averaged, "top": [cmc_id] the TOP_COINS largest by market cap,
     "gainers": [(cmc_id, pct)] the MOVERS biggest risers (only coins that rose), "losers": [(cmc_id, pct)] the biggest
     fallers (only coins that fell)}. Movers are picked among ALL the sector's coins with a 24h change, the score
    from its top 20 by market cap (sector_scores)."""
    scores = sector_scores(rows, changes, names_of, min_coins=min_coins)
    members: dict[str, list[tuple[float, int]]] = {}
    for r in rows:
        for name in names_of(r):
            if name:
                members.setdefault(name, []).append((float(r.get("market_cap_usd") or 0), r["cmc_id"]))
    out = {}
    for name, coins in members.items():
        top = [cid for _, cid in sorted(coins, key=lambda c: c[0], reverse=True)[:TOP_COINS]]
        moved = [(cid, changes[cid]) for _, cid in coins if cid in changes]
        out[name] = {
            "pct": scores[name]["pct"] if name in scores else None,
            "coins": scores[name]["coins"] if name in scores else 0,
            "top": top,
            "gainers": sorted((m for m in moved if m[1] > 0), key=lambda m: m[1], reverse=True)[:MOVERS],
            "losers": sorted((m for m in moved if m[1] < 0), key=lambda m: m[1])[:MOVERS],
        }
    return out


def ranked(names: list[str], scores: dict[str, dict]) -> list[str]:
    """Sectors with a score first, biggest gain first; then the rest in their existing order. A score is
    {"pct": number or None}: None counts as unscored."""
    scored = sorted((n for n in names if scores.get(n, {}).get("pct") is not None), key=lambda n: scores[n]["pct"], reverse=True)
    done = set(scored)
    return scored + [n for n in names if n not in done]


def changes_24h() -> tuple[dict[int, float], str]:
    """({cmc_id: 24h %}, status) from the snapshot table; status is "ready" or "collecting"."""
    from app.core.database import SessionLocal
    from app.services import price_snapshot_service as ps

    db = SessionLocal()
    try:
        status = ps.window_status(db, "24h")["status"]
        changes = {c["coin_id"]: c["pct_change"] for c in ps.compute_changes(db, "24h")} if status == "ready" else {}
        return changes, status
    finally:
        db.close()
