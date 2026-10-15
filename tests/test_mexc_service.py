"""MEXC portfolio (read-only): average cost from trades, the dashboard snapshot from MEXC-shaped demo data,
viewer gating, and that only signed GETs to read endpoints are ever sent, with no secret in any error."""

from pathlib import Path

import pytest
import requests

from app.services import mexc_service as m

FIXTURE = str(Path(__file__).parent / "fixtures" / "mexc_demo.json")


def _fresh_cache() -> dict:
    return {
        "raw_at": 0.0, "ok_at": 0.0, "balances": [], "orders": [], "error": "", "prices_at": 0.0, "tickers": {},
        "trades": {}, "coin_orders": {}, "open_orders_all": None,
    }


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(m, "_cache", _fresh_cache())
    monkeypatch.setattr(m.settings, "mexc_fixture_file", "")
    monkeypatch.setattr(m.settings, "mexc_api_key", "")
    monkeypatch.setattr(m.settings, "mexc_api_secret", "")
    monkeypatch.setattr(m.settings, "mexc_viewer_emails", "")
    monkeypatch.setattr(m, "get_costs", lambda user_id: {})


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setattr(m.settings, "mexc_fixture_file", FIXTURE)


def _t(side, qty, price, time, fee=0.0, fee_asset="USDT", symbol="ABCUSDT"):
    return {"symbol": symbol, "isBuyer": side == "buy", "qty": str(qty), "price": str(price),
            "quoteQty": str(qty * price), "commission": str(fee), "commissionAsset": fee_asset, "time": time}


def test_average_cost_buys_and_sells_at_the_running_average():
    got = m.average_cost([_t("buy", 10, 1.0, 1), _t("buy", 10, 2.0, 2), _t("sell", 5, 3.0, 3)])
    assert got["qty"] == pytest.approx(15) and got["avg_price"] == pytest.approx(1.5) and not got["short"]


def test_average_cost_fees_and_selling_more_than_the_history_shows():
    coin_fee = m.average_cost([_t("buy", 10, 2.0, 1, fee=0.5, fee_asset="ABC")])
    assert coin_fee["qty"] == pytest.approx(9.5) and coin_fee["avg_price"] == pytest.approx(20 / 9.5)
    usdt_fee = m.average_cost([_t("buy", 10, 2.0, 1, fee=1.0)])
    assert usdt_fee["avg_price"] == pytest.approx(2.1)
    assert m.average_cost([_t("buy", 1, 2.0, 1), _t("sell", 3, 2.0, 2)])["short"]


def test_snapshot_from_demo_data(demo):
    snap = m.portfolio()
    assert snap["ok"] and snap["demo"] and not snap["error"]
    by = {h["asset"]: h for h in snap["holdings"]}
    assert set(by) == {"USDT", "BTC", "ETH", "SUI", "SOL", "PEPE", "LINK"}  # DOGE + MX are dust
    assert snap["dust_count"] == 2
    assert by["SUI"]["amount"] == 820 and by["SUI"]["avg_price"] == pytest.approx(1.22) and by["SUI"]["avg_source"] == "trades"
    assert by["SUI"]["pnl"] == pytest.approx((1.0412 - 1.22) * 820)
    assert by["ETH"]["avg_price"] == pytest.approx(1850 / 0.499)
    assert by["LINK"]["avg_price"] == 0 and by["LINK"]["pnl"] == 0  # no trade history: cost unknown
    assert snap["without_cost"] == 1
    assert snap["total_value"] == pytest.approx(sum(h["value"] for h in snap["holdings"]) + snap["dust_value"])
    assert [h["asset"] for h in snap["holdings"]][0] == "BTC"  # biggest value first
    assert sum(h["allocation_pct"] for h in snap["holdings"]) == pytest.approx(100 - snap["dust_value"] / snap["total_value"] * 100)
    sol = next(o for o in snap["orders"] if o["asset"] == "SOL")
    assert sol["type_label"] == "Stop-limit" and sol["distance_pct"] == pytest.approx((150 / 168.40 - 1) * 100)
    assert snap["unmatched_locked_usdt"] == 0  # every open order came back in one call


def test_a_hand_typed_average_wins(demo, monkeypatch):
    monkeypatch.setattr(m, "get_costs", lambda user_id: {"LINK": 15.0, "SUI": 1.0})
    by = {h["asset"]: h for h in m.portfolio(user_id=1)["holdings"]}
    assert by["LINK"]["avg_source"] == "manual" and by["LINK"]["pnl"] == pytest.approx((17.85 - 15.0) * 40)
    assert by["SUI"]["avg_price"] == 1.0


def test_coin_orders(demo):
    assert [o["side"] for o in m.coin_orders("sui")] == ["SELL"]
    assert m.coin_orders("LINK") == []


def test_viewer_gate(monkeypatch):
    assert not m.can_view("me@example.com")  # empty list = nobody
    monkeypatch.setattr(m.settings, "mexc_viewer_emails", "Me@Example.com, other@example.com")
    assert m.can_view("me@example.com") and m.can_view(" OTHER@example.com ") and not m.can_view("x@example.com")


def test_only_read_endpoints_can_be_signed(monkeypatch):
    monkeypatch.setattr(m.settings, "mexc_api_key", "KEY123")
    monkeypatch.setattr(m.settings, "mexc_api_secret", "SECRET456")
    calls = []
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: calls.append(a) or None)
    for path in ("/api/v3/order", "/api/v3/capital/withdraw", "/api/v3/capital/transfer"):
        with pytest.raises(m.MexcError):
            m._get(path, {"symbol": "BTCUSDT"}, signed=True)
    assert calls == []


def test_errors_never_carry_the_secret_or_a_signed_url(monkeypatch):
    monkeypatch.setattr(m.settings, "mexc_api_key", "KEY123")
    monkeypatch.setattr(m.settings, "mexc_api_secret", "SECRET456")

    def boom(url, **kw):
        raise requests.ConnectionError(f"failed {url} {kw['headers']}")

    monkeypatch.setattr(m.requests, "get", boom)
    with pytest.raises(m.MexcError) as err:
        m._get("/api/v3/account", signed=True)
    text = f"{err.value!r} {err.value.__cause__!r} {err.value.__context__ if not err.value.__suppress_context__ else ''}"
    assert "SECRET456" not in text and "KEY123" not in text and "signature" not in text

    class Reply:
        status_code = 400

        def json(self):
            return {"code": 700006, "msg": "IP [1.2.3.4] not in the ip white list"}

    monkeypatch.setattr(m.requests, "get", lambda url, **kw: Reply())
    with pytest.raises(m.MexcError, match="not linked to the MEXC API key"):
        m._get("/api/v3/account", signed=True)


def test_a_failed_refresh_keeps_the_last_good_data(demo, monkeypatch):
    assert m.portfolio()["ok"]
    monkeypatch.setattr(m.settings, "mexc_fixture_file", "")
    monkeypatch.setattr(m.settings, "mexc_api_key", "KEY123")
    monkeypatch.setattr(m.settings, "mexc_api_secret", "SECRET456")
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("down")))
    snap = m.portfolio(force=True)
    assert snap["ok"] and "could not be reached" in snap["error"] and len(snap["holdings"]) == 7


def test_not_configured():
    snap = m.portfolio()
    assert not snap["configured"] and not snap["ok"]
