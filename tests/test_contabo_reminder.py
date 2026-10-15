"""Contabo subscription reminders: next end date, once-only 5 / 3 / 1 day messages, 09:00 KL."""

from datetime import date, datetime, timezone

import pytest

from app.services import contabo_reminder_service as cr


def test_the_next_end_rolls_forward_by_whole_terms_and_keeps_the_day():
    a = date(2026, 9, 11)
    assert cr.next_end(a, date(2026, 9, 1)) == date(2026, 9, 11)  # the anchor itself, still ahead
    assert cr.next_end(a, date(2026, 10, 15)) == date(2026, 11, 11) and cr.next_end(a, date(2026, 11, 11)) == date(2026, 11, 11)
    assert cr.next_end(a, date(2026, 11, 12)) == date(2026, 12, 11)
    assert cr.next_end(a, date(2027, 9, 12), 12) == date(2028, 9, 11)  # a yearly term
    assert cr.next_end(date(2026, 1, 31), date(2026, 2, 1)) == date(2026, 2, 28) and cr.next_end(date(2026, 1, 31), date(2026, 3, 1)) == date(2026, 3, 31)


def test_the_tightest_reached_offset_is_announced_once_and_looser_ones_are_not_sent_late():
    assert cr.due_offset(6, []) is None
    assert cr.due_offset(5, []) == (5, [5])
    assert cr.due_offset(5, [5]) is None and cr.due_offset(4, [5]) is None
    assert cr.due_offset(3, [5]) == (3, [3]) and cr.due_offset(1, [5, 3]) == (1, [1])
    assert cr.due_offset(2, []) == (3, [5, 3])  # first seen 2 days out: one message, the 5-day one is skipped
    assert cr.due_offset(0, [5, 3]) == (1, [1])  # the day itself still gets the last reminder
    assert cr.due_offset(1, [5, 3, 1]) is None and cr.due_offset(-1, []) is None


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(cr, "_STATE_FILE", tmp_path / "sent.json")
    monkeypatch.setattr(cr.settings, "contabo_renewal_date", "2026-11-11")
    monkeypatch.setattr(cr.settings, "contabo_term_months", 1)
    sent = []
    monkeypatch.setattr(cr.dg, "_deliver", lambda text, chats: sent.append(text) or 1)
    monkeypatch.setattr(cr.dg, "connected_chats", lambda: [42])
    return sent


def at(day, hour=9):  # a Kuala Lumpur wall-clock time, as UTC
    return datetime(2026, 11, day, hour - 8, 0, tzinfo=timezone.utc) if hour >= 8 else datetime(2026, 11, day - 1, hour + 16, 0, tzinfo=timezone.utc)


def test_five_three_and_one_day_reminders_are_sent_once_each_at_nine_kl(env):
    sent = env
    assert cr.check_and_send(at(5, 8)) is None and sent == []  # 08:00 KL: too early
    for day, hour in ((5, 9), (5, 15), (6, 9), (8, 9), (8, 20), (9, 9), (10, 9), (10, 12), (11, 9), (12, 9)):
        cr.check_and_send(at(day, hour))
    assert len(sent) == 3
    assert "in 5 days" in sent[0] and "in 3 days" in sent[1] and "tomorrow" in sent[2]
    assert all("Wednesday, 11 Nov 2026" in m and "Contabo" in m for m in sent)


def test_next_term_gets_its_own_reminders_and_a_restart_does_not_repeat(env):
    sent = env
    cr.check_and_send(datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc))  # 10:00 KL, 5 days before 11 Nov
    cr.check_and_send(datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc))  # same state file = a restart
    assert len(sent) == 1
    cr.check_and_send(datetime(2026, 12, 6, 2, 0, tzinfo=timezone.utc))  # 5 days before 11 Dec
    assert len(sent) == 2 and "11 Dec 2026" in sent[1]


def test_off_without_a_date_or_with_a_bad_one_and_a_failed_send_is_retried(env, monkeypatch):
    sent = env
    monkeypatch.setattr(cr.settings, "contabo_renewal_date", "")
    assert cr.check_and_send(at(6, 10)) is None and sent == []
    monkeypatch.setattr(cr.settings, "contabo_renewal_date", "11/11/2026")
    assert cr.check_and_send(at(6, 10)) is None and sent == []
    monkeypatch.setattr(cr.settings, "contabo_renewal_date", "2026-11-11")
    monkeypatch.setattr(cr.dg, "_deliver", lambda text, chats: 0)  # Telegram unreachable
    assert cr.check_and_send(at(6, 10)) is None
    monkeypatch.setattr(cr.dg, "_deliver", lambda text, chats: sent.append(text) or 1)
    assert cr.check_and_send(at(6, 11)) == "2026-11-11" and len(sent) == 1  # sent on the next pass
