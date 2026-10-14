"""Forex Factory in Telegram: 7-day / 3-day / 1-hour reminders (once each, restart safe), the /forex_factory month
list and its menu entry. The calendar and Telegram are faked; nothing leaves the machine."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import User
from app.services import macro_calendar_service as mc
from app.services import macro_reminder_service as rm
from app.services import telegram_digest_service as dg
from app.services import telegram_notify_service as tg

UTC = timezone.utc


def ev(title, iso, currency="USD", impact="High", forecast="", previous=""):
    return mc.parse_feed([{"title": title, "country": currency, "date": iso, "impact": impact, "forecast": forecast, "previous": previous}])[0]


CPI_ROWS = [ev(t, "2026-10-20T08:30:00-04:00", forecast="0.3%", previous="0.2%") for t in ("CPI m/m", "CPI y/y", "Core CPI m/m", "Core CPI y/y")]
CPI_START = CPI_ROWS[0]["start"]  # 2026-10-20 12:30 UTC = 20:30 Kuala Lumpur


@pytest.fixture
def env(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    for mod in (tg, dg):
        monkeypatch.setattr(mod, "SessionLocal", maker)
    monkeypatch.setattr(rm, "_STATE_FILE", tmp_path / "reminders.json")
    monkeypatch.setattr(tg.settings, "telegram_bot_token", "x")
    db = maker()
    db.add(User(id=1, full_name="A", email="a@x.com", password_hash="h", telegram_chat_id=42))
    db.add(User(id=2, full_name="B", email="b@x.com", password_hash="h"))
    db.commit()
    db.close()
    sent = []
    monkeypatch.setattr(tg, "_send", lambda chat_id, text: sent.append((chat_id, text)))
    yield sent
    engine.dispose()


def test_events_at_the_same_time_are_one_reminder_and_members_speeches_are_left_out():
    speech = ev("FOMC Member Waller Speaks", "2026-10-20T10:00:00-04:00", impact="Low")
    chair = ev("Fed Chairman Warsh Speaks", "2026-10-21T11:30:00-04:00")
    other_country = ev("CPI y/y", "2026-10-20T21:30:00-04:00", currency="CNY")
    u = rm.units(CPI_ROWS + [speech, chair, other_country])
    assert [(x["group"], len(x["rows"])) for x in u] == [("CPI", 4), ("FOMC", 1)] and u[1]["rows"][0]["title"] == "Fed Chairman Warsh Speaks"


def test_offsets_fire_once_each_at_7_days_3_days_and_1_hour(env):
    sent = env
    rows = CPI_ROWS
    for delta, want in ((timedelta(days=8), 0), (timedelta(days=7), 1), (timedelta(days=6), 0), (timedelta(days=3), 1), (timedelta(days=2), 0),
                        (timedelta(hours=1), 1), (timedelta(minutes=30), 0), (timedelta(seconds=-1), 0)):
        before = len(sent)
        rm.check_and_send(CPI_START - delta, rows)
        assert len(sent) - before == want, delta
    assert [m[1].split("</b>")[0].split("<b>")[1] for m in sent] == ["US CPI in 7 days", "US CPI in 3 days", "US CPI in 1 hour"]
    assert all(m[0] == 42 for m in sent)  # only the connected account


def test_a_restart_does_not_repeat_and_a_late_event_gets_one_message(env):
    sent = env
    rm.check_and_send(CPI_START - timedelta(days=7, minutes=1), CPI_ROWS)
    rm.check_and_send(CPI_START - timedelta(days=7), CPI_ROWS)  # same state file = a restarted process
    assert len(sent) == 1
    sent.clear()
    rm._STATE_FILE.unlink()
    rm.check_and_send(CPI_START - timedelta(days=2, hours=5), CPI_ROWS)  # first seen 2d5h before: 7d and 3d are both past
    assert len(sent) == 1 and "in 2d 5h" in sent[0][1]  # the real time left, not "in 3 days"
    rm.check_and_send(CPI_START - timedelta(days=2), CPI_ROWS)
    assert len(sent) == 1  # the 3-day one was marked as skipped


def test_message_has_kuala_lumpur_and_new_york_time_and_the_numbers(env):
    now = CPI_START - timedelta(days=7)
    text = rm.reminder_message(rm.units(CPI_ROWS)[0], "7d", now)
    assert "US CPI in 7 days" in text and "Tuesday, 20 Oct 2026" in text and "<b>20:30</b> Kuala Lumpur (08:30 New York)" in text
    assert "CPI m/m  ·  forecast 0.3% · previous 0.2%" in text
    sched = {**CPI_ROWS[0], "scheduled": True, "forecast": "", "previous": ""}
    assert "CPI m/m" not in rm.reminder_message(rm.units([sched])[0], "7d", now)  # a placeholder row has no numbers to show


def test_a_failed_send_is_retried_and_no_connected_chat_is_not_a_loop(env, monkeypatch):
    sent = env
    monkeypatch.setattr(tg, "_send", lambda c, t: (_ for _ in ()).throw(RuntimeError("telegram down")))
    assert rm.check_and_send(CPI_START - timedelta(days=7), CPI_ROWS) == []  # nothing marked as sent
    monkeypatch.setattr(tg, "_send", lambda c, t: sent.append((c, t)))
    assert len(rm.check_and_send(CPI_START - timedelta(days=7), CPI_ROWS)) == 1
    monkeypatch.setattr(dg, "connected_chats", lambda: [])
    rm._STATE_FILE.unlink()
    assert len(rm.check_and_send(CPI_START - timedelta(days=7), CPI_ROWS)) == 1 and len(sent) == 1  # marked done, nobody to tell


def test_month_list_is_only_this_calendar_month_with_past_actuals(env):
    now = datetime(2026, 10, 15, 4, 0, tzinfo=UTC)
    done = ev("CPI m/m", "2026-10-14T08:30:00-04:00", forecast="0.6%")
    done["actual"] = "0.3%"
    member = [ev("FOMC Member Barkin Speaks", "2026-10-14T13:30:00-04:00", impact="Low"), ev("FOMC Member Waller Speaks", "2026-10-14T03:45:00-04:00", impact="Low")]
    nov = ev("CPI m/m", "2026-11-10T08:30:00-05:00")
    sep = ev("CPI m/m", "2026-09-11T08:30:00-04:00")
    fed = ev("Federal Funds Rate", "2026-10-28T14:00:00-04:00", forecast="3.75%")
    msgs = rm.month_messages([done, *member, nov, sep, fed, ev("CPI y/y", "2026-10-13T21:30:00-04:00", currency="CNY")], now)
    text = "\n".join(msgs)
    assert "October 2026" in text and "Nov" not in text and "11 Sep" not in text  # one month only
    assert "✅ 20:30  CPI m/m 0.3%" in text and "▫️ 02:00  Federal Funds Rate (3.75%)" in text
    assert "<b>Wed 14 Oct</b>" in text and "<b>Thu 29 Oct</b>" in text  # 14:00 New York on the 28th is 02:00 on the 29th in Kuala Lumpur
    assert "💬 Members: Waller 15:45" in text and "💬 Members: Barkin 01:30" in text  # one line a day; 13:30 New York is 01:30 next day
    assert rm.month_messages([nov], now)[0].endswith("No CPI, FOMC or Non-Farm Employment events found for this month yet.")


def test_a_long_month_is_split_into_several_messages():
    now = datetime(2026, 10, 15, 4, 0, tzinfo=UTC)
    many = [ev(f"FOMC Statement number {i} " + "x" * 80, f"2026-10-{1 + i % 28:02d}T{8 + i % 10:02d}:00:00-04:00") for i in range(120)]
    msgs = rm.month_messages(many, now)
    assert len(msgs) > 1 and all(len(m) <= 4000 for m in msgs) and "(continued)" in msgs[1]


def test_forex_factory_command_and_hyphen_spelling(env, monkeypatch):
    sent = env
    monkeypatch.setattr(mc, "get_schedule", lambda now=None, currencies=("USD",): {"events": CPI_ROWS})
    monkeypatch.setattr(rm, "mc", mc)
    for text in ("/forex_factory", "/forex-factory", "/forex_factory@RepaceBot"):
        sent.clear()
        tg.handle_message({"chat": {"id": 42, "type": "private"}, "text": text})
        assert sent and sent[0][0] == 42 and "Forex Factory" in sent[0][1], text
    sent.clear()
    tg.handle_message({"chat": {"id": 99, "type": "private"}, "text": "/forex_factory"})  # not a connected chat
    assert len(sent) == 1 and "not connected" in sent[0][1]


def test_forex_factory_is_in_the_menu_and_the_overview():
    assert "forex_factory" in [c["command"] for c in tg.menu_commands()]
    assert all("-" not in c["command"] for c in tg.menu_commands())  # Telegram menus cannot hold hyphens
    text = tg.commands_overview()
    assert "/forex_factory" in text and "/forex-factory" in text and "7 days, 3 days and 1 hour" in text
