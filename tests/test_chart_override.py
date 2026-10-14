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


def test_search_options_lists_the_whole_crypto_tab(monkeypatch):
    """The picker shows everything TradingView's Crypto tab lists (spot, perpetuals, DEX pools,
    indexes) in TradingView's order, merging the ticker, the coin's name and "<ticker>USDT"."""
    from app.services import tradingview_symbol_service as tv

    by_query = {
        "cyberleek": [
            {"symbol": "CYBERLEEK", "exchange": "CRYPTOCAP", "type": "index", "description": "Market Cap CYBERLEEK, $", "typespecs": ["crypto", "synthetic"]},
            {"symbol": "<em>CYBERLEEK</em>USDT", "exchange": "KCEX", "type": "spot", "description": "CyberLeek / USDT", "typespecs": ["crypto"]},
            {"symbol": "CYBERLEEKUSDT.P", "exchange": "LBank", "prefix": "LBANK", "type": "swap", "description": "CYBERLEEK / Tether USD PERPETUAL CONTRACT", "typespecs": ["crypto", "perpetual"]},
            {"symbol": "CYBERLEEKETH_3BCAF5.USD", "exchange": "Uniswap v4 Base", "prefix": "UNISWAP4BASE", "type": "spot",
             "description": "CyberLeek / Ether on Base (0x3BCaF5C01751aD4812162Bed8773735f715cdc1d) in USD", "typespecs": ["crypto"]},
            {"symbol": "OLDUSDT", "exchange": "X", "type": "spot", "description": "gone", "typespecs": ["crypto", "discontinued"]},
        ],
        "cyberleekusdt": [
            {"symbol": "CYBERLEEKUSDT", "exchange": "KCEX", "type": "spot", "description": "CyberLeek / USDT", "typespecs": ["crypto"]},
            {"symbol": "CYBERLEEKUSDT.P", "exchange": "BingX", "prefix": "BINGX", "type": "swap", "description": "CyberLeek/USD Tether Perpetual Contract", "typespecs": ["crypto", "perpetual"]},
        ],
    }
    asked = []
    monkeypatch.setattr(tv, "_search_tradingview", lambda q: asked.append(q) or by_query.get(q.lower(), []))
    out = svc.search_options("cyberleek", also=("CyberLeek",))
    assert asked == ["cyberleek", "CyberLeek", "cyberleekUSDT"]  # ticker, the coin's name, then the pair name
    assert [(o["symbol"], o["kind"], o["market"]) for o in out] == [
        ("KCEX:CYBERLEEKUSDT", "CEX", "spot"),
        ("LBANK:CYBERLEEKUSDT.P", "Perp", "perpetual"),
        ("UNISWAP4BASE:CYBERLEEKETH_3BCAF5.USD", "DEX", "DEX pool"),
        ("BINGX:CYBERLEEKUSDT.P", "Perp", "perpetual"),  # only found by "CYBERLEEKUSDT"
        ("CRYPTOCAP:CYBERLEEK", "Index", "index"),  # indexes last
    ]
    assert svc.search_options("  ") == []


def test_a_perpetual_can_be_saved_permanently(store):
    assert svc.set_override(42395, "bingx:siusdt.p") == "BINGX:SIUSDT.P"
    assert svc.all_overrides() == {42395: "BINGX:SIUSDT.P"}
