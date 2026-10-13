"""CMC credit guard: optional calls pause when the remaining credits are
needed for the essential syncs until the monthly reset."""

from datetime import datetime, timedelta, timezone

from app.services import cmc_budget


def fake_usage(monkeypatch, left, days_to_reset, limit=15000):
    reset = (datetime.now(timezone.utc) + timedelta(days=days_to_reset)).isoformat().replace("+00:00", "Z")
    monkeypatch.setattr(cmc_budget, "usage", lambda force=False: {"limit": limit, "used": limit - left, "left": left, "reset_at": reset})


def test_plenty_left_allows_optional_calls(monkeypatch):
    fake_usage(monkeypatch, left=12000, days_to_reset=20)  # reserve 20 x 250 = 5,000
    assert cmc_budget.optional_calls_allowed()


def test_reserve_for_essentials_blocks_optional_calls(monkeypatch):
    fake_usage(monkeypatch, left=4000, days_to_reset=20)
    assert not cmc_budget.optional_calls_allowed()


def test_used_up_blocks(monkeypatch):
    fake_usage(monkeypatch, left=0, days_to_reset=19)
    assert not cmc_budget.optional_calls_allowed()


def test_unknown_usage_does_not_block(monkeypatch):
    monkeypatch.setattr(cmc_budget, "usage", lambda force=False: None)
    assert cmc_budget.optional_calls_allowed()
