"""Telegram /currency-converter and /pnl-calculator: $ converts to MYR, RM to USD; profit and loss in either currency."""

import time

import pytest

from app.services import calc_service as c
from app.services import fx_service
from app.services import telegram_notify_service as tg

RATE = 4.0


@pytest.fixture(autouse=True)
def rate(monkeypatch):
    monkeypatch.setattr(fx_service, "get_rate", lambda quote="MYR": {"rate": RATE, "note": "Yahoo Finance · live", "as_of": time.time()})


def test_parse_money_accepts_the_symbol_forms_and_the_template_braces():
    cases = {"$1000": ("USD", 1000.0), "RM1000": ("MYR", 1000.0), "rm 250": ("MYR", 250.0), "{RM1000}": ("MYR", 1000.0),
             "${$1000}": ("USD", 1000.0), "1,000.50": ("USD", 1000.5), "USD 5": ("USD", 5.0), "myr7.5": ("MYR", 7.5)}
    for text, want in cases.items():
        assert c.parse_money(text) == want, text
    assert all(c.parse_money(t) is None for t in ("", "abc", "$", "RM", "$-5", "1e3"))


def test_parse_pnl_forms():
    assert c.parse_pnl("$1000 + 50%") == ("USD", 1000.0, 1, 50.0)
    assert c.parse_pnl("$1000 - 50%") == ("USD", 1000.0, -1, 50.0)
    assert c.parse_pnl("RM4000 - 25%") == ("MYR", 4000.0, -1, 25.0)
    assert c.parse_pnl("$1000+50%") == ("USD", 1000.0, 1, 50.0) and c.parse_pnl("$1000 +50") == ("USD", 1000.0, 1, 50.0)
    assert c.parse_pnl("${$1000} ${+} ${50%}") == ("USD", 1000.0, 1, 50.0)  # the usage template typed as it is
    assert c.parse_pnl("${RM1000} ${-} ${50%}") == ("MYR", 1000.0, -1, 50.0)
    assert all(c.parse_pnl(t) is None for t in ("", "$1000", "$1000 +", "$1000 * 5", "+ 50%", "$1000 + abc"))


def test_converter_dollars_to_ringgit_and_back():
    usd = c.converter_message("$1000")
    assert "$1,000.00 = RM4,000.00" in usd and "1 USD = 4.0000 MYR" in usd and "1 MYR = 0.2500 USD" in usd and "Yahoo Finance" in usd
    myr = c.converter_message("RM1000")
    assert "RM1,000.00 = $250.00" in myr
    assert c.converter_message("{RM1000}") == myr
    assert c.converter_message("") == c.CONVERTER_USAGE and c.converter_message("hello") == c.CONVERTER_USAGE


def test_pnl_profit_loss_and_the_other_currency():
    up = c.pnl_message("$1000 + 50%")
    assert "<b>$1,500.00</b>" in up and "$1,000.00 + 50% = $1,500.00" in up and "Profit +$500.00 (+50%)" in up
    assert "In MYR: <b>RM6,000.00</b> (+RM2,000.00)" in up and "1 USD = 4.0000 MYR" in up
    down = c.pnl_message("$1000 - 50%")
    assert "<b>$500.00</b>" in down and "$1,000.00 - 50% = $500.00" in down and "Loss -$500.00 (-50%)" in down and "📉" in down
    myr = c.pnl_message("RM4000 - 25%")
    assert "<b>RM3,000.00</b>" in myr and "RM4,000.00 - 25% = RM3,000.00" in myr and "In USD: <b>$750.00</b> (-$250.00)" in myr
    assert "In USD" in c.pnl_message("RM4000 + 12.5%") and "RM4,500.00" in c.pnl_message("RM4000 + 12.5%")
    clamped = c.pnl_message("$1000 - 150%")
    assert "<b>$0.00</b>" in clamped and "can't be more than 100%" in clamped
    assert c.pnl_message("$1000") == c.PNL_USAGE and c.pnl_message("") == c.PNL_USAGE


def test_without_a_live_rate_the_converter_says_so_and_pnl_still_works(monkeypatch):
    monkeypatch.setattr(fx_service, "get_rate", lambda quote="MYR": None)
    assert c.converter_message("$1000") == c.UNAVAILABLE
    text = c.pnl_message("$1000 + 50%")
    assert "$1,500.00" in text and "In MYR" not in text


def test_the_bot_answers_both_commands_with_and_without_a_hyphen(monkeypatch):
    sent = []
    monkeypatch.setattr(tg, "_send", lambda chat_id, text: sent.append(text))
    monkeypatch.setattr(tg, "_user_for_chat", lambda chat_id: 1)
    say = lambda text: tg.handle_message({"text": text, "message_id": 1, "chat": {"id": 5, "type": "private"}})  # noqa: E731
    say("/currency-converter $1000")
    say("/currency_converter RM1000")
    say("/pnl-calculator $1000 + 50%")
    say("/pnl_calculator@my_bot RM4000 - 25%")
    say("/pnl-calculator ${$1000} ${-} ${50%}")
    say("/currency-converter")
    assert "RM4,000.00" in sent[0] and "$250.00" in sent[1] and "$1,500.00" in sent[2] and "RM3,000.00" in sent[3] and "$500.00" in sent[4]
    assert sent[5] == c.CONVERTER_USAGE
    names = [x["command"] for x in tg.COMMANDS]
    assert "currency_converter" in names and "pnl_calculator" in names
    overview = tg.commands_overview()
    assert "/currency-converter $1000" in overview and "/pnl-calculator $1000 + 50%" in overview


def test_unlinked_chats_get_the_not_connected_line(monkeypatch):
    sent = []
    monkeypatch.setattr(tg, "_send", lambda chat_id, text: sent.append(text))
    monkeypatch.setattr(tg, "_user_for_chat", lambda chat_id: None)
    tg.handle_message({"text": "/pnl-calculator $1000 + 50%", "message_id": 1, "chat": {"id": 9, "type": "private"}})
    assert "not connected" in sent[0]
