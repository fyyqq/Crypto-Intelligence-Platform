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


# ---- homepage Gainers & Losers card (price_snapshot_service.top_movers) --------------------

from app.services import price_snapshot_service as ps  # noqa: E402


def _chg(sym, rank, pct):
    return {"coin_id": rank, "symbol": sym, "name": sym, "rank": rank, "price_now": 1.0, "price_then": 1.0,
            "pct_change": pct, "volume_24h": 1e6, "then_at": None}


def test_top_movers_takes_five_each_from_the_top_100(monkeypatch):
    changes = [_chg(f"G{i}", i, i * 1.5) for i in range(1, 11)] + [_chg(f"L{i}", 10 + i, -i * 2.0) for i in range(1, 11)]
    changes += [_chg("OUT", 150, 99.0), _chg("ZERO", 5, 0.0)]  # rank 150 is another band; 0% is in neither list
    monkeypatch.setattr(ps, "window_status", lambda db, w: {"status": "ready", "hours_remaining": 0})
    monkeypatch.setattr(ps, "compute_changes", lambda db, w: changes)
    m = ps.top_movers(None)
    assert m["status"] == "ready"
    assert [c["symbol"] for c in m["gainers"]] == ["G10", "G9", "G8", "G7", "G6"]  # biggest first
    assert [c["symbol"] for c in m["losers"]] == ["L10", "L9", "L8", "L7", "L6"]  # most negative first
    assert "OUT" not in [c["symbol"] for c in m["gainers"]]


def test_top_movers_while_the_window_is_collecting(monkeypatch):
    monkeypatch.setattr(ps, "window_status", lambda db, w: {"status": "collecting", "hours_remaining": 7})
    monkeypatch.setattr(ps, "compute_changes", lambda db, w: pytest.fail("must not compute before the window is ready"))
    assert ps.top_movers(None) == {"status": "collecting", "hours_remaining": 7, "gainers": [], "losers": []}


# ---- with_stale: a failed refresh keeps the card filled -------------------------------------

def test_with_stale_serves_the_last_good_value_and_backs_off(monkeypatch):
    mts._last_good.clear()
    mts._failed_at.clear()
    calls = []
    state = {"fail": False}

    def fn():
        calls.append(1)
        if state["fail"]:
            raise mts.ToolsDataError("429")
        return {"v": len(calls)}

    assert mts.with_stale("k", fn) == {"v": 1}
    state["fail"] = True
    assert mts.with_stale("k", fn) == {"v": 1}  # refresh failed: the last good value
    assert len(calls) == 2
    assert mts.with_stale("k", fn) == {"v": 1} and len(calls) == 2  # inside the 2-minute back-off: no new call
    monkeypatch.setattr(mts.time, "time", lambda t=mts.time.time: t() + mts.RETRY_AFTER_FAILURE + 1)
    assert mts.with_stale("k", fn) == {"v": 1} and len(calls) == 3  # retried after the back-off, still failing
    state["fail"] = False
    monkeypatch.setattr(mts.time, "time", lambda t=mts.time.time: t() + 2 * mts.RETRY_AFTER_FAILURE + 2)
    assert mts.with_stale("k", fn) == {"v": 4}  # recovered


def test_with_stale_raises_when_there_is_nothing_to_fall_back_on():
    mts._last_good.clear()
    mts._failed_at.clear()

    def fn():
        raise mts.ToolsDataError("down")

    with pytest.raises(mts.ToolsDataError):
        mts.with_stale("never-worked", fn)


def test_with_stale_does_not_serve_a_value_older_than_six_hours(monkeypatch):
    mts._last_good.clear()
    mts._failed_at.clear()
    mts.with_stale("old", lambda: 1)
    monkeypatch.setattr(mts.time, "time", lambda t=mts.time.time: t() + mts.STALE_MAX_SECONDS + 5)

    def fn():
        raise mts.ToolsDataError("down")

    with pytest.raises(mts.ToolsDataError):
        mts.with_stale("old", fn)
