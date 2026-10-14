"""Homepage Market Status card data: the top-20 selection and its 24h change, and
the Fear & Greed arc. The HTTP calls are faked; nothing leaves the machine."""

import re

import pytest

from app.services import market_tools_service as mts


def coin(symbol, name, cap, chg):
    return {"symbol": symbol.lower(), "name": name, "market_cap": cap, "price_change_percentage_24h_in_currency": chg}


@pytest.fixture
def fake_gecko(monkeypatch):
    rows = [
        coin("btc", "Bitcoin", 1000, 10.0),
        coin("usdt", "Tether", 500, 0.0),  # stablecoin: excluded
        coin("eth", "Ethereum", 400, -5.0),
        coin("steth", "Lido Staked Ether", 300, -5.0),  # staked: excluded
        coin("wbtc", "Wrapped Bitcoin", 200, 10.0),  # wrapped: excluded
        coin("xaut", "Tether Gold", 100, 0.0),  # gold-backed: excluded
        *[coin(f"c{i}", f"Coin {i}", 50 - i, 0.0) for i in range(30)],
    ]

    def fake_get(url, **kw):
        if url.endswith("/global"):
            return {"data": {"total_market_cap": {"usd": 5000}, "market_cap_change_percentage_24h_usd": -1.5}}
        return rows

    monkeypatch.setattr(mts, "_get", fake_get)
    mts._cache.pop("market:status", None)


def test_top20_excludes_stablecoins_wrapped_and_gold(fake_gecko):
    s = mts._market_status()
    assert s["total"] == 5000 and s["total_change"] == -1.5
    # BTC 1000 + ETH 400 + 18 filler coins (50-0 ... 50-17), none of the excluded ones
    assert s["top20"] == 1000 + 400 + sum(50 - i for i in range(18))


def test_top20_change_is_the_change_of_the_combined_market_cap(fake_gecko):
    s = mts._market_status()
    before = 1000 / 1.10 + 400 / 0.95 + sum(50 - i for i in range(18))
    assert s["top20_change"] == pytest.approx((s["top20"] / before - 1) * 100)


def test_too_few_coins_is_an_error(monkeypatch):
    monkeypatch.setattr(mts, "_get", lambda url, **kw: {"data": {"total_market_cap": {"usd": 1}}} if url.endswith("/global") else [coin("btc", "Bitcoin", 10, 0)])
    with pytest.raises(mts.ToolsDataError):
        mts._market_status()


def test_market_status_is_cached(fake_gecko, monkeypatch):
    calls = []
    real = mts._get
    monkeypatch.setattr(mts, "_get", lambda url, **kw: (calls.append(url), real(url, **kw))[1])
    mts.get_market_status()
    mts.get_market_status()
    assert len(calls) == 2  # /global + /coins/markets once, the second call is from the cache


def test_fng_arc_svg():
    svg = mts.fng_arc_svg(62)
    assert svg.count("<path") == 5 and ">62</text>" in svg and 'aria-label="Fear and Greed 62"' in svg
    assert "var(--gray-12)" in svg  # the number follows light/dark mode
    cx = float(re.search(r'<circle cx="([\d.]+)"', svg).group(1))
    assert cx > 60  # 62 is right of the middle
    assert float(re.search(r'<circle cx="([\d.]+)"', mts.fng_arc_svg(10)).group(1)) < 60
    assert ">100</text>" in mts.fng_arc_svg(150) and ">0</text>" in mts.fng_arc_svg(-5)  # clamped
