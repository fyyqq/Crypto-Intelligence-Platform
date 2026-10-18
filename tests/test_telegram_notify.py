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


def test_the_alerts_command_and_the_removed_alert_coin_command(env):
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
    tg.handle_message(_msg("/alert eth"))  # removed 2026-10-18: the bot no longer answers /alert {coin}
    tg.handle_message(_msg("/alert@test_bot $ETH"))
    tg.handle_message(_msg("/alert"))
    out = _sent(calls)
    assert len(out) == 2  # only /alerts and /command1 answered
    assert "Active alerts (3)" in out[0] and "BTC" in out[0] and "ETH" in out[0] and "SOL" not in out[0] and "9999" not in out[0]
    assert out[1] == out[0]
    assert not any(c["command"] == "alert" for c in tg.COMMANDS)


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


# ---- /clear_chat ----------------------------------------------------------------------------

def test_clear_chat_deletes_ids_downwards_in_batches_of_100(env, monkeypatch):
    calls, _ = env
    monkeypatch.setattr(tg.time, "sleep", lambda s: None)
    tried = tg.clear_chat(42, 250)
    deletes = [p for m, p in calls if m == "deleteMessages"]
    assert [(p["message_ids"][0], p["message_ids"][-1], len(p["message_ids"])) for p in deletes] == [(250, 151, 100), (150, 51, 100), (50, 1, 50)]
    assert all(p["chat_id"] == 42 for p in deletes) and tried == 250  # never below message id 1


def test_clear_chat_is_capped_and_survives_a_failing_batch(env, monkeypatch):
    calls, _ = env
    monkeypatch.setattr(tg.time, "sleep", lambda s: None)
    real = tg._api

    def flaky(method, **params):
        if method == "deleteMessages" and params["message_ids"][0] == 4900:
            raise RuntimeError("Too Many Requests")
        return real(method, **params)

    monkeypatch.setattr(tg, "_api", flaky)
    tried = tg.clear_chat(42, 5000, max_ids=300)
    ids = [i for m, p in calls if m == "deleteMessages" for i in p["message_ids"]]
    assert tried == 300 and max(ids) == 5000 and min(ids) == 4701
    assert not set(range(4801, 4901)) & set(ids)  # the batch that failed (4900..4801) was skipped, the others ran
    assert {4900 + 100, 4800 - 99} <= set(ids)


def test_clear_chat_command_works_in_any_private_chat_and_confirms(env, monkeypatch):
    calls, _ = env
    monkeypatch.setattr(tg.time, "sleep", lambda s: None)
    monkeypatch.setattr(tg, "CLEAR_MAX_IDS", 120)
    tg.handle_message({"message_id": 500, "text": "/clear_chat", "chat": {"id": 999, "type": "private"}})  # 999 is not linked
    deletes = [p for m, p in calls if m == "deleteMessages"]
    assert [p["message_ids"][0] for p in deletes] == [500, 400] and deletes[0]["chat_id"] == 999
    assert 500 in deletes[0]["message_ids"]  # the command message itself goes too
    confirm = [p for m, p in calls if m == "sendMessage"]
    assert len(confirm) == 1 and "Chat cleared" in confirm[0]["text"] and "48 hours" in confirm[0]["text"]
    n = len(calls)
    tg.handle_message({"message_id": 9, "text": "/clear_chat", "chat": {"id": 7, "type": "group"}})  # groups are ignored
    assert len(calls) == n


def test_clear_chat_is_in_the_menu_and_the_overview():
    assert any(c["command"] == "clear_chat" for c in tg.COMMANDS)
    assert "/clear_chat" in tg.commands_overview()


def test_a_triggered_alert_is_retried_when_telegram_hiccups(monkeypatch):
    sent, calls = [], []
    monkeypatch.setattr(tg.settings, "telegram_bot_token", "x")
    monkeypatch.setattr(tg, "chat_id_for", lambda uid: 42)
    monkeypatch.setattr(tg.time, "sleep", lambda s: None)

    def flaky(chat_id, text):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("network down")
        sent.append((chat_id, text))

    monkeypatch.setattr(tg, "_send", flaky)
    tg.send_channel(1, {"title": "ETH rose above $4,000", "body": "now at $4,012", "tone": "up"})
    assert len(calls) == 3 and sent[0][0] == 42 and "ETH rose above" in sent[0][1]
    monkeypatch.setattr(tg, "_send", lambda c, t: (_ for _ in ()).throw(RuntimeError("down for good")))
    with pytest.raises(RuntimeError):  # after the last attempt it still raises, so notification_service logs it
        tg.send_channel(1, {"title": "x"})
