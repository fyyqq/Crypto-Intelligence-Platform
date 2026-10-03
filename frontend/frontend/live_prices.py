"""Live spot prices for the floating watchlist popup.

TradingView's embedded chart streams its price straight from the exchange
the chart symbol points at (CoinState._resolve_tradingview_symbol picks it),
and offers no price API of its own. So the popup reads the same exchange's
public ticker for the same pair — the same number the chart shows, a few
seconds behind at most. A coin whose chart exchange can't be queried (or that
has no known pair yet) is tried on MEXC, KuCoin, HTX, Bybit and Binance as
{TICKER}USDT, guarded by a price sanity check against the coin's synced price
so a same-ticker different coin is never shown. No match returns nothing and
the caller keeps the synced price.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import httpx

_TIMEOUT = 2.5
# An exchange that timed out/errored is skipped for this long, so one blocked
# or slow venue doesn't add its timeout to every poll.
_BACKOFF_SECONDS = 60
_down_until: dict[str, float] = {}
_FALLBACK_ORDER = ["MEXC", "KUCOIN", "HTX", "BYBIT", "BINANCE"]
_QUOTES = ("USDT", "USDC", "USD", "FDUSD", "BUSD", "DAI", "TUSD")


def _split(pair: str) -> tuple[str, str]:
    for q in _QUOTES:
        if pair.endswith(q) and len(pair) > len(q):
            return pair[: -len(q)], q
    return pair, ""


def _price(client: httpx.Client, exchange: str, pair: str) -> float | None:
    """Last traded price of `pair` (e.g. "BTCUSDT") on `exchange`, or None."""
    if _down_until.get(exchange, 0) > time.monotonic():
        return None
    try:
        if exchange == "MEXC":
            d = client.get("https://api.mexc.com/api/v3/ticker/price", params={"symbol": pair}).json()
            return float(d["price"])
        if exchange == "BINANCE":
            d = client.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": pair}).json()
            return float(d["price"])
        if exchange == "KUCOIN":
            base, quote = _split(pair)
            d = client.get(
                "https://api.kucoin.com/api/v1/market/orderbook/level1", params={"symbol": f"{base}-{quote}"}
            ).json()
            return float(d["data"]["price"])
        if exchange == "HTX":
            d = client.get("https://api.huobi.pro/market/detail/merged", params={"symbol": pair.lower()}).json()
            return float(d["tick"]["close"])
        if exchange == "BYBIT":
            d = client.get(
                "https://api.bybit.com/v5/market/tickers", params={"category": "spot", "symbol": pair}
            ).json()
            return float(d["result"]["list"][0]["lastPrice"])
    except httpx.TransportError:
        _down_until[exchange] = time.monotonic() + _BACKOFF_SECONDS
        return None
    except Exception:  # noqa: BLE001 — bad payload (unknown pair etc.): no live price
        return None
    return None


def _live_price_for(client: httpx.Client, item: dict) -> float | None:
    ref = float(item.get("ref_price") or 0)

    def sane(v: float | None) -> bool:
        return bool(v) and v > 0 and (ref <= 0 or 0.5 <= v / ref <= 2.0)

    chart = item.get("chart_symbol") or ""
    if ":" in chart:
        exchange, pair = chart.split(":", 1)
        # A chart pair quoted in a foreign fiat or DEX pool can't be priced
        # here; _price just returns None for unknown exchanges.
        v = _price(client, exchange, pair)
        if sane(v):
            return v
    ticker = "".join(c for c in item.get("symbol", "").upper() if c.isalnum())
    if not ticker:
        return None
    for exchange in _FALLBACK_ORDER:
        v = _price(client, exchange, f"{ticker}USDT")
        if sane(v):
            return v
    return None


def fetch_live_prices(items: list[dict]) -> dict[int, float]:
    """items: [{cmc_id, symbol, chart_symbol, ref_price}] -> {cmc_id: price}."""
    if not items:
        return {}
    out: dict[int, float] = {}
    with httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}) as client:
        with ThreadPoolExecutor(max_workers=min(8, len(items))) as pool:
            for item, price in zip(items, pool.map(lambda it: _live_price_for(client, it), items)):
                if price:
                    out[int(item["cmc_id"])] = price
    return out
