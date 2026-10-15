"""/price <ticker>: every coin with that ticker, priced from its chart pair, stored price marked when not live."""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.coin import Coin
from app.services import telegram_notify_service as tg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "frontend"))

from frontend import telegram_price  # noqa: E402


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    pairs = [{"exchange_name": "MEXC", "market_pair": "MEME/USDT", "is_dex": False, "price": 0.01, "volume_24h": 10.0}]
    db.add(Coin(cmc_id=1, symbol="MEME", name="Memecoin", slug="memecoin", cmc_rank=120, price_usd=0.01, cached_market_pairs=pairs))
    db.add(Coin(cmc_id=2, symbol="MEME", name="Meme Two", slug="meme-two", cmc_rank=900, price_usd=5.0))
    db.add(Coin(cmc_id=3, symbol="OTHER", name="Other", slug="other", cmc_rank=5, price_usd=1.0))
    db.commit()
    db.close()
    monkeypatch.setattr("app.core.database.SessionLocal", Session)
    monkeypatch.setattr("app.services.chart_override_service.all_overrides", lambda: {})
    monkeypatch.setattr("frontend.live_prices.fetch_live_prices_with_source", lambda items: {1: (0.0123, "chart")})  # coin 2 has no live feed
    return Session


def test_lists_every_coin_with_the_ticker_ranked_and_marks_unlive_prices(env):
    text = telegram_price.price_message("$meme")
    assert "2 coins with this ticker" in text
    assert text.index("Memecoin") < text.index("Meme Two")  # better rank first
    assert "$0.0123" in text and "TradingView chart: MEXC:MEMEUSDT" in text
    assert "last synced price" in text and "$5.00" in text  # the coin without a live feed is flagged
    assert "Other" not in text


def test_a_price_from_another_source_is_labelled_as_such(env, monkeypatch):
    monkeypatch.setattr("frontend.live_prices.fetch_live_prices_with_source", lambda items: {1: (0.5, "dex"), 2: (6.0, "exchange")})
    text = telegram_price.price_message("meme")
    assert "live DEX pool price" in text and "live exchange price" in text and "TradingView chart" not in text


def test_unknown_ticker(env):
    assert "No coin found" in telegram_price.price_message("nothing")


def test_command_replies_through_the_bot(env, monkeypatch):
    sent = []
    monkeypatch.setattr(tg, "_send", lambda chat_id, text: sent.append(text))
    monkeypatch.setattr(tg, "_user_for_chat", lambda chat_id: 1)
    monkeypatch.setattr(tg, "_price_command", lambda sym: f"price of {sym}")
    msg = {"chat": {"id": 5, "type": "private"}, "text": "/price $meme", "message_id": 1}
    tg.handle_message(msg)
    assert sent == ["price of meme"]
    sent.clear()
    tg.handle_message({**msg, "text": "/price"})
    assert sent and "Usage" in sent[0]
