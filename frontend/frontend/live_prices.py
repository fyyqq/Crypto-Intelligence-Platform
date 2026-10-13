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
_BACKOFF_SECONDS = 300  # blocked exchanges (e.g. Binance from Malaysia) cost a ~5s timeout per retry
_down_until: dict[str, float] = {}
# OKX and Gate first: they answer from Malaysia too (Binance, Bybit, KuCoin,
# MEXC and Bitget time out from there), so local development gets prices.
_FALLBACK_ORDER = ["OKX", "GATEIO", "MEXC", "KUCOIN", "HTX", "BYBIT", "BINANCE"]
# TradingView exchange prefixes that name the same venue differently.
_EXCHANGE_ALIASES = {"GATE": "GATEIO", "HUOBI": "HTX"}

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
        if exchange == "OKX":
            base, quote = _split(pair)
            d = client.get("https://www.okx.com/api/v5/market/ticker", params={"instId": f"{base}-{quote}"}).json()
            return float(d["data"][0]["last"])
        if exchange == "GATEIO":
            base, quote = _split(pair)
            d = client.get("https://api.gateio.ws/api/v4/spot/tickers", params={"currency_pair": f"{base}_{quote}"}).json()
            return float(d[0]["last"])
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
        exchange = _EXCHANGE_ALIASES.get(exchange, exchange)
        # A chart pair quoted in a foreign fiat or DEX pool can't be priced
        # here; _price just returns None for unknown exchanges. The chart's
        # own pair is the coin itself, so it gets a wider sanity band than a
        # ticker guess: the stored reference price can lag (e.g. while the
        # CoinMarketCap sync is down) and a real 2-3x move would otherwise be
        # rejected as "a different coin".
        v = _price(client, exchange, pair)
        if v and v > 0 and (ref <= 0 or 0.2 <= v / ref <= 5.0):
            return v
    ticker = "".join(c for c in item.get("symbol", "").upper() if c.isalnum())
    if ticker:
        for exchange in _FALLBACK_ORDER:
            v = _price(client, exchange, f"{ticker}USDT")
            if sane(v):
                return v
    # No exchange we can read lists it (e.g. a memecoin only on KCEX or only
    # on DEXes): its own contract's DEX price. A contract address is an exact
    # identity, so no sanity band against the (possibly stale) stored price.
    return _dex_price(client, item.get("contract") or "")


_dex_cache: dict[str, tuple[float, dict | None]] = {}
_DEX_TTL = 3.0


def _dex_info(client: httpx.Client, contract: str, ttl: float = _DEX_TTL) -> dict | None:
    """The token's own DEX market data from DexScreener (free public API, no
    key, 300 requests/min): {"price": USD price of the deepest pool,
    "liquidity_usd": liquidity summed over every pool of this token,
    "volume_24h": 24h volume summed over every pool}. Only pools whose base
    token IS this contract count. Cached `ttl` seconds."""
    contract = contract.strip()
    if len(contract) < 20 or _down_until.get("DEXSCREENER", 0) > time.monotonic():
        return None
    hit = _dex_cache.get(contract)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    info = None
    try:
        pairs = client.get(f"https://api.dexscreener.com/latest/dex/tokens/{contract}").json().get("pairs") or []
        own = [p for p in pairs if (p.get("baseToken") or {}).get("address", "").lower() == contract.lower()]
        own.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0), reverse=True)
        if own and float(own[0].get("priceUsd") or 0) > 0:
            info = {
                "price": float(own[0]["priceUsd"]),
                "liquidity_usd": sum(float((p.get("liquidity") or {}).get("usd") or 0) for p in own),
                "volume_24h": sum(float((p.get("volume") or {}).get("h24") or 0) for p in own),
            }
    except httpx.TransportError:
        _down_until["DEXSCREENER"] = time.monotonic() + _BACKOFF_SECONDS
    except Exception:  # noqa: BLE001 - bad payload: no data
        info = None
    _dex_cache[contract] = (time.monotonic(), info)
    return info


def _dex_price(client: httpx.Client, contract: str) -> float | None:
    info = _dex_info(client, contract)
    return info["price"] if info else None


def dex_info(contract: str, ttl: float = 60.0) -> dict | None:
    """Public wrapper for the coin page's information panel (liquidity)."""
    return _dex_info(_shared_client(), contract, ttl)


def fetch_live_prices(items: list[dict]) -> dict[int, float]:
    """items: [{cmc_id, symbol, chart_symbol, ref_price}] -> {cmc_id: price}."""
    if not items:
        return {}
    out: dict[int, float] = {}
    client = _shared_client()
    with ThreadPoolExecutor(max_workers=min(8, len(items))) as pool:
        for item, price in zip(items, pool.map(lambda it: _live_price_for(client, it), items)):
            if price:
                out[int(item["cmc_id"])] = price
    return out


_client: httpx.Client | None = None


def _shared_client() -> httpx.Client:
    """One long-lived client (connection keep-alive) instead of a new TLS
    handshake per call: the coin page polls every second."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    return _client
