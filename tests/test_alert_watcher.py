"""The 24/7 alert checker prices each coin from the same chart pair the coin page / TradingView chart uses."""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.coin import Coin
from app.models.price_alert import PriceAlert

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "frontend"))

from frontend import alert_watcher  # noqa: E402


@pytest.fixture
def watcher(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(Coin(
        cmc_id=77, symbol="ABC", name="Abc", slug="abc", price_usd=1.0,
        cached_market_pairs=[
            {"exchange_name": "MEXC", "market_pair": "ABC/USDT", "is_dex": False, "price": 1.0, "volume_24h": 5000.0},
            {"exchange_name": "Binance", "market_pair": "ABC/USDT", "is_dex": False, "price": 1.0, "volume_24h": 9000.0},
        ],
    ))
    db.add(PriceAlert(user_id=1, cmc_id=77, coin_name="Abc", symbol="ABC", direction="above", target_price=1.5))
    db.commit()
    db.close()

    fired, seen = [], []

    class FakeAlerts:
        @staticmethod
        def mark_triggered(user_id, alert_id, price, target_display, price_display):
            fired.append(price)
            return True

    class FakeHub:
        @staticmethod
        def get_prices():
            return {"ABC": {"price": 1.0}}  # the shared list still says 1.0

        @staticmethod
        def plausible(price, ref):
            return True

    monkeypatch.setattr(alert_watcher, "_services", lambda: (Session, Coin, PriceAlert, FakeAlerts, FakeHub))
    monkeypatch.setattr("app.services.chart_override_service.all_overrides", lambda: {})
    alert_watcher._fetch_cache.clear()

    def fake_fetch(items):
        seen.extend(items)
        return {items[0]["cmc_id"]: 2.0}  # the chart pair's last trade crossed the target

    monkeypatch.setattr("frontend.live_prices.fetch_live_prices", fake_fetch)
    return fired, seen


def test_prices_from_the_chart_pair_not_the_shared_list(watcher):
    fired, seen = watcher
    assert alert_watcher.check_once() == 1
    assert fired == [2.0]  # the chart pair's price, not the hub's 1.0
    assert seen[0]["chart_symbol"] == "MEXC:ABCUSDT"  # MEXC outranks Binance, like the coin page
