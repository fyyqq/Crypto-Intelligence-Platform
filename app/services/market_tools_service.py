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


# A CoinMarketCap source that just failed is skipped for this long, so a
# rate-limited or out-of-credit key isn't retried on every page load.
_CMC_FAIL_TTL = 600
_cmc_failed: dict[str, tuple[float, str]] = {}


def _cmc_reason(exc: Exception) -> str:
    text = str(exc)
    if "429" in text:
        return "rate limit or monthly credits used up"
    if "401" in text or "403" in text:
        return "API key rejected"
    return "unreachable"


def _with_cmc_fallback(tool: str, primary, fallback) -> dict:
    """Runs the CoinMarketCap source; when it fails (or failed in the last
    _CMC_FAIL_TTL seconds), returns the free source's result instead with a
    `fallback_note` saying why, rather than an error card."""
    failed = _cmc_failed.get(tool)
    if not failed or time.time() - failed[0] > _CMC_FAIL_TTL:
        try:
            return primary()
        except ToolsDataError as exc:
            failed = (time.time(), _cmc_reason(exc))
            _cmc_failed[tool] = failed
    data = dict(fallback())
    data["fallback_note"] = f"CoinMarketCap unavailable ({failed[1]}), showing {data['source']} instead."
    return data


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
        "ts": ts,  # unix time of the newest value (the Telegram digest checks it is today's)
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
    free = lambda: _cached("fng:alternative", 900, _fng_alternative)  # noqa: E731
    if source != "cmc":
        return {**free(), "fallback_note": ""}
    return _with_cmc_fallback("fng", lambda: {**_cached("fng:cmc", 900, _fng_cmc), "fallback_note": ""}, free)


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
    free = lambda: _cached("season:coingecko", 1800, _season_coingecko)  # noqa: E731
    if source != "cmc":
        return {**free(), "fallback_note": ""}
    return _with_cmc_fallback(
        "season", lambda: {**_cached("season:cmc", 1800, _season_cmc), "fallback_note": ""}, free
    )


# ---- Rainbow chart ---------------------------------------------------------
# Bottom -> top. Palette and labels follow the common Bitcoin Rainbow charts.
RAINBOW_BANDS = [
    ("Fire sale", "#4a6fc0"),
    ("BUY!", "#5f9ea0"),
    ("Accumulate", "#7ebf7e"),
    ("Still cheap", "#b5d686"),
    ("HODL!", "#f6e58d"),
    ("Is this a bubble?", "#ebb35e"),
    ("FOMO intensifies", "#e08a4a"),
    ("Sell. Seriously, SELL!", "#d1522e"),
    ("Maximum bubble territory", "#b5382b"),
]
_BTC_GENESIS = date(2009, 1, 9)
_ETH_GENESIS = date(2015, 7, 30)
# Bitcoin: the widely used logarithmic-growth curve for the centre of the
# rainbow, log10(price) = 2.66167 * ln(days since 2009-01-09) - 17.9183, with
# the nine bands spanning +/-0.6 decades around it (matches Blockchaincenter /
# Coinglass-style charts). Ethereum has no such standard curve, so its centre
# is a least-squares fit of its own history and its bands span the historical
# envelope of the price around that fit.
_BTC_SLOPE, _BTC_ICPT, _BTC_HALF_WIDTH = 2.66167, -17.9183, 0.6
_FUTURE_DAYS = 580  # how far past today the bands are drawn


def _history_coinmetrics(asset: str) -> list[tuple[int, float]]:
    data = _get(
        "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
        f"?assets={asset.lower()}&metrics=PriceUSD&frequency=1d&page_size=10000&start_time=2010-01-01"
    )
    try:
        rows = data["data"]
        return [
            (int(datetime.fromisoformat(r["time"][:19]).replace(tzinfo=timezone.utc).timestamp()), float(r["PriceUSD"]))
            for r in rows
            if r.get("PriceUSD") and float(r["PriceUSD"]) > 0
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ToolsDataError("Unexpected price-history response.") from exc


def _history_yahoo(asset: str) -> list[tuple[int, float]]:
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


def _history(asset: str) -> list[tuple[int, float]]:
    """Daily USD closes. CoinMetrics' free community API has the full history
    (BTC from 2010-07, ETH from 2015-08); Yahoo (BTC from 2014) is the fallback."""

    def load():
        try:
            pts = _history_coinmetrics(asset)
            if len(pts) > 365:
                return pts
        except ToolsDataError:
            pass
        return _history_yahoo(asset)

    return _cached(f"hist:{asset}", 6 * 3600, load)


def _fmt_price(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:g}M"
    if v >= 1000:
        return f"${v / 1000:g}K"
    return f"${v:g}"


def _rainbow_model(asset: str, pts: list[tuple[int, float]]):
    """Returns (center(t), band_bottom_offset, band_top_offset) in log10 units."""
    genesis = _BTC_GENESIS if asset == "BTC" else _ETH_GENESIS
    g = datetime(genesis.year, genesis.month, genesis.day, tzinfo=timezone.utc).timestamp()
    if asset == "BTC":
        slope, icpt = _BTC_SLOPE, _BTC_ICPT
        lo, hi = -_BTC_HALF_WIDTH, _BTC_HALF_WIDTH
    else:
        xs = [math.log((t - g) / 86400) for t, _ in pts if t > g]
        ys = [math.log10(c) for t, c in pts if t > g]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        icpt = my - slope * mx
        res = [y - (slope * x + icpt) for x, y in zip(xs, ys)]
        lo, hi = min(res) - 0.02, max(res) + 0.02

    def center(t: float) -> float:
        return slope * math.log((t - g) / 86400) + icpt

    return center, lo, hi


_W, _H, _L, _R, _T, _B = 1000, 480, 62, 14, 14, 34


def _build_rainbow(asset: str) -> dict:
    """The static part of the chart (bands, axes, daily price line up to the
    last daily close), plus everything the browser needs to draw the live
    point and the hover tooltip (assets/rainbow_hover.js): the chart
    geometry, the band model and the daily price series. Cached 6h with the
    history; the live price is laid over it by rainbow_live()."""
    pts = _history(asset)
    if len(pts) < 365:
        raise ToolsDataError("Not enough price history to draw the chart.")
    center, lo, hi = _rainbow_model(asset, pts)
    step = (hi - lo) / len(RAINBOW_BANDS)

    t0 = pts[0][0]
    t1 = int(time.time()) + _FUTURE_DAYS * 86400

    def edge(t, k):  # k = 0 (bottom of lowest band) .. 9 (top of highest band)
        return center(t) + lo + k * step

    ymin_v = min(min(math.log10(c) for _, c in pts), edge(t0, 0))
    ymax_v = max(max(math.log10(c) for _, c in pts), edge(t1, len(RAINBOW_BANDS)))
    ymin, ymax = math.floor(ymin_v), math.ceil(ymax_v)

    W, H, L, R, T, B = _W, _H, _L, _R, _T, _B
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
        parts.append(f'<polygon points="{" ".join(top + bot)}" fill="{color}"/>')
    for e in range(ymin, ymax + 1):
        y = py(e)
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--gray-a6)" stroke-width="1"/>')
        parts.append(f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="13" fill="var(--gray-11)">{_fmt_price(10 ** e)}</text>')
    y_first = datetime.fromtimestamp(t0, timezone.utc).year + 1
    y_last = datetime.fromtimestamp(t1, timezone.utc).year
    for yr in range(y_first, y_last + 1):
        t = int(datetime(yr, 1, 1, tzinfo=timezone.utc).timestamp())
        if t0 < t < t1:
            parts.append(f'<text x="{px(t):.1f}" y="{H - 10}" text-anchor="middle" font-size="13" fill="var(--gray-11)">{yr}</text>')
    line = " ".join(f"{px(t):.1f},{py(math.log10(c)):.1f}" for t, c in pts[::2] + [pts[-1]])
    parts.append(f'<polyline points="{line}" fill="none" stroke="#111827" stroke-width="1.8" stroke-linejoin="round"/>')
    parts.append("</svg>")

    genesis = _BTC_GENESIS if asset == "BTC" else _ETH_GENESIS
    g = datetime(genesis.year, genesis.month, genesis.day, tzinfo=timezone.utc).timestamp()
    # center(t) = slope * ln(days since genesis) + icpt, so day 1 gives icpt and
    # day e gives slope + icpt. The hover script recomputes band edges from
    # these exactly as edge() does.
    icpt = center(g + 86400)
    slope_icpt = (center(g + 86400 * math.e) - icpt, icpt)
    hover = {
        "asset": asset,
        "W": W, "H": H, "L": L, "R": R, "T": T, "B": B,
        "t0": t0, "t1": t1, "ymin": ymin, "ymax": ymax,
        "g": g, "slope": slope_icpt[0], "icpt": slope_icpt[1], "lo": lo, "step": step,
        "bands": [[n, c] for n, c in RAINBOW_BANDS],
        # daily closes as [day index since t0, price] (every day; ~5.7K points for BTC)
        "pts": [[round((t - t0) / 86400), float(f"{c:.6g}")] for t, c in pts],
    }
    last_t, last_c = pts[-1]
    return {
        "svg": "".join(parts),
        "hover": hover,
        "last_t": last_t,
        "last_c": last_c,
        "geometry": (t0, t1, ymin, ymax),
        "center": center,
        "lo": lo,
        "step": step,
        "legend": [{"label": n, "color": c} for n, c in reversed(RAINBOW_BANDS)],
    }


def _rainbow_static(asset: str) -> dict:
    if asset not in ("BTC", "ETH"):
        raise ToolsDataError("Unknown asset.")
    return _cached(f"rainbow:{asset}", 6 * 3600, lambda: _build_rainbow(asset))


def _live_spot(asset: str) -> tuple[float, str]:
    """Spot USD price right now, from free public exchange tickers (no key):
    Coinbase, then Kraken, then Binance (USDT). Cached 10 seconds."""

    def load():
        tries = (
            ("Coinbase", lambda: float(_get(f"https://api.coinbase.com/v2/prices/{asset}-USD/spot")["data"]["amount"])),
            ("Kraken", lambda: float(next(iter(_get(
                f"https://api.kraken.com/0/public/Ticker?pair={'XBT' if asset == 'BTC' else asset}USD")["result"].values()))["c"][0])),
            ("Binance", lambda: float(_get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT")["price"])),
        )
        for name, fn in tries:
            try:
                price = fn()
                if price > 0:
                    return price, name
            except (ToolsDataError, KeyError, TypeError, ValueError, StopIteration):
                continue
        raise ToolsDataError("No live price source answered.")

    return _cached(f"spot:{asset}", 10, load)


def _band_index(static: dict, t: float, price: float) -> int:
    pos = (math.log10(price) - (static["center"](t) + static["lo"])) / static["step"]
    return max(0, min(len(RAINBOW_BANDS) - 1, int(math.floor(pos))))


def get_rainbow(asset: str) -> dict:
    """The chart plus its current reading. The reading uses the live spot
    price when a free exchange ticker answers, else the last daily close."""
    static = _rainbow_static(asset)
    out = {k: static[k] for k in ("svg", "hover", "legend")}
    out.update(rainbow_live(asset))
    return out


def rainbow_live(asset: str) -> dict:
    """Live reading for the chart: price (raw), band, when, source, and a tiny
    overlay SVG (same viewBox as the chart) with the segment from the last
    daily close to now and the live dot. Small, so it can be pushed often."""
    static = _rainbow_static(asset)
    t0, t1, ymin, ymax = static["geometry"]
    pw, ph = _W - _L - _R, _H - _T - _B

    def px(t):
        return _L + (t - t0) / (t1 - t0) * pw

    def py(v):
        return _T + (ymax - v) / (ymax - ymin) * ph

    last_t, last_c = static["last_t"], static["last_c"]
    try:
        price, source = _live_spot(asset)
        t = time.time()
        live = True
    except ToolsDataError:
        price, source, t, live = last_c, "CoinMetrics daily close", last_t, False
    idx = _band_index(static, t, price)
    x0, y0, x1, y1 = px(last_t), py(math.log10(last_c)), px(t), py(math.log10(price))
    overlay = (
        f'<svg viewBox="0 0 {_W} {_H}" width="100%" xmlns="http://www.w3.org/2000/svg" style="display:block">'
        f'<polyline points="{x0:.1f},{y0:.1f} {x1:.1f},{y1:.1f}" fill="none" stroke="#111827" stroke-width="1.8"/>'
        f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="4.5" fill="#fff" stroke="#111827" stroke-width="2"/></svg>'
    )
    return {
        "price_raw": price,
        "band": RAINBOW_BANDS[idx][0],
        "band_color": RAINBOW_BANDS[idx][1],
        "asof": datetime.fromtimestamp(t, timezone.utc).strftime("%d %b %Y, %H:%M:%S UTC" if live else "%d %b %Y"),
        "live": live,
        "price_source": source,
        "overlay": overlay,
    }


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


# ---- Homepage "Market Status" card ----------------------------------------
_NOT_TOP20 = {"XAUT", "PAXG", "WBTC", "WETH", "WSTETH", "WEETH", "CBBTC"}  # gold-backed / wrapped: not a "top 20 coin"


def _market_status() -> dict:
    """Total crypto market cap (CoinGecko /global) and the combined market cap
    of the 20 biggest coins, excluding stablecoins and wrapped/staked/gold
    tokens, with its 24h change (free, no key)."""
    g = _get("https://api.coingecko.com/api/v3/global")["data"]
    rows = _get(
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd&order=market_cap_desc&per_page=60&page=1&price_change_percentage=24h"
    )
    top = [
        c for c in rows
        if c.get("market_cap")
        and c["symbol"].upper() not in _STABLE
        and c["symbol"].upper() not in _NOT_TOP20
        and not any(w in c["name"].lower() for w in _DERIVATIVE_WORDS)
    ][:20]
    if len(top) < 20:
        raise ToolsDataError("Not enough coins returned for the top 20.")
    now = sum(c["market_cap"] for c in top)
    # each coin's market cap a day ago = now / (1 + its 24h change)
    before = sum(c["market_cap"] / (1 + (c.get("price_change_percentage_24h_in_currency") or 0) / 100) for c in top)
    return {
        "total": float(g["total_market_cap"]["usd"]),
        "total_change": g.get("market_cap_change_percentage_24h_usd"),
        "top20": float(now),
        "top20_change": (now / before - 1) * 100 if before else None,
    }


def get_market_status() -> dict:
    return _cached("market:status", 300, _market_status)


# Last good value per key, for the homepage card: CoinGecko's free API rate-limits
# a server's IP after a few calls (HTTP 429 / connection reset), and a card that
# blanks on one failed refresh is worse than one showing a slightly older figure.
_last_good: dict[str, tuple[float, object]] = {}
_failed_at: dict[str, float] = {}
STALE_MAX_SECONDS = 6 * 3600
RETRY_AFTER_FAILURE = 120


def with_stale(key: str, fn):
    """fn(), remembering the result. If fn fails (ToolsDataError), return the
    last good result (up to 6 h old) and do not call fn again for 2 minutes;
    raise when there is nothing usable."""
    now = time.time()
    good = _last_good.get(key)
    usable = good is not None and now - good[0] < STALE_MAX_SECONDS
    if usable and now - _failed_at.get(key, 0) < RETRY_AFTER_FAILURE:
        return good[1]
    try:
        value = fn()
    except ToolsDataError:
        _failed_at[key] = now
        if usable:
            return good[1]
        raise
    _last_good[key] = (now, value)
    _failed_at.pop(key, None)
    return value


def fng_arc_svg(value: int) -> str:
    """The Fear & Greed gauge for the homepage card: a semicircle of five
    separate colour segments with round ends, the value in the middle and a
    white dot on the arc at the current value."""
    cx, cy, r, gap = 60, 56, 48, 3.0

    def pt(v: float):
        a = math.pi * (1 - v / 100)
        return cx + r * math.cos(a), cy - r * math.sin(a)

    v = max(0, min(100, int(value)))
    out = [
        '<svg viewBox="0 0 120 64" width="100%" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Fear and Greed {v}" style="display:block;overflow:visible">'
    ]
    for a, b, color in _FNG_ZONES:
        x1, y1 = pt(a + gap)
        x2, y2 = pt(b - gap)
        out.append(
            f'<path d="M{x1:.2f},{y1:.2f} A{r},{r} 0 0 1 {x2:.2f},{y2:.2f}" fill="none" stroke="{color}" '
            'stroke-width="6" stroke-linecap="round"/>'
        )
    x, y = pt(v)
    out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="#fff" stroke="rgba(0,0,0,.35)" stroke-width="1.5"/>')
    out.append(
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" font-size="22" font-weight="700" fill="var(--gray-12)">{v}</text>'
    )
    out.append("</svg>")
    return "".join(out)
