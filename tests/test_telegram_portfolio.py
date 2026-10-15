"""Telegram /portfolio: the MEXC balance, profit/loss, holdings and limit / stop orders for the account owner only.
MEXC is served from tests/fixtures/mexc_demo.json (made-up data); Telegram and the database are fakes."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import User
from app.services import mexc_service as m
from app.services import telegram_notify_service as tg

FIXTURE = str(Path(__file__).parent / "fixtures" / "mexc_demo.json")


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(tg, "SessionLocal", maker)
    db = maker()
    db.add(User(id=1, full_name="Owner", email="owner@x.com", password_hash="h", telegram_chat_id=111))
    db.add(User(id=2, full_name="Other", email="other@x.com", password_hash="h", telegram_chat_id=222))
    db.commit()
    db.close()
    monkeypatch.setattr(m.settings, "mexc_fixture_file", FIXTURE)
    monkeypatch.setattr(m.settings, "mexc_viewer_emails", "owner@x.com")
    monkeypatch.setattr(m, "_cache", {
        "raw_at": 0.0, "ok_at": 0.0, "balances": [], "orders": [], "error": "", "prices_at": 0.0, "tickers": {},
        "trades": {}, "coin_orders": {}, "open_orders_all": None,
    })
    monkeypatch.setattr(m, "_rate", {"until": 0.0, "strikes": 0})
    monkeypatch.setattr(m, "get_costs", lambda user_id: {})
    sent = []
    monkeypatch.setattr(tg, "_send", lambda chat_id, text: sent.append((chat_id, text)))
    yield sent
    engine.dispose()


def _say(chat_id, text="/portfolio"):
    tg.handle_message({"text": text, "message_id": 5, "chat": {"id": chat_id, "type": "private"}})


def test_the_owner_gets_balance_pnl_holdings_and_limit_and_stop_orders(env):
    _say(111)
    (chat_id, text), = env
    assert chat_id == 111
    assert "MEXC portfolio" in text and "(demo data)" in text
    assert "Total balance: <b>$8,249.22</b>" in text and "P/L: 🟢 +$125.57 (+2.04%)" in text
    assert "24h:" in text and "Stablecoins: $1,243.50" in text and "In open orders: $1,210.56" in text
    for coin in ("BTC", "ETH", "SUI", "SOL", "PEPE", "LINK", "USDT"):
        assert f"<b>{coin}</b>" in text
    assert "<b>SUI</b> 820 @ $1.0412 = $853.78 · avg $1.22 · P/L 🔴 -$146.62 (-14.66%)" in text  # price via _fmt_price
    assert "Open orders (4)" in text
    assert "🔴 Sell <b>SOL</b> · Stop-limit $149 (trigger $150)" in text  # the stop order
    assert "🔴 Sell <b>SUI</b> · Limit $1.35" in text and "🟢 Buy <b>ETH</b> · Limit $2900" in text
    assert "+ 2 small balances" in text and len(text) < 4096


def test_another_linked_account_gets_one_neutral_line_and_mexc_is_never_called(env, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("MEXC must not be called for a non-viewer")

    monkeypatch.setattr(m, "portfolio", boom)
    _say(222)
    assert env == [(222, "Portfolio is not available for this account.")]


def test_an_unlinked_chat_is_told_to_connect_and_sees_nothing(env):
    _say(999)
    assert len(env) == 1 and "not connected" in env[0][1] and "$" not in env[0][1]


def test_when_mexc_fails_the_message_says_so_without_details(env, monkeypatch):
    monkeypatch.setattr(m.settings, "mexc_fixture_file", "")
    monkeypatch.setattr(m.settings, "mexc_api_key", "KEY123")
    monkeypatch.setattr(m.settings, "mexc_api_secret", "SECRET456")
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: (_ for _ in ()).throw(m.requests.ConnectionError("down")))
    _say(111)
    text = env[0][1]
    assert "unavailable" in text and "could not be reached" in text
    assert "KEY123" not in text and "SECRET456" not in text and "signature" not in text


def test_a_long_portfolio_is_cut_at_a_line_end_under_telegrams_limit(env, monkeypatch):
    base = m.portfolio(1)
    many = dict(base, holdings=[dict(base["holdings"][1], asset=f"C{i}") for i in range(200)])
    monkeypatch.setattr(m, "portfolio", lambda user_id: many)
    text = tg.format_portfolio(1)
    assert len(text) <= tg._PORTFOLIO_MAX_CHARS + 2 and text.endswith("…")
    assert text.count("<b>") == text.count("</b>")  # never cut inside a tag


def test_the_command_is_in_the_bot_menu_and_the_overview(env):
    assert any(c["command"] == "portfolio" for c in tg.COMMANDS)
    assert "/portfolio" in tg.commands_overview()
