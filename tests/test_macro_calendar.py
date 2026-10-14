"""CPI & FOMC calendar: feed parsing and filtering, time zones, countdown, rendering, and the Apify
actuals path including its cost guards. The feed and Apify are faked; nothing leaves the machine."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import macro_calendar_service as mc

UTC = timezone.utc


def row(title, country, date, impact="High", forecast="", previous=""):
    return {"title": title, "country": country, "date": date, "impact": impact, "forecast": forecast, "previous": previous}


FEED = [
    row("CPI m/m", "USD", "2026-10-14T08:30:00-04:00", forecast="0.6%", previous="0.4%"),
    row("Core CPI y/y", "USD", "2026-10-14T08:30:00-04:00", forecast="2.5%", previous="2.4%"),
    row("FOMC Member Barkin Speaks", "USD", "2026-10-14T13:30:00-04:00", impact="Low"),
    row("Federal Funds Rate", "USD", "2026-10-28T14:00:00-04:00", forecast="3.75%", previous="4.00%"),
    row("Fed Chairman Warsh Speaks", "USD", "2026-10-15T23:30:00-04:00"),
    row("CPI y/y", "CNY", "2026-10-13T21:30:00-04:00", impact="Low", forecast="1.0%", previous="0.8%"),
    row("Philly Fed Manufacturing Index", "USD", "2026-10-15T08:30:00-04:00", impact="Medium"),  # not CPI/FOMC
    row("Bank Holiday", "USD", "2026-10-12T07:00:00-04:00", impact="Holiday"),
    {"title": "Broken", "country": "USD", "date": "not a date", "impact": "High"},
    {"country": "USD", "date": "2026-10-14T08:30:00-04:00"},  # no title
]


@pytest.fixture(autouse=True)
def reset(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "_feed", None)
    monkeypatch.setattr(mc, "_blocked_until", 0.0)
    monkeypatch.setattr(mc, "_FEED_FILE", tmp_path / "feed.json")
    monkeypatch.setattr(mc, "_actuals", {})
    monkeypatch.setattr(mc, "_runs", {})
    monkeypatch.setattr(mc, "_last_run", 0.0)
    monkeypatch.setattr(mc, "_ACTUALS_FILE", tmp_path / "actuals.json")
    monkeypatch.setattr(mc.settings, "apify_token", "")


def test_only_cpi_and_fomc_events_are_kept_in_time_order():
    ev = mc.parse_feed(FEED)
    assert [e["title"] for e in ev] == ["CPI y/y", "CPI m/m", "Core CPI y/y", "FOMC Member Barkin Speaks", "Fed Chairman Warsh Speaks", "Federal Funds Rate"]
    assert {e["group"] for e in ev if "CPI" in e["title"]} == {"CPI"} and {e["group"] for e in ev if "CPI" not in e["title"]} == {"FOMC"}
    assert [e["impact"] for e in ev][:3] == ["low", "high", "high"]


def test_times_are_stored_in_utc_and_shown_in_kuala_lumpur_and_new_york():
    cpi = next(e for e in mc.parse_feed(FEED) if e["title"] == "CPI m/m")
    assert cpi["start"] == datetime(2026, 10, 14, 12, 30, tzinfo=UTC)  # 08:30 New York (EDT, UTC-4)
    assert cpi["start"].astimezone(mc.KL).strftime("%a %H:%M") == "Wed 20:30"  # Malaysia is UTC+8
    assert cpi["start"].astimezone(mc.ET).strftime("%H:%M") == "08:30"
    # after the US clocks go back (EST, UTC-5) the same 08:30 is one hour later in UTC and in Kuala Lumpur
    nov = mc.parse_feed([row("CPI m/m", "USD", "2026-11-12T08:30:00-05:00")])[0]
    assert nov["start"].astimezone(mc.KL).strftime("%H:%M") == "21:30" and nov["start"].astimezone(mc.ET).strftime("%H:%M") == "08:30"


def test_event_ids_are_stable_and_distinguish_same_title_events():
    a = mc.parse_feed([row("FOMC Member Barkin Speaks", "USD", "2026-10-13T13:00:00-04:00"), row("FOMC Member Barkin Speaks", "USD", "2026-10-14T13:30:00-04:00")])
    assert len({e["id"] for e in a}) == 2 and a[0]["id"] == mc.parse_feed([FEED[2] | {"date": "2026-10-13T13:00:00-04:00"}])[0]["id"]


def test_countdown_and_next_event_prefers_the_next_high_impact_one():
    ev = mc.parse_feed(FEED)
    now = datetime(2026, 10, 14, 11, 0, tzinfo=UTC)  # 07:00 New York, 90 minutes before CPI
    nxt = mc.next_event(ev, now)
    assert nxt["title"] in ("CPI m/m", "Core CPI y/y") and mc.countdown((nxt["start"] - now).total_seconds()) == "1h 30m"
    after = datetime(2026, 10, 15, 4, 0, tzinfo=UTC)  # only low-impact + later high ones remain
    assert mc.next_event(ev, after)["title"] == "Fed Chairman Warsh Speaks"
    assert mc.next_event(ev, datetime(2026, 11, 1, tzinfo=UTC)) is None
    assert [mc.countdown(s) for s in (30, 600, 3 * 3600 + 120, 2 * 86400 + 5 * 3600)] == ["under a minute", "10m", "3h 2m", "2d 5h"]


def test_html_groups_days_in_kl_time_dims_the_past_and_escapes_text():
    ev = mc.parse_feed(FEED + [row("<b>CPI</b> y/y", "USD", "2026-10-14T09:00:00-04:00")])
    now = datetime(2026, 10, 14, 12, 15, tzinfo=UTC)  # 15 min before CPI
    h = mc.build_html([e for e in ev if e["currency"] == "USD"], now)
    assert "Wednesday, Oct 14" in h and 'class="mc-today"' in h  # 20:15 in Kuala Lumpur is still the 14th
    assert "20:30</b><small>08:30 ET" in h and h.count("mc-soon") >= 2 and "mc-past" not in h.split("mc-day-head")[1].split("Barkin")[0]
    later = mc.build_html([e for e in ev if e["currency"] == "USD"], datetime(2026, 10, 14, 13, 5, tzinfo=UTC))  # CPI is 35 min old
    assert later.count("mc-past") >= 2 and "mc-soon" not in later
    assert "&lt;b&gt;CPI&lt;/b&gt; y/y" in h and "<b>CPI</b> y/y" not in h
    assert "No CPI or FOMC events" in mc.build_html([], now)


def test_feed_is_cached_for_everyone_and_survives_an_outage(monkeypatch):
    calls = []

    class Resp:
        status_code = 200
        headers = {}

        def __init__(self, ok=True):
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                raise RuntimeError("429 Too Many Requests")

        def json(self):
            return FEED

    state = {"ok": True}
    monkeypatch.setattr(mc.requests, "get", lambda *a, **k: (calls.append(1), Resp(state["ok"]))[1])
    for _ in range(5):
        mc.get_events()
    assert len(calls) == 1  # five viewers, one request
    state["ok"] = False
    monkeypatch.setattr(mc, "_feed", (mc._feed[0] - mc.FEED_TTL - 1, mc._feed[1]))  # cache expired
    r = mc.get_events()
    assert r["stale"] and r["error"] and len(r["events"]) == 5  # the last good copy (USD only), flagged as stale
    monkeypatch.setattr(mc, "_feed", (mc._feed[0] - mc.STALE_MAX - 1, mc._feed[1]))
    assert mc.get_events()["events"] == []  # too old to show


def test_a_429_is_obeyed_and_the_disk_copy_survives_restarts(monkeypatch):
    calls = []

    class Resp:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            pass

        def json(self):
            return FEED

    class Limited(Resp):
        status_code = 429
        headers = {"Retry-After": "289"}

    box = {"resp": Resp}
    monkeypatch.setattr(mc.requests, "get", lambda *a, **k: (calls.append(1), box["resp"]())[1])
    assert len(mc.get_events()["events"]) == 5 and len(calls) == 1  # fetched and saved to disk
    # "restart": memory is empty, the copy on disk is fresh, so no request at all
    monkeypatch.setattr(mc, "_feed", None)
    assert len(mc.get_events()["events"]) == 5 and len(calls) == 1
    # the feed starts answering 429: the stale copy is served and no further request is made until Retry-After
    box["resp"] = Limited
    monkeypatch.setattr(mc, "_feed", (mc._feed[0] - mc.FEED_TTL - 1, mc._feed[1]))
    r = mc.get_events()
    assert r["stale"] and "rate limited" in r["error"] and len(r["events"]) == 5 and len(calls) == 2
    for _ in range(4):
        mc.get_events()
    assert len(calls) == 2  # blocked: nobody hammers a limited feed
    assert 280 < mc._blocked_until - __import__("time").time() <= 290


def test_free_actuals_come_from_bls_levels_like_forex_factory_reports_them():
    from decimal import Decimal as D

    levels = {
        "all_sa": {(2026, 9): D("336.298"), (2026, 8): D("334.131")},
        "all_nsa": {(2026, 9): D("336.940"), (2025, 9): D("324.800")},
        "core_sa": {(2026, 9): D("338.896"), (2026, 8): D("337.765")},
        "core_nsa": {(2026, 9): D("339.287"), (2025, 9): D("330.600")},
    }
    assert mc.cpi_from_levels(levels, 2026, 9) == {"CPI m/m": "0.6%", "CPI y/y": "3.7%", "Core CPI m/m": "0.3%", "Core CPI y/y": "2.6%"}
    assert mc.cpi_from_levels(levels, 2026, 10) == {}  # the month is not published yet
    assert mc.cpi_from_levels({"all_sa": {(2026, 1): D("100"), (2025, 12): D("100.25")}}, 2026, 1) == {"CPI m/m": "-0.2%"}  # year boundary, negative


def test_free_actuals_fill_released_cpi_and_the_rate_decision_and_respect_their_limits(monkeypatch):
    from decimal import Decimal as D
    from datetime import date

    ev = mc.parse_feed(FEED)
    levels = {"all_sa": {(2026, 9): D("336.298"), (2026, 8): D("334.131")}, "all_nsa": {(2026, 9): D("336.940"), (2025, 9): D("324.800")},
              "core_sa": {(2026, 9): D("338.896"), (2026, 8): D("337.765")}, "core_nsa": {(2026, 9): D("339.287"), (2025, 9): D("330.600")}}
    bls, fred = [], []
    monkeypatch.setattr(mc, "_fetch_bls_levels", lambda: bls.append(1) or levels)
    monkeypatch.setattr(mc, "_fetch_fed_target", lambda: fred.append(1) or (date(2026, 10, 28), "3.75%"))
    monkeypatch.setattr(mc, "_last_free", 0.0)
    before = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    assert mc.refresh_free_actuals(ev, before) == 0 and not bls  # not released yet: no request
    after = datetime(2026, 10, 14, 12, 40, tzinfo=UTC)
    assert mc.refresh_free_actuals(ev, after) == 2 and len(bls) == 1 and not fred  # CPI m/m and Core CPI y/y are in FEED
    assert {e["title"]: e["actual"] for e in ev if e["group"] == "CPI" and e["actual"]} == {"CPI m/m": "0.6%", "Core CPI y/y": "2.6%"}
    assert mc.refresh_free_actuals(ev, after) == 0  # nothing pending now
    # the rate decision: FRED already shows the decision day's value
    fomc = datetime(2026, 10, 28, 18, 30, tzinfo=UTC)
    monkeypatch.setattr(mc, "_last_free", 0.0)
    assert mc.refresh_free_actuals(ev, fomc) == 1 and next(e for e in ev if e["title"] == "Federal Funds Rate")["actual"] == "3.75%"
    # FRED not updated yet (still yesterday's value): nothing stored, asked again later
    ev2 = mc.parse_feed(FEED)
    monkeypatch.setattr(mc, "_last_free", 0.0)
    monkeypatch.setattr(mc, "_fetch_fed_target", lambda: (date(2026, 10, 27), "4.00%"))
    assert mc.refresh_free_actuals([e for e in ev2 if e["title"] == "Federal Funds Rate"], fomc) == 0
    # the 2-minute gap and the daily cap
    monkeypatch.setattr(mc, "_last_free", __import__("time").time())
    assert mc.refresh_free_actuals([e for e in ev2 if e["group"] == "CPI"], after) == 0


def test_background_lookup_never_blocks_and_runs_one_at_a_time(monkeypatch):
    import threading

    started, release = threading.Event(), threading.Event()
    monkeypatch.setattr(mc, "refresh_free_actuals", lambda ev, now=None: (started.set(), release.wait(5)))
    monkeypatch.setattr(mc, "refresh_actuals", lambda ev, now=None: 0)
    ev = mc.parse_feed(FEED)
    mc.refresh_actuals_in_background(ev)  # returns at once although the lookup is stuck
    assert started.wait(2) and mc._bg_busy.is_set()
    mc.refresh_actuals_in_background(ev)  # a second call while one is running does nothing
    release.set()
    for _ in range(50):
        if not mc._bg_busy.is_set():
            break
        __import__("time").sleep(0.05)
    assert not mc._bg_busy.is_set()


def apify_rows():
    return [{"title": "CPI m/m", "currency": "USD", "actual": "0.5%", "revised": "0.4%"}, {"title": "Core CPI y/y", "currency": "USD", "actual": "2.6%"},
            {"title": "CPI m/m", "currency": "EUR", "actual": "9%"}, {"title": "Unknown", "currency": "USD", "actual": "1"}, {"title": "FOMC Statement", "currency": "USD", "actual": ""}]


def test_apify_rows_are_matched_by_currency_and_title():
    ev = mc.parse_feed(FEED)
    found = mc.match_apify_rows(ev, apify_rows())
    by_title = {e["id"]: e["title"] for e in ev}
    assert sorted((by_title[k], v["actual"], v["revised"]) for k, v in found.items()) == [("CPI m/m", "0.5%", "0.4%"), ("Core CPI y/y", "2.6%", "")]


def test_actuals_do_nothing_without_a_token(monkeypatch):
    monkeypatch.setattr(mc, "_run_apify", lambda t: pytest.fail("no token: Apify must not be called"))
    ev = mc.parse_feed(FEED)
    assert mc.refresh_actuals(ev, datetime(2026, 10, 14, 12, 40, tzinfo=UTC)) == 0


def test_actuals_run_only_after_a_release_and_are_remembered(monkeypatch):
    monkeypatch.setattr(mc.settings, "apify_token", "tok")
    runs = []
    monkeypatch.setattr(mc, "_run_apify", lambda t: runs.append(t) or apify_rows())
    ev = mc.parse_feed(FEED)
    before = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    assert mc.refresh_actuals(ev, before) == 0 and runs == []  # nothing released yet: no run, no cost
    after = datetime(2026, 10, 14, 12, 40, tzinfo=UTC)  # 10 minutes after CPI
    assert mc.refresh_actuals(ev, after) == 2 and runs == ["tok"]
    cpi = next(e for e in ev if e["title"] == "CPI m/m")
    assert (cpi["actual"], cpi["revised"]) == ("0.5%", "0.4%")
    assert mc.refresh_actuals(ev, after) == 0 and len(runs) == 1  # nothing pending now: no second run
    # the number survives a restart (file) and a new request's fresh events
    assert mc.get_events.__defaults__ is not None
    fresh = mc.parse_feed(FEED)
    mc.apply_actuals(fresh, mc._load_actuals())
    assert next(e for e in fresh if e["title"] == "Core CPI y/y")["actual"] == "2.6%"
    assert (mc._ACTUALS_FILE).exists()


def test_actuals_cost_guards(monkeypatch):
    monkeypatch.setattr(mc.settings, "apify_token", "tok")
    monkeypatch.setattr(mc.settings, "macro_actuals_max_runs_per_day", 2)
    runs = []
    monkeypatch.setattr(mc, "_run_apify", lambda t: runs.append(1) or [])  # the actor has nothing yet
    ev = mc.parse_feed(FEED)
    t = datetime(2026, 10, 14, 12, 40, tzinfo=UTC)
    mc.refresh_actuals(ev, t)
    mc.refresh_actuals(ev, t)  # inside the 3-minute gap
    assert len(runs) == 1
    monkeypatch.setattr(mc, "_last_run", 0.0)
    mc.refresh_actuals(ev, t)  # second allowed run of the day
    monkeypatch.setattr(mc, "_last_run", 0.0)
    mc.refresh_actuals(ev, t)  # daily budget (2) spent
    assert len(runs) == 2
    late = datetime(2026, 10, 14, 17, 0, tzinfo=UTC)  # 4.5 hours after the release: stop asking
    monkeypatch.setattr(mc, "_last_run", 0.0)
    monkeypatch.setattr(mc, "_runs", {})
    assert mc.refresh_actuals(ev, late) == 0 and len(runs) == 2


def test_an_apify_failure_never_raises(monkeypatch):
    monkeypatch.setattr(mc.settings, "apify_token", "tok")
    monkeypatch.setattr(mc, "_run_apify", lambda t: (_ for _ in ()).throw(RuntimeError("402 Payment Required")))
    assert mc.refresh_actuals(mc.parse_feed(FEED), datetime(2026, 10, 14, 12, 40, tzinfo=UTC)) == 0


def test_waiting_dots_show_only_while_an_actual_is_expected(monkeypatch):
    ev = [e for e in mc.parse_feed(FEED) if e["title"] == "CPI m/m"]
    just_after = datetime(2026, 10, 14, 12, 40, tzinfo=UTC)
    assert "mc-wait" in mc.build_html(ev, just_after, has_actuals_source=True)
    assert "mc-wait" not in mc.build_html(ev, just_after, has_actuals_source=False)  # no source: a dash, no false promise
    assert "mc-wait" not in mc.build_html(ev, datetime(2026, 10, 14, 17, 0, tzinfo=UTC), has_actuals_source=True)  # window over


def test_arrow_against_the_forecast():
    assert 'title="Above forecast"' in mc._vs_forecast("0.6%", "0.5%") and "▲" in mc._vs_forecast("3.7%", "3.6%")
    assert "▼" in mc._vs_forecast("2.5%", "2.6%") and "▼" in mc._vs_forecast("-1.2B", "-0.5B")
    assert mc._vs_forecast("0.6%", "0.6%") == "" and mc._vs_forecast("", "0.5%") == "" and mc._vs_forecast("0.5%", "") == "" and mc._vs_forecast("3.75%|1.4", "x") == ""
    ev = mc.parse_feed(FEED)
    for e in ev:
        if e["title"] == "CPI m/m":
            e["actual"] = "0.7%"
    assert "▲" in mc.build_html([e for e in ev if e["title"] == "CPI m/m"], datetime(2026, 10, 14, 14, 0, tzinfo=UTC))
