"""Notifications: the service, and that a triggered price alert creates one.
In-memory SQLite shared across sessions; never touches the real database."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.notification import Notification
from app.services import alert_service, notification_service as ns


@pytest.fixture
def factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(ns, "SessionLocal", maker)
    monkeypatch.setattr(alert_service, "SessionLocal", maker)
    yield maker
    engine.dispose()


def test_notify_list_unread_and_read(factory):
    a = ns.notify(1, "system", "Hello", "Body", link_url="/x")
    ns.notify(1, "system", "Second")
    ns.notify(2, "system", "Someone else's")
    assert ns.unread_count(1) == 2 and ns.unread_count(2) == 1
    rows = ns.list_for_user(1)
    assert [r["title"] for r in rows] == ["Second", "Hello"]  # newest first, own account only
    assert rows[1]["kind_label"] == "Announcement" and rows[1]["link_url"] == "/x" and rows[1]["read"] is False
    ns.mark_read(1, a)
    assert ns.unread_count(1) == 1
    ns.mark_read(2, a)  # another account can't touch it
    assert ns.unread_count(1) == 1
    ns.mark_all_read(1)
    assert ns.unread_count(1) == 0 and ns.unread_count(2) == 1


def test_delete_and_clear_are_scoped_to_the_account(factory):
    a = ns.notify(1, "system", "A")
    ns.notify(1, "system", "B")
    ns.notify(2, "system", "C")
    ns.delete(2, a)  # not theirs: ignored
    assert len(ns.list_for_user(1)) == 2
    ns.delete(1, a)
    assert [r["title"] for r in ns.list_for_user(1)] == ["B"]
    ns.clear_all(1)
    assert ns.list_for_user(1) == [] and len(ns.list_for_user(2)) == 1


def test_unknown_kind_or_tone_is_rejected(factory):
    with pytest.raises(ValueError, match="Unknown notification kind"):
        ns.notify(1, "made_up", "x")
    with pytest.raises(ValueError, match="Unknown tone"):
        ns.notify(1, "system", "x", tone="loud")


def test_old_and_overflow_notifications_are_pruned(factory, monkeypatch):
    db = factory()
    db.add(Notification(user_id=1, kind="system", title="ancient", created_at=datetime.now(timezone.utc) - timedelta(days=ns.RETENTION_DAYS + 1)))
    db.commit()
    db.close()
    monkeypatch.setattr(ns, "MAX_PER_USER", 3)
    for i in range(5):
        ns.notify(1, "system", f"n{i}")
    titles = [r["title"] for r in ns.list_for_user(1)]
    assert "ancient" not in titles and len(titles) == 3 and titles[0] == "n4"


def test_triggered_alert_creates_exactly_one_notification(factory):
    alert_id = alert_service.add_alert(7, 1027, "Ethereum", "ETH", "above", 4000.0)
    assert alert_service.mark_triggered(7, alert_id, 4012.5, "$4,000", "$4,012.50") is True
    assert alert_service.mark_triggered(7, alert_id, 4013.0, "$4,000", "$4,013") is False  # second tab
    rows = ns.list_for_user(7)
    assert len(rows) == 1
    n = rows[0]
    assert n["kind"] == "price_alert" and n["tone"] == "up" and n["link_url"] == "/coin/eth"
    assert n["title"] == "ETH rose above $4,000"
    assert "now at $4,012.50" in n["body"] and n["image_url"].endswith("/1027.png")


def test_below_alert_is_a_down_notification(factory):
    alert_id = alert_service.add_alert(7, 1, "Bitcoin", "BTC", "below", 50000.0)
    alert_service.mark_triggered(7, alert_id, 49000.0, "$50,000", "$49,000")
    n = ns.list_for_user(7)[0]
    assert n["tone"] == "down" and n["title"] == "BTC fell below $50,000"


def test_untriggered_or_missing_alert_makes_no_notification(factory):
    assert alert_service.mark_triggered(7, 999, 1.0) is False
    assert ns.list_for_user(7) == []


# ---- local dev auto-login guard ------------------------------------------------
def test_is_local_host():
    from app.services.auth_service import is_local_host

    for ok in ("localhost", "localhost:3000", "127.0.0.1:3000", "127.0.0.1", "[::1]:3000", "app.localhost:3000"):
        assert is_local_host(ok), ok
    for bad in ("", "repace.fyqqflow.com", "repace.fyqqflow.com:443", "207.180.233.86", "evil.com:3000", "localhost.evil.com", "127.0.0.1.evil.com"):
        assert not is_local_host(bad), bad


def test_dev_auto_login_needs_the_env_key_and_a_local_host(factory, monkeypatch):
    from app.models.user import User
    from app.services import auth_service

    monkeypatch.setattr(auth_service, "SessionLocal", factory)
    db = factory()
    db.add(User(full_name="Dev Tester", email="dev-tester@example.com", password_hash="x"))
    db.commit()
    db.close()

    monkeypatch.setattr(auth_service.settings, "dev_auto_login_email", "")
    assert auth_service.dev_auto_login("localhost:3000").ok is False  # key not set (e.g. the live server)

    monkeypatch.setattr(auth_service.settings, "dev_auto_login_email", "dev-tester@example.com")
    assert auth_service.dev_auto_login("repace.fyqqflow.com").ok is False  # real domain, even with the key
    assert auth_service.dev_auto_login("207.180.233.86").ok is False
    ok = auth_service.dev_auto_login("localhost:3000")
    assert ok.ok and ok.user_name == "Dev Tester"

    monkeypatch.setattr(auth_service.settings, "dev_auto_login_email", "nobody@example.com")
    assert auth_service.dev_auto_login("localhost:3000").ok is False  # unknown account


# ---- external channels (Telegram/WhatsApp later) -------------------------------
def test_triggered_alert_reaches_external_channels_once(factory, monkeypatch):
    sent = []
    monkeypatch.setattr(ns, "_CHANNELS", [])
    ns.register_channel(lambda uid, p: sent.append((uid, p["title"], p["link_url"])))
    ns.register_channel(lambda uid, p: (_ for _ in ()).throw(RuntimeError("channel down")))  # a broken channel
    alert_id = alert_service.add_alert(7, 1, "Bitcoin", "BTC", "above", 50000.0)
    assert alert_service.mark_triggered(7, alert_id, 51000.0, "$50,000.00", "$51,000.00")
    assert not alert_service.mark_triggered(7, alert_id, 51000.0)  # second tab/watcher: nothing sent again
    assert sent == [(7, "BTC rose above $50,000.00", "/coin/btc")]
    assert len(ns.list_for_user(7)) == 1  # the broken channel didn't block the saved notification
