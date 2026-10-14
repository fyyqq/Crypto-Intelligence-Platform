"""/site_health: levels, ordering, a failing check never hides the others, and
the command is for linked chats only. Database in-memory SQLite; no network."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.price_snapshot import PriceSnapshot
from app.models.user import User
from app.services import site_health_service as sh
from app.services import telegram_notify_service as tg


def test_ago_and_levels():
    assert sh._ago(5) == "5s ago" and sh._ago(600) == "10 min ago" and sh._ago(7200) == "2 h ago"
    assert sh._ago(3 * 86400) == "3 days ago"
    assert [sh._age_level(a, 100, 200) for a in (50, 150, 500)] == ["ok", "warn", "bad"]


def test_message_sorts_problems_first_and_counts():
    msg = sh.build_message([("ok", "Database: fine"), ("bad", "CoinMarketCap: credits USED UP"), ("warn", "News: slow"),
                            ("bad", "Alerts: stopped")])
    lines = msg.splitlines()
    assert "2 problems, 1 warning" in lines[1]
    assert [ln[0] for ln in lines[3:]] == ["🔴", "🔴", "🟠", "🟢"]
    assert "Everything looks normal" in sh.build_message([("ok", "a"), ("ok", "b")])
    assert "1 warning" in sh.build_message([("ok", "a"), ("warn", "b")]) and "problem" not in sh.build_message([("warn", "b")])


def test_text_is_html_escaped():
    assert "&lt;b&gt;" in sh.build_message([("bad", "x <b> y")])


def test_a_failing_check_is_reported_not_raised(monkeypatch):
    def boom():
        raise RuntimeError("nope")

    monkeypatch.setattr(sh, "CHECKS", [lambda: ("ok", "Fine"), boom])
    res = sh.run_checks()
    assert res[0] == ("ok", "Fine") and res[1][0] == "bad" and "check failed" in res[1][1]


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(sh, "SessionLocal", maker)
    monkeypatch.setattr(tg, "SessionLocal", maker)
    d = maker()
    d.add(User(id=1, full_name="A", email="a@x.com", password_hash="h", telegram_chat_id=42))
    d.commit()
    d.close()
    yield maker
    engine.dispose()


def _snap(maker, minutes_ago, coins=3):
    from datetime import timedelta

    at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes_ago)
    d = maker()
    for i in range(coins):
        d.add(PriceSnapshot(coin_id=i + 1, symbol=f"C{i}", price_usd=1, cmc_rank=i + 1, volume_24h=1, synced_at=at))
    d.commit()
    d.close()


def test_snapshot_check_levels(db):
    assert sh.check_snapshots()[0] == "bad"  # nothing stored
    _snap(db, 30)
    lv, text = sh.check_snapshots()
    assert lv == "ok" and "3 coins" in text
    _snap(db, 120)  # an older row does not matter, the newest counts
    assert sh.check_snapshots()[0] == "ok"


def test_stale_snapshot_is_flagged(db):
    _snap(db, 150)
    assert sh.check_snapshots()[0] == "warn"
    d = db()
    d.query(PriceSnapshot).delete()
    d.commit()
    d.close()
    _snap(db, 400)
    assert sh.check_snapshots()[0] == "bad"


def test_command_for_linked_chats_only(db, monkeypatch):
    sent = []
    monkeypatch.setattr(tg, "_send", lambda chat, text: sent.append((chat, text)))
    monkeypatch.setattr(sh, "run_checks", lambda: [("ok", "Database: fine")])
    tg.handle_message({"text": "/site_health", "chat": {"id": 42, "type": "private"}})
    tg.handle_message({"text": "/site_health", "chat": {"id": 999, "type": "private"}})
    assert "Site health" in sent[0][1] and "Database: fine" in sent[0][1]
    assert "not connected" in sent[1][1]
    assert any(c["command"] == "site_health" for c in tg.COMMANDS)
    assert "/site_health" in tg.commands_overview()
