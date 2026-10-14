"""Unique coin-page URLs: a coin's path is its name (/coins/a-meme-coin), numbered when names repeat; every path
resolves to exactly its own coin, and the old ticker-based links still resolve."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.coin import Coin
from app.services import alert_service


def rows():
    return [
        {"cmc_id": 1, "symbol": "BTC", "name": "Bitcoin", "market_cap_usd": 1000},
        {"cmc_id": 20, "symbol": "MEME", "name": "Meme Coin", "market_cap_usd": 50},
        {"cmc_id": 10, "symbol": "MEME", "name": "Meme coin", "market_cap_usd": 50},  # same name, same cap: lower id first
        {"cmc_id": 30, "symbol": "MEME", "name": "MEME  COIN!", "market_cap_usd": 5},
        {"cmc_id": 40, "symbol": "SI", "name": "Super Inu", "market_cap_usd": 0},
        {"cmc_id": 41, "symbol": "SI", "name": "Sealwifhat", "market_cap_usd": 0},
        {"cmc_id": 50, "symbol": "ETH", "name": "Ethereum", "market_cap_usd": 500},
        {"cmc_id": 51, "symbol": "ETH", "name": "Impostor", "market_cap_usd": 1},
        {"cmc_id": 60, "symbol": "BEIJ", "name": "北京币", "market_cap_usd": 2},  # no Latin letters: the ticker
        {"cmc_id": 61, "symbol": "Z", "name": "???", "market_cap_usd": 0},
        {"cmc_id": 62, "symbol": "Z", "name": "!!!", "market_cap_usd": 0},
    ]


@pytest.fixture
def cs(monkeypatch):
    pytest.importorskip("reflex")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent / "frontend"))
    from frontend.state import coin_state

    return coin_state


def test_every_coin_gets_its_name_as_path_and_a_number_when_names_repeat(cs):
    r = rows()
    slugs = cs.assign_slugs(r)
    assert slugs == {1: "bitcoin", 10: "meme-coin", 20: "meme-coin-2", 30: "meme-coin-3", 40: "super-inu", 41: "sealwifhat",
                     50: "ethereum", 51: "impostor", 60: "beij", 61: "z", 62: "z-2"}
    assert len(set(slugs.values())) == len(slugs)  # every URL is unique
    assert r[1]["slug"] == "meme-coin-2"


def test_every_path_resolves_to_its_own_coin_and_old_links_still_work(cs):
    r = rows()
    cs.assign_slugs(r)
    by_id = {x["cmc_id"]: x for x in r}
    by_slug = {x["slug"]: x for x in r}
    for x in r:
        assert cs.pick_coin(x["slug"], r, by_id, by_slug) is x  # a click always lands on the clicked coin
        assert cs.pick_coin(x["slug"], r, by_id) is x  # and without the prebuilt map
    assert cs.pick_coin("Meme-Coin", r, by_id, by_slug)["cmc_id"] == 10  # case-insensitive
    assert cs.pick_coin("eth", r, by_id, by_slug)["cmc_id"] == 50  # old /coin/<ticker>: the ticker's biggest coin
    assert cs.pick_coin("meme-30", r, by_id, by_slug)["cmc_id"] == 30  # old /coin/<ticker>-<id>
    assert cs.pick_coin("meme-999", r, by_id, by_slug) is None and cs.pick_coin("btc-20", r, by_id, by_slug) is None
    assert cs.pick_coin("nope", r, by_id, by_slug) is None


def test_route_ticker_and_slug_lookup(cs, monkeypatch):
    assert [cs.route_ticker(x) for x in ("meme-1234", "eth", " btc ", "")] == ["meme", "eth", "btc", ""]
    monkeypatch.setitem(cs._UNIVERSE, "slugs", {20: "meme-coin-2"})
    assert cs.coin_slug(20, "MEME") == "meme-coin-2" and cs.coin_slug(99, "XYZ") == "xyz"


def test_alert_links_use_the_same_unique_path():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    for cid, sym, cap in ((10, "MEME", 50), (20, "MEME", 50), (30, "MEME", 5), (1, "BTC", 9)):
        db.add(Coin(cmc_id=cid, symbol=sym, name=sym + str(cid), slug=f"{sym}-{cid}".lower(), market_cap_usd=cap))
    db.commit()
    assert [alert_service.coin_path(db, c, s) for c, s in ((10, "MEME"), (20, "MEME"), (30, "meme"), (1, "BTC"), (7, "NEW"))] == [
        "meme", "meme-20", "meme-30", "btc", "new"]  # a coin with no row of its own gets the plain ticker
