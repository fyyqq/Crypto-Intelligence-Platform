"""Portfolio charts: the balance history the server records every 5 minutes (only fresh, real readings), its
24H / 7D / 1M / Full ranges, and the coin page mini chart's candles and lines (avg buy blue, orders red)."""

import json
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.services import mexc_service as m
from app.services import portfolio_history_service as h

FIXTURE = str(Path(__file__).parent / "fixtures" / "mexc_demo.json")
NOW = 1_800_000_000.0


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(h, "SessionLocal", sessionmaker(bind=engine, autoflush=False))
    monkeypatch.setattr(h, "_cache", {})
    yield
    engine.dispose()


def _at(ts):
    return datetime.fromtimestamp(ts, timezone.utc)


def test_series_ranges_keep_the_last_reading_per_bucket(db):
    for i in range(0, 40 * 86400, 300):  # 40 days, every 5 minutes, value = minutes since start
        h.record(i / 60, at=_at(NOW - 40 * 86400 + i))
    day = h.series("24h", now=NOW)
    assert len(day) == 288 and day[-1][1] == pytest.approx((40 * 86400 - 300) / 60)  # every 5-min reading
    week = h.series("7d", now=NOW)
    assert len(week) in (336, 337) and all(b[0] - a[0] == pytest.approx(1800) for a, b in zip(week[1:], week[2:]))
    month = h.series("1m", now=NOW)
    assert 719 <= len(month) <= 721
    full = h.series("full", now=NOW)
    assert len(full) <= h.MAX_POINTS + 1 and full[0][0] == pytest.approx(NOW - 40 * 86400, abs=6000)
    assert full[-1][1] == day[-1][1]  # every range ends on the latest reading
    assert h.series("5y", now=NOW) == []
    assert h.first_recorded() == pytest.approx(NOW - 40 * 86400)


def test_reads_are_cached_and_a_new_reading_clears_the_cache(db):
    h.record(100.0, at=_at(NOW - 600))
    assert h.series("24h", now=NOW) == [(pytest.approx(NOW - 600), 100.0)]
    h._cache["24h"] = (NOW, [(1.0, 1.0)])
    assert h.series("24h", now=NOW + 10) == [(1.0, 1.0)]  # served from the 60 s cache
    h.record(200.0, at=_at(NOW - 300))
    assert [v for _, v in h.series("24h", now=NOW + 10)] == [100.0, 200.0]


def test_only_fresh_real_readings_are_recorded(db, monkeypatch):
    snaps = iter([
        {"ok": True, "error": "", "updated_at": NOW, "total_value": 123.0, "demo": False},  # saved
        {"ok": True, "error": "", "updated_at": NOW, "total_value": 999.0, "demo": True},  # demo: skipped
        {"ok": True, "error": "MEXC could not be reached.", "updated_at": NOW - 600, "total_value": 5.0, "demo": False},  # stale
        {"ok": False, "error": "x", "updated_at": 0, "total_value": 0, "demo": False},  # nothing
    ])
    monkeypatch.setattr(m, "is_configured", lambda: True)
    monkeypatch.setattr(m, "portfolio", lambda user_id: next(snaps))
    monkeypatch.setattr(h.time, "time", lambda: NOW)
    assert [h.record_from_mexc() for _ in range(4)] == [True, False, False, False]
    monkeypatch.setattr(h, "_cache", {})
    assert [v for _, v in h.series("full", now=NOW)] == [123.0]
    monkeypatch.setattr(m, "is_configured", lambda: False)
    assert h.record_from_mexc() is False


# ------------------------------------------------------------------------------------------------- klines


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setattr(m.settings, "mexc_fixture_file", FIXTURE)
    monkeypatch.setattr(m, "_cache", {
        "raw_at": 0.0, "ok_at": 0.0, "balances": [], "orders": [], "error": "", "prices_at": 0.0, "tickers": {},
        "trades": {}, "coin_orders": {}, "open_orders_all": None,
    })
    monkeypatch.setattr(m, "_rate", {"until": 0.0, "strikes": 0})
    monkeypatch.setattr(m, "get_costs", lambda user_id: {})


def test_klines_are_parsed_oldest_first_and_cached(demo, monkeypatch):
    rows = m.klines("sui")
    assert len(rows) == 168 and rows == sorted(rows) and all(len(r) == 5 and r[4] > 0 for r in rows)
    assert rows[0][0] == json.loads(Path(FIXTURE).read_text())["klines"]["SUIUSDT"][0][0] // 1000  # seconds
    monkeypatch.setattr(m, "_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("cached")))
    assert m.klines("SUI") == rows  # second read: from the 60 s cache, no request


def test_klines_unknown_pair_bad_input_and_errors_give_nothing(demo, monkeypatch):
    assert m.klines("LINK") == []  # no candles in the demo data
    assert m.klines("") == [] and m.klines("bad/sym") == [] and m.klines("SUI", "7h") == []  # unknown interval

    def down(*a, **k):
        raise m.MexcError("MEXC could not be reached.")

    m.klines("SUI")
    m._cache["klines"]["SUIUSDT:60m"]["at"] = 0  # expired
    monkeypatch.setattr(m, "_get", down)
    assert len(m.klines("SUI")) == 168  # the last candles are kept on a hiccup


# ------------------------------------------------------------------------------------------ state helpers


def _ps(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent / "frontend"))
    from frontend.state import portfolio_state

    return portfolio_state


def test_chart_lines_avg_blue_limit_green_stop_red_at_its_trigger(monkeypatch, demo):
    ps = _ps(monkeypatch)
    snap = m.portfolio(1)
    held = next(x for x in snap["holdings"] if x["asset"] == "SOL")
    lines = ps._chart_lines(held, m.coin_orders("SOL"))
    assert lines[0] == {"p": pytest.approx(175.0), "c": ps._LINE_AVG, "t": "Avg buy", "s": 0}
    assert lines[1] == {"p": 150.0, "c": ps._LINE_STOP, "t": "Sell Stop-limit trigger", "s": 2}  # stop-loss: red, dashed
    sui = ps._chart_lines(next(x for x in snap["holdings"] if x["asset"] == "SUI"), m.coin_orders("SUI"))
    assert [(l["t"], l["p"], l["c"], l["s"]) for l in sui] == [("Avg buy", pytest.approx(1.22), ps._LINE_AVG, 0), ("Sell Limit", 1.35, ps._LINE_LIMIT, 0)]
    assert (ps._LINE_AVG, ps._LINE_LIMIT, ps._LINE_STOP) == ("#2962FF", "#22C55E", "#EF4444")  # blue, green, red
    assert ps._chart_lines(None, []) == [] and ps._chart_lines({"avg_price": 0}, []) == []


def test_hist_view_adds_the_live_total_and_the_range_figures(monkeypatch):
    ps = _ps(monkeypatch)
    rows = [(NOW - 3600, 100.0), (NOW - 1800, 150.0), (NOW - 600, 80.0)]
    data, info = ps._hist_view(rows, live_total=120.0, now=NOW)
    assert [p["v"] for p in data] == [100.0, 150.0, 80.0, 120.0] and all(isinstance(p["t"], str) for p in data)
    assert info["value"] == "$120.00" and info["change"] == "+$20.00" and info["change_pct"] == "+20.00%"
    assert info["high"] == "$150.00" and info["low"] == "$80.00"
    assert ps._hist_view([], 0.0, now=NOW) == ([], {})
    data, _ = ps._hist_view([(NOW - 10, 5.0)], live_total=6.0, now=NOW)
    assert [p["v"] for p in data] == [5.0]  # a reading 10 s old is the live value already


def test_logout_clears_the_chart_state(monkeypatch):
    ps = _ps(monkeypatch)
    names = {n for n in ps.PortfolioState.get_fields() if n.startswith(ps._PORTFOLIO_VAR_PREFIXES)}
    assert {"pf_hist_card", "pf_hist_points", "pf_hist_info", "coin_mexc_candles", "coin_mexc_lines", "coin_mexc_has_lines", "coin_mexc_chart_mode", "coin_mexc_interval"} <= names
    s = types.SimpleNamespace(**{n: "x" for n in names}, _pf_trades_all=[1], _pf_snap={"a": 1})
    ps.PortfolioState._clear_portfolio(s)
    assert s.pf_hist_card == [] and s.coin_mexc_lines == "[]" and s.coin_mexc_candles == "[]" and s.pf_hist_range == "full"
    assert s.coin_mexc_has_lines is False and s.coin_mexc_chart_mode == "lines" and s.coin_mexc_interval == "60m"


def test_apply_runs_to_the_end_on_a_real_snapshot_in_both_currencies(monkeypatch, demo):
    """Regression: _apply once lost a local variable and stopped before the allocation ring, so the ring and its
    legend were empty and every refresh logged an error. Run the whole method on the demo snapshot."""
    ps = _ps(monkeypatch)
    from app.services import fx_service

    monkeypatch.setattr(fx_service, "cached", lambda quote: {"rate": 4.0, "note": "test"})
    for currency in ("USD", "MYR"):
        s = types.SimpleNamespace(pf_trade_page=1, pf_currency=currency, pf_fx_note="", pf_fx_error="")
        for name in ("_card_currency", "_show_trades_page"):
            setattr(s, name, types.MethodType(getattr(ps.PortfolioState, name), s))
        ps.PortfolioState._apply(s, m.portfolio(1))
        assert s.pf_loaded and s.pf_ring.startswith("conic-gradient(var(--blue-9)") and len(s.pf_alloc) == 7
        assert s.pf_alloc[0]["label"] == "BTC" and len(s.pf_holdings) == 7 and len(s.pf_trades) == 5
        assert s.pf_summary["total"] == ("$8,249.22" if currency == "USD" else "RM32,996.88")


def test_the_balance_chart_follows_the_myr_usd_choice(monkeypatch):
    """The card and the popup convert every reading with the same live rate as the Total balance card; switching
    back to USD restores the dollar figures from the readings already held (no database read)."""
    ps = _ps(monkeypatch)
    from app.services import fx_service

    monkeypatch.setattr(fx_service, "cached", lambda quote: {"rate": 4.0, "note": "test"})
    rows = [(NOW - 3600, 100.0), (NOW - 1800, 150.0)]
    data, info = ps._hist_view(rows, live_total=120.0, now=NOW, currency="MYR", rate=4.0)
    assert [p["v"] for p in data] == [400.0, 600.0, 480.0]
    assert (info["value"], info["change"], info["high"], info["low"]) == ("RM480.00", "+RM80.00", "RM600.00", "RM400.00")
    assert info["change_pct"] == "+20.00%"  # a percentage does not depend on the currency

    s = types.SimpleNamespace(pf_currency="USD", _pf_snap={"ok": True, "total_value": 120.0}, _pf_hist_card_rows=[], _pf_hist_popup_rows=[],
                              pf_hist_card=[], pf_hist_card_info={}, pf_hist_points=[], pf_hist_info={}, pf_hist_since="")
    for name in ("_chart_currency", "_live_total"):
        setattr(s, name, types.MethodType(getattr(ps.PortfolioState, name), s))
    import time as _time

    rows = [(_time.time() - 3600, 100.0), (_time.time() - 1800, 150.0)]  # _apply_history uses the real clock
    ps.PortfolioState._apply_history(s, rows, rows)
    assert s.pf_hist_card_info["value"] == "$120.00" and s.pf_hist_info["high"] == "$150.00"
    s.pf_currency = "MYR"
    ps.PortfolioState._apply_history(s, None, None)  # what the MYR button does: redraw from the held readings
    assert s.pf_hist_card_info["value"] == "RM480.00" and s.pf_hist_points[-1]["v"] == 480.0 and s.pf_hist_info["low"] == "RM400.00"
    monkeypatch.setattr(fx_service, "cached", lambda quote: None)  # no rate: the chart stays in USD
    ps.PortfolioState._apply_history(s, None, None)
    assert s.pf_hist_card_info["value"] == "$120.00"


def test_klines_are_cached_per_interval_and_the_chart_intervals_are_mexc_ones(monkeypatch, demo):
    ps = _ps(monkeypatch)
    assert {iv for _, iv in ps.CHART_INTERVALS} <= m.KLINE_INTERVALS
    calls = []
    real = m._get
    monkeypatch.setattr(m, "_get", lambda path, params=None, **k: calls.append(params.get("interval")) or real(path, params, **k))
    m.klines("SUI", "60m"), m.klines("SUI", "60m"), m.klines("SUI", "4h"), m.klines("SUI", "4h")
    assert calls == ["60m", "4h"]  # one request per pair + interval, then the 60 s cache


def test_the_lines_view_is_offered_only_with_lines_and_candles(monkeypatch, demo):
    ps = _ps(monkeypatch)
    snap = m.portfolio(1)
    s = types.SimpleNamespace(_chart_currency=lambda: ("USD", 1.0))
    ps.PortfolioState._apply_coin(s, "SUI", snap, m.coin_orders("SUI"), m.klines("SUI"))
    assert s.coin_mexc_has_lines is True and json.loads(s.coin_mexc_lines)[1]["c"] == ps._LINE_LIMIT
    ps.PortfolioState._apply_coin(s, "SUI", snap, m.coin_orders("SUI"), [])  # no MEXC candles: TradingView stays
    assert s.coin_mexc_has_lines is False
    ps.PortfolioState._apply_coin(s, "DOGE", snap, [], m.klines("SUI"))  # candles but nothing of yours: no lines view
    assert s.coin_mexc_has_lines is False


def test_the_coin_page_holding_is_shown_in_the_portfolio_currency_myr_by_default(monkeypatch, demo):
    ps = _ps(monkeypatch)
    snap = m.portfolio(1)
    held = next(h for h in snap["holdings"] if h["asset"] == "SUI")
    usd = types.SimpleNamespace(_chart_currency=lambda: ("USD", 1.0))
    myr = types.SimpleNamespace(_chart_currency=lambda: ("MYR", 4.0))
    ps.PortfolioState._apply_coin(usd, "SUI", snap, [], [])
    ps.PortfolioState._apply_coin(myr, "SUI", snap, [], [])
    assert usd.coin_mexc_holding["value"] == f"${held['value']:,.2f}"
    assert myr.coin_mexc_holding["value"] == f"RM{held['value'] * 4:,.2f}"  # the wallet value in ringgit
    assert myr.coin_mexc_holding["avg"] == usd.coin_mexc_holding["avg"]  # a coin's price stays in USD
    if held["avg_price"] > 0:
        assert myr.coin_mexc_holding["pnl"].startswith(("RM", "-RM", "+RM"))
    assert ps.PortfolioState.get_fields()["pf_currency"].default == "MYR"
