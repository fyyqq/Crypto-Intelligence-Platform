"""The shared exchange price list: parsing, source priority, a blocked
exchange being skipped, and the same-ticker plausibility guard. No network."""

import pytest

from app.services import price_hub as hub


class Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


PAYLOADS = {
    "binance": [{"symbol": "BTCUSDT", "lastPrice": "80000", "priceChangePercent": "-1.5"}, {"symbol": "ETHBTC", "lastPrice": "0.03"}],
    "okx": {"data": [{"instId": "BTC-USDT", "last": "80100", "open24h": "80000"}, {"instId": "SOL-USDT", "last": "110", "open24h": "100"}]},
    "bybit": {"result": {"list": [{"symbol": "XRPUSDT", "lastPrice": "1.4", "price24hPcnt": "0.02"}]}},
    "gateio": [{"currency_pair": "GT_USDT", "last": "9.5", "change_percentage": "3"}, {"currency_pair": "SOL_USDT", "last": "999", "change_percentage": "0"}],
}


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(hub, "_prices", {})
    monkeypatch.setattr(hub, "_fetched_at", 0.0)
    monkeypatch.setattr(hub, "_down_until", {})


def fake_get(blocked=()):
    def get(url, **kw):
        for key, data in PAYLOADS.items():
            if key in url:
                if key in blocked:
                    raise TimeoutError("blocked")
                return Resp(data)
        raise AssertionError(url)
    return get


def test_merge_respects_source_priority(monkeypatch):
    monkeypatch.setattr(hub.requests, "get", fake_get())
    p = hub.get_prices()
    assert p["BTC"]["price"] == 80000 and p["BTC"]["source"] == "Binance"  # Binance beats OKX
    assert p["SOL"]["price"] == 110 and p["SOL"]["source"] == "OKX"  # OKX beats Gate
    assert p["SOL"]["pct_24h"] == pytest.approx(10.0)
    assert p["XRP"]["pct_24h"] == pytest.approx(2.0)  # Bybit gives a fraction
    assert p["GT"]["source"] == "Gate" and "ETH" not in p  # non-USDT pairs ignored


def test_blocked_exchange_is_skipped_and_backed_off(monkeypatch):
    calls = []
    inner = fake_get(blocked=("binance",))
    monkeypatch.setattr(hub.requests, "get", lambda url, **kw: calls.append(url) or inner(url, **kw))
    p = hub.get_prices()
    assert p["BTC"]["source"] == "OKX"  # falls through to the next exchange
    assert "Binance" in hub.status()["down"]
    calls.clear()
    hub.refresh()
    assert not any("binance" in u for u in calls)  # not retried during the backoff


def test_cached_copy_is_reused_within_the_refresh_window(monkeypatch):
    calls = []
    inner = fake_get()
    monkeypatch.setattr(hub.requests, "get", lambda url, **kw: calls.append(url) or inner(url, **kw))
    hub.get_prices()
    n = len(calls)
    hub.get_prices()
    hub.get_prices()
    assert len(calls) == n  # no new calls: every reader shares one copy


def test_plausible_guards_same_ticker_coins():
    assert hub.plausible(105, 100)
    assert not hub.plausible(999, 100)  # a different coin with the same ticker
    assert not hub.plausible(1.0, 0)  # no stored price to compare with


# ---- chart symbol selection (TradingView search results) -----------------------
def _tv(symbol, exchange, description, type_="spot", prefix=None, currency="USDT", typespecs=("crypto",)):
    return {"symbol": symbol, "exchange": exchange, "description": description, "type": type_, "prefix": prefix,
            "currency_code": currency, "typespecs": list(typespecs)}


CYBERLEEK = [
    _tv("CYBERLEEKUSD", "CRYPTO", "CyberLeek", currency="USD", typespecs=("crypto", "synthetic")),
    _tv("CYBERLEEKUSDT", "KCEX", "CyberLeek / USDT"),
    _tv("CYBERLEEKUSDT.P", "BingX", "CyberLeek/USD Tether Perpetual Contract", type_="swap", prefix="BINGX"),
    _tv("CYBERLEEKETH_3BCAF5.USD", "Uniswap v4 Base", "CyberLeek / Ether on Base (0x3BCaF5C01751aD4812162Bed8773735f715cdc1d) in USD", prefix="UNISWAP4BASE", currency="USD"),
]


def test_cex_listing_beats_dex_pools_and_ignores_chain():
    from app.services.tradingview_symbol_service import _pick_best_match

    assert _pick_best_match(CYBERLEEK, "CYBERLEEK", "CyberLeek", {"solana"}) == "KCEX:CYBERLEEKUSDT"
    assert _pick_best_match(CYBERLEEK, "CYBERLEEK", "CyberLeek", set()) == "KCEX:CYBERLEEKUSDT"


def test_dex_pool_on_another_chain_is_never_charted():
    from app.services.tradingview_symbol_service import _pick_best_match

    dex_only = [r for r in CYBERLEEK if r["exchange"] != "KCEX"]
    assert _pick_best_match(dex_only, "CYBERLEEK", "CyberLeek", {"solana"}) is None  # Base pool, Solana coin


def test_preferred_cex_wins_and_dex_on_own_chain_is_used():
    from app.services.tradingview_symbol_service import _ecosystem_hints, _pick_best_match

    rows = [_tv("ABCUSDT", "KCEX", "Abc / USDT"), _tv("ABCUSDT", "Binance", "Abc / TetherUS", prefix="BINANCE")]
    assert _pick_best_match(rows, "ABC", "Abc", set()) == "BINANCE:ABCUSDT"
    pools = [_tv("ABCSOL_1A2B3C.USD", "Raydium", "Abc / SOL on Solana (So11111111111111111111111111111111111111112) in USD", prefix="RAYDIUM", currency="USD"),
             _tv("ABCWETH_9F.USD", "Uniswap v4 Base", "Abc / WETH on Base (0x9f00000000) in USD", prefix="UNISWAP4BASE", currency="USD")]
    assert _pick_best_match(pools, "ABC", "Abc", _ecosystem_hints(["Solana Ecosystem", "Memes"])) == "RAYDIUM:ABCSOL_1A2B3C.USD"
    assert _pick_best_match(pools, "ABC", "Abc", set()) is None  # two chains, no hint: don't guess
