"""Telegram /ai: the free AI usage message, and why a story can be without an AI summary."""
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import ai_budget  # noqa: E402
from app.services import ai_usage_service as u  # noqa: E402
from app.services import news_summary_service as ns  # noqa: E402
from app.services import telegram_notify_service as tg  # noqa: E402

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def _usage(**over):
    base = {"used": 22, "daily_limit": 50, "left_for_visits": 28, "visit_reserve": 30, "background_stops_at": 20, "blocked": False,
            "blocked_until": 0.0, "calls_last_hour": 3, "hourly_cap": 60}
    base.update(over)
    return base


def test_available_message_shows_used_left_and_the_reset(monkeypatch):
    monkeypatch.setattr(ai_budget, "usage", lambda now=None: _usage())
    text = u.build_message(NOW, account={"is_free_tier": True, "usage": 0, "limit": None})
    assert "🟢 <b>Available.</b>" in text and "<b>22 of 50</b>" in text and "<b>28</b> left for page visits" in text
    assert "▰▰▰▰▱▱▱▱▱▱" in text  # 22 of 50 = 4 of 10 blocks
    assert "This hour (web server): 3 of 60 calls" in text and "free tier" in text and "08:00" in text
    assert "local model" in text  # the Malay translation does not spend AI calls


def test_blocked_message_says_when_it_comes_back_and_that_the_key_is_shared(monkeypatch):
    until = datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(ai_budget, "usage", lambda now=None: _usage(used=28, blocked=True, blocked_until=until))
    text = u.build_message(NOW, account={})
    assert "🔴 <b>Free AI limit reached.</b>" in text and "26 Oct 08:00 (KL)" in text and "in 12 h 0 min" in text
    assert "another copy of the site" in text and "28 of 50" in text


def test_almost_used_up_and_no_limit_wording(monkeypatch):
    monkeypatch.setattr(ai_budget, "usage", lambda now=None: _usage(used=47, left_for_visits=3))
    assert "🟠 <b>Almost used up for today.</b>" in u.build_message(NOW, account={})
    monkeypatch.setattr(ai_budget, "usage", lambda now=None: _usage(daily_limit=0, left_for_visits=None, background_stops_at=None))
    assert "no daily limit set" in u.build_message(NOW, account={})


def test_the_usage_numbers_come_from_the_budget_file_and_the_limits(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_budget, "_STATE_FILE", tmp_path / "ai_budget.json")
    monkeypatch.setattr(ai_budget.settings, "openrouter_daily_limit", 50)
    monkeypatch.setattr(ai_budget.settings, "openrouter_visit_reserve", 30)
    now = datetime.now(timezone.utc).timestamp()
    (tmp_path / "ai_budget.json").write_text('{"day": "%s", "used": 12, "blocked_until": 0}' % ai_budget._today())
    got = ai_budget.usage(now)
    assert got["used"] == 12 and got["left_for_visits"] == 38 and got["background_stops_at"] == 20 and got["blocked"] is False
    (tmp_path / "ai_budget.json").write_text('{"day": "%s", "used": 50, "blocked_until": %s}' % (ai_budget._today(), now + 3600))
    assert ai_budget.usage(now)["blocked"] is True


def test_the_ai_command_is_in_the_menu_the_overview_and_answers_a_connected_chat(monkeypatch):
    assert {"command": "ai", "description": "AI usage today and the free AI limit left"} in tg.COMMANDS
    assert "/ai - " in tg.commands_overview()
    sent = []
    monkeypatch.setattr(tg, "_send", lambda chat_id, text, **kw: sent.append((chat_id, text)))
    monkeypatch.setattr(tg, "_user_for_chat", lambda chat_id: 1)
    monkeypatch.setattr(u, "build_message", lambda: "AI-USAGE-TEXT")
    for text in ("/ai", "/ai_usage", "/ai@RepaceBot"):
        tg.handle_message({"chat": {"id": 7, "type": "private"}, "text": text, "message_id": 1})
    assert sent == [(7, "AI-USAGE-TEXT")] * 3
    sent.clear()
    monkeypatch.setattr(tg, "_user_for_chat", lambda chat_id: None)
    tg.handle_message({"chat": {"id": 7, "type": "private"}, "text": "/ai", "message_id": 2})
    assert sent and "not connected" in sent[0][1]  # like /site_health, only a connected chat gets it


def test_a_story_without_a_summary_says_why(monkeypatch):
    monkeypatch.setattr(ns.settings, "openrouter_api_key", "k")
    monkeypatch.setattr(ai_budget, "blocked", lambda: True)
    assert "daily limit" in ns.summary_unavailable_reason(5) and "08:00" in ns.summary_unavailable_reason(5)
    monkeypatch.setattr(ai_budget, "blocked", lambda: False)
    monkeypatch.setattr(ai_budget, "in_cooldown", lambda key: key == "news:5")
    assert "a moment ago" in ns.summary_unavailable_reason(5)
    assert "No AI summary could be made" in ns.summary_unavailable_reason(6)
    monkeypatch.setattr(ns.settings, "openrouter_api_key", "")
    assert "not set up" in ns.summary_unavailable_reason(6)
