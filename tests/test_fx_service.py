"""Live USD -> MYR rate for the portfolio hero card: three free sources, the freshest agreeing quote wins, a failing
source is skipped, a stale rate is kept for a while, and the card converts only its own money amounts."""

import time
import types
from pathlib import Path

import pytest
import requests

from app.services import fx_service as fx
from app.services import mexc_service as m

NOW = 1_800_000_000.0


class Reply:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def yahoo(rate, age=60):
    return Reply({"chart": {"result": [{"meta": {"regularMarketPrice": rate, "regularMarketTime": NOW - age}}]}})


def er_api(rate, age=20 * 3600):
    return Reply({"result": "success", "rates": {"MYR": rate}, "time_last_update_unix": NOW - age})


def ecb(rate, date="2027-01-14"):
    return Reply({"date": date, "rates": {"MYR": rate}})


@pytest.fixture
def feeds(monkeypatch):
    """Fake requests.get: replies come from `box.by_host` (an Exception instance is raised instead)."""
    box = types.SimpleNamespace(by_host={}, calls=[])
    monkeypatch.setattr(fx.time, "time", lambda: NOW)
    monkeypatch.setattr(fx, "_quotes", {})
    monkeypatch.setattr(fx, "_down_until", {})

    def fake_get(url, **kw):
        box.calls.append((url, kw))
        for host, reply in box.by_host.items():
            if host in url:
                if isinstance(reply, Exception):
                    raise reply
                return reply
        raise AssertionError("unexpected URL " + url)

    monkeypatch.setattr(fx.requests, "get", fake_get)
    return box


def test_the_freshest_quote_among_agreeing_sources_wins_and_calls_are_https_without_redirects(feeds):
    feeds.by_host = {"yahoo": yahoo(4.08, age=60), "er-api": er_api(4.0824), "frankfurter": ecb(4.0825)}
    got = fx.get_rate("MYR")
    assert got["rate"] == 4.08 and got["source"] == "Yahoo Finance" and got["live"] and got["note"] == "Yahoo Finance · live"
    assert len(feeds.calls) == 3
    for url, kw in feeds.calls:
        assert url.startswith("https://") and kw["allow_redirects"] is False and kw["timeout"] == fx._TIMEOUT


def test_a_quote_that_disagrees_with_the_others_is_dropped(feeds):
    feeds.by_host = {"yahoo": yahoo(40.8, age=30), "er-api": er_api(4.0824), "frankfurter": ecb(4.0825)}
    got = fx.get_rate("MYR")
    assert got["rate"] == pytest.approx(4.0825, abs=0.001) and got["source"] != "Yahoo Finance"  # the garbage 10x quote lost
    assert got["source"].endswith("(daily)")  # the freshest of the two agreeing daily references


def test_an_old_yahoo_quote_still_beats_the_daily_references_and_is_labelled_with_its_time(feeds):
    feeds.by_host = {"yahoo": yahoo(4.08, age=3300), "er-api": er_api(4.0824), "frankfurter": ecb(4.0825)}
    got = fx.get_rate("MYR")
    assert got["source"] == "Yahoo Finance" and not got["live"] and "quote of" in got["note"] and "KL" in got["note"]


def test_a_failing_source_is_skipped_for_a_while_and_the_rest_still_answer(feeds):
    feeds.by_host = {"yahoo": requests.ConnectionError("blocked"), "er-api": er_api(4.0824), "frankfurter": ecb(4.0825)}
    assert fx.get_rate("MYR")["rate"] == 4.0824 or fx.get_rate("MYR")["rate"] == 4.0825
    calls = len(feeds.calls)
    fx.get_rate("MYR")
    assert len(feeds.calls) == calls  # cached (TTL) and the dead source is not retried for DOWN_SECONDS
    assert fx._down_until["yahoo"] == NOW + fx.DOWN_SECONDS


def test_sources_are_cached_per_ttl_so_open_tabs_do_not_add_calls(feeds, monkeypatch):
    feeds.by_host = {"yahoo": yahoo(4.08), "er-api": er_api(4.0824), "frankfurter": ecb(4.0825)}
    fx.get_rate("MYR")
    assert len(feeds.calls) == 3
    for _ in range(10):
        fx.get_rate("MYR")
    assert len(feeds.calls) == 3
    monkeypatch.setattr(fx.time, "time", lambda: NOW + fx.YAHOO_TTL + 1)  # a minute later only Yahoo is refreshed
    fx.get_rate("MYR")
    assert [u for u, _ in feeds.calls[3:]] and all("yahoo" in u for u, _ in feeds.calls[3:])


def test_when_every_source_fails_the_last_rate_is_kept_until_it_is_too_old(feeds, monkeypatch):
    feeds.by_host = {"yahoo": yahoo(4.08), "er-api": er_api(4.0824), "frankfurter": ecb(4.0825)}
    first = fx.get_rate("MYR")
    for host in list(feeds.by_host):
        feeds.by_host[host] = requests.ConnectionError("down")
    monkeypatch.setattr(fx.time, "time", lambda: NOW + 7200)
    kept = fx.get_rate("MYR")
    assert kept and kept["rate"] == first["rate"] and not kept["live"]
    monkeypatch.setattr(fx.time, "time", lambda: NOW + fx.MAX_AGE_SECONDS + 7200)
    assert fx.get_rate("MYR") is None  # nothing usable: the page stays in USD


def test_garbage_input_and_usd_need_no_network(feeds):
    assert fx.get_rate("not a code") is None and fx.get_rate("") is None
    assert fx.get_rate("USD")["rate"] == 1.0 and feeds.calls == []


def test_amounts_are_formatted_per_currency():
    assert fx.format_amount(1234.5, "USD") == "$1,234.50" and fx.format_amount(1234.5, "MYR") == "RM1,234.50"
    assert fx.format_amount(-5, "MYR") == "-RM5.00" and fx.format_amount(5, "MYR", signed=True) == "+RM5.00"
    assert fx.format_amount(-5, "USD", signed=True) == "-$5.00" and fx.format_amount(0, "MYR", signed=True) == "RM0.00"


# ------------------------------------------------------------------------------------------- the hero card


def _state_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent / "frontend"))
    from frontend.state import portfolio_state

    return portfolio_state


@pytest.fixture
def demo_snapshot(monkeypatch):
    monkeypatch.setattr(m.settings, "mexc_fixture_file", str(Path(__file__).parent / "fixtures" / "mexc_demo.json"))
    monkeypatch.setattr(m, "_cache", {
        "raw_at": 0.0, "ok_at": 0.0, "balances": [], "orders": [], "error": "", "prices_at": 0.0, "tickers": {},
        "trades": {}, "coin_orders": {}, "open_orders_all": None,
    })
    monkeypatch.setattr(m, "_rate", {"until": 0.0, "strikes": 0})
    monkeypatch.setattr(m, "get_costs", lambda user_id: {})
    return m.portfolio(1)


def test_myr_converts_only_the_cards_money_amounts_at_the_live_rate(monkeypatch, demo_snapshot):
    ps = _state_module(monkeypatch)
    usd = ps._summary_view(demo_snapshot)
    myr = ps._summary_view(demo_snapshot, "MYR", 4.08)
    assert usd["total"] == "$8,249.22" and usd["change"] == "+$47.89" and usd["pnl"] == "+$125.57"
    assert myr["total"] == fx.format_amount(demo_snapshot["total_value"] * 4.08, "MYR") == "RM33,656.82"
    assert myr["change"].startswith("+RM") and myr["pnl"].startswith("+RM") and myr["cash"].startswith("RM") and myr["in_orders"].startswith("RM")
    dust = demo_snapshot["dust_value"]
    assert f"({fx.format_amount(dust * 4.08, 'MYR')})" in myr["dust"] and f"({fx.format_amount(dust)})" in usd["dust"]  # the small-balances note converts too
    for key in ("change_pct", "pnl_pct", "cash_pct", "orders_count", "coins", "cost_note", "change_color", "unmatched"):
        assert myr[key] == usd[key], key  # percentages, counts and notes do not change with the currency
    assert myr["cost"] == usd["cost"] and "RM" not in "".join(v for k, v in myr.items() if k in ("cost", "unmatched", "pnl_pct"))


def test_the_card_falls_back_to_usd_with_a_message_when_there_is_no_rate(monkeypatch):
    ps = _state_module(monkeypatch)
    monkeypatch.setattr(fx, "cached", lambda quote: None)
    s = types.SimpleNamespace(pf_currency="MYR", pf_fx_note="old", pf_fx_error="")
    assert ps.PortfolioState._card_currency(s) == ("USD", 1.0)
    assert s.pf_currency == "USD" and s.pf_fx_note == "" and "unavailable" in s.pf_fx_error
    monkeypatch.setattr(fx, "cached", lambda quote: {"rate": 4.2, "note": "Yahoo Finance · live"})
    s = types.SimpleNamespace(pf_currency="MYR", pf_fx_note="", pf_fx_error="x")
    assert ps.PortfolioState._card_currency(s) == ("MYR", 4.2)
    assert s.pf_fx_note == "1 USD = 4.2000 MYR · Yahoo Finance · live" and s.pf_fx_error == ""
    s = types.SimpleNamespace(pf_currency="USD", pf_fx_note="stale", pf_fx_error="stale")
    assert ps.PortfolioState._card_currency(s) == ("USD", 1.0) and s.pf_fx_note == s.pf_fx_error == ""


def test_logout_returns_the_card_to_myr_the_default_and_drops_the_raw_snapshot(monkeypatch):
    ps = _state_module(monkeypatch)
    names = {n for n in ps.PortfolioState.get_fields() if n.startswith(ps._PORTFOLIO_VAR_PREFIXES)}
    assert {"pf_currency", "pf_fx_note", "pf_fx_error"} <= names
    s = types.SimpleNamespace(**{n: "x" for n in names}, _pf_trades_all=[1], _pf_snap={"total_value": 1})
    ps.PortfolioState._clear_portfolio(s)
    assert s.pf_currency == "MYR" and s._pf_snap == {} and s.pf_fx_note == ""  # MYR is the default currency
