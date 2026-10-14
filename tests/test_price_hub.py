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

    no_spot = [r for r in CYBERLEEK if r["exchange"] != "KCEX"]
    assert _pick_best_match(no_spot, "CYBERLEEK", "CyberLeek", {"solana"}) == "BINGX:CYBERLEEKUSDT.P"  # a perpetual trades the coin itself
    dex_only = [r for r in no_spot if r["type"] != "swap" and r["exchange"] != "CRYPTO"]
    assert _pick_best_match(dex_only, "CYBERLEEK", "CyberLeek", {"solana"}) is None  # Base pool, Solana coin: never


def test_preferred_cex_wins_and_dex_on_own_chain_is_used():
    from app.services.tradingview_symbol_service import _ecosystem_hints, _pick_best_match

    rows = [_tv("ABCUSDT", "KCEX", "Abc / USDT"), _tv("ABCUSDT", "Binance", "Abc / TetherUS", prefix="BINANCE")]
    assert _pick_best_match(rows, "ABC", "Abc", set()) == "BINANCE:ABCUSDT"  # a listed big exchange beats an unlisted one
    pools = [_tv("ABCSOL_1A2B3C.USD", "Raydium", "Abc / SOL on Solana (So11111111111111111111111111111111111111112) in USD", prefix="RAYDIUM", currency="USD"),
             _tv("ABCWETH_9F.USD", "Uniswap v4 Base", "Abc / WETH on Base (0x9f00000000) in USD", prefix="UNISWAP4BASE", currency="USD")]
    assert _pick_best_match(pools, "ABC", "Abc", _ecosystem_hints(["Solana Ecosystem", "Memes"])) == "RAYDIUM:ABCSOL_1A2B3C.USD"
    # two chains and no chain hint: the first pool that names the coin, in TradingView's order (since
    # 2026-10-15, on request: better a chart to fix by hand with the report icon than none)
    assert _pick_best_match(pools, "ABC", "Abc", set()) == "RAYDIUM:ABCSOL_1A2B3C.USD"


# ---- Crypto-tab search: Super Inu ("SI") and friends -------------------------------------------
SUPER_INU_BY_NAME = [  # TradingView's Crypto tab for "Super Inu", in its order
    _tv("SIUSDT", "MEXC", "Super Inu / USDT"),
    _tv("SIUSDT.P", "BingX", "Super Inu/USD Tether Perpetual Contract", type_="swap", prefix="BINGX", typespecs=("crypto", "perpetual")),
    _tv("SISUPERUSD", "CRYPTO", "Super Inu", currency="USD", typespecs=("crypto", "cryptoasset", "synthetic")),
    _tv("SIUSDT", "Gate", "Super Inu/Tether", prefix="GATE"),
    _tv("SIUSDT_4F423F", "PancakeSwap v2 BNB chain", "Super Inu / Tether USD on BSC (0x4f423F1B98DF1063628052)", prefix="PANCAKESWAP"),
]
SI_BY_TICKER = [  # "SI": a perpetual of an unnamed "SI" first, then other coins sharing the ticker
    _tv("SIUSDT.P", "MEXC", "SI / Tether PERPETUAL FUTURES", type_="swap", typespecs=("crypto", "perpetual")),
    _tv("SIUSDT", "MEXC", "Super Inu / USDT"),
    _tv("SIUSDT_76A67F", "PancakeSwap v2 BNB chain", "SUPER INTELLIGENCE / Tether USD on BSC (0x76A67f4e49426)", prefix="PANCAKESWAP"),
    _tv("SIUSDT_273346", "Uniswap v4 BNB chain", "SpaceX Inu / Tether USD on BNB Chain (BSC) (0x2733462A8)", prefix="UNISWAP4BSC"),
]


def test_super_inu_gets_its_cex_spot_listing():
    from app.services.tradingview_symbol_service import _ecosystem_hints, _pick_best_match

    hints = _ecosystem_hints(["Solana Ecosystem", "Memes"])
    assert _pick_best_match(SUPER_INU_BY_NAME, "SI", "Super Inu", hints) == "MEXC:SIUSDT"
    assert _pick_best_match(SI_BY_TICKER, "SI", "Super Inu", hints) == "MEXC:SIUSDT"  # the named spot beats the bare perp


def test_cex_priority_follows_the_app_wide_order():
    from app.services.tradingview_symbol_service import _pick_best_match

    rows = [_tv("ABCUSDT", "Binance", "Abc / TetherUS", prefix="BINANCE"), _tv("ABCUSDT", "Bybit", "Abc / USDT", prefix="BYBIT"), _tv("ABCUSDT", "MEXC", "Abc / USDT")]
    assert _pick_best_match(rows, "ABC", "Abc", set()) == "MEXC:ABCUSDT"  # MEXC > KuCoin > HTX > Bybit > Binance


def test_perpetual_when_there_is_no_spot_listing():
    from app.services.tradingview_symbol_service import _pick_best_match

    rows = [_tv("XYZUSDT.P", "LBank", "XYZ coin / Tether USD PERPETUAL CONTRACT", type_="swap", prefix="LBANK", typespecs=("crypto", "perpetual"))]
    assert _pick_best_match(rows, "XYZ", "XYZ coin", set()) == "LBANK:XYZUSDT.P"


def test_first_listing_that_names_the_coin_is_the_fallback_but_never_another_coin():
    from app.services.tradingview_symbol_service import _pick_best_match

    # only pools on two venues and no known chain: the first one that names the coin (TradingView's order)
    pools = [_tv("FOOWETH_1A.USD", "Uniswap v4 Base", "Foo Token / WETH on Base (0x1a00000000)", prefix="UNISWAP4BASE", currency="USD"),
             _tv("FOOBNB_2B", "PancakeSwap v2 BNB chain", "Foo Token / WBNB on BSC (0x2b00000000)", prefix="PANCAKESWAP")]
    assert _pick_best_match(pools, "FOO", "Foo Token", set()) == "UNISWAP4BASE:FOOWETH_1A.USD"
    # same ticker, different coins only: nothing (SpaceX Inu / Super Intelligence are not Super Inu)
    others = [r for r in SI_BY_TICKER if "Super Inu" not in r["description"] and ".P" not in r["symbol"]]
    assert _pick_best_match(others, "SI", "Super Inu", set()) is None


def test_crypto_index_is_the_last_resort():
    from app.services.tradingview_symbol_service import _pick_best_match

    only_index = [_tv("SISUPERUSD", "CRYPTO", "Super Inu", currency="USD", typespecs=("crypto", "cryptoasset", "synthetic"))]
    assert _pick_best_match(only_index, "SI", "Super Inu", set()) == "CRYPTO:SISUPERUSD"


def test_resolver_searches_the_name_first_and_never_calls_coingecko(monkeypatch):
    from types import SimpleNamespace

    from app.services import tradingview_symbol_service as tv

    asked = []
    monkeypatch.setattr(tv, "_search_tradingview", lambda q: asked.append(q) or (SUPER_INU_BY_NAME if q == "Super Inu" else SI_BY_TICKER))
    monkeypatch.setattr("app.services.market_pairs_service.get_market_pairs", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no CoinGecko call")))
    coin = SimpleNamespace(symbol="SI", name="Super Inu", contracts=[], categories=[SimpleNamespace(name="Solana Ecosystem")],
                           tradingview_dex_symbol=None, tradingview_dex_symbol_checked_at=None)
    db = SimpleNamespace(add=lambda c: None, commit=lambda: None)
    assert tv.resolve_dex_chart_symbol(db, coin) == "MEXC:SIUSDT"
    assert asked == ["Super Inu"]  # found by name: the noisy ticker search is not needed
    assert coin.tradingview_dex_symbol_checked_at is not None


def test_resolver_keeps_the_old_symbol_when_tradingview_is_down(monkeypatch):
    from types import SimpleNamespace

    from app.services import tradingview_symbol_service as tv

    monkeypatch.setattr(tv, "_search_tradingview", lambda q: None)
    coin = SimpleNamespace(symbol="SI", name="Super Inu", contracts=[], categories=[], tradingview_dex_symbol="MEXC:SIUSDT", tradingview_dex_symbol_checked_at=None)
    db = SimpleNamespace(add=lambda c: (_ for _ in ()).throw(AssertionError("nothing to save")), commit=lambda: None)
    assert tv.resolve_dex_chart_symbol(db, coin) == "MEXC:SIUSDT" and coin.tradingview_dex_symbol_checked_at is None
