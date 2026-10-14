"""Gainers & Losers in Telegram: commands, message format, schedule, once-only sending.
The movers and the Telegram API are faked; nothing leaves the machine."""

import re
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import User
from app.services import telegram_digest_service as dg
from app.services import telegram_notify_service as tg

KL = dg.TZ


def at(y, m, d, h=8, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=KL)


def coins(*items):
    return [{"symbol": s, "pct_change": p, "price_now": price} for s, p, price in items]


@pytest.fixture
def env(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    for mod in (tg, dg):
        monkeypatch.setattr(mod, "SessionLocal", maker)
    monkeypatch.setattr(dg, "_STATE_FILE", tmp_path / "sent.json")
    monkeypatch.setattr(tg.settings, "telegram_bot_token", "x")
    db = maker()
    db.add(User(id=1, full_name="A", email="a@x.com", password_hash="h", telegram_chat_id=42))
    db.add(User(id=2, full_name="B", email="b@x.com", password_hash="h"))  # not connected
    db.commit()
    db.close()
    sent = []
    monkeypatch.setattr(tg, "_send", lambda chat_id, text: sent.append((chat_id, text)))
    ready = {"24h": True, "7d": True, "30d": True}

    def fake_movers(db, bucket, window, direction, limit=30):
        if not ready[window]:
            return {"status": "collecting", "days_remaining": 3, "hours_remaining": 70, "coins": []}
        rows = coins(("SOL", 12.345, 150.2), ("PEPE", 3.0, 0.000005)) if direction == "gainers" else coins(("ETH", -4.5, 2500))
        return {"status": "ready", "days_remaining": 0, "hours_remaining": 0, "coins": rows, "bucket": bucket}

    monkeypatch.setattr(dg.ps, "get_movers", fake_movers)
    yield sent, ready
    engine.dispose()


def test_command_names_and_bands():
    assert dg.command_window("gainers_losers_24h") == "24h"
    assert dg.command_window("gainer-losers-24H") == "24h"  # the spelling typed by hand
    assert dg.command_window("gainers_losers_7d") == "7d"
    assert dg.command_window("gainers_losers_1m") == "30d"
    assert dg.command_window("gainers_losers_9d") is None and dg.command_window("alerts") is None
    assert [dg.parse_band(a) for a in ("", "200", "top300", "150", "x")] == [100, 200, 300, None, None]


def test_message_format(env, monkeypatch):
    monkeypatch.setattr(tg, "_fmt_price", lambda v: f"USD<{v}>")  # the frontend injects _fmt_usd here
    text, ready = dg.build_message("24h")
    assert ready and "24H · Top 100" in text and "Gainers" in text and "Losers" in text
    assert "<b>SOL</b>  +12.35%" in text and "-4.50%" in text
    assert "USD<150.2>" in text and "USD<2500>" in text  # every price goes through the shared formatter
    assert "Rank 101-200" in dg.build_message("24h", 200)[0]


def test_collecting_window_says_so(env):
    _, ready = env
    ready["7d"] = False
    text, ok = dg.build_message("7d")
    assert not ok and "still collecting" in text and "3 day(s)" in text


def test_commands_via_handle_message(env):
    sent, _ = env
    msg = lambda t, chat=42: {"text": t, "chat": {"id": chat, "type": "private"}}  # noqa: E731
    tg.handle_message(msg("/gainers_losers_24h"))
    tg.handle_message(msg("/gainer-losers-7D 200"))
    tg.handle_message(msg("/gainers_losers_1m banana"))
    tg.handle_message(msg("/gainers_losers_24h", chat=999))
    assert "24H · Top 100" in sent[0][1]
    assert "7D · Rank 101-200" in sent[1][1]
    assert sent[2][1].startswith("Usage:")
    assert "not connected" in sent[3][1]


def test_schedule_rules():
    assert dg.is_due("24h", at(2026, 10, 14)) and dg.is_due("24h", at(2026, 10, 14, 19, 59))
    assert not dg.is_due("24h", at(2026, 10, 14, 7, 59)) and not dg.is_due("24h", at(2026, 10, 14, 20, 0))
    assert dg.is_due("7d", at(2026, 10, 12)) and not dg.is_due("7d", at(2026, 10, 14))  # Monday only
    assert dg.is_due("30d", at(2026, 11, 1)) and not dg.is_due("30d", at(2026, 11, 2))  # 1st only


def test_digest_sent_once_per_period_and_only_to_connected(env):
    sent, _ = env
    monday_first = at(2026, 6, 1)  # a Monday and the 1st: all three boards due
    assert dg.check_and_send(monday_first) == ["24h", "7d", "30d"]
    assert len(sent) == 3 and all(chat == 42 for chat, _ in sent)  # user 2 has no Telegram
    assert dg.check_and_send(at(2026, 6, 1, 9)) == []  # same period: nothing again
    assert dg.check_and_send(at(2026, 6, 2)) == ["24h"]  # next day: only the daily board
    assert len(sent) == 4


def test_collecting_window_is_skipped_then_retried(env):
    sent, ready = env
    ready["7d"] = False
    assert dg.check_and_send(at(2026, 6, 1)) == ["24h", "30d"]
    assert dg.check_and_send(at(2026, 6, 1, 10)) == []  # 7d still collecting
    ready["7d"] = True
    assert dg.check_and_send(at(2026, 6, 1, 11)) == ["7d"]  # sent once it is ready, inside the grace period


def test_band_commands():
    assert dg.parse_command("gainers_losers_24h_top100") == ("24h", 100)
    assert dg.parse_command("gainers_losers_7d_top200") == ("7d", 200)
    assert dg.parse_command("gainer-losers-1M-top500") == ("30d", 500)  # hand-typed spelling
    assert dg.parse_command("gainers_losers_24h") == ("24h", None)
    assert dg.parse_command("gainers_losers_24h_top150") is None and dg.parse_command("gainers_losers_24h_top600") is None


def test_menu_entries_are_valid_for_telegram():
    names = [c["command"] for c in dg.COMMANDS]
    assert len(names) == 18 and len(set(names)) == 18  # 3 windows x (default + 5 bands)
    assert all(re.fullmatch(r"[a-z0-9_]{1,32}", n) for n in names)
    assert all(1 <= len(c["description"]) <= 256 for c in dg.COMMANDS)
    assert "gainers_losers_30d_top200" not in names and "gainers_losers_1m_top200" in names


def test_band_command_replies_with_that_band(env):
    sent, _ = env
    msg = lambda t: {"text": t, "chat": {"id": 42, "type": "private"}}  # noqa: E731
    tg.handle_message(msg("/gainers_losers_24h_top200"))
    tg.handle_message(msg("/gainers_losers_7d_top500@test_bot"))
    tg.handle_message(msg("/gainers_losers_1m_top100"))
    assert "24H · Rank 101-200" in sent[0][1]
    assert "7D · Rank 401-500" in sent[1][1]
    assert "1 Month · Top 100" in sent[2][1]


# ---- past days -----------------------------------------------------------------------------

from datetime import date  # noqa: E402

from app.models.movers_daily import MoversDaily  # noqa: E402


def _save_day(maker, day, window="24h"):
    rows = [
        ("SOL", 5, 10.0, 150.0), ("DOGE", 150, 4.0, 0.2),  # gainers in Top 100 / 101-200
        ("ETH", 2, -6.0, 2500.0), ("ADA", 120, -3.0, 0.5),  # losers
    ]
    db = maker()
    for i, (sym, rank, pct, price) in enumerate(rows):
        db.add(MoversDaily(day=day, window=window, coin_id=i + 1, symbol=sym, name=sym, cmc_rank=rank, price_now=price,
                           price_then=price / (1 + pct / 100), pct_change=pct, volume_24h=1e6,
                           then_at=datetime(2026, 10, 12, 23, 42), now_at=datetime(2026, 10, 13, 23, 42)))
    db.commit()
    db.close()


def test_date_command_parsing():
    assert dg.parse_date_command("gainers_losers_13_10_2026") == (date(2026, 10, 13), "24h", None)
    assert dg.parse_date_command("gainers_losers_7d_top200_13_10_2026") == (date(2026, 10, 13), "7d", 200)
    assert dg.parse_date_command("gainers_losers_1m_top300_13_10_2026") == (date(2026, 10, 13), "30d", 300)
    assert dg.parse_date_command("gainers_losers_24h_13_10_2026") == (date(2026, 10, 13), "24h", None)
    assert dg.parse_date_command("gainers_losers_top200_13_10_2026") == (date(2026, 10, 13), "24h", 200)
    assert dg.parse_date_command("gainer-losers-1M-1-2-2026") == (date(2026, 2, 1), "30d", None)
    assert dg.parse_date_command("gainers_losers_31_02_2026") == (None, "24h", None)  # not a real day
    assert dg.parse_date_command("gainers_losers_top150_13_10_2026") is None
    assert dg.parse_date_command("gainers_losers_13_10_2026_7d") is None  # the old order (date before the window)
    assert dg.parse_date_command("gainers_losers_24h") is None and dg.parse_command("gainers_losers_13_10_2026") is None


def test_past_day_board_and_missing_day(env):
    sent, _ = env
    _save_day(tg.SessionLocal, date(2026, 10, 13))
    msg = lambda t: {"text": t, "chat": {"id": 42, "type": "private"}}  # noqa: E731
    tg.handle_message(msg("/gainers_losers_13_10_2026"))
    tg.handle_message(msg("/gainers_losers_24h_top200_13_10_2026"))
    tg.handle_message(msg("/gainers_losers_7d_13_10_2026"))  # nothing saved for that window
    tg.handle_message(msg("/gainers_losers_01_01_2020"))
    tg.handle_message(msg("/gainers_losers_31_02_2026"))
    top100, top200 = sent[0][1], sent[1][1]
    assert "24H · Top 100 · 13 Oct 2026" in top100 and "Saved board, as of 13 Oct 23:42 UTC" in top100
    assert "SOL" in top100 and "+10.00%" in top100 and "ETH" in top100 and "DOGE" not in top100
    assert "Rank 101-200" in top200 and "DOGE" in top200 and "ADA" in top200 and "SOL" not in top200
    assert "No saved 7D board for 13 Oct 2026" in sent[2][1]
    assert "No saved 24H board for 1 Jan 2020. Saved boards exist from 13 Oct 2026 to 13 Oct 2026" in sent[3][1]
    assert "not a valid date" in sent[4][1]
