"""Hand-picked chart symbols: validation, permanent save/reset, and the
picker's TradingView options (CEX first, no perpetuals/synthetic rows)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.services import chart_override_service as svc


@pytest.fixture
def store(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(svc, "SessionLocal", sessionmaker(bind=engine))
    yield
    engine.dispose()


def test_normalize():
    assert svc.normalize(" kcex:cyberleekusdt ") == "KCEX:CYBERLEEKUSDT"
    assert svc.normalize("UNISWAP4BASE:CYBERLEEKETH_3BCAF5.USD") == "UNISWAP4BASE:CYBERLEEKETH_3BCAF5.USD"
    for bad in ("", "BTCUSDT", "BINANCE:", ":BTC", "BIN ANCE:BTC<script>"):
        with pytest.raises(svc.ChartOverrideError):
            svc.normalize(bad)


def test_save_update_and_reset_are_permanent(store):
    assert svc.all_overrides() == {}
    assert svc.set_override(41910, "kcex:cyberleekusdt", user_id=1) == "KCEX:CYBERLEEKUSDT"
    svc.set_override(41910, "MEXC:CYBERLEEKUSDT")  # change it
    svc.set_override(1, "BINANCE:BTCUSDT")
    assert svc.all_overrides() == {41910: "MEXC:CYBERLEEKUSDT", 1: "BINANCE:BTCUSDT"}
    svc.clear_override(41910)
    assert svc.all_overrides() == {1: "BINANCE:BTCUSDT"}


def test_search_options_cex_first_and_only_real_markets(monkeypatch):
    from app.services import tradingview_symbol_service as tv

    rows = [
        {"symbol": "CYBERLEEKETH_3BCAF5.USD", "exchange": "Uniswap v4 Base", "prefix": "UNISWAP4BASE", "type": "spot",
         "description": "CyberLeek / Ether on Base (0x3BCaF5C01751aD4812162Bed8773735f715cdc1d) in USD", "typespecs": ["crypto"]},
        {"symbol": "CYBERLEEKUSD", "exchange": "CRYPTO", "type": "spot", "description": "CyberLeek", "typespecs": ["crypto", "synthetic"]},
        {"symbol": "CYBERLEEKUSDT.P", "exchange": "BingX", "prefix": "BINGX", "type": "swap", "description": "perp", "typespecs": ["crypto"]},
        {"symbol": "<em>CYBERLEEK</em>USDT", "exchange": "KCEX", "type": "spot", "description": "CyberLeek / USDT", "typespecs": ["crypto"]},
    ]
    monkeypatch.setattr(tv, "_search_tradingview", lambda q: rows)
    out = svc.search_options("cyberleek")
    assert [(o["symbol"], o["kind"]) for o in out] == [("KCEX:CYBERLEEKUSDT", "CEX"), ("UNISWAP4BASE:CYBERLEEKETH_3BCAF5.USD", "DEX")]
    assert svc.search_options("  ") == []
