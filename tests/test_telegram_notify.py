"""Telegram delivery: linking by /start code and sending. The Telegram API is
mocked and the database is in-memory SQLite; nothing leaves the machine."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import User
from app.services import telegram_notify_service as tg


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(tg, "SessionLocal", maker)
    monkeypatch.setattr(tg.settings, "telegram_bot_token", "x")
    monkeypatch.setattr(tg, "_bot_username", "test_bot")
    tg._codes.clear()
    db = maker()
    db.add(User(id=1, full_name="A", email="a@x.com", password_hash="h"))
    db.add(User(id=2, full_name="B", email="b@x.com", password_hash="h"))
    db.commit()
    db.close()
    calls = []
    updates = []

    def fake_api(method, **params):
        calls.append((method, params))
        return updates if method == "getUpdates" and "offset" not in params else []

    monkeypatch.setattr(tg, "_api", fake_api)
    yield calls, updates
    engine.dispose()


def _start(update_id, code, chat_id, chat_type="private"):
    return {"update_id": update_id, "message": {"text": f"/start {code}", "chat": {"id": chat_id, "type": chat_type}}}


def test_link_by_start_code(env):
    calls, updates = env
    code, link = tg.start_link(1)
    assert link == f"https://t.me/test_bot?start={code}"
    assert tg.poll_link(1) is False
    updates.append(_start(10, code, 555))
    assert tg.poll_link(1) is True
    assert tg.chat_id_for(1) == 555
    assert ("getUpdates", {"offset": 11, "timeout": 0}) in calls  # acknowledged
    assert any(m == "sendMessage" and p["chat_id"] == 555 for m, p in calls)


def test_wrong_code_and_group_chats_do_not_link(env):
    _, updates = env
    code, _ = tg.start_link(1)
    updates += [_start(1, "nope", 1), _start(2, code, 2, chat_type="group")]
    assert tg.poll_link(1) is False
    assert tg.chat_id_for(1) is None


def test_other_accounts_press_is_not_lost(env):
    _, updates = env
    code2, _ = tg.start_link(2)
    updates.append(_start(1, code2, 777))
    assert tg.poll_link(1) is False
    assert tg.chat_id_for(2) == 777


def test_send_channel_formats_and_skips_unconnected(env):
    calls, _ = env
    payload = {"title": "BTC <rose> above $1", "body": "a & b", "link_url": "/coin/btc", "tone": "up"}
    tg.send_channel(1, payload)  # not connected: nothing sent
    assert not any(m == "sendMessage" for m, _ in calls)
    tg._set_chat_id(1, 42)
    tg.send_channel(1, payload)
    sent = [p for m, p in calls if m == "sendMessage"][0]
    assert sent["chat_id"] == 42
    assert "&lt;rose&gt;" in sent["text"] and "a &amp; b" in sent["text"] and "/coin/btc" in sent["text"]


def test_disconnect(env):
    tg._set_chat_id(1, 42)
    tg.disconnect(1)
    assert tg.chat_id_for(1) is None


# ---- commands ------------------------------------------------------------------------------

from app.models.price_alert import PriceAlert  # noqa: E402


def _alert(maker, user_id, symbol, direction, price, triggered=False):
    from datetime import datetime, timezone

    db = maker()
    db.add(PriceAlert(user_id=user_id, cmc_id=1, coin_name=symbol, symbol=symbol, direction=direction,
                      target_price=price, triggered_at=datetime.now(timezone.utc) if triggered else None))
    db.commit()
    db.close()


def _msg(text, chat_id=42, chat_type="private"):
    return {"text": text, "chat": {"id": chat_id, "type": chat_type}}


def _sent(calls):
    return [p["text"] for m, p in calls if m == "sendMessage"]


def test_alerts_and_alert_commands(env):
    calls, _ = env
    maker = tg.SessionLocal
    tg._set_chat_id(1, 42)
    _alert(maker, 1, "BTC", "above", 100000)
    _alert(maker, 1, "ETH", "below", 2000)
    _alert(maker, 1, "ETH", "above", 3000)
    _alert(maker, 1, "ETH", "above", 9999, triggered=True)  # already triggered: hidden
    _alert(maker, 2, "SOL", "above", 500)  # another account: hidden
    tg.handle_message(_msg("/alerts"))
    tg.handle_message(_msg("/command1"))  # the name the bot menu had before
    tg.handle_message(_msg("/alert eth"))
    tg.handle_message(_msg("/alert@test_bot $ETH"))
    tg.handle_message(_msg("/alert DOGE"))
    tg.handle_message(_msg("/alert"))
    out = _sent(calls)
    assert "Active alerts (3)" in out[0] and "BTC" in out[0] and "ETH" in out[0] and "SOL" not in out[0]
    assert out[1] == out[0]
    assert "ETH alerts (2)" in out[2] and "below $2000" in out[2] and "9999" not in out[2] and "BTC" not in out[2]
    assert out[3] == out[2]
    assert "No active alerts for <b>DOGE</b>" in out[4]
    assert out[5] == "Usage: /alert ETH"


def test_commands_ignore_unlinked_chats_and_groups(env):
    calls, _ = env
    tg.handle_message(_msg("/alerts", chat_id=999))
    assert "not connected" in _sent(calls)[0]
    n = len(calls)
    tg.handle_message(_msg("/alerts", chat_type="group"))
    tg.handle_message(_msg("hello"))
    assert len(calls) == n


def test_start_with_code_links_through_handle_message(env):
    code, _ = tg.start_link(1)
    tg.handle_message(_msg(f"/start {code}", chat_id=88))
    assert tg.chat_id_for(1) == 88
