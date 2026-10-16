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
    row("Philly Fed Manufacturing Index", "USD", "2026-10-15T08:30:00-04:00", impact="Medium"),  # not CPI/FOMC/NFP
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
    monkeypatch.setattr(mc, "_STORE_FILE", tmp_path / "store.json")
    monkeypatch.setattr(mc, "_SCHEDULE_FILE", tmp_path / "schedule.json")
    monkeypatch.setattr(mc, "_schedule", None)
    monkeypatch.setattr(mc, "_schedule_failed_at", 0.0)
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


def test_countdown_and_next_event_is_the_nearest_upcoming_one():
    ev = mc.parse_feed(FEED)
    now = datetime(2026, 10, 14, 11, 0, tzinfo=UTC)  # 07:00 New York, 90 minutes before CPI
    nxt = mc.next_event(ev, now)
    assert nxt["title"] in ("CPI m/m", "Core CPI y/y") and mc.countdown((nxt["start"] - now).total_seconds()) == "1h 30m"
    after = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)  # the CPI numbers passed; a low-impact speech is nearer than the Fed Chair
    assert mc.next_event(ev, after)["title"] == "Fed Chairman Warsh Speaks"  # the only later one in FEED
    assert mc.next_event(ev, datetime(2026, 11, 1, tzinfo=UTC)) is None
    assert [mc.countdown(s) for s in (30, 600, 3 * 3600 + 120, 2 * 86400 + 5 * 3600)] == ["under a minute", "10m", "3h 2m", "2d 5h"]
    speech = {**ev[0], "title": "FOMC Member X Speaks", "impact": "low", "start": datetime(2026, 10, 14, 12, 0, tzinfo=UTC)}
    assert mc.next_event(ev + [speech], now)["title"] == "FOMC Member X Speaks"  # nearer wins over high impact


def test_html_groups_days_in_kl_time_dims_the_past_and_escapes_text():
    ev = mc.parse_feed(FEED + [row("<b>CPI</b> y/y", "USD", "2026-10-14T09:00:00-04:00")])
    now = datetime(2026, 10, 14, 12, 15, tzinfo=UTC)  # 15 min before CPI
    h = mc.build_html([e for e in ev if e["currency"] == "USD"], now)
    assert "Wednesday, Oct 14" in h and 'class="mc-today"' in h  # 20:15 in Kuala Lumpur is still the 14th
    assert "20:30</b><small>08:30 ET" in h and h.count("mc-soon") >= 2 and "mc-past" not in h.split("mc-day-head")[1].split("Barkin")[0]
    later = mc.build_html([e for e in ev if e["currency"] == "USD"], datetime(2026, 10, 14, 13, 5, tzinfo=UTC))  # CPI is 35 min old
    assert later.count("mc-past") >= 2 and "mc-soon" not in later
    assert "&lt;b&gt;CPI&lt;/b&gt; y/y" in h and "<b>CPI</b> y/y" not in h
    assert "No CPI, PPI, FOMC or Non-Farm Employment events" in mc.build_html([], now)


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


# ---- Non-Farm Employment Change ---------------------------------------------------------------

NFP_FEED = [row("Non-Farm Employment Change", "USD", "2026-11-06T08:30:00-05:00", forecast="55K", previous="29K"),
            row("Unemployment Rate", "USD", "2026-11-06T08:30:00-05:00", impact="High"),  # not asked for
            row("Average Hourly Earnings m/m", "USD", "2026-11-06T08:30:00-05:00", impact="High")]


def test_non_farm_employment_change_is_kept_and_grouped():
    ev = mc.parse_feed(NFP_FEED)
    assert [(e["title"], e["group"], e["impact"], e["forecast"], e["previous"]) for e in ev] == [("Non-Farm Employment Change", "NFP", "high", "55K", "29K")]
    assert mc.parse_feed([row("Non-Farm Employment Change", "USD", "2026-11-06T08:30:00-05:00")])[0]["start"] == datetime(2026, 11, 6, 13, 30, tzinfo=UTC)
    assert 'mc-chip-nfp">NFP' in mc.build_html(ev, datetime(2026, 11, 6, 12, 0, tzinfo=UTC))
    assert mc.next_event(ev, datetime(2026, 11, 6, 12, 0, tzinfo=UTC))["title"] == "Non-Farm Employment Change"


def test_nfp_actual_is_the_change_in_thousands():
    from decimal import Decimal as D

    levels = {"nfp": {(2026, 9): D("159044"), (2026, 8): D("159015"), (2025, 12): D("158000"), (2026, 1): D("157950")}}
    assert mc.nfp_from_levels(levels, 2026, 9) == "29K"
    assert mc.nfp_from_levels(levels, 2026, 1) == "-50K"  # year boundary, negative
    assert mc.nfp_from_levels(levels, 2026, 10) == ""  # not published yet
    assert mc.nfp_from_levels({}, 2026, 9) == ""


def test_nfp_is_filled_from_bls_after_the_release_and_the_key_is_optional(monkeypatch):
    from decimal import Decimal as D

    ev = mc.parse_feed(NFP_FEED)
    levels = {"nfp": {(2026, 10): D("159300"), (2026, 9): D("159044")}}
    monkeypatch.setattr(mc, "_fetch_bls_levels", lambda: levels)
    monkeypatch.setattr(mc, "_last_free", 0.0)
    assert mc.refresh_free_actuals(ev, datetime(2026, 11, 6, 12, 0, tzinfo=UTC)) == 0  # before the release
    assert mc.refresh_free_actuals(ev, datetime(2026, 11, 6, 13, 40, tzinfo=UTC)) == 1  # October's jobs, released 08:30 ET on Nov 6
    assert ev[0]["actual"] == "256K" and "▲" in mc.build_html(ev, datetime(2026, 11, 6, 14, 0, tzinfo=UTC))  # 256K vs 55K forecast


def test_bls_uses_v2_only_when_a_key_is_set(monkeypatch):
    posts = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"seriesID": "CES0000000001", "data": [{"year": "2026", "period": "M09", "value": "159044"}, {"year": "2026", "period": "M08", "value": "-"}]}]}}

    monkeypatch.setattr(mc.requests, "post", lambda url, **k: (posts.append((url, k["json"])), Resp())[1])
    monkeypatch.setattr(mc.settings, "bls_api_key", "")
    levels = mc._fetch_bls_levels()
    assert posts[0][0] == mc.BLS_URL and "registrationkey" not in posts[0][1]
    assert levels["nfp"] == {(2026, 9): __import__("decimal").Decimal("159044")}  # "-" (unpublished) is skipped
    monkeypatch.setattr(mc.settings, "bls_api_key", "abc123")
    mc._fetch_bls_levels()
    assert posts[1][0] == mc.BLS_V2_URL and posts[1][1]["registrationkey"] == "abc123" and "CES0000000001" in posts[1][1]["seriesid"]


# ---- the month ahead ----------------------------------------------------------------------------------

def ev(title, iso, currency="USD", **kw):
    return mc.parse_feed([row(title, currency, iso, **kw)])[0]


def test_the_page_drops_days_before_today_in_malaysia_and_stops_after_30_days():
    now = datetime(2026, 10, 15, 17, 0, tzinfo=UTC)  # 01:00 on the 16th in Kuala Lumpur
    old = ev("CPI m/m", "2026-10-14T08:30:00-04:00")  # 20:30 KL on the 14th
    yesterday_kl = ev("FOMC Member A Speaks", "2026-10-15T10:00:00-04:00")  # 22:00 KL on the 15th: already yesterday in Malaysia
    today_early = ev("FOMC Member B Speaks", "2026-10-15T12:30:00-04:00")  # 00:30 KL on the 16th: earlier today, kept
    far = ev("CPI m/m", "2026-11-20T08:30:00-05:00")
    keep = ev("CPI m/m", "2026-11-12T08:30:00-05:00")
    assert mc.in_window([old, yesterday_kl, today_early, keep, far], now) == [today_early, keep]


def test_month_events_are_the_calendar_month_in_kuala_lumpur():
    now = datetime(2026, 9, 20, 5, 0, tzinfo=UTC)
    sep, early_oct_kl = ev("CPI m/m", "2026-09-11T08:30:00-04:00"), ev("CPI m/m", "2026-09-30T12:30:00-04:00")  # 00:30 KL on 1 Oct
    assert mc.month_events([sep, early_oct_kl, ev("CPI m/m", "2026-10-14T08:30:00-04:00")], now) == [sep]


def test_feed_events_are_remembered_and_a_changed_time_replaces_the_old_one(monkeypatch):
    now = datetime(2026, 10, 15, tzinfo=UTC)
    first = [ev("CPI m/m", "2026-10-14T08:30:00-04:00"), ev("FOMC Member A Speaks", "2026-10-13T10:00:00-04:00")]
    assert [e["title"] for e in mc.remember(first, now)] == ["FOMC Member A Speaks", "CPI m/m"]
    # next fetch: this week's feed no longer lists the speech (past) and moved nothing; the speech stays remembered
    assert len(mc.remember([ev("CPI m/m", "2026-10-14T08:30:00-04:00")], now)) == 2
    moved = mc.remember([ev("CPI m/m", "2026-10-14T09:30:00-04:00")], now)  # same title inside the same week, new time
    assert [e["start"].astimezone(mc.ET).strftime("%H:%M") for e in moved if e["title"] == "CPI m/m"] == ["09:30"]
    assert mc.remember([], datetime(2026, 12, 30, tzinfo=UTC)) == []  # older than 40 days is forgotten


def test_fomc_decision_days_come_from_the_fed_calendar_page():
    page = (
        '<h4><a id="1">2026 FOMC Meetings</a></h4>'
        '<div class="fomc-meeting__month col"><strong>October</strong></div><div class="fomc-meeting__date col">27-28</div>'
        '<div class="fomc-meeting__month col"><strong>August</strong></div><div class="fomc-meeting__date col">22 (notation vote)</div>'
        '<div class="fomc-meeting__month col"><strong>Apr/May</strong></div><div class="fomc-meeting__date col">30-1</div>'
        '<h4><a id="2">2027 FOMC Meetings</a></h4>'
        '<div class="fomc-meeting__month col"><strong>January</strong></div><div class="fomc-meeting__date col">26-27*</div>'
    )
    assert [d.isoformat() for d in mc.parse_fomc_page(page)] == ["2026-05-01", "2026-10-28", "2027-01-27"]


def test_scheduled_releases_fill_the_month_until_the_feed_has_the_real_rows():
    sched = {"fomc": ["2026-10-28"], "cpi": ["2026-11-10", "2026-10-14"], "nfp": ["2026-11-06"]}
    now = datetime(2026, 10, 15, tzinfo=UTC)
    real = [ev("CPI m/m", "2026-10-14T08:30:00-04:00"), ev("Federal Funds Rate", "2026-10-28T14:00:00-04:00")]
    got = mc.placeholder_events(sched, real, now)
    assert [(e["group"], e["start"].astimezone(mc.KL).strftime("%d %b %H:%M")) for e in got] == [("CPI", "10 Nov 21:30"), ("NFP", "06 Nov 21:30")]
    assert all(e["scheduled"] and e["impact"] == "high" and e["currency"] == "USD" for e in got)
    fomc = mc.placeholder_events({"fomc": ["2026-10-28"]}, [], now)[0]
    assert fomc["start"] == datetime(2026, 10, 28, 18, 0, tzinfo=UTC) and fomc["start"].astimezone(mc.KL).strftime("%d %b %H:%M") == "29 Oct 02:00"


def test_get_schedule_merges_stored_events_and_scheduled_ones_and_never_breaks_without_a_fred_key(monkeypatch):
    monkeypatch.setattr(mc, "_load_feed", lambda force=False: ([row("CPI m/m", "USD", "2026-10-14T08:30:00-04:00", forecast="0.3%")], False, ""))
    calls = []

    class R:
        text = '<h4>2026 FOMC Meetings</h4><div class="fomc-meeting__month"><strong>October</strong></div><div class="fomc-meeting__date">27-28</div>'

        def raise_for_status(self):
            pass

    monkeypatch.setattr(mc.requests, "get", lambda url, **kw: calls.append(url) or R())
    monkeypatch.setattr(mc.settings, "fred_api_key", "")
    out = mc.get_schedule(datetime(2026, 10, 15, tzinfo=UTC))["events"]
    assert [(e["title"], bool(e.get("scheduled"))) for e in out] == [("CPI m/m", False), ("FOMC Meeting: Federal Funds Rate decision", True)]
    assert calls == [mc.FED_URL]  # no FRED call without a key
    mc.get_schedule(datetime(2026, 10, 15, tzinfo=UTC))
    assert calls == [mc.FED_URL]  # cached for 12 hours


def test_a_failing_schedule_source_is_retried_later_and_keeps_old_dates(monkeypatch):
    monkeypatch.setattr(mc.settings, "fred_api_key", "k")
    seen = []

    def boom(url, **kw):
        seen.append(url)
        raise OSError("down")

    monkeypatch.setattr(mc.requests, "get", boom)
    s = mc.load_schedule(datetime(2026, 10, 15, tzinfo=UTC))
    assert s["fomc"] == [] and len(seen) == 4  # fed + three FRED releases (CPI, PPI, jobs) tried
    mc.load_schedule(datetime(2026, 10, 15, tzinfo=UTC))
    assert len(seen) == 4  # not hammered: wait 30 minutes after a failure


PPI_FEED = [
    row("PPI m/m", "USD", "2026-11-13T08:30:00-05:00", forecast="0.6%", previous="0.4%"),
    row("Core PPI m/m", "USD", "2026-11-13T08:30:00-05:00", forecast="0.3%", previous="0.2%"),
    row("PPI m/m", "CHF", "2026-11-13T02:30:00-05:00", impact="Low", forecast="0.6%", previous="0.7%"),
    row("PPI y/y", "JPY", "2026-11-12T19:50:00-05:00", impact="Low"),
]


def test_ppi_events_are_kept_grouped_and_get_their_own_chip():
    ev = mc.parse_feed(PPI_FEED)
    usd = [e for e in ev if e["currency"] == "USD"]
    assert [(e["title"], e["group"], e["impact"], e["forecast"]) for e in usd] == [("Core PPI m/m", "PPI", "high", "0.3%"), ("PPI m/m", "PPI", "high", "0.6%")]
    assert all(e["group"] == "PPI" for e in ev)  # other currencies are kept in the raw list, the page filters to USD
    assert 'mc-chip-ppi">PPI' in mc.build_html(usd, datetime(2026, 11, 13, 12, 0, tzinfo=UTC))


def test_ppi_actual_is_the_month_over_month_change_like_forex_factory():
    from decimal import Decimal as D

    levels = {"ppi_sa": {(2026, 9): D("159.780"), (2026, 8): D("157.662")}, "ppi_core_sa": {(2026, 9): D("271.972"), (2026, 8): D("271.372")}}
    assert mc.ppi_from_levels(levels, 2026, 9) == {"PPI m/m": "1.3%", "Core PPI m/m": "0.2%"}
    assert mc.ppi_from_levels(levels, 2026, 10) == {}  # not published yet


def test_ppi_is_filled_from_bls_after_the_release(monkeypatch):
    from decimal import Decimal as D

    ev = [e for e in mc.parse_feed(PPI_FEED) if e["currency"] == "USD"]
    levels = {"ppi_sa": {(2026, 10): D("160.5"), (2026, 9): D("159.780")}, "ppi_core_sa": {(2026, 10): D("272.5"), (2026, 9): D("271.972")}}
    monkeypatch.setattr(mc, "_fetch_bls_levels", lambda: levels)
    monkeypatch.setattr(mc, "_last_free", 0.0)
    assert mc.refresh_free_actuals(ev, datetime(2026, 11, 13, 13, 40, tzinfo=UTC)) == 2
    assert {e["title"]: e["actual"] for e in ev} == {"PPI m/m": "0.5%", "Core PPI m/m": "0.2%"}


def test_ppi_release_dates_fill_the_schedule_and_the_reminder_names_it():
    from app.services import macro_reminder_service as rem

    got = mc.placeholder_events({"ppi": ["2026-11-13"]}, [], datetime(2026, 10, 15, tzinfo=UTC))
    assert [(e["group"], e["title"], e["start"].astimezone(mc.KL).strftime("%d %b %H:%M")) for e in got] == [("PPI", "PPI (release date)", "13 Nov 21:30")]
    unit = rem.units(got)[0]
    assert rem._title(unit) == "US PPI" and rem._ICON["PPI"] == "🏭"
