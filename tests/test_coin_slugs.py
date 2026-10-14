"""Unique coin-page URLs: two coins can share a ticker (two MEME), so the biggest keeps /coin/meme and the other is
/coin/meme-<cmc_id>; every path resolves to exactly its own coin."""

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
        {"cmc_id": 1, "symbol": "BTC", "market_cap_usd": 1000},
        {"cmc_id": 20, "symbol": "MEME", "market_cap_usd": 50},
        {"cmc_id": 10, "symbol": "MEME", "market_cap_usd": 50},  # same cap: the lower id owns the ticker
        {"cmc_id": 30, "symbol": "meme", "market_cap_usd": 5},
        {"cmc_id": 40, "symbol": "SI", "market_cap_usd": 0},
        {"cmc_id": 41, "symbol": "SI", "market_cap_usd": 0},
    ]


@pytest.fixture
def cs(monkeypatch):
    pytest.importorskip("reflex")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent / "frontend"))
    from frontend.state import coin_state

    return coin_state


def test_the_biggest_coin_keeps_the_ticker_path_and_the_others_get_their_id(cs):
    r = rows()
    slugs = cs.assign_slugs(r)
    assert slugs == {1: "btc", 20: "meme-20", 10: "meme", 30: "meme-30", 40: "si", 41: "si-41"}
    assert len(set(slugs.values())) == len(slugs)  # every URL is unique
    assert r[1]["slug"] == "meme-20"


def test_every_path_resolves_to_its_own_coin_and_old_ticker_links_still_work(cs):
    r = rows()
    cs.assign_slugs(r)
    by_id = {x["cmc_id"]: x for x in r}
    for x in r:
        assert cs.pick_coin(x["slug"], r, by_id) is x  # a click always lands on the clicked coin
    assert cs.pick_coin("MEME", r, by_id)["cmc_id"] == 10  # the old /coin/meme link: the ticker owner
    assert cs.pick_coin("meme-999", r, by_id) is None  # unknown id, and "meme-999" is no ticker
    assert cs.pick_coin("btc-20", r, by_id) is None  # an id whose ticker does not match is not that coin
    assert cs.pick_coin("nope", r, by_id) is None


def test_route_ticker_and_slug_lookup(cs, monkeypatch):
    assert [cs.route_ticker(x) for x in ("meme-1234", "eth", " btc ", "")] == ["meme", "eth", "btc", ""]
    monkeypatch.setitem(cs._UNIVERSE, "slugs", {20: "meme-20"})
    assert cs.coin_slug(20, "MEME") == "meme-20" and cs.coin_slug(99, "XYZ") == "xyz"


def test_alert_links_use_the_same_unique_path():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    for cid, sym, cap in ((10, "MEME", 50), (20, "MEME", 50), (30, "MEME", 5), (1, "BTC", 9)):
        db.add(Coin(cmc_id=cid, symbol=sym, name=sym + str(cid), slug=f"{sym}-{cid}".lower(), market_cap_usd=cap))
    db.commit()
    assert [alert_service.coin_path(db, c, s) for c, s in ((10, "MEME"), (20, "MEME"), (30, "meme"), (1, "BTC"), (7, "NEW"))] == [
        "meme", "meme-20", "meme-30", "btc", "new"]  # a coin with no row of its own gets the plain ticker
