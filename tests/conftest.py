"""Shared test fixtures. Tests use an in-memory SQLite database with small
fake data only; they never touch the real Postgres database or call CMC."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - registers every model on Base.metadata
from app.core.database import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def fake_listing(cmc_id: int, symbol: str, price, rank: int, volume=1_000_000.0) -> dict:
    """One coin in the same shape as a CMC listings/quotes response."""
    return {
        "id": cmc_id,
        "symbol": symbol,
        "name": f"{symbol} Coin",
        "slug": symbol.lower(),
        "cmc_rank": rank,
        "tags": [],
        "quote": {"USD": {"price": price, "volume_24h": volume, "market_cap": None}},
    }


@pytest.fixture(autouse=True)
def _no_cmc_credit_check(monkeypatch):
    """Tests never ask CoinMarketCap for the real credit balance (network,
    and a used-up key would block everything); tests of the guard itself
    patch cmc_budget.usage on top of this."""
    from app.services import cmc_budget

    monkeypatch.setattr(cmc_budget, "usage", lambda force=False: None)
