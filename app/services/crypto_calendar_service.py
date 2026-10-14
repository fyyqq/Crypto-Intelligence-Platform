"""Crypto Calendar (/tools/crypto-calendar): the monthly "Crypto + Market Calendar"
post of the Telegram group @layergg, parsed into dated events.

The posts are stored by the Telegram news pipeline (news_articles, source_type
'telegram', source_name like 'Layergg%'). Their text lists "noteworthy events"
one per line, in a format that changes between months:
    10-03 - $HYPE - First AQAv2 USDC yield payout     (October)
    Sep 1: 🇺🇸US - Kevin Warsh will talk with Japan    (September)
    8월 1일: $CRCL(@circle) - 실적 발표                  (August, Korean)
followed by an undated "TBD"/"TBA" list. The image attached to the post holds
more events than the text; only the text is used here.

parse_post turns one post into events, build_month_html renders a month as a
Monday-Friday grid (weekend events and TBD items below it), like the post's own
calendar image: crypto events green, macro orange, earnings blue.
"""
import calendar
import html
import re
from datetime import date, datetime
from functools import lru_cache

from sqlalchemy import text

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_MON_ABBR = {m[:3].lower(): i + 1 for i, m in enumerate(MONTHS)}

# ---- parsing --------------------------------------------------------------------------------

_SEP = re.compile(r"\s*[-–—]\s+")  # "who - description": a dash followed by a space
_DATE_RES = [
    # 10-03 -   /   10/03:
    re.compile(r"^(?P<m>\d{1,2})[-/.](?P<d>\d{1,2})(?:\s*[~–-]\s*\d{1,2})?\s*(?:\([^)]*\))?\s*[:\-–—]\s*(?P<rest>.*)$"),
    # Sep 1:   /   Sep. 9 -
    re.compile(r"^(?P<mon>[A-Za-z]{3})[a-z]*\.?\s+(?P<d>\d{1,2})(?:\s*[~–-]\s*\d{1,2})?\s*(?:\([^)]*\))?\s*[:\-–—]\s*(?P<rest>.*)$"),
    # 8월 1일:
    re.compile(r"^(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일(?:\s*[~–-]\s*\d{1,2}\s*일?)?\s*[:\-–—]\s*(?P<rest>.*)$"),
]
_BULLET = re.compile(r"^[•·▪\-\*]\s*")
_STOP = re.compile(r"^(✖|🚫|#|\*|\.\.\.|and many more|See detail)", re.I)
_TBD_HEADER = re.compile(r"^(TBD|TBA)s?\s*$", re.I)
_TBD_LINE = re.compile(r"^(TBD|TBA)\s*[:\-–—]\s*(?P<rest>.+)$", re.I)
_HANDLE = re.compile(r"\(\s*@[^)]*\)")
_FLAGS = re.compile("[\U0001F1E6-\U0001F1FF]{2}")  # regional-indicator pairs = flag emoji

_MACRO_WORDS = re.compile(
    r"\bFOMC\b|\bCPI\b|\bPPI\b|\bNFP\b|payroll|\bGDP\b|rate decision|interest rate|rate hike|rate cut|bond|treasury|"
    r"unemployment|jobs report|jackson hole|잭슨홀|금리|의회|핵 협상|election|\bvote\b|hearing|comment deadline|legislation",
    re.I,
)
_EARN_WORDS = re.compile(r"earnings|\bQ[1-4]\s+(?:results|report|call|prelim)|실적|dividend|\bresults\b", re.I)
_MACRO_WHO = {"US", "USA", "FED", "FOMC", "BOJ", "BOK", "ECB", "BOE", "PBOC", "SEC", "CFTC", "CBR", "CHINA", "JAPAN", "KOREA", "EU",
              "UK", "ISRAEL", "IRAN", "WHITE HOUSE", "CONGRESS", "TREASURY", "IMF", "G20", "G7", "OPEC"}


# Listed companies the calendar covers: blue ("stocks & earnings") like the source image.
_STOCKS = {"NVDA", "HOOD", "AVGO", "MSFT", "GOOGL", "GOOG", "META", "AAPL", "AMZN", "TSLA", "COIN", "MSTR", "ASML", "INTC", "AMD",
           "NFLX", "SAMSUNG", "SKHYNIX", "SKHY", "GLXY", "CRCL", "STRC", "APPLE", "HYUNDAI", "ORCL", "PLTR"}


def classify(who: str, desc: str) -> str:
    """"macro" | "earnings" (stocks & earnings) | "crypto": the three colours of the source image."""
    if _MACRO_WORDS.search(desc):
        return "macro"
    key = _FLAGS.sub("", who).strip().upper()
    if _EARN_WORDS.search(desc) or key.lstrip("$") in _STOCKS:
        return "earnings"
    if key in _MACRO_WHO or _FLAGS.search(who):
        return "macro"
    return "crypto"


def _split_who_desc(rest: str) -> tuple[str, str]:
    rest = _HANDLE.sub("", rest).strip()
    m = _SEP.search(rest)
    if not m:
        return "", rest
    return rest[: m.start()].strip(), rest[m.end():].strip()


def _event(rest: str, day: date | None) -> dict | None:
    hot = "🔥" in rest
    rest = re.sub(r"\s+", " ", rest.replace("🔥", "")).strip()
    if not rest:
        return None
    who, desc = _split_who_desc(rest)
    if not desc:  # no "who - " part: the whole text is the description
        who, desc = "", rest
    return {
        "date": day.isoformat() if day else None,
        "who": who,
        "ticker": who[1:] if who.startswith("$") and re.fullmatch(r"\$[A-Za-z0-9]{1,10}", who) else "",
        "desc": desc,
        "kind": classify(who, desc),
        "hot": hot,
    }


def post_month(title: str, body: str, posted: datetime | None) -> tuple[int, int] | None:
    """(year, month) of a calendar post: from its title ("2026 October", "2026 8월"),
    else its hashtag (#August), else the day it was posted."""
    ym = re.search(r"(20\d{2})", title)
    year = int(ym.group(1)) if ym else (posted.year if posted else None)
    month = None
    m = re.search(r"\b(" + "|".join(MONTHS) + r")\b", title, re.I)
    if m:
        month = _MON_ABBR[m.group(1)[:3].lower()]
    else:
        k = re.search(r"(\d{1,2})\s*월", title)
        if k:
            month = int(k.group(1))
        else:
            h = re.search(r"#(" + "|".join(MONTHS) + r")\b", body, re.I)
            month = _MON_ABBR[h.group(1)[:3].lower()] if h else (posted.month if posted else None)
    return (year, month) if year and month and 1 <= month <= 12 else None


def parse_post(body: str, year: int, month: int) -> list[dict]:
    """Events of one calendar post. Dated events outside the post's month are
    dropped; undated TBD/TBA items get date None."""
    events: list[dict] = []
    in_tbd = False
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _TBD_HEADER.match(line):
            in_tbd = True
            continue
        if _STOP.match(line):
            in_tbd = False if line.startswith(("✖", "🚫", "#")) else in_tbd
            if line.startswith(("✖", "🚫", "#")):
                break
            continue
        if line.startswith("•"):  # the intro's highlight bullets repeat events listed below
            continue
        t = _TBD_LINE.match(line)
        if t:
            ev = _event(t.group("rest"), None)
            if ev:
                events.append(ev)
            continue
        for rx_ in _DATE_RES:
            d = rx_.match(_BULLET.sub("", line))
            if d:
                g = d.groupdict()
                mm = _MON_ABBR.get((g.get("mon") or "").lower()) if g.get("mon") else int(g["m"])
                try:
                    day = date(year, mm, int(g["d"])) if mm else None
                except ValueError:
                    day = None
                if day and day.month == month:
                    ev = _event(g["rest"], day)
                    if ev:
                        events.append(ev)
                break
        else:
            if in_tbd:
                ev = _event(line, None)
                if ev:
                    events.append(ev)
    return events


# ---- loading ----------------------------------------------------------------------------------

_POSTS_SQL = text(
    """
    SELECT title, full_body_text, published_date, url FROM news_articles
    WHERE source_type = 'telegram' AND source_name ILIKE 'Layergg%'
      AND (title ILIKE '%calendar%' OR title ILIKE '%캘린더%')
      AND title NOT ILIKE '%weekly%'
    ORDER BY published_date
    """
)


def load_months(db) -> dict[str, dict]:
    """{"2026-10": {"events": [...], "url": post url, "posted": datetime}} for every
    stored calendar post of every year (the latest post wins if a month has two)."""
    months: dict[str, dict] = {}
    for title, body, posted, url in db.execute(_POSTS_SQL).all():
        ym = post_month(title or "", body or "", posted)
        if not ym:
            continue
        months[f"{ym[0]}-{ym[1]:02d}"] = {"events": parse_post(body or "", *ym), "url": url, "posted": posted}
    return months


def view_year(months: dict[str, dict], today: date | None = None) -> int:
    """The year the page shows: the latest year that has a calendar post (capped at next year). So
    2026 stays up until the first 2027 post exists, and from then on only 2027 is shown."""
    today = today or date.today()
    years = [int(k[:4]) for k, v in months.items() if v["events"] and int(k[:4]) <= today.year + 1]
    return max(years) if years else today.year


def symbol_icons(db, symbols: set[str]) -> dict[str, int]:
    """Ticker -> CoinMarketCap id (the biggest coin for that symbol), for logos."""
    if not symbols:
        return {}
    rows = db.execute(
        text("SELECT symbol, cmc_id FROM coins WHERE symbol = ANY(:s) ORDER BY market_cap_usd DESC NULLS LAST"),
        {"s": sorted(symbols)},
    ).all()
    out: dict[str, int] = {}
    for sym, cid in rows:
        out.setdefault(sym.upper(), cid)
    return out


# ---- rendering --------------------------------------------------------------------------------

def month_keys(today: date | None = None, months: dict[str, dict] | None = None) -> list[str]:
    """January of the shown year up to the current month, or up to a later month whose post is
    already out (a post is often published the day before its month starts). A past year shows
    all 12 months."""
    today = today or date.today()
    months = months or {}
    year = view_year(months, today)
    if year < today.year:
        last = 12
    else:
        posted = [int(k[5:]) for k, v in months.items() if int(k[:4]) == year and v["events"]]
        last = max(today.month if year == today.year else 0, max(posted, default=0))
    return [f"{year}-{m:02d}" for m in range(1, last + 1)]


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _card(ev: dict, icons: dict[str, int], with_date: bool = False) -> str:
    logo = ""
    # Logos only on crypto events: stock and macro tickers (PLTR, MSTR, NVDA ...) also exist as
    # unrelated tokenized-stock coins, whose logos would be misleading here.
    cid = icons.get(ev["ticker"].upper()) if ev["ticker"] and ev["kind"] == "crypto" else None
    if cid:
        logo = f'<img class="cal-logo" src="https://s2.coinmarketcap.com/static/img/coins/64x64/{cid}.png" alt="" loading="lazy">'
    who = ev["who"].lstrip("$") if ev["ticker"] else ev["who"]
    when = ""
    if with_date and ev["date"]:
        d = date.fromisoformat(ev["date"])
        when = f'<span class="cal-ev-when">{MONTHS[d.month - 1][:3]} {d.day:02d}</span>'
    hot = '<span class="cal-hot" title="Marked as important">🔥</span>' if ev["hot"] else ""
    head = f'<div class="cal-ev-head">{logo}<span class="cal-ev-who">{_esc(who)}</span>{when}{hot}</div>' if (who or logo or when or hot) else ""
    return f'<div class="cal-ev cal-ev-{ev["kind"]}">{head}<div class="cal-ev-desc">{_esc(ev["desc"])}</div></div>'


def build_month_html(key: str, data: dict | None, icons: dict[str, int], today: date | None = None) -> str:
    """One month: Monday-Friday week rows, then weekend events, then TBD items."""
    year, month = int(key[:4]), int(key[5:])
    name = f"{MONTHS[month - 1]} {year}"
    if not data or not data["events"]:
        return f'<div class="cal-empty">No calendar post stored for {_esc(name)} yet.</div>'
    today = today or date.today()
    by_day: dict[int, list[dict]] = {}
    weekend: list[dict] = []
    tbd: list[dict] = []
    for ev in data["events"]:
        if not ev["date"]:
            tbd.append(ev)
            continue
        d = date.fromisoformat(ev["date"])
        (weekend if d.weekday() >= 5 else by_day.setdefault(d.day, [])).append(ev)

    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    out = ['<div class="cal-board">', '<div class="cal-grid cal-weekdays">' + "".join(f'<div class="cal-wd">{n}</div>' for n in names) + "</div>"]
    for week in weeks:
        cells = []
        for i, d in enumerate(week[:5]):
            if d.month != month:
                cells.append('<div class="cal-day cal-out"></div>')
                continue
            evs = by_day.get(d.day, [])
            cls = "cal-day" + ("" if evs else " cal-quiet") + (" cal-today" if d == today else "")
            cells.append(
                f'<div class="{cls}"><div class="cal-num"><span class="cal-dow">{names[i]} </span>{d.day}</div>'
                + "".join(_card(e, icons) for e in evs) + "</div>"
            )
        out.append('<div class="cal-grid">' + "".join(cells) + "</div>")
    if weekend:
        out.append('<div class="cal-section">Weekend events</div><div class="cal-cards">' + "".join(_card(e, icons, True) for e in weekend) + "</div>")
    if tbd:
        out.append('<div class="cal-section">Date to be announced</div><div class="cal-cards">' + "".join(_card(e, icons) for e in tbd) + "</div>")
    out.append("</div>")
    return "".join(out)
