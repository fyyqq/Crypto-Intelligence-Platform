"""A coin's age for the coin page ("Age: 1 year 47 days (12/10/2025)").

Where the launch date comes from (best first; a better source replaces a worse one, a worse one never replaces a
better one):
 1. CoinGecko's `genesis_date` (the coin's real start, when CoinGecko has it: mostly the older, larger coins);
 2. CoinMarketCap's `date_launched` (its /info metadata, no extra credits: stored by the weekly metadata sync);
 3. the creation time of the coin's OLDEST DEX pair (DexScreener, free) for tokens with a contract;
 4. CoinMarketCap's `date_added` (when CMC listed it; the listings payload carries it for free) as the last resort.
Sources 1 and 3 are looked up on demand, once per coin, when its page is opened (a miss is retried after 3 days);
2 and 4 are filled by the CMC syncs whenever CMC credits are available.
"""
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone

import requests

from app.core.database import SessionLocal
from app.models.coin_launch_date import CoinLaunchDate

log = logging.getLogger(__name__)

RANK = {"coingecko": 4, "cmc_launched": 3, "dex": 2, "cmc_added": 1, "": 0}
RETRY_AFTER = timedelta(days=3)
_PLACEHOLDER = re.compile(r"^0x(e{40}|0{40})$", re.IGNORECASE)  # a native coin's stand-in "contract" (ETH, BNB, ...)
_GECKO_BACKOFF_UNTIL = 0.0  # after a CoinGecko 429 (free tier) leave it alone for a while


def format_age(launch: date | None, today: date | None = None) -> str:
    """"1 year 47 days (12/10/2025)" (day/month/year); "23 days (...)" under a year; "Today"; "" when unknown."""
    if launch is None:
        return ""
    today = today or datetime.now(timezone.utc).date()
    days = (today - launch).days
    stamp = launch.strftime("%d/%m/%Y")
    if days < 0:
        return stamp
    years = 0
    while True:  # whole years by calendar, then the days left
        try:
            nxt = launch.replace(year=launch.year + years + 1)
        except ValueError:  # 29 Feb
            nxt = launch.replace(year=launch.year + years + 1, day=28)
        if nxt > today:
            break
        years += 1
    try:
        anchor = launch.replace(year=launch.year + years)
    except ValueError:
        anchor = launch.replace(year=launch.year + years, day=28)
    left = (today - anchor).days
    if years:
        parts = [f"{years} year{'s' if years != 1 else ''}"]
        if left:
            parts.append(f"{left} day{'s' if left != 1 else ''}")
        return f"{' '.join(parts)} ({stamp})"
    if days == 0:
        return f"Today ({stamp})"
    return f"{days} day{'s' if days != 1 else ''} ({stamp})"


def _since(moment: datetime) -> timedelta:
    """How long ago (the database may hand back a naive UTC time)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - moment


def all_dates() -> dict[int, date]:
    """{cmc_id: launch date} of every coin that has one, for the shared coin list."""
    db = SessionLocal()
    try:
        return {r[0]: r[1] for r in db.query(CoinLaunchDate.cmc_id, CoinLaunchDate.launch_date).filter(CoinLaunchDate.launch_date.is_not(None)).all()}
    finally:
        db.close()


def store(db, cmc_id: int, launch: date | None, source: str) -> bool:
    """Saves a found date unless a better source already has one; records a miss (launch None) as a check. True if a
    date was saved."""
    row = db.get(CoinLaunchDate, cmc_id)
    now = datetime.now(timezone.utc)
    if launch is None:
        if row is None:
            db.add(CoinLaunchDate(cmc_id=cmc_id, launch_date=None, source="", checked_at=now))
        else:
            row.checked_at = now
        db.commit()
        return False
    if row is None:
        db.add(CoinLaunchDate(cmc_id=cmc_id, launch_date=launch, source=source, checked_at=now))
    elif row.launch_date is None or RANK.get(source, 0) > RANK.get(row.source, 0):
        row.launch_date, row.source, row.checked_at = launch, source, now
    else:
        return False
    db.commit()
    return True


def record_cmc(db, cmc_id: int, date_launched: str | None, date_added: str | None) -> None:
    """From a CMC payload (listings: date_added; /info: date_launched and date_added). Never raises."""
    try:
        for text, source in ((date_launched, "cmc_launched"), (date_added, "cmc_added")):
            if text:
                store(db, cmc_id, datetime.fromisoformat(text.replace("Z", "+00:00")).date(), source)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.warning("could not record the CMC launch date of %s", cmc_id, exc_info=True)


def _parse(text):
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).date() if text else None
    except ValueError:
        return None


def record_cmc_bulk(db, entries: dict[int, tuple[str | None, str | None]]) -> int:
    """{cmc_id: (date_launched, date_added)} from a CMC payload batch, saved in one go (no per-coin queries); a
    better stored source is never replaced. Returns how many rows changed. Never raises."""
    try:
        existing = {r.cmc_id: r for r in db.query(CoinLaunchDate).filter(CoinLaunchDate.cmc_id.in_(list(entries)))} if entries else {}
        changed = 0
        for cid, (launched, added) in entries.items():
            options = [(d, src) for d, src in ((_parse(launched), "cmc_launched"), (_parse(added), "cmc_added")) if d]
            if not options:
                continue
            day, src = max(options, key=lambda o: RANK[o[1]])
            row = existing.get(cid)
            if row is None:
                db.add(CoinLaunchDate(cmc_id=cid, launch_date=day, source=src))
                changed += 1
            elif row.launch_date is None or RANK[src] > RANK.get(row.source, 0):
                row.launch_date, row.source = day, src
                changed += 1
        db.commit()
        return changed
    except Exception:  # noqa: BLE001  (the dates are a nicety: a failure must never break the CMC sync)
        db.rollback()
        log.warning("could not record CMC launch dates", exc_info=True)
        return 0


# ---- free on-demand sources -----------------------------------------------------------------------------

def gecko_genesis(coin_id_path: str) -> date | None:
    """`coin_id_path` is "<id>" or "<platform>/contract/<address>" (CoinGecko /coins/...)."""
    global _GECKO_BACKOFF_UNTIL
    if time.time() < _GECKO_BACKOFF_UNTIL:
        return None
    try:
        for attempt in (1, 2):  # one short retry: CoinGecko's free tier answers 429 in bursts
            r = requests.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id_path}",
                params={"localization": "false", "tickers": "false", "market_data": "false", "community_data": "false", "developer_data": "false"},
                timeout=10,
            )
            if r.status_code != 429:
                break
            if attempt == 2:
                _GECKO_BACKOFF_UNTIL = time.time() + 120
                return None
            time.sleep(min(float(r.headers.get("Retry-After") or 4), 6))
        if r.status_code != 200:
            return None
        text = (r.json() or {}).get("genesis_date")
        return date.fromisoformat(text) if text else None
    except (requests.RequestException, ValueError):
        return None


def dex_oldest_pair(address: str) -> date | None:
    """The day the token's oldest DEX pair was created (DexScreener, free, no key)."""
    try:
        r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{address}", timeout=10)
        if r.status_code != 200:
            return None
        created = [p["pairCreatedAt"] for p in (r.json() or {}).get("pairs") or [] if p.get("pairCreatedAt")]
        return datetime.fromtimestamp(min(created) / 1000, timezone.utc).date() if created else None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def _real_contract(primary) -> str:
    """The primary contract address, or "" when there is none or it is only a native-coin placeholder."""
    address = (primary.contract_address or "").strip() if primary else ""
    return "" if not address or _PLACEHOLDER.match(address) else address


def lookup(coin) -> tuple[date | None, str]:
    """(launch date, source) for a Coin row (with .contracts), from CoinGecko then DexScreener; (None, "") if neither
    knows it. Blocking; at most 3 HTTP calls. A native coin (placeholder contract) is only ever looked up on CoinGecko
    by its id: a DEX search on the placeholder address would return an unrelated token."""
    from app.services import coingecko_service as cg

    primary = next((c for c in coin.contracts if c.is_primary), None) or (coin.contracts[0] if coin.contracts else None)
    platform = cg._CHAIN_TO_COINGECKO_PLATFORM.get(primary.platform_name) if primary else None
    found = None
    address = _real_contract(primary)
    if platform and address:
        found = gecko_genesis(f"{platform}/contract/{address}")
    if found is None and coin.cmc_rank is not None and coin.cmc_rank <= cg._TOP_COIN_RANK_CUTOFF:
        gid = cg._get_top_coin_symbol_map().get((coin.symbol or "").upper())
        if gid:
            found = gecko_genesis(gid)
    if found:
        return found, "coingecko"
    # The DEX fallback is for smaller tokens only: for a top-500 coin the contract is usually a wrapped / bridged copy
    # whose oldest pair says nothing about the coin's own start (XRP's "contract" would give 2021), so those wait for
    # CoinGecko or CoinMarketCap's date_launched.
    top = coin.cmc_rank is not None and coin.cmc_rank <= cg._TOP_COIN_RANK_CUTOFF
    if address and not top:
        found = dex_oldest_pair(address)
        if found:
            return found, "dex"
    return None, ""


def ensure(cmc_id: int) -> date | None:
    """The coin's launch date: the stored one, else looked up now (once; a miss is retried after RETRY_AFTER)."""
    from sqlalchemy.orm import selectinload

    from app.models.coin import Coin

    db = SessionLocal()
    try:
        row = db.get(CoinLaunchDate, cmc_id)
        if row is not None and row.launch_date is not None and RANK.get(row.source, 0) >= RANK["coingecko"]:
            return row.launch_date
        if row is not None and row.launch_date is None and _since(row.checked_at) < RETRY_AFTER:
            return None
        if row is not None and row.launch_date is not None and _since(row.checked_at) < RETRY_AFTER:
            return row.launch_date  # a lesser source was found recently: do not ask again yet
        coin = db.query(Coin).options(selectinload(Coin.contracts)).filter(Coin.cmc_id == cmc_id).first()
        if coin is None:
            return row.launch_date if row else None
        throttled_before = _GECKO_BACKOFF_UNTIL
        found, source = lookup(coin)
        if found is None and (_GECKO_BACKOFF_UNTIL != throttled_before or time.time() < _GECKO_BACKOFF_UNTIL):
            return row.launch_date if row else None  # CoinGecko was rate limited: not a real miss, ask again on the next visit
        store(db, cmc_id, found, source)
        row = db.get(CoinLaunchDate, cmc_id)
        return row.launch_date if row else None
    finally:
        db.close()
