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
