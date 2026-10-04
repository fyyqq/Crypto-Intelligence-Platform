"""Data for the /tools page: Fear & Greed, Altcoin/Bitcoin Season, BTC/ETH Rainbow.

The TradingView-based charts on that page (total market cap, TOTAL2, BTC
dominance, ETH/BTC, DXY) are plain embeds and need nothing from here.

Every tool can have more than one data source (``SOURCES``). A source may
need an API key from the project's ``.env``; ``source_status`` reports which
keys are present so the page can show the "add your key" popup. ``.env`` is
re-read on every check, so a key added while the app runs is picked up without
a restart.

Everything is cached in-process (the upstream data only moves daily/hourly)
and every fetch raises ``ToolsDataError`` with a readable message on failure.
"""

import math
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
_UA = {"User-Agent": "Mozilla/5.0"}
_TIMEOUT = 20


class ToolsDataError(Exception):
    pass


# tool -> ordered source options. env=None means no key is needed.
SOURCES: dict[str, list[dict]] = {
    "fng": [
        {
            "id": "alternative_me",
            "label": "Alternative.me",
            "env": None,
            "desc": "Free public API, the original Crypto Fear & Greed Index. No key needed.",
        },
        {
            "id": "cmc",
            "label": "CoinMarketCap",
            "env": "COINMARKETCAP_API_KEY",
            "desc": "CoinMarketCap's own Fear & Greed index. Uses 1-2 of your CMC API credits per refresh.",
        },
    ],
    "season": [
        {
            "id": "cmc",
            "label": "CoinMarketCap · 90 days",
            "env": "COINMARKETCAP_API_KEY",
            "desc": "Standard method: how many of the top 50 coins beat Bitcoin over 90 days. Uses 1 CMC credit per refresh.",
        },
        {
            "id": "coingecko",
            "label": "CoinGecko · 30 days",
            "env": None,
            "desc": "Free fallback, no key. Same idea but over 30 days (CoinGecko's free tier has no 90-day figure), so it reacts faster.",
        },
    ],
}


def get_env_key(name: str) -> str:
    """Read a key fresh from .env. The process environment is only used when
    there is no .env file (e.g. a deployment that sets real env vars): the
    app loads .env into os.environ at startup, so trusting os.environ would
    keep reporting a key that was since removed from the file."""
    if _ENV_FILE.exists():
        return (dotenv_values(_ENV_FILE).get(name) or "").strip()
    return (os.environ.get(name) or "").strip()


def source_status(tool: str) -> list[dict]:
    """Source options for a tool with whether each one's key is present."""
    return [
        {
            "id": s["id"],
            "label": s["label"],
            "desc": s["desc"],
            "env": s["env"] or "",
            "needs_key": s["env"] is not None,
            "key_present": s["env"] is None or bool(get_env_key(s["env"])),
        }
        for s in SOURCES[tool]
    ]


def resolve_source(tool: str, chosen: str) -> tuple[str, bool]:
    """(source_id, needs_key_and_missing). A chosen source whose key is
    missing is returned as-is with True so the page can ask for the key;
    with no choice, the first source that is usable is used."""
    options = source_status(tool)
    for o in options:
        if o["id"] == chosen:
            return o["id"], not o["key_present"]
    for o in options:
        if o["key_present"]:
            return o["id"], False
    return options[0]["id"], True


# ---- tiny TTL cache --------------------------------------------------------
_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl: float, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (time.time(), value)
    return value


def _get(url: str, **kw):
    try:
        r = requests.get(url, headers={**_UA, **kw.pop("headers", {})}, timeout=_TIMEOUT, **kw)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001 — surfaced as a readable message
        raise ToolsDataError(f"Could not reach {url.split('/')[2]}: {exc}") from exc


# ---- Fear & Greed ----------------------------------------------------------
def _fng_result(points: list[tuple[int, int, str]], source: str) -> dict:
    """points: newest first [(unix_ts, value, label)]."""
    if not points:
        raise ToolsDataError("No Fear & Greed data returned.")

    def at(i: int):
        if i < len(points):
            return {"value": points[i][1], "label": points[i][2]}
        return {"value": -1, "label": ""}

    ts, value, label = points[0]
    return {
        "value": value,
        "label": label,
        "updated": datetime.fromtimestamp(ts, timezone.utc).strftime("%d %b %Y"),
        "yesterday": at(1),
        "week": at(7),
        "month": at(30),
        "source": source,
    }


def _fng_alternative() -> dict:
    data = _get("https://api.alternative.me/fng/?limit=31")["data"]
    pts = [(int(d["timestamp"]), int(d["value"]), d["value_classification"]) for d in data]
    return _fng_result(pts, "Alternative.me")


def _fng_cmc() -> dict:
    key = get_env_key("COINMARKETCAP_API_KEY")
    if not key:
        raise ToolsDataError("COINMARKETCAP_API_KEY is not set in .env.")
    data = _get(
        "https://pro-api.coinmarketcap.com/v3/fear-and-greed/historical?limit=31",
        headers={"X-CMC_PRO_API_KEY": key},
    )["data"]
    pts = [(int(d["timestamp"]), int(d["value"]), d["value_classification"]) for d in data]
    return _fng_result(pts, "CoinMarketCap")


def get_fear_greed(source: str) -> dict:
    fn = _fng_cmc if source == "cmc" else _fng_alternative
    return _cached(f"fng:{source}", 900, fn)


# ---- Altcoin / Bitcoin Season ---------------------------------------------
_STABLE = {
    "USDT", "USDC", "DAI", "USDE", "USDS", "USD1", "FDUSD", "TUSD", "PYUSD", "BUSD",
    "USDD", "USDP", "GUSD", "FRAX", "LUSD", "USDY", "USDG", "RLUSD", "BUIDL", "USDTB",
    "USDF", "SUSDE", "SUSDS", "EURC", "USDC.E", "USDT0",
}
_DERIVATIVE_WORDS = ("wrapped", "staked", "bridged", "restaked", "liquid staking")


def _season_result(rows: list[dict], window: str, source: str) -> dict:
    btc = next((r for r in rows if r["symbol"] == "BTC"), None)
    if not btc or btc["chg"] is None:
        raise ToolsDataError("Bitcoin's performance was missing from the data.")
    alts = [
        r for r in rows
        if r["symbol"] != "BTC"
        and r["symbol"] not in _STABLE
        and r["chg"] is not None
        and not any(w in r["name"].lower() for w in _DERIVATIVE_WORDS)
        and not r.get("skip")
    ][:50]
    if len(alts) < 30:
        raise ToolsDataError("Not enough coins returned to compute the index.")
    beat = [r for r in alts if r["chg"] > btc["chg"]]
    index = round(len(beat) / len(alts) * 100)
    best = sorted(beat, key=lambda r: r["chg"], reverse=True)[:5]
    if index >= 75:
        label = "Altcoin Season"
    elif index <= 25:
        label = "Bitcoin Season"
    else:
        label = "Neutral"
    return {
        "index": index,
        "label": label,
        "beat": len(beat),
        "total": len(alts),
        "window": window,
        "btc_change": f"{btc['chg']:+.1f}%",
        "best": [{"symbol": r["symbol"], "name": r["name"], "change": f"{r['chg']:+.1f}%"} for r in best],
        "source": source,
    }


def _season_cmc() -> dict:
    key = get_env_key("COINMARKETCAP_API_KEY")
    if not key:
        raise ToolsDataError("COINMARKETCAP_API_KEY is not set in .env.")
    data = _get(
        "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest?limit=150&convert=USD",
        headers={"X-CMC_PRO_API_KEY": key},
    )["data"]
    rows = [
        {
            "symbol": c["symbol"],
            "name": c["name"],
            "chg": c["quote"]["USD"].get("percent_change_90d"),
            "skip": "stablecoin" in (c.get("tags") or []) or "wrapped-tokens" in (c.get("tags") or []),
        }
        for c in data
    ]
    return _season_result(rows, "90 days", "CoinMarketCap")


def _season_coingecko() -> dict:
    data = _get(
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd&order=market_cap_desc&per_page=120&page=1&price_change_percentage=30d"
    )
    rows = [
        {
            "symbol": c["symbol"].upper(),
            "name": c["name"],
            "chg": c.get("price_change_percentage_30d_in_currency"),
        }
        for c in data
    ]
    return _season_result(rows, "30 days", "CoinGecko")


def get_altcoin_season(source: str) -> dict:
    fn = _season_cmc if source == "cmc" else _season_coingecko
    return _cached(f"season:{source}", 1800, fn)


# ---- Rainbow chart ---------------------------------------------------------
_GENESIS = {"BTC": date(2009, 1, 3), "ETH": date(2015, 7, 30)}
# Bottom -> top.
RAINBOW_BANDS = [
    ("Fire sale", "#3b4cc0"),
    ("BUY!", "#2f7ed8"),
    ("Accumulate", "#1fa187"),
    ("Still cheap", "#4cae4f"),
    ("HODL!", "#a8c93a"),
    ("Is this a bubble?", "#f2d03b"),
    ("FOMO intensifies", "#f6a21e"),
    ("Sell. Seriously, SELL!", "#ee6a1f"),
    ("Maximum bubble territory", "#d62828"),
]
_BAND_STEP = 0.8  # in residual standard deviations


def _history(asset: str) -> list[tuple[int, float]]:
    def load():
        start = int(datetime(2010, 1, 1, tzinfo=timezone.utc).timestamp())
        data = _get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{asset}-USD"
            f"?period1={start}&period2={int(time.time())}&interval=1d"
        )
        try:
            res = data["chart"]["result"][0]
            closes = res["indicators"]["quote"][0]["close"]
            stamps = res["timestamp"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ToolsDataError("Unexpected price-history response.") from exc
        return [(t, c) for t, c in zip(stamps, closes) if c and c > 0]

    return _cached(f"hist:{asset}", 6 * 3600, load)


def _fit(points: list[tuple[int, float]], genesis: date):
    g = datetime(genesis.year, genesis.month, genesis.day, tzinfo=timezone.utc).timestamp()
    xs = [math.log((t - g) / 86400) for t, _ in points]
    ys = [math.log10(c) for _, c in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    icpt = my - slope * mx
    sigma = math.sqrt(sum((y - (slope * x + icpt)) ** 2 for x, y in zip(xs, ys)) / n)
    return g, slope, icpt, sigma


def _fmt_price(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:g}M"
    if v >= 1000:
        return f"${v / 1000:g}K"
    return f"${v:g}"


def _build_rainbow(asset: str) -> dict:
    pts = _history(asset)
    if len(pts) < 365:
        raise ToolsDataError("Not enough price history to draw the chart.")
    g, slope, icpt, sigma = _fit(pts, _GENESIS[asset])
    step = _BAND_STEP * sigma

    def center(t: float) -> float:
        return slope * math.log((t - g) / 86400) + icpt

    t0 = pts[0][0]
    t1 = int(time.time()) + 365 * 86400
    def edge(t, k):  # k from 0..9 -> bottom of band 0 ... top of band 8
        return center(t) + (k - 4.5) * step

    ymin_v = min(min(math.log10(c) for _, c in pts), edge(t0, 0))
    ymax_v = max(max(math.log10(c) for _, c in pts), edge(t1, 9))
    ymin, ymax = math.floor(ymin_v), math.ceil(ymax_v)

    W, H, L, R, T, B = 1000, 480, 62, 14, 14, 34
    pw, ph = W - L - R, H - T - B

    def px(t):
        return L + (t - t0) / (t1 - t0) * pw

    def py(v):
        return T + (ymax - v) / (ymax - ymin) * ph

    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" role="img" '
             f'aria-label="{asset} rainbow chart" style="display:block">']
    samples = [t0 + (t1 - t0) * i // 80 for i in range(81)]
    for i, (name, color) in enumerate(RAINBOW_BANDS):
        top = [f"{px(t):.1f},{py(edge(t, i + 1)):.1f}" for t in samples]
        bot = [f"{px(t):.1f},{py(edge(t, i)):.1f}" for t in reversed(samples)]
        parts.append(f'<polygon points="{" ".join(top + bot)}" fill="{color}" fill-opacity="0.9"/>')
    # Grid + axes.
    for e in range(ymin, ymax + 1):
        y = py(e)
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--gray-a6)" stroke-width="1"/>')
        parts.append(f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="13" fill="var(--gray-11)">{_fmt_price(10 ** e)}</text>')
    y0 = datetime.fromtimestamp(t0, timezone.utc).year + 1
    y1 = datetime.fromtimestamp(t1, timezone.utc).year
    for yr in range(y0, y1 + 1):
        t = int(datetime(yr, 1, 1, tzinfo=timezone.utc).timestamp())
        if t0 < t < t1:
            x = px(t)
            parts.append(f'<text x="{x:.1f}" y="{H - 10}" text-anchor="middle" font-size="13" fill="var(--gray-11)">{yr}</text>')
    line = " ".join(f"{px(t):.1f},{py(math.log10(c)):.1f}" for t, c in pts[::2] + [pts[-1]])
    parts.append(f'<polyline points="{line}" fill="none" stroke="#111827" stroke-width="1.8" stroke-linejoin="round"/>')
    last_t, last_c = pts[-1]
    parts.append(f'<circle cx="{px(last_t):.1f}" cy="{py(math.log10(last_c)):.1f}" r="4.5" fill="#fff" stroke="#111827" stroke-width="2"/>')
    parts.append("</svg>")

    pos = (math.log10(last_c) - center(last_t)) / step + 4.5
    idx = max(0, min(8, int(math.floor(pos))))
    return {
        "svg": "".join(parts),
        "price": f"${last_c:,.2f}",
        "band": RAINBOW_BANDS[idx][0],
        "band_color": RAINBOW_BANDS[idx][1],
        "asof": datetime.fromtimestamp(last_t, timezone.utc).strftime("%d %b %Y"),
        "legend": [{"label": n, "color": c} for n, c in reversed(RAINBOW_BANDS)],
    }


def get_rainbow(asset: str) -> dict:
    if asset not in _GENESIS:
        raise ToolsDataError("Unknown asset.")
    return _cached(f"rainbow:{asset}", 6 * 3600, lambda: _build_rainbow(asset))


# ---- Fear & Greed gauge SVG -----------------------------------------------
_FNG_ZONES = [(0, 25, "#ea3943"), (25, 45, "#ea8c00"), (45, 55, "#d6b800"), (55, 75, "#93d900"), (75, 100, "#16c784")]


def fng_gauge_svg(value: int) -> str:
    cx, cy, r_out, r_in = 150, 150, 130, 98

    def pt(v: float, r: float):
        a = math.pi * (1 - v / 100)
        return cx + r * math.cos(a), cy - r * math.sin(a)

    out = ['<svg viewBox="0 0 300 168" width="100%" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Fear and Greed gauge" style="display:block">']
    for a, b, color in _FNG_ZONES:
        x1, y1 = pt(a + 0.6, r_out)
        x2, y2 = pt(b - 0.6, r_out)
        x3, y3 = pt(b - 0.6, r_in)
        x4, y4 = pt(a + 0.6, r_in)
        out.append(
            f'<path d="M{x1:.1f},{y1:.1f} A{r_out},{r_out} 0 0 1 {x2:.1f},{y2:.1f} '
            f'L{x3:.1f},{y3:.1f} A{r_in},{r_in} 0 0 0 {x4:.1f},{y4:.1f} Z" fill="{color}"/>'
        )
    v = max(0, min(100, value))
    nx, ny = pt(v, r_out - 8)
    out.append(f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="var(--gray-12)" stroke-width="4" stroke-linecap="round"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="9" fill="var(--gray-12)"/>')
    for v_lbl, txt in ((0, "0"), (100, "100")):
        x, y = pt(v_lbl, r_out + 0)
        out.append(f'<text x="{x + (14 if v_lbl == 0 else -14):.1f}" y="{y + 16:.1f}" text-anchor="middle" font-size="11" fill="var(--gray-11)">{txt}</text>')
    out.append("</svg>")
    return "".join(out)
