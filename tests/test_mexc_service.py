"""MEXC portfolio (read-only): average cost from trades, the dashboard snapshot from MEXC-shaped demo data,
viewer gating, and that only signed GETs to read endpoints are ever sent, with no secret in any error."""

import logging
import types
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
    monkeypatch.setattr(m, "_rate", {"until": 0.0, "strikes": 0})
    monkeypatch.setattr(m, "_deposits", {})


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


# ------------------------------------------------------------------------------------------- hardening


class Reply:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body if body is not None else {}, headers or {}

    def json(self):
        return self._body


@pytest.fixture
def live(monkeypatch):
    """A configured key and a recording stand-in for requests.get (replies come from `replies`)."""
    monkeypatch.setattr(m.settings, "mexc_api_key", "KEY123")
    monkeypatch.setattr(m.settings, "mexc_api_secret", "SECRET456")
    box = types.SimpleNamespace(calls=[], replies=[])

    def fake_get(url, **kw):
        box.calls.append((url, kw))
        return box.replies.pop(0) if len(box.replies) > 1 else box.replies[0]

    monkeypatch.setattr(m.requests, "get", fake_get)
    return box


def test_requests_use_https_never_follow_redirects_and_time_out(live):
    live.replies = [Reply(body={"balances": []})]
    m._get("/api/v3/account", signed=True)
    m._get("/api/v3/ticker/24hr")
    for url, kw in live.calls:
        assert url.startswith("https://api.mexc.com/")
        assert kw["allow_redirects"] is False and kw["timeout"] == m._TIMEOUT


def test_an_unknown_mexc_error_is_generic_on_the_page_and_logged_in_full(live, caplog):
    live.replies = [Reply(400, {"code": 99999, "msg": "IP [203.0.113.7] is weird"})]
    with caplog.at_level(logging.WARNING, logger=m._log.name):
        with pytest.raises(m.MexcError) as err:
            m._get("/api/v3/account", signed=True)
    assert "203.0.113.7" not in str(err.value) and "99999" in str(err.value) and "server log" in str(err.value)
    assert "203.0.113.7" in caplog.text and "99999" in caplog.text  # the detail is kept, server side only
    live.replies = [Reply(400, {"code": 700006, "msg": "IP [203.0.113.7] not in the ip white list"})]
    with pytest.raises(m.MexcError, match="not linked to the MEXC API key") as err:
        m._get("/api/v3/account", signed=True)
    assert "203.0.113.7" not in str(err.value)


def test_a_429_pauses_every_request_and_the_forced_refresh_cannot_skip_it(live, monkeypatch, caplog):
    now = [1000.0]
    monkeypatch.setattr(m.time, "time", lambda: now[0])
    live.replies = [Reply(429, headers={})]
    with caplog.at_level(logging.WARNING, logger=m._log.name):
        with pytest.raises(m.MexcRateLimited):
            m._get("/api/v3/account", signed=True)
    assert "rate limit" in caplog.text and len(live.calls) == 1
    assert m._rate["until"] == pytest.approx(1000.0 + m.ACCOUNT_TTL)
    for _ in range(3):  # paused: nothing is sent, however often it is asked (refresh icon = force=True)
        with pytest.raises(m.MexcRateLimited):
            m._get("/api/v3/account", signed=True)
        m._refresh(force=True)
    assert len(live.calls) == 1 and "rate limit" in m._cache["error"]


def test_the_429_pause_grows_honours_retry_after_and_resets_after_a_good_reply(live, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(m.time, "time", lambda: now[0])
    waits = []
    for _ in range(3):  # strikes 1..3: 20 s, 40 s, 80 s
        live.replies = [Reply(429)]
        with pytest.raises(m.MexcRateLimited):
            m._get("/api/v3/account", signed=True)
        waits.append(m._rate["until"] - now[0])
        now[0] = m._rate["until"] + 0.1
    assert waits == pytest.approx([m.ACCOUNT_TTL, m.ACCOUNT_TTL * 2, m.ACCOUNT_TTL * 4])
    live.replies = [Reply(429, headers={"Retry-After": "250"})]
    with pytest.raises(m.MexcRateLimited):
        m._get("/api/v3/account", signed=True)
    assert m._rate["until"] - now[0] == pytest.approx(250)  # MEXC's own wait is longer than ours
    now[0] = m._rate["until"] + 0.1
    live.replies = [Reply(200, {"balances": []})]
    assert m._get("/api/v3/account", signed=True) == {"balances": []}
    assert m._rate["strikes"] == 0
    live.replies = [Reply(429)]
    with pytest.raises(m.MexcRateLimited):
        m._get("/api/v3/account", signed=True)
    assert m._rate["until"] - now[0] == pytest.approx(m.ACCOUNT_TTL)  # back to the short pause


def test_a_429_in_the_body_counts_too_and_the_page_keeps_its_last_data(demo, monkeypatch):
    assert m.portfolio()["ok"]
    monkeypatch.setattr(m.settings, "mexc_fixture_file", "")
    monkeypatch.setattr(m.settings, "mexc_api_key", "KEY123")
    monkeypatch.setattr(m.settings, "mexc_api_secret", "SECRET456")
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: Reply(200, {"code": 429, "msg": "Too many requests"}))
    snap = m.portfolio(force=True)
    assert snap["ok"] and len(snap["holdings"]) == 7 and "rate limit" in snap["error"]


# ---------------------------------------------------------------- page state (what the browser receives)


def _state_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent / "frontend"))  # the Reflex app root
    from frontend.state import portfolio_state

    return portfolio_state


def test_the_page_data_has_no_order_id_and_only_display_strings(monkeypatch, demo):
    ps = _state_module(monkeypatch)
    snap = m.portfolio()
    assert snap["orders"] and "order_id" in snap["orders"][0]  # the service keeps it, server side
    for order in snap["orders"]:
        view = ps._order_view(order)
        assert "id" not in view and "order_id" not in view and order["order_id"] not in view.values()
        assert all(isinstance(v, str) for v in view.values())


def test_clearing_resets_every_portfolio_var_to_its_default(monkeypatch):
    ps = _state_module(monkeypatch)
    import dataclasses

    fields = {n: f for n, f in ps.PortfolioState.get_fields().items() if n.startswith(ps._PORTFOLIO_VAR_PREFIXES)}
    assert {"pf_summary", "pf_holdings", "pf_orders", "pf_trades", "coin_mexc_holding", "coin_mexc_orders", "coin_mexc_error"} <= set(fields)
    stand_in = types.SimpleNamespace(**{n: "STALE-BALANCE" for n in fields}, _pf_trades_all=[{"asset": "STALE"}])
    ps.PortfolioState._clear_portfolio(stand_in)
    assert stand_in._pf_trades_all == []  # the backend-only rows are emptied too
    for name, field in fields.items():
        factory = field.default_factory
        expected = factory() if factory is not None and factory is not dataclasses.MISSING else field.default
        if name == "pf_loaded":
            expected = False
        assert getattr(stand_in, name) == expected, name
    ps.PortfolioState._clear_portfolio(stand_in, loaded=True)
    assert stand_in.pf_loaded is True and stand_in.pf_allowed is False and stand_in.pf_summary == {}


def test_recent_fills_are_shown_five_per_page_and_the_page_is_kept_and_clamped(monkeypatch):
    ps = _state_module(monkeypatch)
    rows = [{"asset": f"T{i}"} for i in range(12)]
    s = types.SimpleNamespace(_pf_trades_all=rows, pf_trade_page=1, pf_trades=[], pf_trade_pages=1, pf_trade_total=0)
    ps.PortfolioState._show_trades_page(s)
    assert [r["asset"] for r in s.pf_trades] == ["T0", "T1", "T2", "T3", "T4"] and (s.pf_trade_pages, s.pf_trade_total) == (3, 12)
    s.pf_trade_page = 3
    ps.PortfolioState._show_trades_page(s)
    assert [r["asset"] for r in s.pf_trades] == ["T10", "T11"]  # the last page holds the remainder
    s.pf_trade_page = 9  # out of range -> the last page
    ps.PortfolioState._show_trades_page(s)
    assert s.pf_trade_page == 3
    s._pf_trades_all = rows[:3]  # the list shrank on a refresh: back to page 1 of 1
    ps.PortfolioState._show_trades_page(s)
    assert s.pf_trade_page == 1 and len(s.pf_trades) == 3 and s.pf_trade_pages == 1
    s._pf_trades_all = []
    ps.PortfolioState._show_trades_page(s)
    assert s.pf_trades == [] and s.pf_trade_pages == 1


def test_held_assets_lists_only_priced_non_stable_coins_worth_a_dollar(demo):
    held = m.held_assets()
    assert {"BTC", "ETH", "SUI", "SOL", "PEPE", "LINK"} <= set(held) and "USDT" not in held
    assert "MX" not in held  # 0.03 MX is dust
    assert all(price > 0 for price in held.values())


def test_held_assets_is_empty_when_mexc_is_not_connected_or_fails(monkeypatch):
    assert m.held_assets() == {}  # not configured
    monkeypatch.setattr(m.settings, "mexc_api_key", "k")
    monkeypatch.setattr(m.settings, "mexc_api_secret", "s")
    monkeypatch.setattr(m, "_refresh", lambda force=False: (_ for _ in ()).throw(RuntimeError("boom")))
    assert m.held_assets() == {}


def test_solana_deposit_address_is_the_solana_network_one(demo):
    got = m.deposit_address("SOL")  # the demo lists a BEP20 and a Solana address: only the Solana one is shown
    assert got["address"] == "DemoSo1anaDepositAddressForLocalTestOnly1111" and got["network"] == "Solana(SOL)" and not got["error"]
    assert m.portfolio()["deposit_sol"]["address"] == got["address"]  # the dashboard snapshot carries it


def test_deposit_address_refusal_is_an_error_text_not_an_exception_and_is_cached(monkeypatch):
    calls = []

    def refuse(path, params=None, signed=False):
        calls.append(path)
        raise m.MexcError("MEXC rejected the request")

    monkeypatch.setattr(m, "_get", refuse)
    first = m.deposit_address("SOL")
    assert first["address"] == "" and "could not be read" in first["error"] and "MEXC rejected" in first["error"]
    m.deposit_address("SOL")
    assert calls == ["/api/v3/capital/deposit/address"]  # asked once; the refusal is remembered for DEPOSIT_RETRY


def test_deposit_address_when_mexc_lists_no_solana_address(monkeypatch):
    monkeypatch.setattr(m, "_get", lambda path, params=None, signed=False: [{"coin": "SOL", "network": "BNB Smart Chain(BEP20)", "address": "0xabc", "memo": None}])
    got = m.deposit_address("SOL")
    assert got["address"] == "" and "no SOL deposit address" in got["error"]


def test_the_deposit_address_call_is_a_signed_get_to_a_read_path_only():
    assert "/api/v3/capital/deposit/address" in m._READ_PATHS
    src = Path(m.__file__).read_text()
    assert "requests.post" not in src and "requests.put" not in src and "requests.delete" not in src  # nothing can write


def test_deposit_address_is_re_read_every_minute_and_a_change_is_flagged(monkeypatch):
    answers = [[{"network": "Solana(SOL)", "address": "AddrOne"}], [{"network": "Solana(SOL)", "address": "AddrOne"}], [{"network": "Solana(SOL)", "address": "AddrTwo"}]]
    calls = []

    def fake(path, params=None, signed=False):
        calls.append(1)
        return answers[len(calls) - 1]

    now = [1000.0]
    monkeypatch.setattr(m.time, "time", lambda: now[0])
    monkeypatch.setattr(m, "_get", fake)
    first = m.deposit_address("SOL")
    assert first["address"] == "AddrOne" and not first["changed"]
    now[0] += 30
    assert m.deposit_address("SOL")["address"] == "AddrOne" and len(calls) == 1  # inside DEPOSIT_TTL: no new call
    now[0] += 31
    again = m.deposit_address("SOL")  # a minute later: read again, same address
    assert len(calls) == 2 and again["address"] == "AddrOne" and not again["changed"]
    now[0] += 5
    forced = m.deposit_address("SOL", force=True)  # the refresh icon reads at once
    assert len(calls) == 3 and forced["address"] == "AddrTwo" and forced["changed"] and forced["changed_at"] == now[0]


def test_a_refused_re_read_keeps_the_last_good_address_with_the_error(monkeypatch):
    state = {"fail": False}

    def fake(path, params=None, signed=False):
        if state["fail"]:
            raise m.MexcError("MEXC rate limit reached.")
        return [{"network": "Solana(SOL)", "address": "AddrOne"}]

    monkeypatch.setattr(m, "_get", fake)
    assert m.deposit_address("SOL")["address"] == "AddrOne"
    state["fail"] = True
    got = m.deposit_address("SOL", force=True)
    assert got["address"] == "AddrOne" and "could not be read" in got["error"]


def test_a_permission_refusal_on_the_deposit_address_names_the_deposit_permission(monkeypatch):
    def refuse(path, params=None, signed=False):
        raise m.MexcError(m._ERRORS[700007])

    monkeypatch.setattr(m, "_get", refuse)
    err = m.deposit_address("SOL")["error"]
    assert "Deposit/Withdrawal Details" in err and "never Withdraw" in err and "View Account Details" not in err


def test_coin_trades_for_a_held_coin_and_a_coin_traded_before(demo):
    sui = m.coin_trades("sui")  # held: every fill, oldest first (the demo's SUI: one buy, one sell)
    assert [r[1] for r in sui] == ["B", "S"]
    assert sui == sorted(sui, key=lambda r: r[0]) and all(len(r) == 4 and r[0] > 1_000_000_000 and r[2] > 0 and r[3] > 0 for r in sui)
    ada = m.coin_trades("ADA")  # not held, but traded before: still has its B and S
    assert [r[1] for r in ada] == ["B", "S"]
    assert m.portfolio()["ok"] and "ADAUSDT" not in m._cache["trades"]  # the traded-before coin does not leak into the Recent fills table


def test_coin_trades_nothing_to_show_cases(demo, monkeypatch):
    assert m.coin_trades("DOGE") == []  # no trades in the demo data
    assert m.coin_trades("") == [] and m.coin_trades("bad/sym") == [] and m.coin_trades("USDT") == []


def test_coin_trades_a_refusal_gives_nothing_and_is_not_asked_again_at_once(monkeypatch):
    monkeypatch.setattr(m.settings, "mexc_api_key", "k")
    monkeypatch.setattr(m.settings, "mexc_api_secret", "s")
    calls = []

    def refuse(path, params=None, signed=False):
        calls.append(path)
        raise m.MexcError("Invalid symbol")

    monkeypatch.setattr(m, "_get", refuse)
    assert m.coin_trades("NOPE") == [] and m.coin_trades("NOPE") == []
    assert len(calls) == 1  # remembered for COIN_TRADES_NEGATIVE_TTL
