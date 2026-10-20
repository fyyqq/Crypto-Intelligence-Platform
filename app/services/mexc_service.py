"""The owner's MEXC spot portfolio, read-only (/portfolio and the coin page's "Your MEXC orders").

Safety:
- The key is a READ-ONLY MEXC key (Spot: View Account Details + View Order Details) linked to the server's IP.
  On top of that, this module can only send signed GET requests, and only to the read endpoints in
  _READ_PATHS: nothing here can place, change or cancel an order, or move funds. (The GET deposit-address
  endpoint only READS an address that already exists; the POST that creates one is never called.)
- The key and secret are read from settings on the server and used only to sign a request. They are never
  logged, never put in an exception or page state, and every network error is re-raised as a plain
  MexcError `from None` so no URL or traceback with a signature reaches the error log.
- Only logged-in accounts listed in MEXC_VIEWER_EMAILS see the data (can_view); the state checks it on the
  server for every event.

What MEXC gives (Spot API v3): balances (free + locked), open orders per symbol, and the account's own trades
of the last month per symbol (MEXC keeps one month in the API). Prices come from MEXC's own public 24h
ticker list (one call), so every pair you hold is priced from the exchange it trades on.

The average buy price per coin is worked out from that trade history (average-cost method). When the history
does not cover the whole holding (bought more than a month ago, deposited from elsewhere), the coin has no
average and no profit/loss until one is typed in by hand (portfolio_costs, set_cost).

Every viewer reads the same cached account (one key = one account): balances and orders refresh at most every
ACCOUNT_TTL seconds and prices every PRICES_TTL seconds however many tabs are open.

MEXC_FIXTURE_FILE (local UI testing only) serves MEXC-shaped responses from a JSON file instead of calling
MEXC; the snapshot is then marked demo=True and the page says so."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import threading
import time
import urllib.parse
from pathlib import Path

import requests

from app.core.config import settings

_log = logging.getLogger(__name__)

BASE_URL = "https://api.mexc.com"
_TIMEOUT = (4, 10)  # connect, read
ACCOUNT_TTL = 20  # seconds: balances + open orders
PRICES_TTL = 10  # seconds: public 24h tickers
TRADES_TTL = 600  # seconds: a coin's trade history (refetched sooner when its balance changes)
COIN_ORDERS_TTL = 20  # seconds: open orders of a coin you don't hold (coin page)
KLINES_TTL = 60  # seconds: the coin page lines chart's candles (public market data, shared)
DUST_USD = 1.0  # holdings worth less than this are summed as "small balances"
RECENT_FILLS = 50  # latest trades returned (the page shows them 5 at a time)
_TRADE_PAGES = 5  # up to 5 x 100 trades per coin

# Signed calls are only ever sent to these read endpoints (GET).
_READ_PATHS = frozenset({"/api/v3/account", "/api/v3/openOrders", "/api/v3/myTrades", "/api/v3/capital/deposit/address"})
DEPOSIT_TTL = 3600  # seconds: a deposit address does not change, so it is read once an hour
DEPOSIT_RETRY = 600  # seconds before asking again after MEXC refused or failed

# Priced at $1 when MEXC has no USDT pair for them (USDT itself always).
_STABLES = frozenset({"USDT", "USDC", "FDUSD", "USDE", "DAI", "TUSD", "USD1", "PYUSD", "USDD", "BUSD"})

_ORDER_TYPES = {
    "LIMIT": "Limit",
    "LIMIT_MAKER": "Post-only",
    "MARKET": "Market",
    "STOP_LOSS": "Stop-loss",
    "STOP_LOSS_LIMIT": "Stop-limit",
    "TAKE_PROFIT": "Take-profit",
    "TAKE_PROFIT_LIMIT": "Take-profit limit",
    "IMMEDIATE_OR_CANCEL": "IOC",
    "FILL_OR_KILL": "FOK",
}

# MEXC error codes -> what to do about them (anything else shows MEXC's own message).
_ERRORS = {
    700006: "This server's IP address is not linked to the MEXC API key. Add it under MEXC > API Management > Link IP Address.",
    700002: "MEXC rejected the request signature. Check MEXC_API_SECRET in the server's .env.",
    700003: "The server clock is out of sync with MEXC. Try again in a minute.",
    700007: "The MEXC API key lacks a permission. Tick Spot 'View Account Details' and 'View Order Details'.",
    10072: "MEXC does not recognise the API key. Check MEXC_API_KEY in the server's .env (keys without a linked IP expire after 90 days).",
}


class MexcError(RuntimeError):
    """A message that is safe to show on the page (never contains the key, secret, a signed URL or the server's
    IP: MEXC's own error text is only ever written to the server log)."""


class MexcRateLimited(MexcError):
    """MEXC answered HTTP 429 (or code 429): every MEXC request is paused until _rate["until"]."""


# Rate-limit pause shared by every request (one key, one IP): the first 429 pauses for ACCOUNT_TTL seconds
# (longer if MEXC sends Retry-After), each further 429 doubles it up to RATE_LIMIT_MAX_SECONDS, and a good reply
# resets the count. The pause also blocks the refresh icon (force=True): _get checks it before sending anything.
RATE_LIMIT_MAX_SECONDS = 300
_rate: dict = {"until": 0.0, "strikes": 0}


def _rate_limited(reply) -> MexcRateLimited:
    _rate["strikes"] = min(_rate["strikes"] + 1, 8)
    try:
        retry_after = float(getattr(reply, "headers", {}).get("Retry-After") or 0)
    except (TypeError, ValueError):
        retry_after = 0.0
    wait = min(max(retry_after, ACCOUNT_TTL * 2 ** (_rate["strikes"] - 1)), RATE_LIMIT_MAX_SECONDS)
    _rate["until"] = time.time() + wait
    _log.warning("MEXC rate limit (429): pausing all MEXC requests for %ds (strike %d)", wait, _rate["strikes"])
    return MexcRateLimited(f"MEXC rate limit reached. Waiting about {int(wait)} s before asking again.")


# ---------------------------------------------------------------------------------------------- access


def viewer_emails() -> set[str]:
    return {e.strip().lower() for e in (settings.mexc_viewer_emails or "").split(",") if e.strip()}


def can_view(email: str) -> bool:
    """Only listed accounts see the MEXC data; no list = nobody."""
    return bool(email) and email.strip().lower() in viewer_emails()


def is_configured() -> bool:
    return bool(settings.mexc_fixture_file) or bool(settings.mexc_api_key and settings.mexc_api_secret)


# --------------------------------------------------------------------------------------------- transport

_fixture_cache: dict = {"path": "", "mtime": 0.0, "data": None}


def _fixture() -> dict | None:
    path = settings.mexc_fixture_file
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent.parent / p
    mtime = p.stat().st_mtime
    if _fixture_cache["path"] != str(p) or _fixture_cache["mtime"] != mtime:
        _fixture_cache.update(path=str(p), mtime=mtime, data=json.loads(p.read_text()))
    return _fixture_cache["data"]


def _from_fixture(fx: dict, path: str, params: dict) -> object:
    if path == "/api/v3/account":
        return fx.get("account", {"balances": []})
    if path == "/api/v3/ticker/24hr":
        return fx.get("ticker24hr", [])
    if path == "/api/v3/openOrders":
        orders = fx.get("openOrders", {})
        if "symbol" not in params:
            return [o for rows in orders.values() for o in rows]
        return orders.get(params["symbol"], [])
    if path == "/api/v3/myTrades":
        return fx.get("myTrades", {}).get(params.get("symbol", ""), [])
    if path == "/api/v3/klines":
        return fx.get("klines", {}).get(params.get("symbol", ""), [])
    if path == "/api/v3/capital/deposit/address":
        return fx.get("depositAddress", {}).get(params.get("coin", ""), [])
    raise MexcError("Not available in demo data.")


def _get(path: str, params: dict | None = None, signed: bool = False) -> object:
    params = dict(params or {})
    fx = _fixture()
    if fx is not None:
        return _from_fixture(fx, path, params)
    paused = _rate["until"] - time.time()
    if paused > 0:  # a 429 paused MEXC: nothing is sent (not even a forced refresh) until it ends
        raise MexcRateLimited(f"MEXC rate limit reached. Waiting about {int(paused) + 1} s before asking again.")
    headers = {"User-Agent": "Mozilla/5.0"}
    if signed:
        if path not in _READ_PATHS:  # read endpoints only, whatever a caller asks for
            raise MexcError("Only read-only MEXC requests are allowed.")
        if not (settings.mexc_api_key and settings.mexc_api_secret):
            raise MexcError("MEXC is not connected: MEXC_API_KEY and MEXC_API_SECRET are not set on this server.")
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 10000
        query = urllib.parse.urlencode(params)
        signature = hmac.new(settings.mexc_api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        query += "&signature=" + signature
        headers["X-MEXC-APIKEY"] = settings.mexc_api_key
    else:
        query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{path}" + (f"?{query}" if query else "")
    try:
        # No redirects: a signed request (and its API-key header) must never be forwarded to another address.
        r = requests.get(url, headers=headers, timeout=_TIMEOUT, allow_redirects=False)
        if r.status_code == 429:
            raise _rate_limited(r)
        data = r.json()
    except requests.RequestException:
        raise MexcError("MEXC could not be reached. It will retry shortly.") from None
    except ValueError:
        raise MexcError(f"MEXC sent an unreadable reply (HTTP {r.status_code}).") from None
    if isinstance(data, dict) and data.get("code") not in (None, 0, 200):
        code = data.get("code")
        if code == 429:
            raise _rate_limited(r)
        # MEXC's own text can contain this server's IP address: it goes to the server log, never to the page.
        _log.warning("MEXC API error: code=%s msg=%s (HTTP %s)", code, str(data.get("msg") or "")[:200], r.status_code)
        raise MexcError(_ERRORS.get(code, f"MEXC API error (code {code}). Details are in the server log.")) from None
    if r.status_code != 200:
        raise MexcError(f"MEXC answered HTTP {r.status_code}.") from None
    _rate["strikes"] = 0
    return data


# ------------------------------------------------------------------------------------------------ helpers


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _split_symbol(symbol: str) -> tuple[str, str]:
    for quote in ("USDT", "USDC", "USDE", "BTC", "ETH"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, ""


def average_cost(trades: list[dict]) -> dict:
    """Average-cost method over one coin's trades (USDT pair), oldest first. Buys add their USDT cost (plus a
    USDT fee); a fee paid in the coin itself reduces the coins received; sells take coins out at the running
    average. Returns {"qty", "avg_price", "short"}: qty = coins the history accounts for, short = a sell was
    bigger than the coins seen so far (the coin was held before the history starts)."""
    qty = cost = 0.0
    short = False
    for t in sorted(trades, key=lambda t: _f(t.get("time"))):
        q, quote_qty = _f(t.get("qty")), _f(t.get("quoteQty")) or _f(t.get("qty")) * _f(t.get("price"))
        fee, fee_asset = _f(t.get("commission")), str(t.get("commissionAsset") or "")
        base, quote = _split_symbol(str(t.get("symbol") or ""))
        if t.get("isBuyer"):
            if fee_asset == base:
                q -= fee
            elif fee_asset == quote:
                quote_qty += fee
            qty += max(q, 0.0)
            cost += quote_qty
        else:
            if q > qty + 1e-12:
                short = True
            sold = min(q, qty)
            if qty > 0:
                cost -= cost / qty * sold
            qty -= sold
            if qty <= 1e-12:
                qty = cost = 0.0
    return {"qty": qty, "avg_price": cost / qty if qty > 0 else 0.0, "short": short}


# -------------------------------------------------------------------------------------------- formatting
# Shared by the /portfolio page (state/portfolio_state.py) and the Telegram /portfolio command. Coin PRICES are
# not formatted here: they go through the frontend's _fmt_usd (page) / telegram_notify_service._fmt_price.


def fmt_money(v: float) -> str:
    """A USD amount (a value, not a coin price)."""
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def fmt_signed_money(v: float) -> str:
    return ("+" if v > 0 else "-" if v < 0 else "") + f"${abs(v):,.2f}"


def fmt_qty(v: float) -> str:
    """A coin amount: thousands separators, up to 8 decimals for small amounts, no trailing zeros."""
    if v >= 1000:
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    if v >= 1:
        return f"{v:,.4f}".rstrip("0").rstrip(".")
    return f"{v:.8f}".rstrip("0").rstrip(".") or "0"


# ---------------------------------------------------------------------------------------------- caching

_lock = threading.Lock()
_cache: dict = {
    "raw_at": 0.0,
    "ok_at": 0.0,
    "balances": [],
    "orders": [],
    "error": "",
    "prices_at": 0.0,
    "tickers": {},
    "trades": {},  # symbol -> {"at", "amount", "rows"}
    "coin_orders": {},  # symbol -> {"at", "rows"}
    "open_orders_all": None,  # None = not tried, True/False = MEXC does / doesn't list all symbols in one call
}


def _refresh_prices(force: bool = False) -> None:
    if not force and time.time() - _cache["prices_at"] < PRICES_TTL:
        return
    rows = _get("/api/v3/ticker/24hr")
    tickers = {}
    for row in rows if isinstance(rows, list) else []:
        last = _f(row.get("lastPrice"))
        if last > 0:
            tickers[str(row.get("symbol"))] = {"price": last, "open": _f(row.get("openPrice"))}
    if tickers:
        _cache["tickers"], _cache["prices_at"] = tickers, time.time()


def price_of(asset: str) -> tuple[float, float]:
    """(last price, price 24h ago) in USD for a MEXC asset code; (0, 0) when MEXC has no pair for it."""
    t = _cache["tickers"]
    if asset == "USDT":
        return 1.0, 1.0
    row = t.get(f"{asset}USDT")
    if row:
        return row["price"], row["open"] or row["price"]
    usdc = t.get(f"{asset}USDC")
    if usdc:
        return usdc["price"], usdc["open"] or usdc["price"]
    if asset in _STABLES:
        return 1.0, 1.0
    return 0.0, 0.0


def _open_orders(symbols: list[str]) -> list[dict]:
    """Every open order: one call when MEXC lists all symbols at once, else one call per symbol."""
    if _cache["open_orders_all"] is not False:
        try:
            rows = _get("/api/v3/openOrders", signed=True)
            if isinstance(rows, list):
                _cache["open_orders_all"] = True
                return rows
        except MexcError:
            if _cache["open_orders_all"]:
                raise
        _cache["open_orders_all"] = False
    rows: list[dict] = []
    for symbol in symbols:
        got = _get("/api/v3/openOrders", {"symbol": symbol}, signed=True)
        rows.extend(got if isinstance(got, list) else [])
    return rows


def _trades(symbol: str, amount: float) -> list[dict]:
    """The account's trades on one pair (newest pages first, up to _TRADE_PAGES x 100), cached; refetched when
    the held amount changed (an order filled) or after TRADES_TTL."""
    hit = _cache["trades"].get(symbol)
    if hit and time.time() - hit["at"] < TRADES_TTL and abs(hit["amount"] - amount) <= max(amount, 1e-12) * 1e-9:
        return hit["rows"]
    rows: list[dict] = []
    end_time = None
    for _ in range(_TRADE_PAGES):
        params = {"symbol": symbol, "limit": 100}
        if end_time:
            params["endTime"] = end_time
        page = _get("/api/v3/myTrades", params, signed=True)
        page = page if isinstance(page, list) else []
        rows.extend(page)
        if len(page) < 100:
            break
        end_time = int(min(_f(t.get("time")) for t in page)) - 1
    _cache["trades"][symbol] = {"at": time.time(), "amount": amount, "rows": rows}
    return rows


def _refresh_account(force: bool = False) -> None:
    if not force and time.time() - _cache["raw_at"] < ACCOUNT_TTL:
        return
    account = _get("/api/v3/account", signed=True)
    balances = [
        {"asset": str(b.get("asset")), "free": _f(b.get("free")), "locked": _f(b.get("locked"))}
        for b in (account.get("balances") or [] if isinstance(account, dict) else [])
        if _f(b.get("free")) + _f(b.get("locked")) > 0
    ]
    _refresh_prices()
    # Orders on every coin worth at least DUST_USD or with coins locked in an order.
    symbols = sorted(
        f"{b['asset']}USDT"
        for b in balances
        if b["asset"] not in _STABLES and (b["locked"] > 0 or (b["free"] + b["locked"]) * price_of(b["asset"])[0] >= DUST_USD)
    )
    orders = _open_orders(symbols)
    for b in balances:
        amount = b["free"] + b["locked"]
        if b["asset"] not in _STABLES and amount * price_of(b["asset"])[0] >= DUST_USD:
            _trades(f"{b['asset']}USDT", amount)
    now = time.time()
    _cache.update(balances=balances, orders=orders, raw_at=now, ok_at=now, error="")


def _refresh(force: bool = False) -> None:
    with _lock:
        try:
            _refresh_account(force)
            _refresh_prices(force)
        except MexcError as exc:
            _cache["error"] = str(exc)
            _cache["raw_at"] = time.time()  # back off for ACCOUNT_TTL instead of hammering MEXC


# ---------------------------------------------------------------------------------------------- snapshot


_deposits: dict[str, dict] = {}  # coin -> {"at", "address", "network", "memo", "error"}


def deposit_address(coin: str = "SOL") -> dict:
    """The account's own deposit address for `coin` (Solana by default) as {"address", "network", "memo", "error"}.
    Read-only (GET /api/v3/capital/deposit/address: it only returns an address the account already has) and cached for
    DEPOSIT_TTL; a refusal (for example the key lacks the permission) is remembered for DEPOSIT_RETRY and shown as `error`,
    never raised, so the page around it keeps working. Blocking: call it from a thread."""
    coin = (coin or "").upper()
    hit = _deposits.get(coin)
    if hit and time.time() - hit["at"] < (DEPOSIT_TTL if hit["address"] else DEPOSIT_RETRY):
        return {k: hit[k] for k in ("address", "network", "memo", "error")}
    result = {"address": "", "network": "", "memo": "", "error": ""}
    try:
        rows = _get("/api/v3/capital/deposit/address", {"coin": coin}, signed=True)
        for row in rows if isinstance(rows, list) else []:
            network = str(row.get("network") or "")
            if coin == "SOL" and not re.search(r"solana|^sol$", network, re.I):
                continue  # SOL can also be sent on other networks: only the Solana network's address is shown
            if row.get("address"):
                result.update(address=str(row["address"]), network=network, memo=str(row.get("memo") or ""))
                break
        if not result["address"]:
            result["error"] = f"MEXC has no {coin} deposit address for this account yet. Open Deposit > {coin} on MEXC once to create it."
    except MexcError as err:
        result["error"] = f"The deposit address could not be read from MEXC: {err}"
    _deposits[coin] = {"at": time.time(), **result}
    return result


def held_assets() -> dict[str, float]:
    """{asset code: USD price} of every non-stable coin worth at least DUST_USD in the account, for marking the
    coins you hold on /gainers-losers. Shares the account cache (a read at most every ACCOUNT_TTL). Blocking.
    {} when MEXC is not configured or the read failed and nothing is cached; never raises. No amounts leave here."""
    if not is_configured():
        return {}
    try:
        _refresh()
        out: dict[str, float] = {}
        for b in _cache["balances"]:
            asset = b["asset"]
            if asset in _STABLES:
                continue
            price = price_of(asset)[0]
            if price > 0 and (b["free"] + b["locked"]) * price >= DUST_USD:
                out[asset] = price
        return out
    except Exception:  # noqa: BLE001 - the board simply shows no holdings
        return {}


def _order_row(o: dict) -> dict:
    symbol = str(o.get("symbol") or "")
    asset, quote = _split_symbol(symbol)
    qty, filled = _f(o.get("origQty")), _f(o.get("executedQty"))
    price, stop = _f(o.get("price")), _f(o.get("stopPrice"))
    market = price_of(asset)[0]
    target = stop or price
    order_type = str(o.get("type") or "")
    return {
        "order_id": str(o.get("orderId") or ""),
        "symbol": symbol,
        "asset": asset,
        "quote": quote,
        "side": str(o.get("side") or "").upper(),
        "type": order_type,
        "type_label": _ORDER_TYPES.get(order_type, order_type.replace("_", " ").title()),
        "price": price,
        "stop_price": stop,
        "qty": qty,
        "filled": filled,
        "filled_pct": filled / qty * 100 if qty else 0.0,
        "value": (qty - filled) * (price or market),
        "time_ms": _f(o.get("time")),
        "market_price": market,
        "distance_pct": (target / market - 1) * 100 if market and target else 0.0,
    }


def portfolio(user_id: int | None = None, force: bool = False) -> dict:
    """The whole dashboard as plain numbers (the state formats them). Blocking: call it from a thread.
    On a MEXC error the last good data is kept and `error` says what is wrong."""
    if not is_configured():
        return {"ok": False, "configured": False, "error": "MEXC is not connected on this server.", "holdings": [], "orders": [], "trades": []}
    _refresh(force)
    costs = get_costs(user_id) if user_id else {}
    holdings, dust_count, dust_value = [], 0, 0.0
    total = change = cost_total = pnl_total = 0.0
    for b in _cache["balances"]:
        asset = b["asset"]
        amount = b["free"] + b["locked"]
        price, open_price = price_of(asset)
        value = amount * price
        stable = asset in _STABLES
        if value < DUST_USD and b["locked"] <= 0:
            dust_count += 1
            dust_value += value
            total += value
            continue
        avg, source = 0.0, ""
        if asset in costs:
            avg, source = costs[asset], "manual"
        elif not stable:
            hist = average_cost(_cache["trades"].get(f"{asset}USDT", {}).get("rows", []))
            # The history must account for (nearly) the whole holding, else part of it has an unknown cost.
            if hist["qty"] > 0 and hist["qty"] >= amount * 0.98 and not hist["short"]:
                avg, source = hist["avg_price"], "trades"
        pnl = (price - avg) * amount if avg > 0 and price > 0 else 0.0
        if avg > 0 and price > 0:
            cost_total += avg * amount
            pnl_total += pnl
        day_change = amount * (price - open_price) if not stable else 0.0
        total += value
        change += day_change
        holdings.append(
            {
                "asset": asset,
                "free": b["free"],
                "locked": b["locked"],
                "amount": amount,
                "price": price,
                "value": value,
                "pct_24h": (price / open_price - 1) * 100 if open_price and not stable else 0.0,
                "change_24h": day_change,
                "avg_price": avg,
                "avg_source": source,
                "pnl": pnl,
                "pnl_pct": (price / avg - 1) * 100 if avg > 0 and price > 0 else 0.0,
                "is_stable": stable,
                "priced": price > 0,
            }
        )
    holdings.sort(key=lambda h: h["value"], reverse=True)
    for h in holdings:
        h["allocation_pct"] = h["value"] / total * 100 if total else 0.0
    orders = sorted((_order_row(o) for o in _cache["orders"]), key=lambda o: o["time_ms"], reverse=True)
    locked_usdt = sum(b["locked"] for b in _cache["balances"] if b["asset"] == "USDT")
    buy_usdt = sum(o["value"] for o in orders if o["side"] == "BUY" and o["quote"] == "USDT")
    trades = []
    for symbol, hit in _cache["trades"].items():
        for t in hit["rows"]:
            asset, quote = _split_symbol(symbol)
            trades.append(
                {
                    "asset": asset,
                    "side": "BUY" if t.get("isBuyer") else "SELL",
                    "price": _f(t.get("price")),
                    "qty": _f(t.get("qty")),
                    "value": _f(t.get("quoteQty")) or _f(t.get("qty")) * _f(t.get("price")),
                    "fee": _f(t.get("commission")),
                    "fee_asset": str(t.get("commissionAsset") or ""),
                    "time_ms": _f(t.get("time")),
                }
            )
    trades.sort(key=lambda t: t["time_ms"], reverse=True)
    stable_value = sum(h["value"] for h in holdings if h["is_stable"])
    locked_value = sum(b["locked"] * price_of(b["asset"])[0] for b in _cache["balances"])
    return {
        "ok": bool(_cache["ok_at"]),  # there is data to show (an error may still be shown above it)
        "configured": True,
        "demo": bool(settings.mexc_fixture_file),
        "error": _cache["error"],
        "updated_at": _cache.get("ok_at", 0.0),  # last successful read (0 = never)
        "total_value": total,
        "change_24h": change,
        "change_24h_pct": change / (total - change) * 100 if total - change > 0 else 0.0,
        "stable_value": stable_value,
        "locked_value": locked_value,
        "cost_total": cost_total,
        "pnl": pnl_total,
        "pnl_pct": pnl_total / cost_total * 100 if cost_total else 0.0,
        "with_cost": sum(1 for h in holdings if h["avg_price"] > 0),
        "without_cost": sum(1 for h in holdings if not h["is_stable"] and h["avg_price"] <= 0),
        "holdings": holdings,
        "dust_count": dust_count,
        "dust_value": dust_value,
        "orders": orders,
        # USDT locked in buy orders this page could not find (MEXC lists orders per coin; a buy order on a
        # coin you don't hold shows on that coin's page).
        "unmatched_locked_usdt": max(locked_usdt - buy_usdt, 0.0) if _cache["open_orders_all"] is False else 0.0,
        "trades": trades[:RECENT_FILLS],
        "deposit_sol": deposit_address("SOL"),
    }


def coin_orders(asset: str) -> list[dict]:
    """Open orders for one coin (coin page), including a buy order on a coin you don't hold yet."""
    asset = (asset or "").upper()
    if not asset or not is_configured():
        return []
    _refresh()
    rows = [o for o in _cache["orders"] if _split_symbol(str(o.get("symbol") or ""))[0] == asset]
    held = {b["asset"] for b in _cache["balances"]}
    if not rows and _cache["open_orders_all"] is False and asset not in held:
        symbol = f"{asset}USDT"
        with _lock:
            hit = _cache["coin_orders"].get(symbol)
            if not hit or time.time() - hit["at"] > COIN_ORDERS_TTL:
                try:
                    got = _get("/api/v3/openOrders", {"symbol": symbol}, signed=True)
                except MexcError:
                    got = []
                hit = {"at": time.time(), "rows": got if isinstance(got, list) else []}
                _cache["coin_orders"][symbol] = hit
        rows = hit["rows"]
    return sorted((_order_row(o) for o in rows), key=lambda o: o["price"], reverse=True)


KLINE_INTERVALS = {"1m", "5m", "15m", "30m", "60m", "4h", "1d", "1W", "1M"}  # MEXC's names


def klines(asset: str, interval: str = "60m", limit: int = 300) -> list[list[float]]:
    """Public candles of <asset>USDT on MEXC for the coin page's lines chart: [[open time (s), open, high, low,
    close], ...] oldest first (the last `limit` candles of `interval`). Cached per pair and interval for KLINES_TTL
    seconds and shared; [] when MEXC has no such pair or cannot be reached (respects the rate-limit pause)."""
    asset = (asset or "").upper()
    if not asset or not re.fullmatch(r"[A-Z0-9]{1,20}", asset) or interval not in KLINE_INTERVALS or not is_configured():
        return []
    symbol = f"{asset}USDT"
    store = _cache.setdefault("klines", {})
    key = f"{symbol}:{interval}"
    hit = store.get(key)
    if hit and time.time() - hit["at"] < KLINES_TTL:
        return hit["rows"]
    try:
        raw = _get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    except MexcError:
        raw = hit["rows"] if hit else []  # keep the last candles on a hiccup
        store[key] = {"at": time.time(), "rows": raw}
        return raw
    rows = []
    for k in raw if isinstance(raw, list) else []:
        try:
            rows.append([int(float(k[0]) / 1000), _f(k[1]), _f(k[2]), _f(k[3]), _f(k[4])])
        except (TypeError, ValueError, IndexError):
            continue
    rows = [r for r in rows if r[4] > 0]
    rows.sort(key=lambda r: r[0])
    store[key] = {"at": time.time(), "rows": rows}
    return rows


# ------------------------------------------------------------------------------------------- manual costs


def get_costs(user_id: int) -> dict[str, float]:
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.portfolio_cost import PortfolioCost

    db = SessionLocal()
    try:
        rows = db.execute(select(PortfolioCost.asset, PortfolioCost.avg_price).where(PortfolioCost.user_id == user_id))
        return {asset: price for asset, price in rows}
    finally:
        db.close()


def set_cost(user_id: int, asset: str, avg_price: float | None) -> None:
    """Saves (or with None / 0 clears) the hand-typed average buy price of one coin."""
    from app.core.database import SessionLocal
    from app.models.portfolio_cost import PortfolioCost

    asset = (asset or "").strip().upper()[:30]
    if not asset:
        raise ValueError("No coin given.")
    db = SessionLocal()
    try:
        row = db.get(PortfolioCost, (user_id, asset))
        if not avg_price or avg_price <= 0:
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(PortfolioCost(user_id=user_id, asset=asset, avg_price=float(avg_price)))
        else:
            row.avg_price = float(avg_price)
        db.commit()
    finally:
        db.close()
