"""Forex Factory calendar page (/tools/cpi-fomc): this week's US inflation (CPI), producer prices (PPI), Federal
Reserve (FOMC) and Non-Farm Employment Change (NFP) events from Forex Factory's economic calendar.

Sources
- **Schedule, forecast, previous** (always): the free public feed
  https://nfs.faireconomy.media/ff_calendar_thisweek.json, a mirror of the Forex Factory calendar.
  No key, no trial; it refreshes about every minute upstream but is **rate limited** (HTTP 429 "Rate
  Limited" with Retry-After ~5 minutes after a handful of requests), so it is fetched at most once every
  3 minutes for everyone, a Retry-After is obeyed, and the last good copy is kept on disk. It holds
  the current week only (the next-week file does not exist until it is published). Fields: title,
  country (currency), date (ISO with the New York offset), impact, forecast, previous. It has NO
  actual or revised values.
- **Actual, free and official**: US CPI and Non-Farm Employment from the Bureau of Labor Statistics' public
  API (no key needed; a free registration key, BLS_API_KEY, raises the limit from 25 to 500 requests a
  day): the four CPI events are computed from the published index levels the way Forex Factory reports
  them (m/m from the seasonally adjusted series, y/y from the not adjusted one, one decimal), and
  "Non-Farm Employment Change" is the month's change in total nonfarm payrolls in thousands ("29K"); the Federal Funds
  Rate decision from FRED's public CSV of the target's upper bound (FRED can lag the decision by a day).
  Looked up only after a release, at most once every 2 minutes and 20 times a day (the BLS v1 limit is 25).
- **Actual, optional extra**: the Apify actor scrapemint/forexfactory-economic-calendar, only when
  settings.apify_token is set. Pay per event ($0.01 per row, the first 25 rows of every run free):
  each run asks for USD, high and medium impact only, this week, which is under 25 rows, so a run is
  normally free. Cost guards: it runs only when a CPI/FOMC event that has already happened still has
  no actual, at most once every 3 minutes, at most settings.macro_actuals_max_runs_per_day a day, and
  found actuals are remembered (logs/macro_actuals.json) so a released number is fetched once.

Forex Factory itself has no API and blocks scripted page requests; this module never reads its pages.
"""
import csv
import hashlib
import io
import json
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from app.core.config import settings

log = logging.getLogger(__name__)

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FEED_TTL = 180  # seconds between fetches (the feed answers 429 to anything faster than a few per 5 minutes)
STALE_MAX = 6 * 3600  # keep showing the last good copy this long when the feed is unreachable
APIFY_RUN_URL = "https://api.apify.com/v2/acts/scrapemint~forexfactory-economic-calendar/run-sync-get-dataset-items"
ACTUALS_MIN_GAP = 180  # seconds between Apify runs
ACTUALS_WINDOW = timedelta(hours=3)  # keep asking Apify for an actual for 3 hours after the event time
FREE_WINDOW = timedelta(hours=36)  # the official sources are free: keep looking for a day and a half (FRED can lag)
KL = ZoneInfo("Asia/Kuala_Lumpur")
ET = ZoneInfo("America/New_York")
_ACTUALS_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "macro_actuals.json"
_FEED_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "macro_feed.json"
_STORE_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "macro_events.json"
_SCHEDULE_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "macro_schedule.json"
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FRED_DATES_URL = "https://api.stlouisfed.org/fred/release/dates"
SCHEDULE_TTL = 12 * 3600  # the Fed and FRED calendars change a few times a year
SCHEDULE_RETRY = 1800  # after a failed fetch, wait this long
STORE_KEEP = timedelta(days=40)  # remembered feed events (the /forex_factory month list needs the past days of the month)
HORIZON_DAYS = 30  # the page shows today and the next 30 days

# CPI events, everything FOMC (the committee's members' speeches, statement, minutes, press conference,
# the rate decision, which Forex Factory names "Federal Funds Rate", and the Fed Chair) and the monthly
# jobs report, "Non-Farm Employment Change".
_KEEP = re.compile(r"\bCPI\b|\bPPI\b|FOMC|Federal Funds Rate|\bFed Chair|Non-?Farm Employment Change", re.I)
_IMPACT = {"high": "high", "medium": "medium", "low": "low", "holiday": "holiday", "non-economic": "low"}

_lock = threading.Lock()
_feed: tuple[float, list[dict]] | None = None  # (fetched at, raw feed events)
_feed_error = ""
_blocked_until = 0.0  # after a 429, no request before this time (time.time())
_actuals: dict[str, dict] | None = None
_runs: dict[str, int] = {}  # "YYYY-MM-DD" -> Apify runs started that day
_last_run = 0.0
_schedule: dict | None = None
_schedule_failed_at = 0.0


def _event_id(title: str, currency: str, start: datetime) -> str:
    return hashlib.sha1(f"{currency}|{title}|{start.isoformat()}".encode()).hexdigest()[:12]


def group_of(title: str) -> str:
    if re.search(r"\bCPI\b", title, re.I):
        return "CPI"
    if re.search(r"\bPPI\b", title, re.I):
        return "PPI"
    return "NFP" if re.search(r"Non-?Farm Employment", title, re.I) else "FOMC"


def parse_feed(raw: list[dict]) -> list[dict]:
    """Raw feed rows -> CPI/FOMC events (any currency), oldest first."""
    out = []
    for r in raw or []:
        title = (r.get("title") or "").strip()
        if not title or not _KEEP.search(title):
            continue
        try:
            start = datetime.fromisoformat(r["date"]).astimezone(timezone.utc)
        except (KeyError, ValueError):
            continue
        currency = (r.get("country") or "").strip().upper()
        out.append(
            {
                "id": _event_id(title, currency, start),
                "title": title,
                "currency": currency,
                "impact": _IMPACT.get((r.get("impact") or "").strip().lower(), "low"),
                "start": start,
                "forecast": (r.get("forecast") or "").strip(),
                "previous": (r.get("previous") or "").strip(),
                "actual": "",
                "revised": "",
                "group": group_of(title),
            }
        )
    out.sort(key=lambda e: (e["start"], e["title"]))
    return out


def _read_feed_file() -> tuple[float, list[dict]] | None:
    try:
        d = json.loads(_FEED_FILE.read_text())
        if isinstance(d.get("rows"), list):
            return float(d["at"]), d["rows"]
    except Exception:  # noqa: BLE001
        pass
    return None


def _load_feed(force: bool = False) -> tuple[list[dict], bool, str]:
    """(raw rows, is_stale, error). One request per FEED_TTL however many viewers there are; a copy on
    disk survives restarts and rate-limit blocks."""
    global _feed, _feed_error, _blocked_until
    with _lock:
        now = time.time()
        if _feed is None:
            _feed = _read_feed_file()
        if _feed and not force and now - _feed[0] < FEED_TTL:
            return _feed[1], False, ""
        if now < _blocked_until:  # told to wait: serve what we have
            return (_feed[1], True, _feed_error) if _feed and now - _feed[0] < STALE_MAX else ([], True, _feed_error)
        try:
            r = requests.get(FEED_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=(5, 15))
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After") or 300)
                _blocked_until = now + min(max(wait, 30), 900)
                raise RuntimeError(f"rate limited, retry in {wait}s")
            r.raise_for_status()
            rows = r.json()
            if not isinstance(rows, list):
                raise ValueError("unexpected feed shape")
            _feed, _feed_error = (now, rows), ""
            try:
                _FEED_FILE.parent.mkdir(exist_ok=True)
                _FEED_FILE.write_text(json.dumps({"at": now, "rows": rows}))
            except Exception:  # noqa: BLE001
                log.warning("could not save the calendar feed copy", exc_info=True)
            return rows, False, ""
        except Exception as exc:  # noqa: BLE001  (rate limit, network, bad JSON: serve the last copy)
            _feed_error = f"{type(exc).__name__}: {str(exc)[:80]}"
            log.warning("macro calendar feed failed: %s", _feed_error)
            if _feed and now - _feed[0] < STALE_MAX:
                return _feed[1], True, _feed_error
            return [], True, _feed_error


# ---- actual values: free official sources (BLS for CPI, FRED for the fed funds target) -----------------

BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
BLS_V2_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
_BLS = {"all_sa": "CUSR0000SA0", "all_nsa": "CUUR0000SA0", "core_sa": "CUSR0000SA0L1E", "core_nsa": "CUUR0000SA0L1E",
        "nfp": "CES0000000001",  # total nonfarm employment, seasonally adjusted, thousands
        "ppi_sa": "WPSFD4",  # PPI final demand, seasonally adjusted
        "ppi_core_sa": "WPSFD4131"}  # PPI final demand less foods and energy, seasonally adjusted
FREE_MIN_GAP = 120
_free_runs: dict[str, int] = {}
_last_free = 0.0


def _pct(now_v: Decimal, then_v: Decimal) -> str:
    return f"{((now_v / then_v - 1) * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


def cpi_from_levels(levels: dict[str, dict[tuple[int, int], Decimal]], year: int, month: int) -> dict[str, str]:
    """{"CPI m/m": "0.6%", "CPI y/y": ..., "Core CPI m/m": ..., "Core CPI y/y": ...} for the reference
    month from index levels ({series key: {(year, month): value}}); {} when the month is not published yet.
    m/m uses the seasonally adjusted series, y/y the not adjusted one (as Forex Factory/BLS headlines do)."""
    prev = (year, month - 1) if month > 1 else (year - 1, 12)
    out: dict[str, str] = {}
    for label, sa, nsa in (("CPI", "all_sa", "all_nsa"), ("Core CPI", "core_sa", "core_nsa")):
        s_, n_ = levels.get(sa, {}), levels.get(nsa, {})
        if (year, month) in s_ and prev in s_:
            out[f"{label} m/m"] = _pct(s_[(year, month)], s_[prev])
        if (year, month) in n_ and (year - 1, month) in n_:
            out[f"{label} y/y"] = _pct(n_[(year, month)], n_[(year - 1, month)])
    return out


def ppi_from_levels(levels: dict[str, dict[tuple[int, int], Decimal]], year: int, month: int) -> dict[str, str]:
    """{"PPI m/m": "0.6%", "Core PPI m/m": "0.3%"} for the reference month from the seasonally adjusted final demand
    indexes (Forex Factory's "PPI m/m" and "Core PPI m/m", one decimal); {} for a month not published yet."""
    prev = (year, month - 1) if month > 1 else (year - 1, 12)
    out: dict[str, str] = {}
    for label, key in (("PPI m/m", "ppi_sa"), ("Core PPI m/m", "ppi_core_sa")):
        s_ = levels.get(key, {})
        if (year, month) in s_ and prev in s_:
            out[label] = _pct(s_[(year, month)], s_[prev])
    return out


def nfp_from_levels(levels: dict[str, dict[tuple[int, int], Decimal]], year: int, month: int) -> str:
    """"29K" / "-12K": the month's change in total nonfarm payrolls (thousands), the way the headline
    "Non-Farm Employment Change" is reported (this month's level minus the revised previous month's);
    "" when the month is not published yet."""
    s_ = levels.get("nfp", {})
    prev = (year, month - 1) if month > 1 else (year - 1, 12)
    if (year, month) not in s_ or prev not in s_:
        return ""
    change = (s_[(year, month)] - s_[prev]).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{change}K"


def _fetch_bls_levels() -> dict[str, dict[tuple[int, int], Decimal]]:
    key = settings.bls_api_key.strip()
    body = {"seriesid": list(_BLS.values())}
    if key:
        body["registrationkey"] = key
    r = requests.post(BLS_V2_URL if key else BLS_URL, json=body, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    reply = r.json()
    if reply.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS: {reply.get('message')}")
    by_id = {s["seriesID"]: s["data"] for s in reply["Results"]["series"]}
    levels: dict[str, dict[tuple[int, int], Decimal]] = {}
    for key, sid in _BLS.items():
        levels[key] = {(int(d["year"]), int(d["period"][1:])): Decimal(d["value"]) for d in by_id.get(sid, [])
                            if d["period"].startswith("M") and d["period"] != "M13" and re.fullmatch(r"\d+(\.\d+)?", d.get("value", ""))}  # "-" = not published
    return levels


def _fetch_fed_target() -> tuple[date, str] | None:
    """(date, "3.75%") of the latest day in FRED's fed funds target upper bound series."""
    since = (date.today() - timedelta(days=21)).isoformat()  # a short window: the series is daily
    # No custom User-Agent on purpose: FRED stalls "Mozilla/5.0"-style and unknown ones (the request hangs until
    # it times out) but answers the HTTP library's own default instantly.
    r = requests.get(FRED_URL, params={"id": "DFEDTARU", "cosd": since}, timeout=(5, 15))
    r.raise_for_status()
    rows = [row for row in csv.reader(io.StringIO(r.text)) if len(row) == 2 and row[1] not in ("", ".")]
    if len(rows) < 2:
        return None
    day, value = rows[-1]
    return date.fromisoformat(day), f"{Decimal(value):.2f}%"


def refresh_free_actuals(events: list[dict], now: datetime | None = None) -> int:
    """Looks up the official number for released, still-empty CPI and Federal Funds Rate events.
    Returns how many actuals were stored. Never raises; rate-limited (FREE_MIN_GAP, a daily cap)."""
    global _last_free
    now = now or datetime.now(timezone.utc)
    pending = [e for e in events if e["currency"] == "USD" and not e["actual"] and e["start"] <= now <= e["start"] + FREE_WINDOW
               and (e["group"] in ("CPI", "PPI", "NFP") or e["title"].lower() == "federal funds rate")]
    if not pending:
        return 0
    day = now.date().isoformat()
    cap = max(settings.macro_free_actuals_max_per_day, 200) if settings.bls_api_key.strip() else settings.macro_free_actuals_max_per_day  # v2 allows 500/day
    with _lock:
        if time.time() - _last_free < FREE_MIN_GAP or _free_runs.get(day, 0) >= cap:
            return 0
        _last_free = time.time()
        _free_runs[day] = _free_runs.get(day, 0) + 1
    found: dict[str, dict] = {}
    bls_events = [e for e in pending if e["group"] in ("CPI", "PPI", "NFP")]
    if bls_events:
        try:
            levels = _fetch_bls_levels()
            for e in bls_events:
                ref = e["start"].astimezone(ET).date().replace(day=1) - timedelta(days=1)  # the month before the release
                if e["group"] == "CPI":
                    value = cpi_from_levels(levels, ref.year, ref.month).get(e["title"], "")
                elif e["group"] == "PPI":
                    value = ppi_from_levels(levels, ref.year, ref.month).get(e["title"], "")
                else:
                    value = nfp_from_levels(levels, ref.year, ref.month)
                if value:
                    found[e["id"]] = {"actual": value, "revised": ""}
        except Exception:  # noqa: BLE001
            log.warning("BLS lookup failed", exc_info=True)
    for e in pending:
        if e["title"].lower() == "federal funds rate":
            try:
                got = _fetch_fed_target()
                if got and got[0] >= e["start"].astimezone(ET).date():  # FRED already shows the decision day
                    found[e["id"]] = {"actual": got[1], "revised": ""}
            except Exception:  # noqa: BLE001
                log.warning("FRED fed funds lookup failed", exc_info=True)
    return _store(events, found)


_bg_busy = threading.Event()


def refresh_actuals_in_background(events: list[dict], now: datetime | None = None) -> None:
    """Looks for actuals (free official sources first, then Apify if a token is set) on a daemon thread,
    so a slow or stalled lookup never delays the page; the next page refresh shows what was found. At
    most one lookup runs at a time. `events` are copied, the stored actuals are applied on read."""
    if _bg_busy.is_set():
        return
    snapshot = [dict(e) for e in events]

    def run():
        try:
            refresh_free_actuals(snapshot, now)
            refresh_actuals(snapshot, now)
        except Exception:  # noqa: BLE001
            log.warning("background actuals lookup failed", exc_info=True)
        finally:
            _bg_busy.clear()

    _bg_busy.set()
    threading.Thread(target=run, name="macro-actuals", daemon=True).start()


def _store(events: list[dict], found: dict[str, dict]) -> int:
    store = _load_actuals()
    new = {k: v for k, v in found.items() if store.get(k) != v}
    if new:
        store.update(new)
        _save_actuals()
    apply_actuals(events, store)
    return len(new)


# ---- actual values (Apify, optional) ------------------------------------------------------------

def _load_actuals() -> dict[str, dict]:
    global _actuals
    if _actuals is None:
        try:
            _actuals = json.loads(_ACTUALS_FILE.read_text())
        except Exception:  # noqa: BLE001
            _actuals = {}
    return _actuals


def _save_actuals() -> None:
    try:
        _ACTUALS_FILE.parent.mkdir(exist_ok=True)
        _ACTUALS_FILE.write_text(json.dumps(_actuals or {}))
    except Exception:  # noqa: BLE001
        log.warning("could not save macro actuals", exc_info=True)


def apply_actuals(events: list[dict], found: dict[str, dict]) -> None:
    for e in events:
        hit = found.get(e["id"])
        if hit:
            e["actual"], e["revised"] = hit.get("actual", ""), hit.get("revised", "")


def match_apify_rows(events: list[dict], rows: list[dict]) -> dict[str, dict]:
    """Apify rows -> {event id: {"actual", "revised"}}. Rows are matched to feed events by currency and
    title (a CPI/FOMC title is unique within a week, except the speeches, which carry no actual); the
    actor's field names are read tolerantly (title/event, actual, revised)."""
    out: dict[str, dict] = {}
    pool = list(events)
    for row in rows or []:
        title = str(row.get("title") or row.get("event") or "").strip().lower()
        cur = str(row.get("currency") or row.get("country") or "").strip().upper()
        actual = str(row.get("actual") if row.get("actual") is not None else "").strip()
        if not title or not actual:
            continue
        for e in pool:
            if e["title"].strip().lower() == title and (not cur or e["currency"] == cur):
                out[e["id"]] = {"actual": actual, "revised": str(row.get("revised") or "").strip()}
                pool.remove(e)
                break
    return out


def _run_apify(token: str) -> list[dict]:
    r = requests.post(
        APIFY_RUN_URL,
        params={"token": token},
        json={"range": "this_week", "currencies": ["USD"], "impactLevels": ["high", "medium"], "maxEvents": 60},
        timeout=150,
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def refresh_actuals(events: list[dict], now: datetime | None = None) -> int:
    """Fetches actuals when (and only when) a CPI/FOMC event that has already happened still has none.
    Returns how many new actuals were stored. Never raises."""
    global _last_run
    token = settings.apify_token.strip()
    if not token:
        return 0
    now = now or datetime.now(timezone.utc)
    # only what the free official sources could not fill (e.g. the rate decision before FRED catches up)
    pending = [e for e in events if e["currency"] == "USD" and e["impact"] in ("high", "medium")
               and not e["actual"] and e["start"] <= now <= e["start"] + ACTUALS_WINDOW]
    if not pending:
        return 0
    day = now.date().isoformat()
    with _lock:
        if time.time() - _last_run < ACTUALS_MIN_GAP or _runs.get(day, 0) >= settings.macro_actuals_max_runs_per_day:
            return 0
        _last_run = time.time()
        _runs[day] = _runs.get(day, 0) + 1
    try:
        found = match_apify_rows(events, _run_apify(token))
    except Exception:  # noqa: BLE001
        log.warning("Apify actuals run failed", exc_info=True)
        return 0
    return _store(events, found)


# ---- the month ahead: remembered feed events + the official release calendars --------------------------
# The free feed holds only the current week, so a month view and "7 days before" reminders need more:
#  - every feed event is remembered on disk (past days of the month, and a time that changed);
#  - FOMC meetings come from the Federal Reserve's own calendar page (no key, decision day 14:00 New York);
#  - CPI, PPI and the jobs report dates come from FRED's release calendar (free key, FRED_API_KEY; without it
#    these only appear once the feed's week reaches them). They are placeholders ("scheduled") that
#    the feed's real rows (with forecast and previous) replace as soon as that week is published.

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _ser(e: dict) -> dict:
    return {**e, "start": e["start"].isoformat()}


def _de(d: dict) -> dict:
    return {**d, "start": datetime.fromisoformat(d["start"])}


def _load_store() -> list[dict]:
    try:
        return [_de(d) for d in json.loads(_STORE_FILE.read_text())]
    except Exception:  # noqa: BLE001
        return []


def remember(events: list[dict], now: datetime | None = None) -> list[dict]:
    """Merges the feed's events into the on-disk store and returns the whole store (oldest first, only the
    last STORE_KEEP days). A feed event replaces a stored one with the same currency and title inside
    the feed's own week (its time or numbers changed). Never raises."""
    now = now or datetime.now(timezone.utc)
    stored = _load_store()
    if events:
        lo, hi = min(e["start"] for e in events) - timedelta(hours=12), max(e["start"] for e in events) + timedelta(hours=12)
        keys = {(e["currency"], e["title"]) for e in events}
        stored = [e for e in stored if not (lo <= e["start"] <= hi and (e["currency"], e["title"]) in keys)]
        stored += events
    stored = [e for e in {e["id"]: e for e in stored}.values() if e["start"] >= now - STORE_KEEP]
    stored.sort(key=lambda e: (e["start"], e["title"]))
    try:
        _STORE_FILE.parent.mkdir(exist_ok=True)
        _STORE_FILE.write_text(json.dumps([_ser(e) for e in stored]))
    except Exception:  # noqa: BLE001
        log.warning("could not save the remembered calendar events", exc_info=True)
    return stored


def parse_fomc_page(page: str) -> list[date]:
    """Decision days (the last day of each two-day meeting) from the Federal Reserve's calendar page.
    Lines without a day range (e.g. "22 (notation vote)") are skipped."""
    out: list[date] = []
    heads = [(m.start(), int(m.group(1))) for m in re.finditer(r"(\d{4}) FOMC Meetings", page)]
    for i, (pos, year) in enumerate(heads):
        part = page[pos: heads[i + 1][0] if i + 1 < len(heads) else len(page)]
        for mon, days in re.findall(r'fomc-meeting__month[^>]*><strong>([A-Za-z/ ]+)</strong>.*?fomc-meeting__date[^>]*>([^<]*)<', part, re.S):
            m = re.match(r"\s*(\d{1,2})\s*-\s*(\d{1,2})", days)
            names = [n.strip().lower()[:3] for n in mon.split("/")]
            if not m or names[0] not in _MONTHS or names[-1] not in _MONTHS:
                continue
            first, last = int(m.group(1)), int(m.group(2))
            month = _MONTHS[names[-1]] if len(names) > 1 else _MONTHS[names[0]] + (1 if last < first else 0)
            y = year + (1 if month > 12 else 0)
            try:
                out.append(date(y, (month - 1) % 12 + 1, last))
            except ValueError:
                continue
    return sorted(set(out))


def _fetch_fred_dates(release_id: int, today: date) -> list[date]:
    r = requests.get(
        FRED_DATES_URL,
        params={"release_id": release_id, "api_key": settings.fred_api_key.strip(), "file_type": "json",
                "realtime_start": today.isoformat(), "realtime_end": "9999-12-31",
                "include_release_dates_with_no_data": "true", "sort_order": "asc", "limit": 20},
        timeout=(5, 15),
    )
    r.raise_for_status()
    return [date.fromisoformat(d["date"]) for d in r.json().get("release_dates", []) if d.get("date", "") >= today.isoformat()]


def _read_schedule() -> dict | None:
    try:
        d = json.loads(_SCHEDULE_FILE.read_text())
        return d if isinstance(d.get("fomc"), list) else None
    except Exception:  # noqa: BLE001
        return None


def load_schedule(now: datetime | None = None) -> dict:
    """{"fomc": [iso dates], "cpi": [...], "nfp": [...]}: upcoming release days, cached 12 hours on disk. A source
    that fails keeps its last known dates; a failure is retried after 30 minutes. Never raises."""
    global _schedule, _schedule_failed_at
    now = now or datetime.now(timezone.utc)
    with _lock:
        if _schedule is None:
            _schedule = _read_schedule() or {"at": 0.0, "fomc": [], "cpi": [], "ppi": [], "nfp": []}
        t = time.time()
        if t - _schedule["at"] < SCHEDULE_TTL or t - _schedule_failed_at < SCHEDULE_RETRY:
            return _schedule
        today = now.astimezone(ET).date()
        new, ok = dict(_schedule), True
        try:
            r = requests.get(FED_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=(5, 15))
            r.raise_for_status()
            days = [d for d in parse_fomc_page(r.text) if d >= today]
            if days:
                new["fomc"] = [d.isoformat() for d in days]
        except Exception as exc:  # noqa: BLE001
            ok = False
            log.warning("Fed meeting calendar failed: %s", exc)
        if settings.fred_api_key.strip():
            for key, rid in (("cpi", 10), ("ppi", 46), ("nfp", 50)):
                try:
                    new[key] = [d.isoformat() for d in _fetch_fred_dates(rid, today)]
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    log.warning("FRED %s release dates failed: %s", key, type(exc).__name__)
        if ok:
            new["at"] = t
        else:
            _schedule_failed_at = t
        _schedule = new
        try:
            _SCHEDULE_FILE.parent.mkdir(exist_ok=True)
            _SCHEDULE_FILE.write_text(json.dumps(new))
        except Exception:  # noqa: BLE001
            log.warning("could not save the release schedule", exc_info=True)
        return _schedule


_RELEASES = {  # key -> (group, title, impact, hour, minute) New York time
    "cpi": ("CPI", "CPI (release date)", "high", 8, 30),
    "ppi": ("PPI", "PPI (release date)", "high", 8, 30),
    "nfp": ("NFP", "Non-Farm Employment Change", "high", 8, 30),
    "fomc": ("FOMC", "FOMC Meeting: Federal Funds Rate decision", "high", 14, 0),
}
_FOMC_DECISION = re.compile(r"Federal Funds Rate|FOMC Statement|FOMC Press Conference|FOMC Meeting", re.I)


def placeholder_events(schedule: dict, real: list[dict], now: datetime | None = None) -> list[dict]:
    """USD events from the release calendars that the feed has not published yet. A day the feed (or the
    store) already has a real row for the same release is skipped."""
    now = now or datetime.now(timezone.utc)
    have = {(e["group"], e["start"].astimezone(ET).date()) for e in real
            if e["currency"] == "USD" and (e["group"] != "FOMC" or _FOMC_DECISION.search(e["title"]))}
    out = []
    for key, (group, title, impact, h, m) in _RELEASES.items():
        for iso in schedule.get(key, []):
            try:
                day = date.fromisoformat(iso)
            except ValueError:
                continue
            if (group, day) in have:
                continue
            start = datetime(day.year, day.month, day.day, h, m, tzinfo=ET).astimezone(timezone.utc)
            out.append({"id": _event_id(title, "USD", start), "title": title, "currency": "USD", "impact": impact,
                        "start": start, "forecast": "", "previous": "", "actual": "", "revised": "", "group": group,
                        "scheduled": True})
    return out


def get_schedule(now: datetime | None = None, currencies: tuple[str, ...] | None = ("USD",)) -> dict:
    """get_events() plus the remembered past days and the scheduled upcoming releases: the month view's data."""
    now = now or datetime.now(timezone.utc)
    data = get_events(now, None)
    stored = remember(data["events"], now)
    events = stored + placeholder_events(load_schedule(now), stored, now)
    if currencies:
        events = [e for e in events if e["currency"] in currencies]
    events.sort(key=lambda e: (e["start"], e["title"]))
    apply_actuals(events, _load_actuals())
    return {**data, "events": events}


# ---- public API -----------------------------------------------------------------------------------

def get_events(now: datetime | None = None, currencies: tuple[str, ...] | None = ("USD",)) -> dict:
    """{"events": [...], "stale": bool, "error": str, "has_actuals_source": bool, "fetched_at": datetime}.
    currencies=None keeps every currency."""
    raw, stale, error = _load_feed()
    events = parse_feed(raw)
    if currencies:
        events = [e for e in events if e["currency"] in currencies]
    apply_actuals(events, _load_actuals())
    return {
        "events": events,
        "stale": stale,
        "error": error,
        "has_actuals_source": True,  # BLS/FRED need no key; Apify is an optional extra
        "fetched_at": datetime.fromtimestamp(_feed[0], timezone.utc) if _feed else None,
    }


def next_event(events: list[dict], now: datetime | None = None) -> dict | None:
    """The nearest upcoming event of any kind (CPI, jobs report, rate decision, a speech); None when
    everything has passed."""
    now = now or datetime.now(timezone.utc)
    return next((e for e in sorted(events, key=lambda e: (e["start"], e["title"])) if e["start"] >= now), None)


def in_window(events: list[dict], now: datetime | None = None, days: int = HORIZON_DAYS) -> list[dict]:
    """The page's events: from the start of today (Kuala Lumpur date, so earlier days drop out of the table)
    up to `days` days ahead."""
    now = now or datetime.now(timezone.utc)
    start = datetime.combine(now.astimezone(KL).date(), datetime.min.time(), tzinfo=KL)
    end = now + timedelta(days=days)
    return [e for e in events if start <= e["start"] <= end]


def month_events(events: list[dict], now: datetime | None = None) -> list[dict]:
    """Every event of the current calendar month in Kuala Lumpur time (past days included)."""
    now = now or datetime.now(timezone.utc)
    ym = (now.astimezone(KL).year, now.astimezone(KL).month)
    return [e for e in events if (e["start"].astimezone(KL).year, e["start"].astimezone(KL).month) == ym]


def countdown(seconds: float) -> str:
    s = int(max(0, seconds))
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m" if m else "under a minute"


# ---- rendering -------------------------------------------------------------------------------------

def _esc(v: str) -> str:
    import html

    return html.escape(v or "", quote=True)


def _cell(v: str) -> str:
    return _esc(v) if v else '<span class="mc-dash">–</span>'


def _num(v: str) -> float | None:
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*[%KMBT]?\s*", v or "", re.I)
    return float(m.group(1)) if m else None


def _vs_forecast(actual: str, forecast: str) -> str:
    """A small arrow when the actual is above or below the forecast (neutral colour: whether that is good
    or bad depends on the reader)."""
    a, f = _num(actual), _num(forecast)
    if a is None or f is None or a == f:
        return ""
    up = a > f
    return f'<span class="mc-vs" title="{"Above" if up else "Below"} forecast">{"▲" if up else "▼"}</span>'


def build_html(events: list[dict], now: datetime | None = None, has_actuals_source: bool = False) -> str:
    """The week as day groups of rows (Kuala Lumpur time, with the New York time alongside):
    time | currency | impact | event | actual | forecast | previous. Past rows are dimmed, the next 30
    minutes pulse, and a released event that is still waiting for its actual shows animated dots."""
    now = now or datetime.now(timezone.utc)
    if not events:
        return '<div class="mc-empty">No CPI, PPI, FOMC or Non-Farm Employment events in the next 30 days.</div>'
    days: dict[date, list[dict]] = {}
    for e in events:
        days.setdefault(e["start"].astimezone(KL).date(), []).append(e)
    today = now.astimezone(KL).date()
    out = ['<div class="mc-board">']
    for day in sorted(days):
        label = day.strftime("%A, %b ") + str(day.day)
        tag = '<span class="mc-today">Today</span>' if day == today else ""
        out.append(f'<div class="mc-day"><div class="mc-day-head">{_esc(label)}{tag}</div>')
        for e in days[day]:
            kl, et = e["start"].astimezone(KL), e["start"].astimezone(ET)
            delta = (e["start"] - now).total_seconds()
            state = "past" if delta < 0 else "soon" if delta <= 1800 else "later"
            waiting = (
                not e["actual"] and has_actuals_source and e["currency"] == "USD" and e["impact"] in ("high", "medium")
                and -ACTUALS_WINDOW.total_seconds() <= delta < 0
            )
            actual = (
                '<span class="mc-wait" title="Waiting for the released value"><i></i><i></i><i></i></span>' if waiting
                else _cell(e["actual"]) + _vs_forecast(e["actual"], e["forecast"])
            )
            revised = f'<span class="mc-rev" title="Revised">rev {_esc(e["revised"])}</span>' if e["revised"] else ""
            out.append(
                f'<div class="mc-row mc-{state} mc-impact-{e["impact"]}">'
                f'<div class="mc-time"><b>{kl:%H:%M}</b><small>{et:%H:%M} ET</small></div>'
                f'<div class="mc-cur">{_esc(e["currency"])}</div>'
                f'<div class="mc-imp" title="{e["impact"].title()} impact"><span></span></div>'
                f'<div class="mc-title"><span class="mc-chip mc-chip-{e["group"].lower()}">{e["group"]}</span>{_esc(e["title"])}</div>'
                f'<div class="mc-num mc-actual" data-label="Actual">{actual}{revised}</div>'
                f'<div class="mc-num" data-label="Forecast">{_cell(e["forecast"])}</div>'
                f'<div class="mc-num" data-label="Previous">{_cell(e["previous"])}</div>'
                "</div>"
            )
        out.append("</div>")
    out.append("</div>")
    return "".join(out)
