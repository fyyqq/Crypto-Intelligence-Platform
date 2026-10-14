"""OpenRouter daily budget: page-visit calls keep a reserve, a daily-limit 429 pauses everything until the reset."""

import json
import time
from datetime import datetime, timezone

import pytest

from app.services import ai_budget as ab

DAILY_429 = json.dumps({"error": {"message": "Rate limit exceeded: free-models-per-day", "code": 429,
                                   "metadata": {"headers": {"X-RateLimit-Limit": "50", "X-RateLimit-Remaining": "0",
                                                            "X-RateLimit-Reset": str(int((time.time() + 3600) * 1000))}}}})


@pytest.fixture(autouse=True)
def reset(monkeypatch, tmp_path):
    monkeypatch.setattr(ab, "_STATE_FILE", tmp_path / "budget.json")
    monkeypatch.setattr(ab, "_calls", ab.deque())
    monkeypatch.setattr(ab, "_failed_at", {})
    monkeypatch.setattr(ab.settings, "openrouter_daily_limit", 10)
    monkeypatch.setattr(ab.settings, "openrouter_visit_reserve", 4)
    monkeypatch.setattr(ab.settings, "openrouter_max_calls_per_hour", 0)


def test_background_work_stops_before_the_visit_reserve():
    with ab.background():
        assert [ab.allow_call() for _ in range(8)] == [True] * 6 + [False] * 2  # 10 - 4 reserved = 6
    assert [ab.allow_call() for _ in range(6)] == [True] * 4 + [False] * 2  # visits use the reserve, then the daily limit


def test_zero_means_unlimited_and_the_count_resets_each_utc_day(monkeypatch):
    monkeypatch.setattr(ab.settings, "openrouter_daily_limit", 0)
    assert all(ab.allow_call() for _ in range(30))
    monkeypatch.setattr(ab.settings, "openrouter_daily_limit", 2)
    ab._STATE_FILE.write_text(json.dumps({"day": "2020-01-01", "used": 99, "blocked_until": 0}))
    assert ab.allow_call() and json.loads(ab._STATE_FILE.read_text())["day"] == datetime.now(timezone.utc).date().isoformat()


def test_a_daily_limit_429_blocks_everything_until_the_reset_and_does_not_start_a_cooldown():
    assert ab.note_response(429, "upstream busy") is False and ab.note_response(500, DAILY_429) is False
    assert ab.allow_call() is True
    assert ab.note_response(429, DAILY_429) is True
    assert ab.blocked() and ab.allow_call() is False
    with ab.background():
        assert ab.allow_call() is False
    ab.mark_failed("news:1")
    assert ab.in_cooldown("news:1") is False  # retried as soon as the limit resets


def test_the_block_ends_at_the_reset_time(monkeypatch):
    ab.note_response(429, DAILY_429, now=time.time())
    st = json.loads(ab._STATE_FILE.read_text())
    st["blocked_until"] = time.time() - 1
    ab._STATE_FILE.write_text(json.dumps(st))
    assert ab.blocked() is False and ab.allow_call() is True


def test_a_429_without_a_reset_header_blocks_until_the_end_of_the_utc_day():
    assert ab.note_response(429, "Rate limit exceeded: free-models-per-day") is True
    assert 0 < json.loads(ab._STATE_FILE.read_text())["blocked_until"] - time.time() <= 86400


def test_an_unreadable_state_file_never_blocks_summaries(monkeypatch):
    monkeypatch.setattr(ab, "_STATE_FILE", ab._STATE_FILE.parent / "missing" / "deep" / "x.json")
    monkeypatch.setattr(ab.Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("read only")), raising=False)
    assert ab.allow_call() is True


def test_a_daily_limit_stops_the_retries_and_the_fallback_models(monkeypatch):
    from app.services import news_summary_service as ns

    posted = []

    class R:
        status_code = 429
        text = DAILY_429

        def raise_for_status(self):
            raise ns.requests.HTTPError("429")

    monkeypatch.setattr(ns.settings, "openrouter_api_key", "k")
    monkeypatch.setattr(ns.requests, "post", lambda *a, **k: posted.append(k["json"]["model"]) or R())
    monkeypatch.setattr(ns.time, "sleep", lambda s: None)
    assert ns._call_openrouter("x") is None
    assert len(posted) == 1  # no retry, no fallback model, no further request that would count against the limit
    assert ns._call_openrouter("x") is None and len(posted) == 1  # and nothing at all until the reset
    assert "qwen" not in " ".join(ns._FALLBACK_MODELS)


def test_filter_search_ranks_word_starts_first_and_fixes_the_ai_spelling(monkeypatch):
    pytest.importorskip("reflex")
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent / "frontend"))  # the Reflex app package root
    from frontend.state.coin_state import _search_names, fix_ai

    names = ["All narratives", "BNB Chain Ecosystem", "AI Agents", "Memes", "Generative AI", "DeFAI"]
    assert _search_names(names, "All narratives", "ai") == ["AI Agents", "Generative AI", "BNB Chain Ecosystem", "DeFAI"]
    assert _search_names(names, "All narratives", " zzz ") == []
    assert fix_ai("Ai Big Data") == "AI Big Data" and fix_ai("Ai") == "AI" and fix_ai("Daily Ai Memes") == "Daily AI Memes"
    assert fix_ai("Maintain") == "Maintain" and fix_ai("AI Agents") == "AI Agents" and fix_ai("") == ""
